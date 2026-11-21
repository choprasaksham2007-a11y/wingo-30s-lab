import sys

import numpy as np
import pandas as pd
from scipy import stats

# python src\analyze_all.py            -> real data
# python src\analyze_all.py --control  -> fake random digits (must find nothing)
CONTROL = "--control" in sys.argv

df = pd.read_csv("data/processed/rounds_30s_clean.csv", dtype={"period_id": str})
ts = pd.to_datetime(df["timestamp"])
df["game_day"] = df["period_id"].str[:8]
df["hour"] = ts.dt.hour
df["minute"] = ts.dt.minute
df["weekday"] = ts.dt.day_of_week

if CONTROL:
    df["number"] = np.random.default_rng(42).integers(0, 10, len(df))
    print(">>> CONTROL MODE: numbers replaced by fake random digits <<<")

df["big"] = (df["number"] >= 5).astype(int)
df["odd"] = (df["number"] % 2).astype(int)                    # odd = Green side
df["violet"] = df["number"].isin([0, 5]).astype(int)
df["daypart"] = pd.cut(df["hour"], [-1, 5, 11, 17, 23], labels=False)

print(f"Rounds: {len(df)} | Blocks: {df['block_id'].nunique()} | Days: {df['game_day'].nunique()}")

blocks = [g.sort_values("pos_in_block") for _, g in df.groupby("block_id")]
BIN = {"Big": ("big", 0.5), "Odd/Green": ("odd", 0.5), "Violet": ("violet", 0.2)}
results = []   # (id, group, name, p, note)
skipped = []   # (id, name, reason)


def add(cid, group, name, p, note=""):
    results.append((cid, group, name, float(min(1.0, max(0.0, p))), note))


def lag_pairs(col, lag):
    a, b = [], []
    for g in blocks:
        x = g[col].values
        if len(x) > lag:
            a.append(x[:-lag])
            b.append(x[lag:])
    return np.concatenate(a), np.concatenate(b)


def table_p(a, b):
    t = pd.crosstab(a, b)
    if t.shape[0] < 2 or t.shape[1] < 2:
        return 1.0, ""
    chi2, p, dof, exp = stats.chi2_contingency(t)
    if t.shape == (2, 2) and exp.min() < 5:
        return stats.fisher_exact(t.values)[1], ""
    note = "rough: many small cells" if (exp < 5).mean() > 0.2 else ""
    return p, note


def merge_bins(obs, exp, minexp=5):
    o, e, co, ce = [], [], 0, 0
    for x, y in zip(obs, exp):
        co += x
        ce += y
        if ce >= minexp:
            o.append(co)
            e.append(ce)
            co = ce = 0
    if co or ce:
        if o:
            o[-1] += co
            e[-1] += ce
        else:
            o.append(co)
            e.append(ce)
    return np.array(o), np.array(e)


def window_balance(col, w, p0):
    counts = []
    for g in blocks:
        b = g[col].values
        for s in range(0, len(b) - w + 1, w):
            counts.append(int(b[s:s + w].sum()))
    counts = np.array(counts)
    obs = np.bincount(counts, minlength=w + 1)
    exp = stats.binom.pmf(np.arange(w + 1), w, p0) * len(counts)
    o, e = merge_bins(obs, exp)
    if len(o) < 3:
        return None, len(counts)
    return stats.chisquare(o, e).pvalue, len(counts)


def runs_p(col):
    runs = mu_t = var_t = 0.0
    for g in blocks:
        b = g[col].values
        n1, m = int(b.sum()), len(b)
        n0 = m - n1
        if n1 == 0 or n0 == 0 or m < 3:
            continue
        runs += 1 + (b[1:] != b[:-1]).sum()
        mu = 2 * n1 * n0 / m + 1
        mu_t += mu
        var_t += (mu - 1) * (mu - 2) / (m - 1)
    z = (runs - mu_t) / np.sqrt(var_t)
    return 2 * (1 - stats.norm.cdf(abs(z))), z


def fft_p(col):
    b = max(blocks, key=len)[col].values.astype(float)
    if len(b) < 100:
        return None, 0, 0
    x = b - b.mean()
    power = np.abs(np.fft.rfft(x)) ** 2
    power = power[1:-1] if len(x) % 2 == 0 else power[1:]
    g = power / power.mean()
    p = 1 - (1 - np.exp(-g.max())) ** len(g)
    return p, len(x) / (g.argmax() + 1), len(x)


# ---------------- Group A: are the frequencies fair? ----------------
counts = df["number"].value_counts().reindex(range(10), fill_value=0)
add("A1", "A Fairness", "Digits 0-9 equally common", stats.chisquare(counts).pvalue,
    f"lowest digit {counts.idxmin()} ({counts.min()}), highest {counts.idxmax()} ({counts.max()})")
