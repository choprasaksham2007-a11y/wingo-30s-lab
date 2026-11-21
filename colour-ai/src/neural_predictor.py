"""Train a digit neural network and record prospective predictions from the live CSV."""
import argparse
import copy
import hashlib
import json
import sqlite3
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from scipy.stats import binomtest
from sklearn.metrics import log_loss
from sklearn.neural_network import MLPClassifier
from sklearn.preprocessing import StandardScaler
from threadpoolctl import threadpool_limits

ROOT = Path(__file__).resolve().parents[1]
LIVE = ROOT / "wingo_investigation/collected_data/wingo_30s_history.csv"
POINTER = ROOT / "models/latest_neural.json"
DATABASE = ROOT / "results/live_predictions.sqlite3"
LAGS = 20
UTC = timezone.utc


def period_index(pid):
    if len(pid) != 17 or not pid.isdigit() or pid[8:13] != "10005":
        raise ValueError(f"Invalid WinGo 30S period: {pid}")
    day = datetime.strptime(pid[:8], "%Y%m%d")
    counter = int(pid[-4:])
    if not 1 <= counter <= 2880:
        raise ValueError(f"Invalid round counter: {pid}")
    return day.toordinal() * 2880 + counter - 1


def next_period(pid):
    period_index(pid)
    counter = int(pid[-4:])
    day = datetime.strptime(pid[:8], "%Y%m%d")
    if counter == 2880:
        day += timedelta(days=1)
        counter = 0
    return day.strftime("%Y%m%d") + "10005" + f"{counter + 1:04d}"


def round_end(pid):
    period_index(pid)
    return datetime.strptime(pid[:8], "%Y%m%d").replace(tzinfo=UTC) + timedelta(seconds=int(pid[-4:]) * 30)


def read_rounds(path, id_column):
    frame = pd.read_csv(path, dtype={id_column: str}).rename(columns={id_column: "period_id"})
    frame = frame[["period_id", "number"]].copy()
    frame["number"] = pd.to_numeric(frame.number, errors="raise")
    if not (frame.number.between(0, 9) & frame.number.mod(1).eq(0)).all():
        raise ValueError(f"Invalid digit in {path}")
    if frame.groupby("period_id").number.nunique().gt(1).any():
        raise ValueError(f"Conflicting duplicate outcomes in {path}")
    frame["number"] = frame.number.astype(int)
    frame["index"] = frame.period_id.map(period_index)
    return frame.drop_duplicates("period_id").sort_values("index").reset_index(drop=True)


def load_training_data():
    old = read_rounds(ROOT / "data/processed/rounds_30s_clean.csv", "period_id")
    live = read_rounds(LIVE, "issueNumber")
    overlap = old.merge(live, on="period_id", suffixes=("_old", "_live"))
    conflicts = int((overlap.number_old != overlap.number_live).sum())
    print(f"Collector replaces {conflicts} conflicting workbook-derived outcomes.", flush=True)
    return pd.concat([old, live]).drop_duplicates("period_id", keep="last").sort_values("index").reset_index(drop=True)


def features(past, target_pid):
    """All outcomes must precede the target; its known ID supplies clock features."""
    past = np.asarray(past, dtype=int)
    if len(past) != LAGS:
        raise ValueError(f"Need exactly {LAGS} previous consecutive rounds")
    one_hot = np.eye(10)[past[::-1]].ravel()
    counts = np.concatenate([np.bincount(past[-w:], minlength=10) / w for w in (5, 10, 20)])
    angle = 2 * np.pi * (int(target_pid[-4:]) - 1) / 2880
    return np.concatenate([one_hot, counts, [np.sin(angle), np.cos(angle)]])


def training_rows(frame):
    X, y, ids = [], [], []
    for _, group in frame.groupby(frame["index"].diff().ne(1).cumsum()):
        digits, pids = group.number.to_numpy(), group.period_id.to_numpy()
        for i in range(LAGS, len(group)):
            X.append(features(digits[i-LAGS:i], pids[i]))
            y.append(digits[i])
            ids.append(pids[i])
    return np.asarray(X), np.asarray(y), np.asarray(ids)


def soften(probabilities, temperature):
    logp = np.log(np.clip(probabilities, 1e-12, 1)) / temperature
    values = np.exp(logp - logp.max(axis=1, keepdims=True))
    return values / values.sum(axis=1, keepdims=True)


def make_network(hidden):
    return MLPClassifier(hidden_layer_sizes=hidden, alpha=1.0, batch_size=256,
                         learning_rate_init=0.001, random_state=42, shuffle=True)


