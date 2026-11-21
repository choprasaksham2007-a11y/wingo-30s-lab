> Historical Antigravity report. Numerical and verification claims below are attributed to its authoring session. Consult the [claim ledger](../../docs/CLAIM_LEDGER.md) for the publication assessment.

# ML_Ready & Excel Structure Audit Report

**Auditor:** Agent 3 (ML_Ready & Excel Structure Auditor)  
**Date:** October 24, 2026  
**Audit Scope:** 
1. `Colour_Prediction_Dataset_v3.xlsx` (2,135 verified rounds — complete 3-session dataset)
2. `Colour_Prediction_Dataset_corrected.xlsx` (1,260 verified rounds — initial corrected dataset)

---

## Executive Summary

A comprehensive, two-pass programmatic audit was performed on both workbooks. Every single row in `ML_Ready` (2,095 rows in `v3`, 1,230 rows in `corrected`) and `Raw_Data` (2,135 rows in `v3`, 1,260 rows in `corrected`) was inspected at the cell, formula, and XML data-type level.

| Audit Area | `Colour_Prediction_Dataset_v3.xlsx` | `Colour_Prediction_Dataset_corrected.xlsx` | Status |
| :--- | :--- | :--- | :--- |
| **Pass 1: ML_Ready Lag & Target Integrity** | 2,095 / 2,095 rows 100% verified | 1,230 / 1,230 rows 100% verified | **PASS** |
| **Pass 1: Zero Gap-Crossing Enforcement** | 0 gap crossings across all 7 gaps | 0 gap crossings across all 5 gaps | **PASS** |
| **Pass 1: Mathematical Row Count Formula** | $2135 - (5 \times 8) = 2,095$ (Exact) | $1260 - (5 \times 6) = 1,230$ (Exact) | **PASS** |
| **Pass 2: 17-Digit Period ID Data Types** | 100% `data_type == 's'`, `@` format | 100% `data_type == 's'` (MR format: `General`) | **PASS** |
| **Pass 2: Number Distribution Accuracy** | 100% match across 0–9 | 100% match across 0–9 | **PASS** |
| **Pass 2: Colour Distribution Accuracy** | 100% match across all 4 colours | 100% match across all 4 colours | **PASS** |
| **Pass 2: Size Distribution Table** | *Omitted from Summary sheet* | *Omitted from Summary sheet* | **NOTE** |
| **Pass 2: Summary KPI Table Accuracy** | 100% match to Raw_Data counts | 100% match to Raw_Data counts | **PASS** |
| **Pass 2: Audit Sheet Honesty & Completeness** | Fully documented | Fully documented (incl. 26-row occlusion log) | **PASS** |

---

## Pass 1: ML_Ready Integrity & Lag Validation

### 1. Mathematical Row Count Formula Validation

The theoretical row count for supervised machine learning samples with a lag window of $k=5$ without crossing gaps is:
$$\text{ML Rows} = \sum_{i=1}^{N_{\text{blocks}}} \max(0, L_i - k) = \text{Total Rounds} - (k \times N_{\text{blocks}})$$

#### A. `Colour_Prediction_Dataset_v3.xlsx`
- **Total Rounds in Raw_Data:** 2,135
- **Documented Gaps in `Missing_Rounds`:** 7
- **Unbroken Blocks ($N_{\text{blocks}}$):** 8
- **Block Lengths ($L_i$):**
  - Block 1: 636 rounds $\rightarrow 636 - 5 = 631$ samples
  - Block 2: 88 rounds $\rightarrow 88 - 5 = 83$ samples
  - Block 3: 130 rounds $\rightarrow 130 - 5 = 125$ samples
  - Block 4: 148 rounds $\rightarrow 148 - 5 = 143$ samples
  - Block 5: 50 rounds $\rightarrow 50 - 5 = 45$ samples
  - Block 6: 588 rounds $\rightarrow 588 - 5 = 583$ samples
  - Block 7: 486 rounds $\rightarrow 486 - 5 = 481$ samples
  - Block 8: 9 rounds $\rightarrow 9 - 5 = 4$ samples
