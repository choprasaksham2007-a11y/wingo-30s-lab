import numpy as np
import pandas as pd
from scipy import stats

CHUNK = 150          # rounds per chunk
FLAG_P = 0.01        # flag chunks with p below this

df = pd.read_csv("data/processed/rounds_30s_clean.csv", dtype={"period_id": str})
print(f"Rounds: {len(df)} | chunk size: {CHUNK} | flag if p < {FLAG_P}\n")
print("chunk | from -> to                  | rounds | p-value | count of 6 | count of 8 | note")

rows = []
for b, g in df.groupby("block_id"):
    g = g.sort_values("pos_in_block")
    starts = list(range(0, len(g), CHUNK))
    for s in starts:
        part = g.iloc[s:s + CHUNK]
        if len(part) < CHUNK // 2:
            continue
        rows.append(part)

flagged = 0
for i, part in enumerate(rows, 1):
    c = part["number"].value_counts().reindex(range(10), fill_value=0)
    p = stats.chisquare(c).pvalue
    note = ""
    if p < FLAG_P:
        flagged += 1
        z = (c - len(part) / 10) / np.sqrt(len(part) * 0.1 * 0.9)
        note = f"CHECK digit {int(z.idxmax())} too many ({int(c[z.idxmax()])}), digit {int(z.idxmin())} too few ({int(c[z.idxmin()])})"
    span = f"{part['timestamp'].iloc[0][5:16]} -> {part['timestamp'].iloc[-1][5:16]}"
    print(f"{i:>5} | {span:<27} | {len(part):>6} | {p:>7.4f} | {int(c[6]):>10} | {int(c[8]):>10} | {note}")

print(f"\nChunks checked: {len(rows)} | flagged: {flagged} (luck alone flags about {len(rows) * FLAG_P:.1f})")
print("A flagged chunk usually means a misread digit (6/8, 1/7, 0/8, 3/8, 5/6 look alike), not a pattern.")