for name, (col, p0) in BIN.items():
    k, n = int(df[col].sum()), len(df)
    add({"Big": "A2", "Odd/Green": "A3", "Violet": "A4"}[name], "A Fairness", f"{name} share = {p0:.0%}",
        stats.binomtest(k, n, p0).pvalue, f"share {k / n:.3f}")
cls = df["number"].map({1: 0, 3: 0, 7: 0, 9: 0, 2: 1, 4: 1, 6: 1, 8: 1, 5: 2, 0: 3})
obs = cls.value_counts().reindex(range(4), fill_value=0).values
add("A5", "A Fairness", "Colour classes (G, R, G+V, R+V)",
    stats.chisquare(obs, np.array([0.4, 0.4, 0.1, 0.1]) * len(df)).pvalue, f"counts {obs.tolist()}")

# ---------------- Group B: does the past change the next result? ----------------
ids = iter(["B1", "B2", "B3"])
for name, (col, p0) in BIN.items():
    a, b = lag_pairs(col, 1)
    p, _ = table_p(a, b)
    add(next(ids), "B Past vs next", f"{name}: last result vs next", p,
        f"next=1 after 1: {b[a == 1].mean():.3f}, after 0: {b[a == 0].mean():.3f}")
ids = iter(["B4", "B5", "B6"])
for name, (col, p0) in BIN.items():
    p, z = runs_p(col)
    add(next(ids), "B Past vs next", f"{name}: streak (runs) test", p, f"z = {z:.2f}")
ids = iter(["B7", "B8"])
for name in ("Big", "Odd/Green"):
    col = BIN[name][0]
    succ = trials = 0
    for g in blocks:
        b = g[col].values
        for i in range(3, len(b)):
            if b[i - 1] == b[i - 2] == b[i - 3]:
                trials += 1
                succ += int(b[i] == b[i - 1])
    if trials:
        add(next(ids), "B Past vs next", f"{name}: streak of 3 continues?",
            stats.binomtest(succ, trials, 0.5).pvalue, f"continued {succ}/{trials} = {succ / trials:.3f}")
ids = iter(["B9", "B10", "B11"])
for name, (col, p0) in BIN.items():
    best_p, best_lag, best_r = 1.0, 0, 0.0
    for lag in range(1, 31):
        a, b = lag_pairs(col, lag)
        if a.std() == 0 or b.std() == 0:
            continue
        r = np.corrcoef(a, b)[0, 1]
        p = 2 * (1 - stats.norm.cdf(abs(r) * np.sqrt(len(a))))
        if p < best_p:
            best_p, best_lag, best_r = p, lag, r
    add(next(ids), "B Past vs next", f"{name}: link at lag 1-30", best_p * 30,
        f"best lag {best_lag}, r = {best_r:+.3f}, fixed for 30 tries")

# ---------------- Group C: number sequences ----------------
a, b = lag_pairs("number", 1)
p, note = table_p(a, b)
add("C1", "C Numbers", "Digit transition table (lag 1)", p, note)
a2, b2 = lag_pairs("number", 2)
p, note = table_p(a2, b2)
add("C2", "C Numbers", "Digit transition table (lag 2)", p, note)

best_p, best_lag, best_rate = 1.0, 0, 0.0
for lag in range(1, 61):
    x, y = lag_pairs("number", lag)
    m = int((x == y).sum())
    p = stats.binomtest(m, len(x), 0.1).pvalue
    if p < best_p:
        best_p, best_lag, best_rate = p, lag, m / len(x)
add("C3", "C Numbers", "Same digit k rounds later (k 1-60)", best_p * 60,
    f"best k {best_lag}: {best_rate:.3f} (chance 0.100), fixed for 60 tries")

hits = trials = 0
for g in blocks:
    last = {}
    for i, d in enumerate(g["number"].values):
        if len(last) == 10:
            overdue = max(last, key=lambda k: i - last[k])
            trials += 1
            hits += int(d == overdue)
        last[d] = i
add("C4", "C Numbers", "Overdue digit comes next?", stats.binomtest(hits, trials, 0.1).pvalue,
    f"hit {hits}/{trials} = {hits / trials:.3f}")

hits = trials = 0
for g in blocks:
    x = g["number"].values
    for i in range(20, len(x)):
        c = np.bincount(x[i - 20:i], minlength=10)
        if (c == c.max()).sum() == 1:
            trials += 1
            hits += int(x[i] == c.argmax())
add("C5", "C Numbers", "Hot digit (last 20 rounds) comes next?", stats.binomtest(hits, trials, 0.1).pvalue,
    f"hit {hits}/{trials} = {hits / trials:.3f}")


def dup_count(arrays):
    grams = [tuple(x[i:i + 4]) for x in arrays for i in range(len(x) - 3)]
    return len(grams) - len(set(grams))


