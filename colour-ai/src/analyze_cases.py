import sys

import numpy as np
import pandas as pd
from scipy import stats

# Run with:  python src\analyze_cases.py            (real data)
#            python src\analyze_cases.py --control  (fake random data, must find nothing)
CONTROL = "--control" in sys.argv

df = pd.read_csv("data/processed/rounds_30s_clean.csv", dtype={"period_id": str})
df["counter"] = df["period_id"].str[-5:].astype(int)
df["game_day"] = df["period_id"].str[:8]
df["hour"] = pd.to_datetime(df["timestamp"]).dt.hour

if CONTROL:
    rng_c = np.random.default_rng(42)
    df["number"] = rng_c.integers(0, 10, len(df))
    print(">>> CONTROL MODE: numbers replaced by fake random digits <<<")
df["big"] = (df["number"] >= 5).astype(int)

print("Rounds:", len(df), "| Blocks:", df["block_id"].nunique())

blocks = [g.sort_values("pos_in_block") for _, g in df.groupby("block_id")]
results = []      # (case, name, p-value, note)
not_run = []      # (case, name, reason)


def add(case, name, p, note=""):
    results.append((case, name, float(p), note))
    print(f"Case {case:>2} | {name:<28} | p = {p:.4f} | {note}")


def pairs(lag, col="number"):
    """Pairs of rounds that are `lag` apart, inside the same block only."""
    a, b = [], []
    for g in blocks:
        x = g[col].values
        if len(x) > lag:
            a += list(x[:-lag])
            b += list(x[lag:])
    return np.array(a), np.array(b)


print("\n=== Tests that work with the current data ===")

# Case 4: hour of day
tab = pd.crosstab(df["hour"], df["big"])
add(4, "Hour of day vs Big", stats.chi2_contingency(tab)[1], f"{len(tab)} hours")

# Case 5: streaks (after 3 equal results, does the 4th match?)
succ = trials = 0
for g in blocks:
    b = g["big"].values
    for i in range(3, len(b)):
        if b[i - 1] == b[i - 2] == b[i - 3]:
            trials += 1
            succ += int(b[i] == b[i - 1])
add(5, "Streak of 3 continues?", stats.binomtest(succ, trials, 0.5).pvalue,
    f"continued {succ}/{trials} = {succ / trials:.3f} (chance 0.500)")

# Case 6: number repeats exactly k rounds later (k = 1..60)
best_p, best_lag, best_rate = 1.0, 0, 0.0
for lag in range(1, 61):
    a, b = pairs(lag)
    m = int((a == b).sum())
    p = stats.binomtest(m, len(a), 0.1).pvalue
    if p < best_p:
        best_p, best_lag, best_rate = p, lag, m / len(a)
add(6, "Number repeats at lag 1-60", min(1.0, best_p * 60),
    f"best lag {best_lag}: {best_rate:.3f} (chance 0.100), p fixed for 60 tries")

# Case 7: "overdue" digit (the digit not seen for the longest time)
hits = trials = 0
for g in blocks:
    x = g["number"].values
    last = {}
    for i, d in enumerate(x):
        if len(last) == 10:
            overdue = max(last, key=lambda k: i - last[k])
            trials += 1
            hits += int(d == overdue)
        last[d] = i
add(7, "Overdue digit comes next?", stats.binomtest(hits, trials, 0.1).pvalue,
    f"hit {hits}/{trials} = {hits / trials:.3f} (chance 0.100)")

# Case 8: digit transitions (10 x 10 table)
a, b = pairs(1)
add(8, "Digit transition table", stats.chi2_contingency(pd.crosstab(a, b))[1],
    "previous digit -> next digit")

# Case 9: forced balance in windows of 10 rounds
counts = []
for g in blocks:
    b = g["big"].values
    for s in range(0, len(b) - 9, 10):
        counts.append(int(b[s:s + 10].sum()))
counts = np.array(counts)
bins = [(0, 2), (3, 3), (4, 4), (5, 5), (6, 6), (7, 7), (8, 10)]
obs = np.array([((counts >= lo) & (counts <= hi)).sum() for lo, hi in bins])
exp = np.array([stats.binom.pmf(range(lo, hi + 1), 10, 0.5).sum() for lo, hi in bins]) * len(counts)
add(9, "Balance in 10-round windows", stats.chisquare(obs, exp).pvalue, f"{len(counts)} windows")

# Case 10: last digit of the Period ID vs number
add(10, "Last ID digit vs number",
    stats.chi2_contingency(pd.crosstab(df["counter"] % 10, df["number"]))[1], "")

# Case 11: odd / even round vs Big
add(11, "Odd/even round vs Big",
    stats.chi2_contingency(pd.crosstab(df["counter"] % 2, df["big"]))[1], "")

