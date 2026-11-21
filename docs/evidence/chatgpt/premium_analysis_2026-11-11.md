> ARCHIVED REPORT — the findings below were reported in the earlier 88,865-round analysis. “Verified” and “untouched” describe that original report, not a new validation in this release. Current v19 has 88,916 rounds. See [reconciliation](../../DATA_PROVENANCE.md) and [limitations](../../RESULTS_AND_LIMITATIONS.md).

# WinGo premium-generation analysis

**Data source:** User-uploaded `Colour_Prediction_Dataset_v19.xlsx`, `Raw_Data` worksheet.  
**Analysis date:** 2026-11-11.  
**Question:** Can the generation method or next five-digit `premium` / winning digit be inferred from the historical records?

## Verified data inventory

- Rows read from `Raw_Data`: **88,865** (unique period IDs).
- Distinct five-digit text premiums: **88,816 records**, comprising **56,595 different five-digit values**.
- Single-digit premium entries: **49**, excluded from analyses requiring a full five-digit value.
- For all **88,816** full premiums, `int(premium) % 10 == winning_number`; **0 exceptions**.
- Period covered: **2026-10-12 00:00:00 to 2026-11-11 20:57:30** in the worksheet's timestamps (time zone of these fields not independently verified).
- Timestamp increment: **30 seconds for 88,863 adjacent pairs**; one gap of **1,560 seconds**, corresponding to **51 missing 30-second periods**.
- The 49 single-digit premiums fall on **2026-11-10**, between **22:20 and 23:09:30** in recorded timestamps, with the above missing-round gap.

## What can be established about the premium

1. Every full premium is a string of **exactly five decimal digits**, with a nonzero first digit. The observed numerical range is **10,001–99,999**.
2. The winning result equals its last decimal digit. This is an **output-conversion relationship**, not evidence of the upstream generation algorithm.
3. The sample looks broadly consistent with independent draws from the **90,000 integers from 10,000 through 99,999**. This is one statistically compatible model, **not identification** of an implementation.

### Marginal digit tests

Pearson chi-square goodness-of-fit tests against uniform digits (first position uniform 1–9, remaining positions uniform 0–9):

| Premium digit position | p-value |
|---|---:|
| 1st | 0.1646 |
| 2nd | 0.0136 |
| 3rd | 0.7033 |
| 4th | 0.3790 |
| 5th | 0.0454 |

The full 0–9 winning-digit distribution has p = **0.0489** under a uniformity chi-square test. These are **nominal p-values without adjustment for the many analyses performed**; they do not establish an exploitable bias or an identifiable RNG.

The strongest cross-position signal (position 2 against position 3) had p = **0.00481** in the full sample, with tiny Cramér's V **0.0121**, but **did not independently replicate**: first half p = **0.155**, second half p = **0.422**. That argues against interpreting the pooled result as a reliable predictive rule.

No individual relationship between any of the first four positions and the final winning digit was statistically convincing (p-values 0.901, 0.661, 0.429, 0.461).

### Duplicate/collision test

- Number of different five-digit values observed: **56,595**.
- Expected different values under independent uniform sampling from 90,000 possibilities: **56,452.6**.
- 450 simulated independent, uniform samples of the same size gave mean **56,453.3** and standard deviation **89.8**; observed count is **1.58 standard deviations above** the simulation mean, not an unusual discrepancy.
- Observed equal-value collision pairs: **43,496**, compared with uniform expectation **43,823.3**.

### Temporal and period relationships

- Lag-1 correlation between consecutive winning digits: approximately **-0.0036**.
- The 10×10 transition contingency test between one winning digit and the next had p = **0.216**.
- Tests of winning-digit relationships with period ID residues modulo 2, 3, 5, 7, 10, 20, 30, 60, and 100 did not produce convincing associations.
- In a trial of a simple *directly exposed* linear congruential recurrence on the 5-digit premium, converted to the range 0–89,999, a candidate fitted to an initial triple failed on the following **998 unconstrained transitions**. This rejects that particular simple recurrence model; it does **not** rule out more complex PRNGs with hidden state, truncation, or other mappings.

## Chronological prediction experiment

The test used **88,806 usable samples** requiring a complete five-digit target, five available preceding rounds, and no gap crossing.

- Discovery/training: **62,164** oldest samples.
- Validation: **8,880** next samples.
- Untouched chronological test: **17,762** newest samples.
- Features included past winning digits, previous 5-digit premiums, time of day, and known period-ID components. No future data or current-round premium was used for prediction.

| Method | Validation accuracy | Final test accuracy | 95% Wilson interval for final test |
|---|---:|---:|---|
| Most common training digit | 10.25% | **9.97%** | 9.54%–10.42% |
| Repeat previous digit | 9.67% | **9.82%** | 9.40%–10.27% |
| 1-step transition model | 10.36% | **10.40%** | 9.96%–10.86% |
| 2-step transition model | 10.34% | **10.01%** | 9.58%–10.46% |
| 3-step transition model | 10.65% | **9.84%** | 9.41%–10.29% |
| Random forest, last-5 and historical premiums | 9.90% | **10.08%** | 9.65%–10.53% |
| Logistic model, history/time/period | 10.51% | **10.17%** | 9.73%–10.62% |

The 1-step model's nominal one-sided test against an exact 10% null was p ≈ **0.040**, but its **95% two-sided interval includes 10%**; many candidate methods were screened; and its **paired comparison against the observed training-frequency baseline** was not significant (McNemar exact p ≈ **0.19**). Therefore a reliable predictive advantage **was not established**.

Simple MD5, SHA-1, and SHA-256 hashes of the public period ID, with several ordinary output-to-digit mappings, gave final-test accuracies roughly **9.61%–10.35%**. None establishes the original result algorithm; unkeyed hash mappings only tested specific candidate formulas, not all possibilities.

## Overall conclusion

**No verified algorithm for generating the premium was recovered. No demonstrated strategy predicts the unseen winning digit materially better than chance from the tested historical features.** The premium's observed distribution is compatible with uniform five-digit sampling in 10,000–99,999, and the displayed winner is consistently its last digit.

The data **cannot distinguish** browser `Math.random()`, a server PRNG, a secure CSPRNG, a cryptographic hash of secret inputs, a generated/constructed `premium` value, or other mechanisms solely from these checks. An independent source-code disclosure, documented provably-fair method with seed commitments, or authorized internal generator records would be necessary to identify the actual implementation.

**Additional caution:** The full five-digit `premium` might be constructed by a downstream result provider rather than originally generated by the central RNG. The equal last-digit relationship alone does not decide that provenance question.