arrays = [g["number"].values for g in blocks]
observed = dup_count(arrays)
rng = np.random.default_rng(0)
sims = np.array([dup_count([rng.permutation(x) for x in arrays]) for _ in range(500)])
add("C6", "C Numbers", "Repeated 4-number sequences", (1 + (sims >= observed).sum()) / 501,
    f"seen {observed}, shuffled average {sims.mean():.1f}")

# C7: waiting time between the same digit. FIXED: compared with shuffled copies, because blocks end early
# (a block that ends before the next same digit hides long waits, which fakes a pattern in the old version)
E7 = [(1, 1), (2, 2), (3, 3), (4, 5), (6, 8), (9, 12), (13, 20), (21, 40), (41, 10 ** 9)]


def gap_counts(arrs):
    gp = []
    for x in arrs:
        pos = {}
        for i, dg in enumerate(x):
            if dg in pos:
                gp.append(i - pos[dg])
            pos[dg] = i
    gp = np.array(gp)
    return np.array([((gp >= lo) & (gp <= hi)).sum() for lo, hi in E7]), len(gp)


obs7, n7 = gap_counts(arrays)
sims7 = np.array([gap_counts([rng.permutation(x) for x in arrays])[0] for _ in range(400)])
mu7 = sims7.mean(axis=0)
use7 = mu7 >= 5
stat7 = lambda c: (((c[use7] - mu7[use7]) ** 2) / mu7[use7]).sum()
s_obs7, s_sims7 = stat7(obs7), np.array([stat7(c) for c in sims7])
add("C7", "C Numbers", "Waiting time between same digit", (1 + (s_sims7 >= s_obs7).sum()) / 401, f"{n7} waiting times (shuffle test)")

diff = (b - a) % 10
add("C8", "C Numbers", "Next = previous + k (mod 10)", stats.chisquare(np.bincount(diff, minlength=10)).pvalue, "")

hits = trials = 0
for g in blocks:
    x = g["number"].values
    if len(x) > 2:
        trials += len(x) - 2
        hits += int(((x[:-2] + x[1:-1]) % 10 == x[2:]).sum())
add("C9", "C Numbers", "Next = (last two digits added) mod 10", stats.binomtest(hits, trials, 0.1).pvalue,
    f"hit {hits}/{trials} = {hits / trials:.3f}")

# ---------------- Group D: balance and hidden waves ----------------
for cid, name, col, w, p0 in [("D1", "Big", "big", 10, 0.5), ("D2", "Big", "big", 20, 0.5),
                              ("D3", "Odd/Green", "odd", 10, 0.5), ("D4", "Violet", "violet", 20, 0.2)]:
    p, nw = window_balance(col, w, p0)
    if p is None:
        skipped.append((cid, f"{name} balance in {w}-round windows", "too few windows"))
    else:
        add(cid, "D Balance/waves", f"{name}: balance in {w}-round windows", p, f"{nw} windows")
for cid, name, col in [("D5", "Big", "big"), ("D6", "Odd/Green", "odd"), ("D7", "Violet", "violet")]:
    p, period, n = fft_p(col)
    if p is None:
        skipped.append((cid, f"{name}: hidden wave", "longest block under 100 rounds"))
    else:
        add(cid, "D Balance/waves", f"{name}: hidden wave (FFT)", p, f"strongest every {period:.1f} rounds (block {n})")

# ---------------- Group E: clock and ID ----------------
p, _ = table_p(df["hour"], df["big"]);        add("E1", "E Clock/ID", "Hour of day vs Big", p, f"{df['hour'].nunique()} hours")
p, _ = table_p(df["hour"], df["odd"]);        add("E2", "E Clock/ID", "Hour of day vs Odd/Green", p, "")
p, _ = table_p(df["hour"], df["violet"]);     add("E3", "E Clock/ID", "Hour of day vs Violet", p, "")
p, n = table_p(df["daypart"], df["number"]);  add("E4", "E Clock/ID", "Part of day vs digit", p, n)
p, _ = table_p(df["counter"] % 2, df["big"]); add("E5", "E Clock/ID", "Odd/even round vs Big", p, "")
p, n = table_p(df["counter"] % 10, df["number"]); add("E6", "E Clock/ID", "Last ID digit vs digit", p, n)
p, _ = table_p(df["counter"] % 10, df["big"]);    add("E7", "E Clock/ID", "Last ID digit vs Big", p, "")


def best_mod(target, lo, hi):
    best_p, best_m = 1.0, 0
    for m in range(lo, hi + 1):
        p, _ = table_p(df["counter"] % m, df[target])
        if p < best_p:
            best_p, best_m = p, m
    return best_p * (hi - lo + 1), best_m


