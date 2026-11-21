from pathlib import Path

import pandas as pd

RAW_FILE = Path("data/raw/Colour_Prediction_Dataset_corrected.xlsx")  # change if your file name is different
SHEET = "Raw_Data"
OUT_CLEAN = Path("data/processed/rounds_30s_clean.csv")
OUT_BLOCKS = Path("data/processed/block_map_30s.csv")

ROUNDS_PER_DAY = 2880
FIRST_COUNTER = 50001
LAST_COUNTER = 52880

# Rules you confirmed for this site
COLOUR_RULE = {
    0: "Red+Violet",
    1: "Green", 3: "Green", 7: "Green", 9: "Green",
    2: "Red", 4: "Red", 6: "Red", 8: "Red",
    5: "Green+Violet",
}


def size_rule(n):
    return "Small" if n <= 4 else "Big"


# 1. Load (read Period ID as text so it is never rounded)
df = pd.read_excel(RAW_FILE, sheet_name=SHEET, dtype={"Period ID": str})
df = df.rename(columns={"Period ID": "period_id"})
df = df.dropna(subset=["period_id", "number"]).copy()
df["period_id"] = df["period_id"].astype(str).str.strip()
print("Rows loaded:", len(df))

# 2. Period ID must be exactly 17 digits, number must be 0-9
bad_id = df[~df["period_id"].str.fullmatch(r"\d{17}")]
if len(bad_id):
    print(bad_id[["period_id", "number"]].head(10).to_string())
    raise SystemExit("STOP: some Period IDs are not 17 digits. If you typed them in Excel, "
                     "format the column as TEXT first, because Excel rounds long numbers.")
df["number"] = pd.to_numeric(df["number"], errors="coerce")
if df["number"].isna().any() or not df["number"].between(0, 9).all():
    print(df[df["number"].isna() | ~df["number"].between(0, 9)][["period_id", "number"]].head(10))
    raise SystemExit("STOP: some numbers are missing or outside 0-9.")
df["number"] = df["number"].astype(int)

# 2b. Add the rounds saved by the live collector (clean digits from the game's own history)
LIVE_CSV = Path("wingo_investigation/collected_data/wingo_30s_history.csv")
if LIVE_CSV.exists():
    live = pd.read_csv(LIVE_CSV, dtype={"issueNumber": str})
    live = live.rename(columns={"issueNumber": "period_id"})[["period_id", "number"]].dropna()
    live["period_id"] = live["period_id"].str.strip()
    live["number"] = pd.to_numeric(live["number"], errors="coerce")
    live = live.dropna()
    live["number"] = live["number"].astype(int)
    live = live[live["period_id"].str.fullmatch(r"\d{17}") & live["number"].between(0, 9)]
    live = live.drop_duplicates("period_id")
    sheet_ids = set(df["period_id"])
    both = df.merge(live, on="period_id", suffixes=("_sheet", "_live"))
    disagree = both[both["number_sheet"] != both["number_live"]]
    print(f"Live collector: {len(live)} rounds | also in workbook: {len(both)} | disagreements: {len(disagree)}")
    if len(disagree):
        print(disagree[["period_id", "number_sheet", "number_live"]].head(15).to_string())
        print("(the live collector wins: the workbook digit was probably misread)")
    beyond = live[~live["period_id"].isin(sheet_ids)]
    if len(beyond):
        last_id = beyond["period_id"].max()
        last_time = pd.to_datetime(last_id[:8], format="%Y%m%d") + pd.Timedelta(hours=5, minutes=30) \
            + pd.Timedelta(seconds=30 * int(last_id[-4:]))
        print(f"Live collector: new rounds beyond the workbook: {len(beyond)} | newest: {last_id} (time {last_time})")
    else:
        print("Live collector: no new rounds beyond the workbook yet.")
    df = df[~df["period_id"].isin(live["period_id"])]          # live data replaces workbook rows it covers
    live_rows = live.copy()
    live_rows["size"] = live_rows["number"].map(size_rule)
    live_rows["colour"] = live_rows["number"].map(COLOUR_RULE)
    live_rows["colour_original"] = live_rows["colour"]
    df = pd.concat([df, live_rows], ignore_index=True)
    print("Rows after adding live rounds:", len(df))
else:
    print("Live collector: no collector file found, using the workbook only.")

df["date"] = pd.to_datetime(df["period_id"].str[:8], format="%Y%m%d")
df["counter"] = df["period_id"].str[-5:].astype(int)
out_range = df[(df["counter"] < FIRST_COUNTER) | (df["counter"] > LAST_COUNTER)]
if len(out_range):
    print(out_range[["period_id"]].head(10).to_string())
    raise SystemExit(f"STOP: round counter must be between {FIRST_COUNTER} and {LAST_COUNTER}.")
