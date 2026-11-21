# WinGo 30S: historical predictability, evidence provenance, and the limits of output-only inference

**Saksham Chopra · Publication edition v1.0.0 · 2026-11-21**

## Abstract

This paper consolidates a completed investigation of WinGo 30S: a canonical archive of 88,916 rounds spanning 31 calendar dates, earlier prediction experiments, and recorded distribution-layer observations. Publication checks reconcile an earlier 88,865-record snapshot with the current data: 51 additional rounds and 49 completed premium fields, with unchanged winning digits on overlapping observations. Existing trained-model evaluations do not establish a reliable forecasting advantage. An exploratory recent-history baseline did score above 50% on one Big/Small backtest, which motivates caution about universal negative claims and retrospective selection. The author reports a separate implementation finding involving .NET's cryptographic random-number API; this paper distinguishes that attributed finding from what the supplied output data independently establishes. No new training or game-server investigation was performed for this edition.

## 1. Research questions and evidence boundaries

The original work asked whether past digits, premiums, period IDs, clock time, streaks and transition patterns predict future results; whether simple recurrence or hash formulas explain the observations; and what the visible API infrastructure reveals about provenance.

This publication asks a narrower question: which existing conclusions are supported, reproducible, or overstated? It preserves the work without treating every earlier narrative conclusion as established. Empirical model evaluation, data integrity, implementation identification and operational security are separate questions.

The study is observational. We do not have independently authenticated backend source, internal RNG state, seed commitments, operator logs or an exhaustive list of deployment configurations. “No recovered seed” describes the result of this investigation, not a theorem that all conceivable generators are unidentifiable.

## 2. Data and reconciliation

Current v19 has 88,916 distinct periods and complete five-digit premiums. All map to their recorded digit by reduction modulo ten. The workbook and raw CSV agree on periods, premiums and winning digits. The ML export has 88,911 records because five preceding observations are required. It contains target fields and five lagged number/colour/size triplets, not the one-hot and cyclical encodings described in one earlier blueprint.

The older comparison matrix has 2,880 rows indexed by clock slot and 31 date columns. Parsing its date cells recovers 88,865 observations: 88,816 complete premiums and 49 one-digit premiums. An exact timestamp join against current v19 finds 51 newly present observations, 49 changed premium fields, no removed timestamps and no winning-digit disagreements. The matrix does not retain period IDs; this join is explicitly timestamp-based. The underlying earlier report supplies the older period-ID counts. [Data provenance and machine-readable reconciliation](DATA_PROVENANCE.md)

Do not merge the older and newer files as independent samples. The snapshots substantially overlap. The old comparison matrix is useful evidence about changes, not an additional 88,865 independent draws.

## 3. Targets and leakage

Let the winning digit be \(D_t\in\{0,\ldots,9\}\). Define size \(B_t=1[D_t\ge5]\), primary colour \(C_t=D_t\bmod2\) with 0=Red and 1=Green, and Violet membership \(V_t=1[D_t\in\{0,5\}]\).

Under uniform digits, \(P(B_t=1)=P(C_t=1)=1/2\), and \(P(V_t=1)=1/5\). Red-only and Green-only each have probability 2/5; Red+Violet and Green+Violet each have probability 1/10. A binary Violet classifier always saying “no” achieves 80% under this reference model. That high accuracy is not evidence of predictive information.

Let \(P_t\) denote the published premium. The observed mapping \(D_t=P_t\bmod10\) is deterministic. Therefore the target premium, target size and target colour in a training export must not be used as features for forecasting \(D_t\). The target premium reveals the answer; target size and colour reveal parts of it. Only information available before the prediction deadline is eligible. A current period ID is not the same as the previous draw's resolved outcome, and a scheduled result is not a finalized result.

## 4. What conditional mathematics does—and does not—prove

### 4.1 The history-only reference accuracy

Assume digits are independent and uniform. Let \(H_t\) be the information available before draw \(t\), and let a possibly randomized predictor assign probabilities \(q_d(H_t)\) over ten guesses. Then

