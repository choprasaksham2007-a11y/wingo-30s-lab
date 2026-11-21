"""Bounded model search with rolling validation, separate calibration, and final test.

Never chooses architecture, weights, epochs or calibration using the final test.
Saves an advanced candidate; promotes only if the declared comparison gate passes.
"""
import argparse
import hashlib
import json
from datetime import datetime

import joblib
import numpy as np
from scipy.stats import binomtest
from sklearn.ensemble import ExtraTreesClassifier, HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import log_loss
from sklearn.neural_network import MLPClassifier
from sklearn.preprocessing import StandardScaler
from threadpoolctl import threadpool_limits

from advanced_model import AdvancedEnsemble, FEATURE_VERSION, advanced_features, aligned_probabilities, build_advanced_rows, temper
from neural_predictor import ROOT, POINTER, UTC, features, load_training_data, make_network

CONFIGS = [
    {"name": "mlp32_recent", "kind": "mlp", "lookback": 20, "hidden": (32,), "alpha": 10, "seed": 7},
    {"name": "mlp64_recent", "kind": "mlp", "lookback": 20, "hidden": (64, 32), "alpha": 1, "seed": 42},
    {"name": "mlp128_recent", "kind": "mlp", "lookback": 20, "hidden": (128, 64), "alpha": 10, "seed": 7},
    {"name": "mlp64_long", "kind": "mlp", "lookback": 60, "hidden": (64, 32), "alpha": 10, "seed": 42},
    {"name": "mlp128_long", "kind": "mlp", "lookback": 60, "hidden": (128, 64, 32), "alpha": 10, "seed": 7},
    {"name": "mlp256_long", "kind": "mlp", "lookback": 60, "hidden": (256, 128, 64), "alpha": 25, "seed": 42},
    {"name": "mlp64_long_seed7", "kind": "mlp", "lookback": 60, "hidden": (64, 32), "alpha": 10, "seed": 7},
    {"name": "mlp128_long_seed42", "kind": "mlp", "lookback": 60, "hidden": (128, 64, 32), "alpha": 10, "seed": 42},
    {"name": "logistic_recent", "kind": "linear", "lookback": 20, "C": 0.01},
    {"name": "logistic_long", "kind": "linear", "lookback": 60, "C": 0.005},
    {"name": "boosting", "kind": "boosting", "lookback": 20},
    {"name": "extra_trees", "kind": "trees", "lookback": 60},
]


def new_model(config):
    if config["kind"] == "mlp":
        return MLPClassifier(hidden_layer_sizes=config["hidden"], alpha=config["alpha"],
                             learning_rate_init=0.0005, batch_size=256, random_state=config["seed"])
    if config["kind"] == "linear":
        return LogisticRegression(C=config["C"], max_iter=500)
    if config["kind"] == "boosting":
        return HistGradientBoostingClassifier(max_iter=60, max_leaf_nodes=7, min_samples_leaf=80,
                                               l2_regularization=10, learning_rate=0.04, early_stopping=False, random_state=42)
    return ExtraTreesClassifier(n_estimators=200, max_depth=8, min_samples_leaf=30,
                                max_features=0.5, n_jobs=2, random_state=42)


def fit_member(config, X, y, max_epochs, fixed_epochs=None):
    epochs = fixed_epochs
    if config["kind"] == "mlp" and epochs is None:
        # Early-stopping labels are strictly inside this fold's training interval.
        split = int(len(y) * 0.85)
        inner_scaler = StandardScaler().fit(X[:split])
        train_x, val_x = inner_scaler.transform(X[:split]), inner_scaler.transform(X[split:])
        search = new_model(config)
        best_loss, epochs = float("inf"), 1
        for epoch in range(1, max_epochs+1):
            search.partial_fit(train_x, y[:split], classes=np.arange(10))
            loss = log_loss(y[split:], search.predict_proba(val_x), labels=np.arange(10))
            if loss < best_loss - 0.0001:
                best_loss, epochs = loss, epoch
            if epoch - epochs >= 8:
                break
    scaler = StandardScaler().fit(X) if config["kind"] in ("mlp", "linear") else None
    xs = scaler.transform(X) if scaler is not None else X
    model = new_model(config)
    if config["kind"] == "mlp":
        for _ in range(epochs):
            model.partial_fit(xs, y, classes=np.arange(10))
    else:
        model.fit(xs, y)
    return {"model": model, "scaler": scaler, "lookback": config["lookback"], "name": config["name"], "epochs": epochs}


def predict_member(member, X):
    return aligned_probabilities(member["model"], member["scaler"].transform(X) if member["scaler"] is not None else X)