p, m = best_mod("big", 3, 60);  add("E8", "E Clock/ID", "Round counter mod m vs Big (m 3-60)", p, f"best m = {m}")
p, m = best_mod("odd", 3, 60);  add("E9", "E Clock/ID", "Round counter mod m vs Odd (m 3-60)", p, f"best m = {m}")
p, m = best_mod("number", 3, 12); add("E10", "E Clock/ID", "Round counter mod m vs digit (m 3-12)", p, f"best m = {m}")
p, _ = table_p(df["minute"], df["big"]);        add("E11", "E Clock/ID", "Minute of hour vs Big", p, "")

# ---------------- Group F: needs several days (checked automatically) ----------------
NEED = 200
dates = pd.to_datetime(df["game_day"], format="%Y%m%d")
by_day = {d: g.set_index("counter") for d, g in df.groupby(dates)}


def overlap(gap_days, col):
    match = total = 0
    for d, s in by_day.items():
        o = by_day.get(d + pd.Timedelta(days=gap_days))
        if o is None:
            continue
        common = s.index.intersection(o.index)
        match += int((s.loc[common, col].values == o.loc[common, col].values).sum())
        total += len(common)
    return match, total


for cid, name, gap, col, p0 in [("F1", "Same time every day: digit", 1, "number", 0.1),
                                ("F2", "Same time every day: Big/Small", 1, "big", 0.5),
                                ("F3", "Same time every week: digit", 7, "number", 0.1)]:
    m, t = overlap(gap, col)
    if t >= NEED:
        add(cid, "F Multi-day", name, stats.binomtest(m, t, p0).pvalue, f"matched {m}/{t} (chance {p0})")
    else:
        skipped.append((cid, name, f"only {t} overlapping time slots (need {NEED})"))

starts = {}
for d, g in df.groupby("game_day"):
    first = g.set_index("counter")["number"]
    if all(c in first.index for c in range(50001, 50021)):
        starts[d] = [first[c] for c in range(50001, 50021)]
if len(starts) >= 5:
    keys, ms, tot = list(starts), 0, 0
    for i in range(len(keys)):
        for j in range(i + 1, len(keys)):
            ms += sum(u == v for u, v in zip(starts[keys[i]], starts[keys[j]]))
            tot += 20
    add("F4", "F Multi-day", "Same first 20 rounds each day", stats.binomtest(ms, tot, 0.1).pvalue, f"matched {ms}/{tot}")
else:
    skipped.append(("F4", "Same first 20 rounds each day", f"only {len(starts)} full day-starts (need 5)"))

dc = df.groupby("game_day").size()
good = dc[dc >= NEED].index
if len(good) >= 5:
    sub = df[df["game_day"].isin(good)]
    p, _ = table_p(sub["game_day"], sub["big"])
    add("F5", "F Multi-day", "Day-to-day drift in Big", p, f"{len(good)} days")
else:
    skipped.append(("F5", "Day-to-day drift in Big", f"only {len(good)} days with {NEED}+ rounds (need 5)"))
wd = df.groupby("weekday").size()
if (wd >= NEED).sum() >= 5:
    sub = df[df["weekday"].isin(wd[wd >= NEED].index)]
    p, _ = table_p(sub["weekday"], sub["big"])
    add("F6", "F Multi-day", "Weekday vs Big", p, f"{(wd >= NEED).sum()} weekdays")
else:
    skipped.append(("F6", "Weekday vs Big", f"only {(wd >= NEED).sum()} weekdays with {NEED}+ rounds (need 5)"))
skipped.append(("G1", "Link to other game modes", "needs 1-min data collected at the same time"))
skipped.append(("G2", "Crowd effect (bet volume)", "needs data we cannot get"))

# ---------------- Report ----------------
print("\n=== All tests, in order ===")
last_group = ""
for cid, group, name, p, note in results:
    if group != last_group:
        print(f"\n[{group}]")
        last_group = group
    print(f"{cid:>3} | p = {p:.4f} | {name:<44} | {note}")

print("\n=== Not run ===")
for cid, name, why in skipped:
    print(f"{cid:>3} | {name:<44} | {why}")

n = len(results)
bar = 0.05 / n
lucky = sum(p < 0.05 for _, _, _, p, _ in results)
print("\n=== Summary ===")
print(f"Tests run: {n}")
print(f"Bar for 'interesting' (Bonferroni): p < {bar:.5f}")
print(f"Tests with p < 0.05: {lucky}  (luck alone gives about {0.05 * n:.1f})")
print("\n5 lowest p-values:")
for cid, group, name, p, note in sorted(results, key=lambda r: r[3])[:5]:
    flag = "LOOK CLOSER" if p < bar else "probably luck"
    print(f"  p = {p:.4f} | {cid} {name} | {flag}")
if all(p >= bar for _, _, _, p, _ in results):
    print("\nVerdict: no test passed the bar. No pattern found in this data.")
else:
    print("\nVerdict: some tests passed the bar. They must repeat on FRESH data before we believe them.")
