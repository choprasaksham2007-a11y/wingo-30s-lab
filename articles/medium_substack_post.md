# I audited 88,916 WinGo rounds. Here is what the prediction experiments actually showed.

*Why preserving failed models—and correcting my own audit claims—made the research stronger.*

By Saksham Chopra

I began with a straightforward question: if a game produces a number every 30 seconds, could enough historical data reveal the next result?

I collected and organized WinGo 30S records, examined streaks and clock patterns, worked through statistical diagnostics, and trained models. The work eventually covered 88,916 recorded rounds across 31 calendar dates. I used VS Code, Google Antigravity and ChatGPT as development and research assistants.

The result is a public research archive—not a bot that guarantees the next number.

The evaluated trained models did not establish a reliable forecasting advantage. That conclusion matters. So does being precise about what it does not prove.

## First, define what is being predicted

WinGo displays one winning digit from 0 to 9. That digit determines the other categories:

- Small is 0–4; Big is 5–9.
- Even digits are Red and odd digits are Green.
- Zero is also Violet, and five is also Violet.

For independent uniform digits, guessing the exact number has a 10% reference rate. Big/Small and primary Red/Green each have a 50% reference rate. Violet appears on 20% of digits; it overlaps the primary colours.

These distinctions prevent a misleading headline. A model that always predicts “not Violet” would achieve 80% under that reference distribution without learning anything about the next draw. Accuracy needs a clearly defined target and an appropriate baseline.

## The five-digit premium was not a recovered seed

The archive includes a five-digit field called `premium`. In all 88,916 current records, its last digit equals the winning number.

That is a useful consistency check. It is not evidence that the field is the generator's secret seed.

If the premium is released with a completed result, a model using that same round's premium is reading the answer. Historical premiums can be candidate inputs for a future round; the current target premium cannot be treated as information available beforehand.

Even the direction of construction remains a separate question. A provider might generate a premium and take its last digit, or construct a premium after choosing the result. The last-digit relationship alone cannot decide between those possibilities.

## More features did not produce a breakthrough

One saved VS Code experiment used 1,000 candidate features, 4,096 training examples, 1,500 selection examples and 5,000 later test examples. Its saved scores were:

- Exact digit: **8.76%**.
- Big/Small: **48.26%**.
- Primary Red/Green: **49.52%**.
- Four exact colour sets: **39.02%**.

Calling these inputs “1,000 patterns” would overstate what was learned. They were features to test, not 1,000 established predictive rules.

An earlier ChatGPT-assisted analysis reported a one-step transition model at 10.40% on a different 17,762-example digit test. Its 95% interval was 9.96–10.86%, and its paired comparison with the observed baseline did not establish an advantage. Other reported models were also near the 10% reference rate.

There was a positive-looking result worth preserving: a recent-100 Big/Small frequency baseline scored **51.68%** in the VS Code backtest. I am not hiding it. But that historical data had already been explored, and many candidate approaches had been considered. It is an observation requiring a fresh, precommitted test—not a guarantee about future rounds. No new experiment was run for this publication.

## A clean dataset still needs version history

One earlier report described 88,865 records, while my current archive contained 88,916. Rather than choose the larger number and ignore the discrepancy, the publication preparation reconciled them.

The earlier date-and-clock comparison matrix reconstructs 88,865 observations. Matching its timestamps against the current archive shows **51 added rounds and 49 completed premium fields**. The winning digits already present did not change.

That explains the count difference. It also explains why results from the earlier snapshot must retain their original sample sizes. Two overlapping exports do not become independent evidence because they have different filenames.

## The hardest correction was to the audit language

My research included a report organized into 110 dimensions. It was tempting to describe that as 110 cryptographic tests passed.

The source code did not justify that description. Some verdicts were constants. Some calculations were heuristics rather than the named standard tests. Some binary tests encoded five-digit integers into four bytes, introducing predictable leading zeros. A few narrative conclusions contradicted the saved outputs.

The public archive records those problems in a claim ledger. It retains the code and historical outputs rather than quietly changing the method and pretending the old results came from the revised version.

Passing statistical checks is not proof of cryptographic security. NIST's guidance makes that distinction explicitly: statistical testing cannot replace cryptanalysis. [NIST SP 800-22](https://csrc.nist.gov/pubs/sp/800/22/r1/upd1/final)

## What about the generator implementation?

My separate GitHub-based investigation led me to identify .NET's `System.Security.Cryptography.RandomNumberGenerator`, backed by an operating-system CSPRNG, as the working implementation finding.

The publication attributes that finding to my research. It does not claim that the output statistics or CDN headers independently prove the implementation. The supplied archive does not include an authenticated source-to-production link establishing the deployed generator, exact operating system or reseeding policy.

That separation is deliberate. A framework-style error response can be a clue. A Cloudflare edge location is not the generator's location. A storage ETag, a JWT signature and an RNG seed are different things.

## Why a long streak does not automatically reveal the next result

If draws are independent and uniform, conditioning on the history leaves each next digit at 10%, and each next Big/Small category at 50%. A model that uses the history cannot gain an advantage under those assumptions, regardless of its size.

The phrase “under those assumptions” matters. No finite dataset proves that every future round is independent, that the operator is fair, or that every possible attack fails. The experiments support a narrower conclusion: these evaluated models did not demonstrate a reliable forecasting edge, and this investigation did not recover a seed.

## What I am publishing

The repository includes the whitepaper, a small data sample, full dataset release files, checksums, snapshot reconciliation, saved evaluation evidence, an inventory of the existing models, archived scripts, and offline integrity checks. Original model weights remain preserved locally; nothing was retrained for the publication.

The most useful outcome was learning to distinguish a pattern worth testing from a pattern that has survived testing—and to distinguish a confident report from evidence that actually supports its claims.

**Read the research and reproduction instructions: https://github.com/choprasaksham2007-a11y/wingo-30s-lab**

Research and curation: Saksham Chopra. Development, analysis and editorial assistance: Google Antigravity and ChatGPT. The archive identifies which results were checked locally, retained from earlier reports, hypothesized, or left unknown.