share_00 = (df["period_id"].str[-2:] == "00").mean()
if share_00 > 0.05:
    print(f"WARNING: {share_00:.1%} of IDs end in 00 (normal is about 1%). "
          "Excel may have rounded some IDs. Please check.")

# 3. Duplicates: same ID twice is fine only if the number is the same
dup = df[df.duplicated("period_id", keep=False)]
if len(dup):
    conflict = dup.groupby("period_id")["number"].nunique()
    conflict = conflict[conflict > 1]
    if len(conflict):
        print(conflict.head(10))
        raise SystemExit("STOP: the same Period ID has different numbers. Check these rounds.")
    before = len(df)
    df = df.drop_duplicates("period_id", keep="first")
    print("Duplicate rows removed:", before - len(df))

# 4. Check Big/Small against the number (if the column exists)
df["size_rule"] = df["number"].map(size_rule)
if "size" in df.columns:
    given = df["size"].astype(str).str.strip().str.capitalize()
    bad_size = df[given != df["size_rule"]]
    print("Rows where Big/Small breaks the number rule:", len(bad_size))
    if len(bad_size):
        print(bad_size[["period_id", "number", "size"]].head(15).to_string())
        raise SystemExit("STOP: a number and its Big/Small label disagree. One of them was misread.")
df["size"] = df["size_rule"]

# 5. Colour comes from the number. Keep the original colour for comparison.
df["colour_rule"] = df["number"].map(COLOUR_RULE)
given_colour = df["colour"] if "colour" in df.columns else df["colour_rule"]
if "colour_original" in df.columns:
    df["colour_original"] = df["colour_original"].fillna(given_colour)
else:
    df["colour_original"] = given_colour
df["colour"] = df["colour_rule"]
df["colour_fixed"] = df["colour"].str.lower() != df["colour_original"].astype(str).str.lower().str.replace(",", "+", regex=False)
print("Colour values that differ from the rule (set from the number):", int(df["colour_fixed"].sum()))
if df["colour_fixed"].mean() > 0.05:
    print("WARNING: more than 5% of colours differ. The screenshots may need a re-check.")

# 6. Time order, and the time calculated from the Period ID
day_no = (df["date"] - df["date"].min()).dt.days
df["abs_index"] = day_no * ROUNDS_PER_DAY + (df["counter"] - FIRST_COUNTER)
df = df.sort_values("abs_index").reset_index(drop=True)
calc_time = df["date"] + pd.Timedelta(hours=5, minutes=30) + pd.to_timedelta((df["counter"] - 50000) * 30, unit="s")
if "timestamp" in df.columns:
    file_time = pd.to_datetime(df["timestamp"], errors="coerce")
    mismatch = (file_time.notna() & (file_time != calc_time)).sum()
    print("Rows where the file time differs from the Period ID time:", int(mismatch))
df["timestamp"] = calc_time.dt.strftime("%Y-%m-%d %H:%M:%S")

# 7. Gaps and blocks
jump = df["abs_index"].diff().fillna(1).astype(int)
df["block_id"] = (jump > 1).cumsum()
df["pos_in_block"] = df.groupby("block_id").cumcount()
print("Days:", df["period_id"].str[:8].nunique(), "| Gaps:", int((jump > 1).sum()),
      "| Missing rounds:", int((jump[jump > 1] - 1).sum()), "| Blocks:", df["block_id"].nunique())

blocks = (
    df.groupby("block_id")
    .agg(
        rounds=("period_id", "size"),
        first_period=("period_id", "first"),
        last_period=("period_id", "last"),
        first_time=("timestamp", "first"),
        last_time=("timestamp", "last"),
    )
    .reset_index()
)
sizes = blocks["rounds"]
print(f"Block sizes: smallest {sizes.min()}, median {int(sizes.median())}, largest {sizes.max()}, "
      f"blocks under 20 rounds: {(sizes < 20).sum()}")
if len(blocks) <= 15:
    print()
    print(blocks.to_string(index=False))

# 8. Save
keep = ["period_id", "timestamp", "number", "size", "colour", "colour_original", "colour_fixed",
        "counter", "abs_index", "block_id", "pos_in_block"]
OUT_CLEAN.parent.mkdir(parents=True, exist_ok=True)
df[keep].to_csv(OUT_CLEAN, index=False)
blocks.to_csv(OUT_BLOCKS, index=False)
print()
print("Total clean rounds:", len(df))
print("Saved:", OUT_CLEAN)
print("Saved:", OUT_BLOCKS)
