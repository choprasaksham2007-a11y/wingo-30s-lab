import sys

import numpy as np
import pandas as pd
from scipy import stats
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import balanced_accuracy_score
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

# python src\walk_forward.py            -> real data
# python src\walk_forward.py --control  -> fake random digits (every model must score about chance)
CONTROL = "--control" in sys.argv
LAGS = 5          # how many past rounds each model may look at
N_CHUNKS = 8       # chunk 1 is training only; each later chunk is tested using ONLY earlier chunks

df = pd.read_csv("data/processed/rounds_30s_clean.csv", dtype={"period_id": str})
if CONTROL:
    df["number"] = np.random.default_rng(42).integers(0, 10, len(df))
    print(">>> CONTROL MODE: numbers replaced by fake random digits <<<")

# ---------- 1. Build features from the PAST only, inside each block ----------
names = ([f"big_{k}" for k in range(1, LAGS + 1)] + [f"odd_{k}" for k in range(1, LAGS + 1)]
         + [f"violet_{k}" for k in range(1, LAGS + 1)] + ["big_count", "streak"]
         + [f"last{k}_is_{d}" for k in (1, 2, 3) for d in range(10)])
X, y_num, order = [], [], []
for _, g in df.groupby("block_id"):
    g = g.sort_values("pos_in_block")
    num, idx = g["number"].values, g["abs_index"].values
    for i in range(LAGS, len(g)):                 # the first 10 rounds of a block have no full history
        past = num[i - LAGS:i][::-1]              # past[0] = the round just before
        big, odd, vio = (past >= 5).astype(int), past % 2, np.isin(past, [0, 5]).astype(int)
        run = 1
        while run < LAGS and big[run] == big[0]:
            run += 1
        feats = list(big) + list(odd) + list(vio) + [big.sum(), run if big[0] == 1 else -run]
        for k in range(3):
            one_hot = np.zeros(10)
            one_hot[past[k]] = 1
            feats += list(one_hot)
        X.append(feats)
        y_num.append(num[i])
        order.append(idx[i])
X = pd.DataFrame(X, columns=names)
y_num = np.array(y_num)
order = np.array(order)
sort = np.argsort(order)                           # true time order across all blocks
X, y_num = X.iloc[sort].reset_index(drop=True), y_num[sort]
y_big = (y_num >= 5).astype(int)
print(f"Usable rounds: {len(X)} (first {LAGS} rounds of every block are warm-up) | features: {X.shape[1]}")

chunks = np.array_split(np.arange(len(X)), N_CHUNKS)
test_rows = np.concatenate(chunks[1:])
print(f"Walk-forward: {N_CHUNKS - 1} tests, each uses only EARLIER chunks for training. Tested rounds: {len(test_rows)}")


def wilson(k, n):
    ci = stats.binomtest(int(k), int(n)).proportion_ci(confidence_level=0.95, method="wilson")
    return ci.low, ci.high


def run(target, models, chance):
    preds = {name: [] for name in models}
    truth = []
    for k in range(1, N_CHUNKS):
        tr = np.concatenate(chunks[:k])
        te = chunks[k]
        truth.append(target[te])
        for name, make in models.items():
            preds[name].append(make(X.iloc[tr], target[tr], X.iloc[te]))
    truth = np.concatenate(truth)
    preds = {n: np.concatenate(p) for n, p in preds.items()}
    return truth, preds


def report(title, truth, preds, chance, base_name, classes_names=None):
    n = len(truth)
    base = preds[base_name]
    print(f"\n=== {title} (tested on {n} rounds, chance = {chance:.0%}) ===")
    print(f"{'model':<28} {'accuracy':>8}  {'95% range':<15} {'balanced':>8}  {'p vs chance':>11}  {'p vs baseline':>13}")
    out = {}
    for name, p in preds.items():
        hit = p == truth
        lo, hi = wilson(hit.sum(), n)
        bal = balanced_accuracy_score(truth, p)
        p_chance = stats.binomtest(int(hit.sum()), n, chance).pvalue
        b = int((hit & (base != truth)).sum())
        c = int((~hit & (base == truth)).sum())
        p_base = stats.binomtest(min(b, c), b + c, 0.5).pvalue if b + c > 0 and name != base_name else float("nan")
        out[name] = (hit.mean(), p_base)
        pb = "-" if name == base_name else f"{p_base:.4f}"
        print(f"{name:<28} {hit.mean():>8.3f}  {lo:.3f} to {hi:.3f}  {bal:>8.3f}  {p_chance:>11.4f}  {pb:>13}")
    if classes_names:
        print("Per-class hit rate (recall):")
        for name, p in preds.items():
            parts = [f"{cn}: {np.mean(p[truth == v] == v):.3f}" for v, cn in classes_names.items()]
            print(f"  {name:<28} " + " | ".join(parts))
    half = (wilson((preds[base_name] == truth).sum(), n)[1] - wilson((preds[base_name] == truth).sum(), n)[0]) / 2
    print(f"-> With {n} tested rounds, any score is uncertain by about +-{half:.1%}.")
    return out


# ---------- 2. Models (each gets only past data) ----------
def majority(Xtr, ytr, Xte):
    return np.full(len(Xte), np.bincount(ytr).argmax())


def repeat_last(Xtr, ytr, Xte):
    return Xte["big_1"].values


def opposite_last(Xtr, ytr, Xte):
    return 1 - Xte["big_1"].values


def logistic(Xtr, ytr, Xte):
    m = make_pipeline(StandardScaler(), LogisticRegression(C=0.05, max_iter=2000))
    return m.fit(Xtr, ytr).predict(Xte)


def forest(Xtr, ytr, Xte):
    m = RandomForestClassifier(n_estimators=200, max_depth=6, min_samples_leaf=20, random_state=0, n_jobs=-1)
    return m.fit(Xtr, ytr).predict(Xte)


big_models = {"Baseline: always majority": majority, "Rule: repeat last result": repeat_last,
              "Rule: opposite of last": opposite_last, "Logistic regression": logistic, "Random forest": forest}
num_models = {"Baseline: most common digit": majority, "Logistic regression": logistic, "Random forest": forest}

t, p = run(y_big, big_models, 0.5)
r1 = report("Target 1: Big or Small", t, p, 0.5, "Baseline: always majority", {0: "Small", 1: "Big"})
t, p = run(y_num, num_models, 0.1)
r2 = report("Target 2: the exact number 0-9", t, p, 0.1, "Baseline: most common digit")

# ---------- 3. Verdict, with the rule fixed BEFORE looking ----------
tests = [(n, v) for r in (r1, r2) for n, v in r.items() if not n.startswith("Baseline")]
bar = 0.05 / len(tests)
print(f"\n=== Verdict ===\nModels compared with their baseline: {len(tests)} -> a model only 'wins' if it scores higher AND p vs baseline < {bar:.4f}")
wins = []
for label, r in (("Big/Small", r1), ("Number", r2)):
    base_acc = [v[0] for n, v in r.items() if n.startswith("Baseline")][0]
    for n, (acc, pb) in r.items():
        if not n.startswith("Baseline") and acc > base_acc and pb < bar:
            wins.append((label, n, acc, pb))
if wins:
    for w in wins:
        print(f"WIN (needs checking on FRESH data): {w}")
else:
    print("No model beat its baseline. No usable signal found in this data.")