def select_strategy(probabilities, truth):
    """Selection sees rolling-validation predictions only; it maximizes exact hits."""
    ranking = sorted(probabilities, key=lambda name: (-np.mean(probabilities[name].argmax(axis=1) == truth), log_loss(truth, probabilities[name], labels=np.arange(10))))
    strategies = [({name: 1.0}, name) for name in ranking]
    for n in (2, 3, 5):
        names = ranking[:n]
        strategies.append(({name: 1/len(names) for name in names}, f"top_{len(names)}_equal_ensemble"))
    # Also test diversity rather than just the top scorers' correlated errors.
    neural = [n for n in ranking if n.startswith("mlp")][:3]
    diverse = neural + [n for n in ("logistic_recent", "boosting", "extra_trees") if n in probabilities]
    if diverse:
        strategies.append(({name: 1/len(diverse) for name in diverse}, "diverse_ensemble"))
    results = []
    for weights, name in strategies:
        p = sum(probabilities[k] * v for k, v in weights.items())
        results.append({"name": name, "weights": weights,
                        "accuracy": float(np.mean(p.argmax(axis=1) == truth)),
                        "log_loss": float(log_loss(truth, p, labels=np.arange(10)))})
    results.sort(key=lambda r: (-r["accuracy"], r["log_loss"]))
    return results[0], results


def metrics(truth, probabilities, baseline):
    hit = probabilities.argmax(axis=1) == truth
    base_hit = baseline == truth
    wins, losses = int((hit & ~base_hit).sum()), int((~hit & base_hit).sum())
    ci = binomtest(int(hit.sum()), len(truth)).proportion_ci(method="wilson")
    return {"accuracy": float(hit.mean()), "hits": int(hit.sum()), "rounds": len(truth),
            "log_loss": float(log_loss(truth, probabilities, labels=np.arange(10))),
            "accuracy_95_percent_interval": [ci.low, ci.high], "baseline_accuracy": float(base_hit.mean()),
            "p_above_chance": binomtest(int(hit.sum()), len(truth), 0.1, alternative="greater").pvalue,
            "p_above_baseline": binomtest(wins, wins+losses, 0.5, alternative="greater").pvalue if wins+losses else 1.0}


