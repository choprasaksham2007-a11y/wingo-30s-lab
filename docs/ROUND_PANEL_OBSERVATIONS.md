# Did the top-ranked digit win?

Research by **Saksham Chopra**. Three saved snapshots show the ten digits ranked on the game panel. Joining each snapshot to the completed result by its exact period ID puts a concrete question to the records. Where did the eventual winner appear on the panel?

| Period ID | Panel phase | Digit ranked first | Final premium | Winning digit | Winner’s displayed rank | Winner’s displayed percentage |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| `20261110100051085` | FinalBoost | 3 | 17858 | 8 | 3 | 16% |
| `20261110100051504` | Betting | 1 | 58066 | 6 | 9 | 5% |
| `20261112100051191` | Locked | 8 | 82842 | 2 | 5 | 9% |

The first-ranked digit missed all three rounds. In the Locked snapshot, digits 8 and 0 both displayed 17%, while the panel assigned them ranks 1 and 2. The table preserves the rank the panel supplied. Re-sorting rounded percentages could change the order of tied digits. The three captures were selected during the investigation. They are too few to estimate how well panel ranks predict future outcomes, and the meaning of the displayed percentage remains unverified.

## Reproduce the comparison

1. Read the [30 panel entries](evidence/panel_rankings.csv) with `period_id` as text. Each period has ten entries. The two November 10 snapshots come from the archived prediction investigation. The November 12 snapshot comes from the screenshot extraction investigation.
2. Look up the November 10 periods in the [v19 raw results](https://github.com/choprasaksham2007-a11y/wingo-30s-lab/releases/download/v1.0.0/colour_raw_data_v19.csv). For each period, take its `number` and look up that digit in the corresponding panel entries.
3. The November 12 round falls after the end of v19. Its result comes from a separate response preserved with the extraction session. That record gives period `20261112100051191`, premium `82842`, digit `2` and finalized state `1`. The published v19 round count stays at 88,916.

## Rechecking an earlier 11.46% digit score

An early screening report discussed in the prediction investigation selected the best of **30 candidate formulas**. It reported **252 correct calls out of 2,199** for a SHA-1 period-ID rule. Under an independent 10% exact-digit null, the probability of at least 252 hits for one prespecified rule is **0.01354**. Accounting for the 30 rules with a Bonferroni adjustment gives **0.40619**. The apparent advantage is weak once the selection is taken into account.

The match count and number of rules are historical reported figures. The probabilities above were recalculated from those inputs. In a separate ten-round check, the same reported mapping (the SHA-1 digest of the decimal period-ID text, interpreted as an integer, modulo ten) matched **0 of 10** v19 winning digits for periods `20261109100052240` through `20261109100052249`, inclusive. Under the same independent 10% null, a ten-round run with zero hits has probability **34.87%**. Neither result identifies the deployed generator.
