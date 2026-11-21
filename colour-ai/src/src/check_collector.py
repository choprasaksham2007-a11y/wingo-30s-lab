from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

# Finds the collector file by walking up from this script until the folder wingo_investigation is found
HERE = Path(__file__).resolve()
LIVE_CSV = next((p / "wingo_investigation" / "collected_data" / "wingo_30s_history.csv"
                 for p in HERE.parents if (p / "wingo_investigation").exists()), None)
if LIVE_CSV is None or not LIVE_CSV.exists():
    raise SystemExit("STOP: cannot find wingo_investigation\\collected_data\\wingo_30s_history.csv")
IST = timezone(timedelta(hours=5, minutes=30))

df = pd.read_csv(LIVE_CSV, dtype={"issueNumber": str})
df = df.drop_duplicates("issueNumber").sort_values("issueNumber").reset_index(drop=True)
day = pd.to_datetime(df["issueNumber"].str[:8], format="%Y%m%d")
rnd = df["issueNumber"].str[-4:].astype(int)
df["end"] = day + pd.Timedelta(hours=5, minutes=30) + pd.to_timedelta(rnd * 30, unit="s")   # when the round ended (IST)
now = datetime.now(IST).replace(tzinfo=None)

print(f"Rounds saved: {len(df)} | first ended: {df['end'].iloc[0]} | newest ended: {df['end'].iloc[-1]}")
age = (now - df["end"].iloc[-1]).total_seconds()
print(f"Newest round ended {age / 60:.1f} minutes ago -> "
      + ("collector is ALIVE" if age < 180 else "collector looks STOPPED (check Task Scheduler and collector.log)"))

print("\nCoverage (saved rounds / rounds that happened):")
for hours in (6, 24, 72):
    start = max(now - timedelta(hours=hours), df["end"].iloc[0])
    expected = (now - start).total_seconds() / 30
    got = int((df["end"] >= start).sum())
    print(f"  last {hours:>2} hours: {got} of about {expected:.0f} = {min(got / expected, 1):.0%}")

gap = (df["end"].diff().dt.total_seconds() / 30 - 1).round()
big = df.assign(missing=gap, before=df["end"].shift(1))[gap >= 5].sort_values("missing", ascending=False).head(6)
print("\nBiggest holes (5 or more missing rounds):")
if big.empty:
    print("  none")
for _, r in big.iterrows():
    print(f"  {r['before']} -> {r['end']} | {int(r['missing'])} rounds missing ({r['missing'] * 30 / 3600:.2f} h)")
