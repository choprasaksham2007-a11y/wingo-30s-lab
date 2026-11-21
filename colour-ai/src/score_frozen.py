import sys
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from scipy import stats
from sklearn.metrics import balanced_accuracy_score

from common import build_features

MIN_FRESH = 300          # do not score fewer fresh rounds than this
NAMES = {"logistic": "Logistic regression", "forest": "Random forest"}

files = sorted(Path("models").glob("frozen_[0-9]*.joblib"))
path = Path(sys.argv[1]) if len(sys.argv) > 1 else (files[0] if files else None)   # the OLDEST freeze
if path is None:
    raise SystemExit("STOP: no frozen model found. Run freeze_model.py first.")
b = joblib.load(path)
print("Frozen model:", path.name, "| created (UTC):", b["created_utc"])
print("Trained on rounds up to:", b["last_period_id"], "| training rows:", b["n_train_rows"])

models = {"big": dict(b["big"]), "number": dict(b["number"])}
strong_path = Path("models") / f"frozen_strong_{b['last_period_id']}.joblib"
if strong_path.exists():
    s = joblib.load(strong_path)
    assert s["last_period_id"] == b["last_period_id"], "strong file was frozen on different data"
    models["big"].update(s["big"])
    models["number"].update(s["number"])
    print("Strong models loaded:", strong_path.name)
else:
    print("(no strong models frozen for this data)")

df = pd.read_csv("data/processed/rounds_30s_clean.csv", dtype={"period_id": str})
X, y_num, pids = build_features(df)
fresh = pids > b["last_period_id"]                   # only rounds the model never saw
n = int(fresh.sum())
print(f"Fresh rounds available: {n}")
if n < MIN_FRESH:
    raise SystemExit(f"STOP: only {n} fresh rounds. Collect at least {MIN_FRESH} (2000+ is better), then run again.")
Xf, yn = X[fresh], y_num[fresh]
yb = (yn >= 5).astype(int)


def predict(mods, Xf):
    out = {"Baseline (majority)": np.full(len(Xf), mods["majority"])}
    for k, m in mods.items():
        if k != "majority":
            out[NAMES.get(k, k)] = m.predict(Xf)
    return out


def wilson(k, n):
    ci = stats.binomtest(int(k), int(n)).proportion_ci(confidence_level=0.95, method="wilson")
    return ci.low, ci.high


def report(title, truth, preds, chance):
    base = preds["Baseline (majority)"]
    print(f"\n=== {title} (fresh rounds: {len(truth)}, chance = {chance:.0%}) ===")
    print(f"{'model':<28} {'accuracy':>8}  {'95% range':<15} {'balanced':>8}  {'p vs chance':>11}  {'p vs baseline':>13}")
    res = {}
    for name, p in preds.items():
        hit = p == truth
        lo, hi = wilson(hit.sum(), len(truth))
        bb = int((hit & (base != truth)).sum())
        cc = int((~hit & (base == truth)).sum())
        pb = stats.binomtest(min(bb, cc), bb + cc, 0.5).pvalue if (bb + cc > 0 and name != "Baseline (majority)") else float("nan")
        res[name] = (hit.mean(), pb)
        print(f"{name:<28} {hit.mean():>8.3f}  {lo:.3f} to {hi:.3f}  {balanced_accuracy_score(truth, p):>8.3f}  "
              f"{stats.binomtest(int(hit.sum()), len(truth), chance).pvalue:>11.4f}  "
              f"{'-' if name.startswith('Baseline') else format(pb, '.4f'):>13}")
    return res


r1 = report("Big or Small", yb, predict(models["big"], Xf), 0.5)
r2 = report("Exact number 0-9", yn, predict(models["number"], Xf), 0.1)

k = (len(r1) - 1) + (len(r2) - 1)
bar = 0.05 / k
print(f"\n=== Verdict === ({k} comparisons, a model wins only if it beats the baseline AND p vs baseline < {bar:.4f})")
wins = [(lab, n_, round(a, 3), round(p, 4)) for lab, r in (("Big/Small", r1), ("Number", r2))
        for n_, (a, p) in r.items()
        if not n_.startswith("Baseline") and a > r["Baseline (majority)"][0] and p < bar]
print("WIN on fresh data:" if wins else "No model beat its baseline on fresh data. No usable signal.")
for w in wins:
    print("  ", w)
