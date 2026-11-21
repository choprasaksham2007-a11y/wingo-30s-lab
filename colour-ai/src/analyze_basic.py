import numpy as np
import pandas as pd
from scipy import stats

df = pd.read_csv("data/processed/rounds_30s_clean.csv", dtype={"period_id": str})
df["big"] = (df["size"] == "Big").astype(int)
print("Rounds:", len(df), "| Blocks:", df["block_id"].nunique())

# 1. Are the digits 0-9 equally common?
print("\n--- 1. Number frequency ---")
counts = df["number"].value_counts().sort_index()
print(counts.to_string())
chi = stats.chisquare(counts)
print(f"Chi-square test for equal digits: p = {chi.pvalue:.3f}")

# 2. Is Big about 50%?
print("\n--- 2. Big / Small ---")
n_big, n = int(df["big"].sum()), len(df)
ci = stats.binomtest(n_big, n, 0.5).proportion_ci(confidence_level=0.95)
print(f"Big share: {n_big / n:.3f}  (95% range {ci.low:.3f} to {ci.high:.3f})")
print(f"Test against 50%: p = {stats.binomtest(n_big, n, 0.5).pvalue:.3f}")

# 3. Does the last result change the next one? (inside blocks only)
print("\n--- 3. Big/Small after Big/Small ---")
prev, nxt = [], []
for _, g in df.groupby("block_id"):
    b = g["big"].values
    prev += list(b[:-1])
    nxt += list(b[1:])
table = pd.crosstab(pd.Series(prev, name="previous"), pd.Series(nxt, name="next"))
print(table.to_string())
print(f"Chi-square test (independent?): p = {stats.chi2_contingency(table)[1]:.3f}")

# 4. Runs (streak) test, block by block
print("\n--- 4. Streak (runs) test ---")
runs_total = mu_total = var_total = 0.0
for _, g in df.groupby("block_id"):
    b = g["big"].values
    n1, n0, m = b.sum(), len(b) - b.sum(), len(b)
    if n1 == 0 or n0 == 0:
        continue
    runs_total += 1 + (b[1:] != b[:-1]).sum()
    mu = 2 * n1 * n0 / m + 1
    mu_total += mu
    var_total += (mu - 1) * (mu - 2) / (m - 1)
z = (runs_total - mu_total) / np.sqrt(var_total)
print(f"Runs seen: {int(runs_total)} | expected: {mu_total:.1f} | z = {z:.2f}")
print("(z between -2 and +2 means normal)")

# 5. Do earlier numbers link to later numbers? (inside blocks only)
print("\n--- 5. Correlation between numbers k rounds apart ---")
for lag in (1, 2, 3, 5, 10):
    a, b = [], []
    for _, g in df.groupby("block_id"):
        x = g["number"].values
        if len(x) > lag:
            a += list(x[:-lag])
            b += list(x[lag:])
    r = np.corrcoef(a, b)[0, 1]
    print(f"lag {lag:>2}: r = {r:+.3f}   (pairs: {len(a)}, noise level about +-{2 / np.sqrt(len(a)):.3f})")

# 6. The baseline: train on the oldest blocks, test on the newest blocks
print("\n--- 6. Simple baseline (guess the most common result) ---")
train = df[df["block_id"] <= 2]
test = df[df["block_id"] >= 3]
maj_size = train["big"].mode()[0]
acc = (test["big"] == maj_size).mean()
ci = stats.binomtest(int((test["big"] == maj_size).sum()), len(test)).proportion_ci(0.95)
print(f"Train rounds: {len(train)} | Test rounds: {len(test)}")
print(f"Big/Small: always guess {'Big' if maj_size else 'Small'} -> test accuracy {acc:.3f} (95% range {ci.low:.3f} to {ci.high:.3f})")
maj_num = train["number"].mode()[0]
acc_n = (test["number"] == maj_num).mean()
print(f"Number: always guess {maj_num} -> test accuracy {acc_n:.3f} (pure luck is 0.100)")
