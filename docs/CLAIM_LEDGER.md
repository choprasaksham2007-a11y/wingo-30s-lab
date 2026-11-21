# Claim ledger and editorial corrections

Status refers to the available evidence, not a platform certification. **VERIFIED**: checked locally for this release. **REPORTED**: retained historical result, not rerun. **HYPOTHESIS**: unestablished explanation. **UNKNOWN**: necessary evidence absent.

| Claim | Status | Evidence and publication treatment |
|---|---|---|
| Current raw data has 88,916 unique complete rounds | VERIFIED | Offline schema, ID, timestamp and mapping checks |
| Premium's last digit is the result | VERIFIED | All canonical records; does not establish causality or seed identity |
| Earlier snapshot had 88,865 observations and 49 incomplete premiums | VERIFIED for the archived matrix | Reconstructed date/clock cells; original period-ID assertion is REPORTED |
| 51 rounds added; 49 premiums completed; old digits unchanged | VERIFIED | Exact timestamp comparison with the preserved matrix |
| 1,000-feature model accuracy and historical protocol | REPORTED, with stored predictions available | Saved evaluation; no weights deserialized or model rerun |
| ChatGPT forest/transition/logistic results | REPORTED | Narrative report; corresponding training executable and weights absent from ZIP |
| .NET cryptographic RNG backed by OS CSPRNG | REPORTED working finding | Author's separate GitHub research; deployed implementation link not included |
| .NET 8, kernel ChaCha/AES variant, 256-bit seed, zeroization, fork safety | UNKNOWN | Not established by output correlations or HTTP fingerprints |
| Identical nameservers prove identical ownership/Cloudflare account | HYPOTHESIS, unsupported as proof | Shared infrastructure alone is insufficient |
| A 5-second lockout proves no early leakage | UNKNOWN | Constants in scripts do not measure access controls or timing leakage |
| `premium` is the raw RNG seed | UNKNOWN / terminology withdrawn | It is a published field; internal state relationship unestablished |
| A 110-test cryptographic certification was completed | Unsupported | Mix of calculations, heuristic thresholds, narrative topics and constants |
| No model could ever beat chance | Unsupported | A finite experiment cannot establish this universal statement |

## Specific defects preserved in the archived scripts

The legacy source is intentionally preserved with path/launch guards, rather than silently rewriting historical methods and presenting the old outputs as results of new methods.

1. **Section 2, entries 26–28:** five-digit integers are encoded in four bytes. Leading zero bits violate the fair-bit null. Saved p-values are zero with `pass: false`, contradicting the master report's blanket pass wording.
2. **Section 2, entry 30:** p=0.0467877 passes the script's 0.01 threshold, but is nominally significant at 0.05. Neither “confirmed uniform” nor an exploitable edge follows; report the threshold and multiplicity.
3. **Section 2, entry 33:** the saved coupon-collector heuristic is `false`, while the later narrative says exact convergence. Thresholds differ across versions; do not count them as independent confirmation.
4. **Section 2, entries 41–43:** unsigned byte arithmetic in `2 * bitstream - 1` can wrap zero to 255, invalidating the intended ±1 walk. Saved walk verdicts must not be interpreted as a standard random-walk test.
5. **Section 2, entry 49:** mapping digits by `% 6 + 1` does not produce fair dice. Comparing the simulated game with the fair-dice craps benchmark uses the wrong null.
6. **Section 2, entry 50:** parking-lot density is a constant. Other entries such as longest runs, gap summaries and poker summaries include unconditional pass flags.
7. **Section 3:** `premium - 10000` lies in 0–89,999, a proper subset of 17-bit words. Fair independent-bit assumptions cannot simply be applied. Hamming/bit-slice/rank verdicts are not a security certification.
8. **Sections 3/4:** regression on consecutive premiums is not lattice reduction; a commented discussion of MT19937 is not an SMT inversion; constants for algebraic degree, cube attacks, state-space bounds and prediction resistance are not attacks that ran.
9. **Section 4, entry 70:** correlation of premium parity and result parity follows directly from modulo ten, and is not a strict-avalanche test of an internal generator.
10. **Section 4, entry 73:** counting output 10-grams is not Floyd's cycle-finding algorithm on generator state. `cycle_detected: false` is assigned directly. A lag-1,000 correlation does not test forward secrecy.
11. **Section 5/6:** lockout, commitment availability, reset interpretation and cross-instance pass flags include constants. Ten unaligned cross-feed digits cannot establish a shared or separate generator.
12. **Twenty-vector script:** colour keys are lower-case while canonical labels are title-case; the “45/45/10” allocation does not describe actual overlapping colour membership. Correct probabilities are in the README.
13. **Compression:** the original script stores one digit per byte, not at the entropy-optimal bit width. A 48.37% size ratio reflects substantial encoding redundancy; it is not proof of maximal incompressibility.
14. **Test names:** these local heuristics are not executions of the official NIST STS, TestU01, PractRand, Dieharder or ENT binaries. No comprehensive certification by those suites is claimed.

No new experiments were launched to replace these results. Reproduction of a flawed calculation is useful provenance, not validation of its scientific interpretation.
