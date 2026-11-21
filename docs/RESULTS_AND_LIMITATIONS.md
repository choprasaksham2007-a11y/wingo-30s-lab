# Results and limitations

## What the evidence supports

The present v19 archive contains 88,916 unique, chronologically continuous rounds with complete premiums. Every recorded digit is the last digit of its premium; recorded categories agree with the digit rules. Earlier snapshot discrepancies are explained by additions and completed fields, not changed overlapping winning digits.

The evaluated trained models did not establish a reliable advantage. The saved VS Code model predicted Big/Small correctly 48.26% of the time, primary colour 49.52%, exact digit 8.76%, and exact four-way colour 39.02% on 5,000 later examples. The earlier ChatGPT report lists exact-digit scores near 10% on a different 17,762-example test. Antigravity's saved lag-five random forest lists 9.69% on its separate 10,000-example test. [VS Code report](evidence/vscode/thousand_report.json), [ChatGPT report](evidence/chatgpt/premium_analysis_2026-11-11.md), [Antigravity output](evidence/antigravity/audit_section4.json)

## Positive-looking results remain visible

The recent-100 Big/Small baseline scored 2,584/5,000 = 51.68%, with a saved nominal 95% interval of 50.29–53.06% and paired p≈0.0168 against a training-prior baseline. The original protocol says this historical data had been explored before. Repeated model/pattern screening, overlapping histories and any unrecorded selection choices limit a clean confirmatory interpretation. This result does not justify erasing the observation, asserting a persistent profitable edge, or guaranteeing a higher future accuracy. [Saved baseline verification](evidence/vscode/thousand_verification.json)

Likewise, the older one-step digit model's nominal one-sided p≈0.040 is not the same test as its two-sided interval or its paired comparison with an observed baseline. Multiplicity matters. A failure to establish a robust advantage is not a proof that the advantage is exactly zero.

## Why 110 labels are not 110 proofs

The original report grouped statistical diagnostics, implementation claims and cryptanalytic topics into 110 dimensions. Some source entries are constants or descriptive calculations rather than hypothesis tests; some binary tests use an inappropriate encoding/null; others contradict their own saved pass flags. This release provides the source/output evidence and [specific corrections](CLAIM_LEDGER.md), and does not claim that official NIST/TestU01/PractRand/Dieharder batteries were executed.

Large p-values do not prove randomness. Small nominal p-values after many tests do not automatically identify a predictive mechanism. Marginal Shannon entropy does not measure conditional entropy given the entire available history. Small linear correlation does not rule out nonlinear dependence. These distinctions are essential to the negative result's credibility.

## What is still unknown

- The independently authenticated deployed generator implementation and its state/seed.
- Whether the premium is directly generated upstream or constructed downstream to match a result.
- Exact backend ownership, physical origin, runtime version, operating-system generator and reseeding policy.
- Whether every future round follows the same distribution and implementation as the recorded interval.
- Whether any differently specified model would pass a preregistered prospective evaluation.
- Whether timing or access-control vulnerabilities exist; no publication-phase network investigation was performed.

The author's .NET OS-CSPRNG finding remains attributed as **REPORTED**. The collection and publication checks do not certify the platform's fairness, operational security or financial integrity.

## Reproducibility limits

The default workflow reproduces data/evidence integrity checks and reads existing outputs. It does not reproduce training or infer the authenticity of the upstream records from checksums. The ChatGPT analysis executable is absent from its ZIP. Existing VS Code serialized models remain local; metrics and prediction artifacts are published. Optional legacy replay is provided for transparency but retains known methodological defects. The existing data were extensively explored, so the saved chronological tests should not be rebranded as newly collected prospective trials.