def train(max_epochs=80):
    frame = load_training_data()
    histories, y, pids = build_advanced_rows(frame)
    if len(y) < 2000:
        raise ValueError("Need at least 2,000 usable examples")
    sizes = [int(len(y) * f) for f in (0.4, 0.5, 0.6, 0.7, 0.8)]
    fit_end, calibration_end = sizes[-2:]
    X = {lookback: np.asarray([advanced_features(h, pid, lookback) for h, pid in zip(histories, pids)])
         for lookback in (20, 60)}
    print(f"Advanced search: {len(y)} examples | {len(CONFIGS)} configurations | 3 rolling folds | calibration {calibration_end-fit_end} | test {len(y)-calibration_end}", flush=True)
    validation_ids = np.arange(sizes[0], fit_end)
    oof, chosen_epochs, fold_reports = {}, {}, []
    for config in CONFIGS:
        chunks, epochs = [], []
        for fold, (end, stop) in enumerate(zip(sizes[:3], sizes[1:4]), 1):
            member = fit_member(config, X[config["lookback"]][:end], y[:end], max_epochs)
            p = predict_member(member, X[config["lookback"]][end:stop])
            chunks.append(p)
            if member["epochs"] is not None:
                epochs.append(member["epochs"])
            fold_reports.append({"candidate": config["name"], "fold": fold,
                                 "train_end": str(pids[end-1]), "validation_start": str(pids[end]),
                                 "validation_end": str(pids[stop-1]), "epochs": member["epochs"],
                                 "accuracy": float(np.mean(p.argmax(axis=1) == y[end:stop]))})
        oof[config["name"]] = np.concatenate(chunks)
        chosen_epochs[config["name"]] = int(np.median(epochs)) if epochs else None
        print(f"{config['name']}: rolling accuracy {np.mean(oof[config['name']].argmax(axis=1) == y[validation_ids]):.2%}; epochs {epochs}", flush=True)
    selected, leaderboard = select_strategy(oof, y[validation_ids])
    print("Selected using rolling validation:", json.dumps(selected), flush=True)
    configs = {c["name"]: c for c in CONFIGS}
    members = [fit_member(configs[name], X[configs[name]["lookback"]][:fit_end], y[:fit_end],
                           max_epochs, chosen_epochs[name]) for name in selected["weights"]]
    weights = list(selected["weights"].values())
    calibration_probs = sum(w * predict_member(m, X[m["lookback"]][fit_end:calibration_end]) for w, m in zip(weights, members))
    temperature = min((1, 2, 4, 8, 16, 32), key=lambda t: log_loss(y[fit_end:calibration_end], temper(calibration_probs, t), labels=np.arange(10)))

    # Fair legacy comparison: fit its fixed architecture/epoch on the SAME prefix.
    # Do not score the deployed legacy bundle on history it has already trained on.
    legacy_X = np.asarray([features(h[-20:], pid) for h, pid in zip(histories, pids)])
    legacy_scaler = StandardScaler().fit(legacy_X[:fit_end])
    legacy_model = make_network((64, 32))
    for _ in range(3):
        legacy_model.partial_fit(legacy_scaler.transform(legacy_X[:fit_end]), y[:fit_end], classes=np.arange(10))
    legacy_cal = legacy_model.predict_proba(legacy_scaler.transform(legacy_X[fit_end:calibration_end]))
    legacy_temp = min((1, 2, 4, 8, 16, 32), key=lambda t: log_loss(y[fit_end:calibration_end], temper(legacy_cal, t), labels=np.arange(10)))

    test_p = temper(sum(w * predict_member(m, X[m["lookback"]][calibration_end:]) for w, m in zip(weights, members)), temperature)
    legacy_p = temper(legacy_model.predict_proba(legacy_scaler.transform(legacy_X[calibration_end:])), legacy_temp)
    truth = y[calibration_end:]
    majority = np.full(len(truth), np.bincount(y[:fit_end], minlength=10).argmax())
    result, reference = metrics(truth, test_p, majority), metrics(truth, legacy_p, majority)
    # Predeclared engineering promotion gate, NOT a claim of statistical advantage.
    promote = result["accuracy"] > reference["accuracy"] and result["log_loss"] <= reference["log_loss"]
    comparison = metrics(truth, test_p, legacy_p.argmax(axis=1))
    report = {"feature_version": FEATURE_VERSION, "source_rows": len(frame), "usable_rows": len(y),
              "test_start": str(pids[calibration_end]), "test_end": str(pids[-1]),
              "calibration_start": str(pids[fit_end]), "calibration_end": str(pids[calibration_end-1]),
              "folds": fold_reports, "validation_leaderboard": leaderboard, "selected": selected,
              "selected_epochs": {name: chosen_epochs[name] for name in selected["weights"]},
              "temperature": temperature, "test": result, "legacy_reference_test": reference,
              "p_above_legacy": comparison["p_above_baseline"], "promoted": bool(promote),
              "promotion_rule": "Higher final-test exact-digit accuracy AND no worse log loss than the matched-prefix legacy network. This is an engineering gate, not statistical significance.",
              "demonstrated_advantage": bool(result["p_above_chance"] < 0.05 and result["p_above_baseline"] < 0.05),
              "limitations": "Previously explored history is reused. No candidate/weight/epoch/temperature is chosen using the final test in this run. Refit on all history transfers calibration; future accuracy and calibration require prospective evaluation."}
    print("Final test:", json.dumps({k: report[k] for k in ("test", "legacy_reference_test", "promoted", "demonstrated_advantage")}, indent=2), flush=True)
    # Every selected component is refitted on the same frozen data snapshot.
    final_members = [fit_member(configs[name], X[configs[name]["lookback"]], y, max_epochs, chosen_epochs[name])
                     for name in selected["weights"]]
    advanced = AdvancedEnsemble(final_members, weights, temperature)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    path = ROOT / "models" / f"neural_advanced_{stamp}.joblib"
    bundle = {"model_id": path.stem, "advanced_model": advanced, "feature_version": FEATURE_VERSION,
              "lags": 20, "max_history": 60, "trained_through": str(frame.period_id.iloc[-1]),
              "baseline_digit": int(np.bincount(y, minlength=10).argmax()), "evaluation": report,
              "data_sha256": hashlib.sha256(frame.to_csv(index=False).encode()).hexdigest()}
    joblib.dump(bundle, path)
    report_path = ROOT / "results" / f"{path.stem}_evaluation.json"
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    # Check serialization and feature/prediction agreement before any activation.
    restored = joblib.load(path)
    np.testing.assert_allclose(advanced.predict_from_history(histories[-1], pids[-1]),
                               restored["advanced_model"].predict_from_history(histories[-1], pids[-1]))
    if promote:
        previous = json.loads(POINTER.read_text(encoding="utf-8")) if POINTER.exists() else None
        (ROOT / "models" / f"previous_pointer_{stamp}.json").write_text(json.dumps(previous, indent=2), encoding="utf-8")
        temporary = POINTER.with_suffix(".tmp")
        temporary.write_text(json.dumps({"model_path": str(path), "report_path": str(report_path)}, indent=2), encoding="utf-8")
        temporary.replace(POINTER)
        print("Advanced candidate passed the promotion gate and is now selected for live predictions.", flush=True)
    else:
        print("Advanced candidate saved, but did not pass the promotion gate. Current live model retained.", flush=True)
    print(f"Model: {path}\nReport: {report_path}", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--epochs", type=int, default=80)
    args = parser.parse_args()
    if args.epochs < 1:
        parser.error("epochs must be positive")
    with threadpool_limits(limits=2):
        train(args.epochs)
