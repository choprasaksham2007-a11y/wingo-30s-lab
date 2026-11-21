"""Read-only chronological check using workbook-derived and collector records.

Train simple rules before the processed-data cutoff; evaluate after it.
Never bridge missing rounds. Existing model bundles are not retrained.
"""
from collections import Counter, defaultdict
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from scipy.stats import binomtest

from common import build_features

ROOT = Path(__file__).resolve().parents[1]


def main():
    old = pd.read_csv(ROOT / "data/processed/rounds_30s_clean.csv", dtype={"period_id": str})
    cutoff = old.period_id.max()
    live = pd.read_csv(ROOT / "wingo_investigation/collected_data/wingo_30s_history.csv",
                       dtype={"issueNumber": str}).rename(columns={"issueNumber": "period_id"})
    overlap = old.merge(live, on="period_id", suffixes=("_old", "_live"))
    print("Overlapping outcome disagreements:", int((overlap.number_old != overlap.number_live).sum()))
    df = pd.concat([old[["period_id", "number"]], live[["period_id", "number"]]])
    df = df.drop_duplicates("period_id", keep="last").sort_values("period_id").reset_index(drop=True)
    assert df.period_id.str.fullmatch(r"\d{17}").all()
    assert df.number.between(0, 9).all() and (df.number % 1 == 0).all()
    df["number"] = df.number.astype(int)
    dates = pd.to_datetime(df.period_id.str[:8], format="%Y%m%d")
    df["counter"] = df.period_id.str[-4:].astype(int)
    assert df.counter.between(1, 2880).all()
    df["abs_index"] = (dates - dates.min()).dt.days * 2880 + df.counter
    df["block_id"] = df.abs_index.diff().fillna(1).ne(1).cumsum()
    df["pos_in_block"] = df.groupby("block_id").cumcount()
    print(f"Combined rounds: {len(df)} | cutoff: {cutoff} | newest: {df.period_id.max()}")

    # Require the same ten-round history for all candidates and frozen models.
    X, numbers, pids = build_features(df)
    test = pids > cutoff
    if not test.any():
        raise SystemExit("No new rounds with ten consecutive preceding rounds.")
    yn = numbers[test]
    prior = np.bincount(df.loc[df.period_id <= cutoff, "number"], minlength=10) + 1
    prior = prior / prior.sum()
    baseline = np.full(len(yn), prior.argmax())
    predictions = {}
    train_counts = {name: defaultdict(Counter) for name in ("Previous digit", "Previous two digits", "Previous three digits", "Round modulo 10", "Round modulo 30")}
    samples = []
    for _, group in df.groupby("block_id"):
        digits = group.number.to_numpy()
        for i in range(10, len(group)):
            row = group.iloc[i]
            keys = {"Previous digit": tuple(digits[i-1:i]),
                    "Previous two digits": tuple(digits[i-2:i]),
                    "Previous three digits": tuple(digits[i-3:i]),
                    "Round modulo 10": int(row.counter) % 10,
                    "Round modulo 30": int(row.counter) % 30}
            if row.period_id <= cutoff:
                for name, key in keys.items():
                    train_counts[name][key][int(digits[i])] += 1
            else:
                samples.append((row.period_id, keys, digits[max(0, i-20):i].copy()))
    samples.sort(key=lambda row: row[0])
    assert [s[0] for s in samples] == list(pids[test])
    for name, mapping in train_counts.items():
        # Fixed smoothing, chosen without tuning against the test outcomes.
        predictions[name] = np.array([np.argmax(np.array([mapping[keys[name]][d] for d in range(10)]) + 20 * prior)
                                      for _, keys, _ in samples])
    predictions["Recent most common digit"] = np.array([np.argmax(np.bincount(past, minlength=10) + prior) for _, _, past in samples])
    predictions["Repeat previous digit"] = np.array([past[-1] for _, _, past in samples])
    predictions["Last two digits sum modulo 10"] = np.array([sum(past[-2:]) % 10 for _, _, past in samples])

    results = []

    def record(name, truth, prediction, base, chance):
        hit, base_hit = prediction == truth, base == truth
        wins = int((hit & ~base_hit).sum())
        losses = int((~hit & base_hit).sum())
        pbase = binomtest(wins, wins + losses, 0.5, alternative="greater").pvalue if wins + losses else 1.0
        pchance = binomtest(int(hit.sum()), len(truth), chance, alternative="greater").pvalue
        ci = binomtest(int(hit.sum()), len(truth)).proportion_ci(method="wilson")
        results.append((name, hit.mean(), base_hit.mean(), pbase, pchance, ci.low, ci.high))

    for name, pred in predictions.items():
        record("Digit rule: " + name, yn, pred, baseline, 0.1)

    paths = sorted((ROOT / "models").glob("frozen_[0-9]*.joblib"))
    if paths:
        bundle = joblib.load(paths[0])
        assert bundle["last_period_id"] <= cutoff
        strong_path = ROOT / "models" / f"frozen_strong_{bundle['last_period_id']}.joblib"
        strong = joblib.load(strong_path) if strong_path.exists() else {"big": {}, "number": {}}
        if strong_path.exists():
            assert strong["last_period_id"] == bundle["last_period_id"]
        for target, truth, chance in (("number", yn, 0.1), ("big", (yn >= 5).astype(int), 0.5)):
            models = {**bundle[target], **strong[target]}
            base = np.full(len(truth), models.pop("majority"))
            for name, model in models.items():
                record(f"Frozen {target}: {name}", truth, model.predict(X[test]), base, chance)

    bar = 0.05 / len(results)
    print(f"New test rounds with uninterrupted history: {len(yn)} | {pids[test][0]} through {pids[test][-1]}")
    print(f"Candidates: {len(results)} | corrected significance threshold: {bar:.6f}")
    print("Candidate | accuracy | baseline | p better than baseline | p above chance | 95% interval")
    for name, acc, base, pb, pc, lo, hi in results:
        print(f"{name} | {acc:.4f} | {base:.4f} | {pb:.6f} | {pc:.6f} | {lo:.4f}-{hi:.4f}")
    winners = [name for name, acc, base, pb, pc, *_ in results if acc > base and pb < bar and pc < bar]
    print("Candidates passing both checks:", winners or "none")
    print("Latest ten saved digits:", df.number.tail(10).tolist())
    print("This is an exploratory historical check. A passing rule still requires prospective validation.")


if __name__ == "__main__":
    main()