# Case 12: clock seed idea (counter mod m, m = 3..60) vs Big
best_p, best_m = 1.0, 0
for m in range(3, 61):
    p = stats.chi2_contingency(pd.crosstab(df["counter"] % m, df["big"]))[1]
    if p < best_p:
        best_p, best_m = p, m
add(12, "Counter mod m vs Big (m 3-60)", min(1.0, best_p * 58), f"best m = {best_m}, p fixed for 58 tries")

# Case 14: repeating 4-number sequences (compared with shuffled copies)
def dup_count(arrays):
    grams = [tuple(x[i:i + 4]) for x in arrays for i in range(len(x) - 3)]
    return len(grams) - len(set(grams))


arrays = [g["number"].values for g in blocks]
observed = dup_count(arrays)
rng = np.random.default_rng(0)
sims = np.array([dup_count([rng.permutation(x) for x in arrays]) for _ in range(500)])
add(14, "Repeated 4-number sequences", (1 + (sims >= observed).sum()) / 501,
    f"observed {observed} repeats, shuffled average {sims.mean():.1f}")

# Case 15: hidden regular wave in the longest block (frequency analysis)
big_block = max(blocks, key=len)["big"].values.astype(float)
x = big_block - big_block.mean()
power = np.abs(np.fft.rfft(x)) ** 2
power = power[1:-1] if len(x) % 2 == 0 else power[1:]
g = power / power.mean()
M = len(g)
add(15, "Hidden wave (FFT)", 1 - (1 - np.exp(-g.max())) ** M,
    f"strongest wave repeats every {len(x) / (g.argmax() + 1):.1f} rounds, block of {len(x)}")

print("\n=== Tests that need more data (checked automatically) ===")


def overlap_test(gap_days):
    d = pd.to_datetime(df["game_day"], format="%Y%m%d")
    by_day = {day: grp.set_index("counter")["number"] for day, grp in df.groupby(d)}
    match = total = 0
    for day, s in by_day.items():
        other = by_day.get(day + pd.Timedelta(days=gap_days))
        if other is None:
            continue
        common = s.index.intersection(other.index)
        match += int((s.loc[common].values == other.loc[common].values).sum())
        total += len(common)
    return match, total


NEED = 200
m1, t1 = overlap_test(1)
if t1 >= NEED:
    add(1, "Same time every day", stats.binomtest(m1, t1, 0.1).pvalue, f"matched {m1}/{t1} (chance 0.100)")
else:
    not_run.append((1, "Same time every day", f"only {t1} overlapping time slots between days (need {NEED})"))
m2, t2 = overlap_test(7)
if t2 >= NEED:
    add(2, "Same time every week", stats.binomtest(m2, t2, 0.1).pvalue, f"matched {m2}/{t2} (chance 0.100)")
else:
    not_run.append((2, "Same time every week", f"only {t2} overlapping slots 7 days apart (need {NEED})"))

starts = {}
for day, grp in df.groupby("game_day"):
    first = grp.set_index("counter")["number"]
    if all(c in first.index for c in range(50001, 50021)):
        starts[day] = [first[c] for c in range(50001, 50021)]
if len(starts) >= 5:
    ms = tot = 0
    keys = list(starts)
    for i in range(len(keys)):
        for j in range(i + 1, len(keys)):
            ms += sum(u == v for u, v in zip(starts[keys[i]], starts[keys[j]]))
            tot += 20
    add(3, "Same first 20 rounds each day", stats.binomtest(ms, tot, 0.1).pvalue, f"matched {ms}/{tot}")
else:
    not_run.append((3, "Same first 20 rounds each day", f"only {len(starts)} full day-starts in the data (need 5)"))

day_counts = df.groupby("game_day").size()
good_days = day_counts[day_counts >= 200].index
if len(good_days) >= 5:
    sub = df[df["game_day"].isin(good_days)]
    add(13, "Day-to-day drift in Big", stats.chi2_contingency(pd.crosstab(sub["game_day"], sub["big"]))[1],
        f"{len(good_days)} days")
else:
    not_run.append((13, "Day-to-day drift in Big", f"only {len(good_days)} days with 200+ rounds (need 5)"))

not_run.append((16, "Link to other game modes", "needs 1-min data collected at the same time"))
not_run.append((17, "Crowd effect", "needs bet-volume data, which we do not have"))
for case, name, why in not_run:
    print(f"Case {case:>2} | {name:<30} | NOT RUN: {why}")

print("\n=== Summary ===")
bar = 0.05 / len(results)
print(f"Tests run: {len(results)} | A result is only interesting if p < {bar:.4f} (0.05 divided by {len(results)})")
print()
for case, name, p, note in sorted(results, key=lambda r: r[2]):
    flag = "LOOK CLOSER" if p < bar else ("below 0.05 but probably luck" if p < 0.05 else "nothing")
    print(f"p = {p:.4f} | Case {case:>2} | {name:<30} | {flag}")
print()
print("Reminder: even a 'LOOK CLOSER' result must repeat on fresh data before we believe it.")