- **Expected Samples:** $2,135 - (5 \times 8) = 2,095$
- **Actual Samples in `ML_Ready`:** **2,095** (Exact match)

#### B. `Colour_Prediction_Dataset_corrected.xlsx`
- **Total Rounds in Raw_Data:** 1,260
- **Documented Gaps in `Missing_Rounds`:** 5
- **Unbroken Blocks ($N_{\text{blocks}}$):** 6
- **Block Lengths ($L_i$):**
  - Block 1: 636 rounds $\rightarrow 631$ samples
  - Block 2: 88 rounds $\rightarrow 83$ samples
  - Block 3: 130 rounds $\rightarrow 125$ samples
  - Block 4: 148 rounds $\rightarrow 143$ samples
  - Block 5: 50 rounds $\rightarrow 45$ samples
  - Block 6: 208 rounds $\rightarrow 203$ samples
- **Expected Samples:** $1,260 - (5 \times 6) = 1,230$
- **Actual Samples in `ML_Ready`:** **1,230** (Exact match)

---

### 2. Row-by-Row Lag Feature Alignment

Every single row of `ML_Ready` was verified against `Raw_Data`:
- **Lag Direction Semantics:**
  - `prev_1` = Round $t - 1$ (immediate prior round)
  - `prev_2` = Round $t - 2$
  - `prev_3` = Round $t - 3$
  - `prev_4` = Round $t - 4$
  - `prev_5` = Round $t - 5$ (5 rounds prior)
- **Target Fields:**
  - `target_number`, `target_colour`, `target_size`, `target_timestamp` match the target round in `Raw_Data` with **0 mismatches (100% agreement)**.
- **Lag Fields:**
  - `prev_{1..5}_number`, `prev_{1..5}_colour`, `prev_{1..5}_size` match the exact historical rounds in `Raw_Data` with **0 mismatches (100% agreement)**.
- **Deterministic Game Rule Adherence:**
  - Tested all $2,095 \times 6 = 12,570$ number-colour-size tuples across targets and lags: **0 rule violations**.

---

### 3. Critical Zero Gap-Crossing Verification

We audited every gap boundary to confirm that no 5-round window straddles a gap interval.

For each gap $(ID_{\text{before}} \rightarrow ID_{\text{after}})$, the candidate targets in the subsequent block at offsets $+0, +1, +2, +3, +4$ must NOT appear in `ML_Ready`, and offset $+5$ must be the first valid target.

#### `Colour_Prediction_Dataset_v3.xlsx` Boundary Test Results:
- **Gap 1 (`...52217` $\rightarrow$ `...52219`, 1 round missing):**
  - Offsets $+0$ through $+4$ (`...52219` to `...52223`): Excluded (In ML_Ready: `False`)
  - Offset $+5$ (`...52224`): Included (In ML_Ready: `True`)
- **Gap 2 (`...52306` $\rightarrow$ `...52308`, 1 round missing):**
  - Offsets $+0$ through $+4$ (`...52308` to `...52312`): Excluded (In ML_Ready: `False`)
  - Offset $+5$ (`...52313`): Included (In ML_Ready: `True`)
- **Gap 3 (`...52437` $\rightarrow$ `...52823`, 385 rounds missing):**
  - Offsets $+0$ through $+4$ (`...52823` to `...52827`): Excluded (In ML_Ready: `False`)
  - Offset $+5$ (`...52828`): Included (In ML_Ready: `True`)
- **Gap 4 (`...50090` $\rightarrow$ `...50101`, 10 rounds missing):**
  - Offsets $+0$ through $+4$ (`...50101` to `...50105`): Excluded (In ML_Ready: `False`)
  - Offset $+5$ (`...50106`): Included (In ML_Ready: `True`)