def train(max_epochs):
    frame = load_training_data()
    X, y, pids = training_rows(frame)
    if len(y) < 1000:
        raise ValueError("Need at least 1,000 rounds with 20-round histories for chronological training and testing")
    a, b = int(len(y) * 0.6), int(len(y) * 0.8)
    scaler = StandardScaler().fit(X[:a])
    xs = scaler.transform(X)
    print(f"Usable rounds: {len(y)} | train: {a} | validation: {b-a} | untouched test: {len(y)-b}", flush=True)
    best = None
    for hidden in ((64, 32), (128, 64)):
        model = make_network(hidden)
        best_loss, best_epoch, best_model = float("inf"), 0, None
        for epoch in range(1, max_epochs + 1):
            model.partial_fit(xs[:a], y[:a], classes=np.arange(10))
            loss = log_loss(y[a:b], model.predict_proba(xs[a:b]), labels=np.arange(10))
            if loss < best_loss - 0.0001:
                best_loss, best_epoch, best_model = loss, epoch, copy.deepcopy(model)
            if epoch - best_epoch >= 8:
                break
        print(f"Network {hidden}: selected epoch {best_epoch}, validation log loss {best_loss:.5f}", flush=True)
        if best is None or best_loss < best[0]:
            best = (best_loss, hidden, best_epoch, best_model)
    _, hidden, epochs, selected = best
    val_probs = selected.predict_proba(xs[a:b])
    temperature = min((1, 2, 4, 8, 16), key=lambda t: log_loss(y[a:b], soften(val_probs, t), labels=np.arange(10)))
    # Test is read only after architecture, stopping epoch and temperature are fixed.
    test_probs = soften(selected.predict_proba(xs[b:]), temperature)
    pred, truth = test_probs.argmax(axis=1), y[b:]
    prior = (np.bincount(y[:a], minlength=10) + 1) / (a + 10)
    base = np.full(len(truth), prior.argmax())
    hit, base_hit = pred == truth, base == truth
    wins, losses = int((hit & ~base_hit).sum()), int((~hit & base_hit).sum())
    pb = binomtest(wins, wins + losses, 0.5, alternative="greater").pvalue if wins + losses else 1.0
    pc = binomtest(int(hit.sum()), len(truth), 0.1, alternative="greater").pvalue
    ci = binomtest(int(hit.sum()), len(truth)).proportion_ci(method="wilson")
    report = {
        "usable_rows": len(y), "train_rows": a, "validation_rows": b-a, "test_rows": len(truth),
        "test_start": str(pids[b]), "test_end": str(pids[-1]), "architecture": list(hidden),
        "epochs": epochs, "temperature": temperature, "accuracy": float(hit.mean()),
        "accuracy_95_percent_interval": [ci.low, ci.high], "baseline_digit": int(prior.argmax()),
        "baseline_accuracy": float(base_hit.mean()), "log_loss": float(log_loss(truth, test_probs, labels=np.arange(10))),
        "uniform_log_loss": float(np.log(10)), "baseline_log_loss": float(log_loss(truth, np.tile(prior, (len(truth), 1)), labels=np.arange(10))),
        "p_above_chance": pc, "p_above_baseline": pb,
        "historical_advantage_detected": bool(pb < 0.05 and pc < 0.05 and hit.mean() > base_hit.mean()),
        "note": "Chronological holdout for this run; history has been explored before. Prospective live results are the decisive check. Final production network is refitted on all available rows; its live performance is not the holdout score."
    }
    print(json.dumps(report, indent=2), flush=True)
    print("Refitting the selected architecture on all available history for future predictions...", flush=True)
    final_scaler = StandardScaler().fit(X)
    final_X = final_scaler.transform(X)
    final_model = make_network(hidden)
    for _ in range(epochs):
        final_model.partial_fit(final_X, y, classes=np.arange(10))
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    path = ROOT / "models" / f"neural_{stamp}.joblib"
    path.parent.mkdir(exist_ok=True)
    bundle = {"model_id": path.stem, "model": final_model, "scaler": final_scaler,
              "lags": LAGS, "temperature": temperature, "trained_through": str(frame.period_id.iloc[-1]),
              "baseline_digit": int(np.bincount(y, minlength=10).argmax()),
              "data_sha256": hashlib.sha256(frame.to_csv(index=False).encode()).hexdigest(), "evaluation": report}
    joblib.dump(bundle, path)
    report_path = ROOT / "results" / f"{path.stem}_evaluation.json"
    report_path.parent.mkdir(exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    temp = POINTER.with_suffix(".tmp")
    temp.write_text(json.dumps({"model_path": str(path), "report_path": str(report_path)}, indent=2), encoding="utf-8")
    temp.replace(POINTER)
    print(f"Saved trained neural network: {path}", flush=True)


def open_database(path=DATABASE):
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.execute("""CREATE TABLE IF NOT EXISTS predictions (
        target_period TEXT PRIMARY KEY, created_utc TEXT NOT NULL, deadline_utc TEXT NOT NULL,
        source_period TEXT NOT NULL, model_id TEXT NOT NULL, trained_through TEXT NOT NULL,
        digit INTEGER NOT NULL, probabilities TEXT NOT NULL, baseline_digit INTEGER NOT NULL,
        actual INTEGER, scored_utc TEXT)""")
    connection.commit()
    return connection


def reconcile(connection, frame):
    outcomes = dict(zip(frame.period_id, frame.number))
    now = datetime.now(UTC).isoformat()
    completed = []
    for target, predicted, model_id in connection.execute("SELECT target_period, digit, model_id FROM predictions WHERE actual IS NULL ORDER BY target_period").fetchall():
        if target in outcomes:
            actual = int(outcomes[target])
            updated = connection.execute("UPDATE predictions SET actual=?, scored_utc=? WHERE target_period=? AND actual IS NULL",
                                         (actual, now, target))
            if updated.rowcount:
                completed.append((target, predicted, actual, model_id))
    connection.commit()
    return completed


def print_result(target, predicted, actual, recent=False):
    label = "RECENT RESULT" if recent else "RESULT"
    print(f"{label} | completed period {target} | predicted {predicted} | actual {actual} | "
          + ("HIT" if predicted == actual else "MISS"), flush=True)


def live_forecast(bundle, frame, now=None):
    now = now or datetime.now(UTC)
    recent = frame.tail(bundle.get("max_history", LAGS))
    if bundle.get("feature_version") == "advanced-v1":
        # Use only the newest uninterrupted segment, never an older segment.
        segments = recent["index"].diff().ne(1).cumsum()
        recent = recent[segments == segments.iloc[-1]] if len(recent) else recent
    if len(recent) < LAGS or not recent["index"].diff().iloc[1:].eq(1).all():
        return None, f"Waiting for {LAGS} consecutive live rounds after the latest gap."
    source = str(recent.period_id.iloc[-1])
    target = next_period(source)
    deadline = round_end(target)
    if now >= deadline - timedelta(seconds=2):
        return None, "Collector data is too old for a prospective next-round prediction; waiting for an update."
    if round_end(source) > now + timedelta(seconds=5):
        return None, "Collector timestamps appear ahead of the computer clock; check the clock before predicting."
    if bundle["trained_through"] > source:
        return None, "Model was trained after this source round; refusing a retrospective prediction."
    if bundle["lags"] != LAGS:
        raise ValueError("Model feature version mismatch")
    if bundle.get("feature_version") == "advanced-v1":
        probabilities = bundle["advanced_model"].predict_from_history(recent.number.to_numpy(), target)
    elif bundle.get("feature_version") is None:
        x = features(recent.number.to_numpy(), target).reshape(1, -1)
        probabilities = soften(bundle["model"].predict_proba(bundle["scaler"].transform(x)), bundle["temperature"])[0]
    else:
        raise ValueError("Unknown model feature version")
    if len(probabilities) != 10 or not np.isfinite(probabilities).all() or (probabilities < 0).any() or not np.isclose(probabilities.sum(), 1):
        raise ValueError("Invalid model probabilities")
    return {"target": target, "source": source, "deadline": deadline,
            "digit": int(probabilities.argmax()), "probabilities": probabilities}, None


def record_forecast(connection, bundle, forecast):
    # Check the actual clock again after inference, immediately before committing.
    created = datetime.now(UTC)
    if created >= forecast["deadline"] - timedelta(seconds=2):
        return False
    with connection:
        result = connection.execute("""INSERT OR IGNORE INTO predictions
            (target_period, created_utc, deadline_utc, source_period, model_id, trained_through,
             digit, probabilities, baseline_digit) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (forecast["target"], created.isoformat(), forecast["deadline"].isoformat(), forecast["source"],
             bundle["model_id"], bundle["trained_through"], forecast["digit"],
             json.dumps(forecast["probabilities"].tolist()), bundle["baseline_digit"]))
    return result.rowcount == 1


def print_status(connection, model_id=None):
    clause = " AND model_id=?" if model_id else ""
    parameters = (model_id,) if model_id else ()
    rows = connection.execute("SELECT digit, actual, baseline_digit FROM predictions WHERE actual IS NOT NULL" + clause, parameters).fetchall()
    pending = connection.execute("SELECT COUNT(*) FROM predictions WHERE actual IS NULL" + clause, parameters).fetchone()[0]
    if not rows:
        print(f"Live score: no completed predictions yet | pending: {pending}", flush=True)
        return
    hits = sum(digit == actual for digit, actual, _ in rows)
    base_hits = sum(base == actual for _, actual, base in rows)
    ci = binomtest(hits, len(rows)).proportion_ci(method="wilson")
    print(f"Live score: {hits}/{len(rows)} = {hits/len(rows):.1%} | majority baseline: {base_hits/len(rows):.1%} "
          f"| 95% range: {ci.low:.1%}-{ci.high:.1%} | pending: {pending}", flush=True)


def watch(once=False, seconds=None):
    pointer = json.loads(POINTER.read_text(encoding="utf-8"))
    bundle = joblib.load(pointer["model_path"])
    connection = open_database()
    print(f"Using {bundle['model_id']} | trained through {bundle['trained_through']}", flush=True)
    print("Probabilities are model estimates, not proven win rates. Watching the existing collector CSV.", flush=True)
    print("RESULT and Live score refer to completed rounds. NEXT PREDICTION is still awaiting its result.", flush=True)
    recent_results = connection.execute("SELECT target_period, digit, actual FROM predictions WHERE model_id=? AND actual IS NOT NULL ORDER BY target_period DESC LIMIT 3",
                                        (bundle["model_id"],)).fetchall()
    for target, predicted, actual in reversed(recent_results):
        print_result(target, predicted, actual, recent=True)
    start = time.monotonic()
    last_stamp, last_message = None, None
    try:
        while True:
            try:
                stamp = LIVE.stat().st_mtime_ns
                if stamp != last_stamp or once:
                    latest = json.loads(POINTER.read_text(encoding="utf-8"))
                    if latest["model_path"] != pointer["model_path"]:
                        replacement = joblib.load(latest["model_path"])
                        bundle, pointer = replacement, latest
                        print(f"Switched to {bundle['model_id']} | trained through {bundle['trained_through']}", flush=True)
                    frame = read_rounds(LIVE, "issueNumber")
                    completed = reconcile(connection, frame)
                    for target, predicted, actual, model_id in completed:
                        if model_id == bundle["model_id"]:
                            print_result(target, predicted, actual)
                    print_status(connection, bundle["model_id"])
                    forecast, message = live_forecast(bundle, frame)
                    if forecast and record_forecast(connection, bundle, forecast):
                        rank = np.argsort(forecast["probabilities"])[::-1][:3]
                        local_deadline = forecast["deadline"].astimezone(timezone(timedelta(hours=5, minutes=30)))
                        print(f"NEXT PREDICTION (awaiting result) | period {forecast['target']} | digit {forecast['digit']} | "
                              f"estimated probability {forecast['probabilities'][forecast['digit']]:.2%} | "
                              f"round ends {local_deadline:%Y-%m-%d %H:%M:%S} IST | "
                              + "top 3: " + ", ".join(f"{d} ({forecast['probabilities'][d]:.2%})" for d in rank), flush=True)
                    elif message and message != last_message:
                        print(message, flush=True)
                    last_stamp, last_message = stamp, message
            except (OSError, ValueError, pd.errors.ParserError) as exc:
                print(f"Waiting for a readable collector update: {exc}", flush=True)
                if once:
                    raise
            if once or (seconds is not None and time.monotonic() - start >= seconds):
                break
            time.sleep(1)
    except KeyboardInterrupt:
        print("Stopped. Recorded predictions and scores are preserved.", flush=True)
    finally:
        connection.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("train", "predict", "watch", "status"))
    parser.add_argument("--epochs", type=int, default=60)
    parser.add_argument("--seconds", type=int, help="Optional bounded watch duration")
    args = parser.parse_args()
    if args.epochs < 1 or (args.seconds is not None and args.seconds < 1):
        parser.error("epochs and seconds must be positive")
    with threadpool_limits(limits=2):
        if args.command == "train":
            train(args.epochs)
        elif args.command == "status":
            connection = open_database()
            try:
                if LIVE.exists():
                    reconcile(connection, read_rounds(LIVE, "issueNumber"))
                print("All models combined:", flush=True)
                print_status(connection)
                for (model_id,) in connection.execute("SELECT DISTINCT model_id FROM predictions ORDER BY model_id"):
                    print(model_id, flush=True)
                    print_status(connection, model_id)
            finally:
                connection.close()
        else:
            watch(once=args.command == "predict", seconds=args.seconds)


if __name__ == "__main__":
    main()