\[
P(\widehat D_t=D_t\mid H_t)
=\sum_{d=0}^{9}q_d(H_t)P(D_t=d\mid H_t)
=\frac1{10}\sum_{d=0}^{9}q_d(H_t)=\frac1{10}.
\]

The analogous Big/Small expression is 1/2. This includes predictors conditioned on five Big results, repeated sixes, or a long time history. The result follows **from the independence and uniformity assumptions**. Finite-data tests do not prove those assumptions hold for every future draw. A nonuniform but independent distribution instead gives an optimal constant-class accuracy of \(\max_d P(D_t=d)\).

### 4.2 Balanced modulo partition

There are 90,000 integers in 10,000 through 99,999 inclusive. Exactly 9,000 have each last digit. Thus if \(P_t\) is uniform on this set,

\[
P(P_t\bmod10=d)=9000/90000=0.1.
\]

This shows that modulo ten adds no imbalance to a **uniform draw on that domain**. It does not show that the upstream draw is uniform, that this is the actual generator domain, or that a premium is an RNG seed. Microsoft documents discard-and-retry sampling for its bounded `RandomNumberGenerator.GetInt32` API; that API description is not evidence that this deployment calls it. [Microsoft documentation](https://learn.microsoft.com/en-us/dotnet/api/system.security.cryptography.randomnumbergenerator.getint32)

### 4.3 Streaks are observations, not a debt owed by randomness

For independent fair Big/Small draws, any specified next block of \(k\) all-Big outcomes has probability \(2^{-k}\). An all-Big **or** all-Small block at a specified location has probability \(2^{1-k}\). A long recording offers many overlapping possible locations, so the existence of a long streak is much less surprising than its probability at one preselected position. These formulas do not imply the next draw must reverse or continue.

### 4.4 Computational unpredictability is conditional

A properly designed and implemented CSPRNG aims to prevent an efficient attacker without its secret state from predicting future output with useful advantage. That claim depends on the algorithm, seeding, state protection and deployment assumptions. A statistical test of published digits is not a test of state erasure, fork safety, key management, entropy health or forward/backtracking resistance. NIST explicitly separates statistical testing from cryptanalysis; a passing battery does not certify suitability for a cryptographic application. [NIST SP 800-22](https://csrc.nist.gov/pubs/sp/800/22/r1/upd1/final)

## 5. Existing empirical results

### 5.1 Earlier 88,865-round snapshot

The archived report describes 62,164 training examples, 8,880 validation examples and 17,762 test examples out of 88,806 usable samples. Features were historical digits/premiums and public clock/period components. Reported digit accuracies were 9.97% for the training-majority baseline, 9.82% for repeating the previous digit, 10.40% for a one-step transition model, 10.01% for a two-step model, 9.84% for a three-step model, 10.08% for a random forest and 10.17% for logistic regression.

The one-step model's 95% interval was 9.96–10.86%. Its reported nominal one-sided p-value against an exact 10% null was approximately 0.040, while the paired baseline comparison was approximately 0.19. These answer different questions and are not contradictory. Multiple candidate selection further limits interpretation. The report did not establish a robust advantage. Its training executable, fitted weights and row-level predictions are not present in the supplied ZIP, so this edition labels those model metrics **REPORTED**, not independently reproduced. [Archived report](evidence/chatgpt/premium_analysis_2026-11-11.md)

### 5.2 VS Code 1,000-feature experiment

The saved protocol uses 4,096 training rows, 1,500 selection rows and 5,000 later test rows. Model choices, mixture weights and calibration were selected before the final chronological segment. The protocol itself acknowledges that the underlying history had already been explored. It is an exploratory chronological backtest, not a fresh prospective trial. Earlier observed test outcomes may enter later histories; frozen model parameters must not be confused with a frozen input history.

| Target | Correct / 5,000 | Accuracy | Saved 95% interval | Training-prior baseline |
|---|---:|---:|---|---:|
| Exact digit | 438 | 8.76% | 8.01–9.58% | 10.66% |
| Big/Small | 2,413 | 48.26% | 46.88–49.65% | 49.20% |
| Primary Red/Green | 2,476 | 49.52% | 48.14–50.91% | 49.58% |
| Four exact colour sets | 1,951 | 39.02% | 37.68–40.38% | 38.92% |

These saved intervals are descriptive binomial intervals, not corrections for repeated exploration or dependence. The recent-100 Big/Small baseline's 51.68% result (95% interval 50.29–53.06%) must be disclosed. Its nominal paired p-value against the training-prior baseline was 0.0168. That result is a candidate for a future precommitted test, not grounds for either a guaranteed edge or a claim that every method achieved exactly chance.

### 5.3 Statistical audit archive

Saved diagnostics report digit chi-square 17.1254, nominal p=0.04679; empirical single-digit Shannon entropy 3.32178875 bits; lag-one correlation approximately -0.003575; and a lag-five random forest accuracy of 9.69%. The random forest used 20,000 training examples and the following 10,000 examples for evaluation. These outputs were preserved, not rerun.

The large audit report's verdict labels require correction. A number of entries are hardcoded assertions, not executed attacks. Four-byte encoding of five-digit integers necessarily introduces leading zero bits. Even encoding values 0–89,999 into 17 bits is not equivalent to uniform independent bits across all 131,072 bit patterns. Rejections against the wrong binary null do not establish a flawed lottery RNG. Likewise, uniform digit marginals and high marginal entropy do not establish conditional unpredictability. [Detailed claim ledger](CLAIM_LEDGER.md)

## 6. Infrastructure and generator attribution

The archived collector identifies Platsaas's historical results endpoint and AR Lottery's rolling history and scheduling endpoints. Saved November 15 response headers show HTTP 200, `server: cloudflare`, and OSS-style storage headers from both recorded draw hosts. That observation concerns the distribution layer. It does not reveal a private origin IP, prove ownership, or identify a generator location.

The author's separate GitHub investigation concluded that the implementation uses `.NET System.Security.Cryptography.RandomNumberGenerator` backed by an OS CSPRNG. This is retained as an attributed **REPORTED working finding**. The available statistical scripts and headers do not independently establish a deployed source-code link, exact runtime version, operating-system RNG algorithm, state size, reseeding schedule or memory-zeroization policy. Those details remain **UNKNOWN** in this publication. A .NET-style validation response is a framework clue, not implementation attestation. [Infrastructure map](INFRASTRUCTURE.md)

## 7. Reproducibility, preservation and limitations

The publication provides checksums, snapshot reconciliation, saved metrics and predictions for the VS Code experiment, archived statistical audit scripts and JSON outputs, guarded historical collection tools, and an offline validation wrapper. It does not imply that the old experiments were rerun or that every script is a standards-compliant statistical implementation.

All 12 saved VS Code model artifacts are preserved locally without deserialization. Three extraction `.pkl` files are serialized observations, not additional trained models. The initial public release excludes these binaries, original screenshots, account-specific captures, internal handoffs and downloaded third-party frontend code. Publication checks establish consistency of supplied files; they do not independently authenticate every recorded round against an operator ledger.

This archive supports a narrow conclusion: **the evaluated trained models did not demonstrate a reliable forecasting advantage, and the available outputs did not recover a seed or establish the deployed generator implementation independently.** It does not certify fairness, rule out all possible vulnerabilities, or promise that more training will reach any target accuracy.

## References and research credits

- [Forecasting protocol, metrics and row-level predictions](evidence/vscode/).
- [Statistical audit evidence](evidence/antigravity/) and [dataset provenance](DATA_PROVENANCE.md).
- [Earlier premium and prediction analysis](evidence/chatgpt/premium_analysis_2026-11-11.md).
- NIST, [SP 800-22 Rev. 1a](https://csrc.nist.gov/pubs/sp/800/22/r1/upd1/final), scope and limitations of statistical tests.
- Microsoft, [RandomNumberGenerator.GetInt32](https://learn.microsoft.com/en-us/dotnet/api/system.security.cryptography.randomnumbergenerator.getint32), bounded cryptographic random-number API semantics.