- **Gap 5 (`...50150` $\rightarrow$ `...50231`, 80 rounds missing):**
  - Offsets $+0$ through $+4$ (`...50231` to `...50235`): Excluded (In ML_Ready: `False`)
  - Offset $+5$ (`...50236`): Included (In ML_Ready: `True`)
- **Gap 6 (`...50818` $\rightarrow$ `...51773`, 954 rounds missing):**
  - Offsets $+0$ through $+4$ (`...51773` to `...51777`): Excluded (In ML_Ready: `False`)
  - Offset $+5$ (`...51778`): Included (In ML_Ready: `True`)
- **Gap 7 (`...52258` $\rightarrow$ `...52260`, 1 round missing):**
  - Offsets $+0$ through $+4$ (`...52260` to `...52264`): Excluded (In ML_Ready: `False`)
  - Offset $+5$ (`...52265`): Included (In ML_Ready: `True`)

**Result:** **0 gap crossings detected across the entire dataset.**

---

## Pass 2: Excel Formatting, Data Types & Summary Consistency

### 1. Period ID Data Type & Text Preservation Audit

All 17-digit Period IDs were inspected across all sheets for precision loss, float conversion, scientific notation, and format masks:

| Sheet | Column Name | Total Inspected | `data_type == 's'` | `number_format` | Exact 17 Digits | Scientific Notation |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **`v3`: Raw_Data** | `Period ID` | 2,135 | 2,135 (100%) | `@` (100%) | 2,135 (100%) | 0 (0%) |
| **`v3`: ML_Ready** | `Target Period ID` | 2,095 | 2,095 (100%) | `@` (100%) | 2,095 (100%) | 0 (0%) |
| **`v3`: Missing_Rounds** | `Before Period ID` | 7 | 7 (100%) | `@` (100%) | 7 (100%) | 0 (0%) |
| **`v3`: Missing_Rounds** | `After Period ID` | 7 | 7 (100%) | `@` (100%) | 7 (100%) | 0 (0%) |
| **`v3`: User_Provided** | `User-provided Period ID` | 4 | 4 (100%) | `General` | 4 (100%) | 0 (0%) |
| **`corrected`: Raw_Data** | `Period ID` | 1,260 | 1,260 (100%) | `@` (100%) | 1,260 (100%) | 0 (0%) |
| **`corrected`: ML_Ready** | `Target Period ID` | 1,230 | 1,230 (100%) | `@` (100%) | 1,230 (100%) | 0 (0%) |
| **`corrected`: Missing_Rounds**| `prior_period_id` | 5 | 5 (100%) | `General` | 5 (100%) | 0 (0%) |
| **`corrected`: Missing_Rounds**| `subsequent_period_id` | 5 | 5 (100%) | `General` | 5 (100%) | 0 (0%) |

> [!NOTE]
> In `v3`, 100% of Period IDs across `Raw_Data`, `ML_Ready`, and `Missing_Rounds` strictly use both `data_type == 's'` and format `@`. In `User_Provided` (and `Missing_Rounds` of `corrected`), the cells are stored as text strings (`s`) with 17 digits, but the format mask is `General`. No precision loss or numeric truncation occurred.

---

### 2. Summary Sheet vs True Raw_Data Counts

#### A. Number Distribution (0–9)

| Number | `v3` Raw True | `v3` Summary | `v3` Match | `corrected` Raw True | `corrected` Summary | `corrected` Match |
| :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **0** | 186 | 186 | Exact | 124 | 124 | Exact |
| **1** | 362 | 362 | Exact | 138 | 138 | Exact |
| **2** | 154 | 154 | Exact | 119 | 119 | Exact |
| **3** | 180 | 180 | Exact | 133 | 133 | Exact |
| **4** | 268 | 268 | Exact | 119 | 119 | Exact |
| **5** | 213 | 213 | Exact | 135 | 135 | Exact |
| **6** | 193 | 193 | Exact | 134 | 134 | Exact |
| **7** | 230 | 230 | Exact | 123 | 123 | Exact |
| **8** | 207 | 207 | Exact | 128 | 128 | Exact |
| **9** | 142 | 142 | Exact | 107 | 107 | Exact |
| **Total** | **2,135** | **2,135** | **100% Match** | **1,260** | **1,260** | **100% Match** |

