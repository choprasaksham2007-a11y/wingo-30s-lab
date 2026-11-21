import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

# The API gives two extra fields per round: premium and sum. We never tested them.
# python src\check_extra_fields.py            -> finds wingo_30s_history.csv by itself
# python src\check_extra_fields.py "full\path\to\wingo_30s_history.csv"
if len(sys.argv) > 1:
    path = Path(sys.argv[1])
else:
    path = next(Path.cwd().rglob("wingo_30s_history.csv"), None)
if path is None or not path.exists():
    raise SystemExit("STOP: cannot find wingo_30s_history.csv. Pass its full path after the script name.")
print("Using:", path)

df = pd.read_csv(path, dtype={"issueNumber": str}).drop_duplicates("issueNumber").sort_values("issueNumber").reset_index(drop=True)
day = pd.to_datetime(df["issueNumber"].str[:8], format="%Y%m%d")
df["abs"] = (day - day.min()).dt.days * 2880 + df["issueNumber"].str[-4:].astype(int)
df["premium"] = pd.to_numeric(df["premium"], errors="coerce")
df["sum"] = pd.to_numeric(df["sum"], errors="coerce")
df = df.dropna(subset=["premium", "sum", "number"]).reset_index(drop=True)
print(f"Rounds: {len(df)}")
print(f"premium: {df['premium'].nunique()} different values, from {df['premium'].min()} to {df['premium'].max()}")
print(f"sum:     {df['sum'].nunique()} different values, from {df['sum'].min()} to {df['sum'].max()}")
print(df[["issueNumber", "number", "premium", "sum"]].head(5).to_string(index=False))


def to_groups(s, k=10):
    return s.astype(int) if s.nunique() <= 30 else pd.qcut(s, k, duplicates="drop", labels=False)


def table_p(a, b):
    t = pd.crosstab(a, b)
    return stats.chi2_contingency(t)[1] if t.shape[0] > 1 and t.shape[1] > 1 else 1.0


print("\n--- 1. Inside the same round: how do the fields relate? ---")
n, p, s = df["number"], df["premium"], df["sum"]
rules = {"sum == number + premium": s == n + p, "sum == number": s == n, "sum == premium": s == p,
         "sum % 10 == number": (s % 10) == n, "premium % 10 == number": (p % 10) == n, "premium == number": p == n}
for name, ok in rules.items():
    print(f"  {name:<26} true in {ok.mean():.1%} of rounds")
print(f"  number vs premium (chi-square p) = {table_p(n, to_groups(p)):.4f}")
print(f"  number vs sum     (chi-square p) = {table_p(n, to_groups(s)):.4f}")

print("\n--- 2. THE REAL QUESTION: does this round's premium/sum help guess the NEXT number? ---")
nxt = df["abs"].shift(-1) == df["abs"] + 1                  # only true neighbours, never across a gap
pairs = df[nxt].copy()
pairs["next_number"] = df["number"].shift(-1)[nxt].astype(int)
cut = int(len(pairs) * 0.7)                                  # learn on the older 70%, test on the newer 30%
bonf = 2
for field in ("premium", "sum"):
    g = to_groups(pairs[field])
    p_all = table_p(g, pairs["next_number"])
    tr, te = pairs.iloc[:cut], pairs.iloc[cut:]
    gtr, gte = g.iloc[:cut], g.iloc[cut:]
    best = tr.groupby(gtr)["next_number"].agg(lambda x: x.value_counts().idxmax())
    pred = gte.map(best)
    ok = (pred == te["next_number"])[pred.notna()]
    p_test = stats.binomtest(int(ok.sum()), len(ok), 0.1).pvalue if len(ok) else 1.0
    print(f"  {field:<8} -> next number: chi-square p = {p_all:.4f} | rule learned on old rounds hits {ok.mean():.3f} on new rounds "
          f"(luck = 0.100, p = {p_test:.4f}, {len(ok)} rounds)")
print(f"  (bar for 'interesting' with 2 questions: p < {0.05 / bonf:.3f})")