#### B. Colour Distribution

| Colour | `v3` Raw True | `v3` Summary | `v3` Match | `corrected` Raw True | `corrected` Summary | `corrected` Match |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **Green** | 914 | 914 | Exact | 501 | 501 | Exact |
| **Red** | 822 | 822 | Exact | 500 | 500 | Exact |
| **Green+Violet** | 213 | 213 | Exact | 135 | 135 | Exact |
| **Red+Violet** | 186 | 186 | Exact | 124 | 124 | Exact |
| **Total** | **2,135** | **2,135** | **100% Match** | **1,260** | **1,260** | **100% Match** |

#### C. Size Distribution Audit Finding

> [!IMPORTANT]
> **Audit Finding regarding Size Distribution:**  
> The Summary sheets in **both** `Colour_Prediction_Dataset_v3.xlsx` and `Colour_Prediction_Dataset_corrected.xlsx` do **not** contain a Size distribution table. Only "Distribution by Number (0-9)" and "Distribution by Colour" are present.  
> 
> **True Raw_Data Size Distribution:**
> - In `Colour_Prediction_Dataset_v3.xlsx`:  
>   - **Small (0–4):** 1,150 rounds (53.86%)  
>   - **Big (5–9):** 985 rounds (46.14%)  
>   - **Total:** 2,135 rounds  
> - In `Colour_Prediction_Dataset_corrected.xlsx`:  
>   - **Small (0–4):** 633 rounds (50.24%)  
>   - **Big (5–9):** 627 rounds (49.76%)  
>   - **Total:** 1,260 rounds  

#### D. KPI Table Verification

- **Total Verified Unique Rounds:** 2,135 in `v3` (Summary: 2,135); 1,260 in `corrected` (Summary: 1,260). $\rightarrow$ **100% Match**
- **Total Eligible ML Training Samples:** 2,095 in `v3` (Summary: 2,095); 1,230 in `corrected` (Summary: 1,230). $\rightarrow$ **100% Match**
- **User-Supplied Outcomes:** 4 documented in `User_Provided` sheet (Rounds 51954–51957). Summary lists 4. $\rightarrow$ **100% Match**
- **Batch Breakdown (`v3`):** Batch 1 (1,260) + Batch 2 (380) + Batch 3 (495) = 2,135. $\rightarrow$ **100% Match**
- **Documented Gaps:** 7 in `v3` (Summary: 7); 5 in `corrected` (Summary: 5). $\rightarrow$ **100% Match**

---

### 3. Audit Sheet & Documentation Review

- **Honesty & Transparency:** Both workbooks honestly document all checks, including the calibration anchor (`52278 = 2026-10-24 00:29:00 AM` and `50494 = 2026-10-23 09:37:00 AM`), the exact 30-second interval continuity, 0 rule violations, zero gap crossings, and the 4 user-supplied records.
- **Occlusion Changelog in `corrected`:** The Audit sheet in `Colour_Prediction_Dataset_corrected.xlsx` documents the 26 floating icon occlusion corrections with pixel-level RGB counts and screenshot confirmation evidence.
- **Unrecorded Gaps Audit:** A chronological scan across all consecutive rows in `Raw_Data` confirmed that **zero unrecorded gaps exist**. 100% of timestamp/period jumps are accounted for in `Missing_Rounds`.

---

## Final Certification

The dataset files have been thoroughly audited and validated.
1. `Colour_Prediction_Dataset_v3.xlsx` represents the complete, fully consolidated 2,135-round dataset.
2. `ML_Ready` in both workbooks strictly adheres to chronological 5-lag window requirements with zero gap-crossing and zero data leakage.
3. 100% of Period IDs are preserved as 17-digit text without numeric truncation or scientific notation.
4. Summary sheet counts match `Raw_Data` true counts with 100% accuracy.
