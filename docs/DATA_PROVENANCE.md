# Data provenance and version reconciliation

## Canonical publication snapshot

The release uses the v19 CSV exports from the author's Antigravity research directory and the byte-identical workbook copies in that directory and Downloads. Original files were preserved. The author's VS Code collector archive also has 88,916 rows; it is a richer collection schema and is not appended to v19.

| Property | Value / scope |
|---|---|
| Raw rows / unique periods | 88,916 / 88,916 |
| Five-digit premiums | 88,916 |
| Duplicate periods / missing periods | 0 / 0 across the recorded interval |
| Complete-premium modulo-ten matches | 88,916 |
| First / last period | `20261011100052221` / `20261111100051856` |
| First / last worksheet timestamp | `2026-10-12 00:00:00` / `2026-11-11 20:57:30` |
| Timestamp timezone | Not independently established; do not silently relabel as UTC or IST |
| Raw CSV columns | 9 |
| ML rows / columns | 88,911 / 23 |
| Workbook sheets | Raw_Data, ML_Ready, Missing_Rounds, Summary, Read_Me, Audit, Change_Log |
| Workbook bytes | 13,140,942 |

The workbook has 88,916 data rows in `Raw_Data`, 88,911 in `ML_Ready`, and an empty `Missing_Rounds` sheet apart from its header. Publication preparation scanned every worksheet cell for formulas and credential/private-path patterns; the initial scan found no matches. File integrity is not independent authentication of the underlying game records.

## Earlier snapshot reconstructed from the supplied ZIP

The three downloaded evidence ZIP copies are byte-identical. One was extracted into a private preparation directory after hashing; all seven entries in its supplied checksum manifest matched. The ZIP also contains the manifest itself. Internal research handoffs remain private; the earlier public-style analysis report is archived with a status banner.

`WinGo_same_time_every_day.csv` is a derived pivot, not a second independent raw dataset. Its 2,880 clock-slot rows and 31 date columns reconstruct **88,865 observations**: **88,816 five-digit premiums plus 49 one-digit premiums**.

The timestamp join with current v19 establishes:

- 51 timestamps now have records where the older matrix had no observation.
- 49 overlapping records now contain full premiums where the earlier matrix had a single digit.
- 0 previously present timestamps were removed.
- 0 winning digits changed across overlapping observations.

Thus `88,865 + 51 = 88,916`, and `88,816 + 49 + 51 = 88,916` complete premiums. The earlier 51-round gap and incomplete-premium count describe that old snapshot, not corruption in the present v19 file. The old matrix has no period-ID columns, so the comparison uses exact recorded timestamps and does not claim a direct old/new period-ID join.

Machine-readable evidence: [snapshot comparison](evidence/archive_reconciliation.json), [workbook comparison](evidence/workbook_reconciliation.json), and [ZIP verification](evidence/chatgpt/zip_manifest_verification.json). In the workbook comparison JSON, `old_*` denotes the workbook-side variable in the validation helper; **it is the current v19 workbook**, not the older ChatGPT snapshot. Both current copies agree.

## Hashes take precedence over stale prose

| Canonical file | SHA-256 |
|---|---|
| Raw CSV | `055b076b0abbd2b74d06ed7c8172608062a8fca19255a988c90f57ab998ffb65` |
| ML CSV | `a6994563dc71e5787762c8695e4e083161ae6e310bd26766589f89157fed7c6b` |
| Workbook | `a3d6bb1626070ede86985c8c47399900db8e1c044b1272c621b81cc901788bb0` |

The blueprint's workbook size/hash differ from the actual local workbook. This edition records the observed 13,140,942-byte file and the hash above; it does not manufacture a file matching stale metadata. The raw and ML hashes match the blueprint. Downloads did not contain the requested standalone CSV exports; the matching research-directory copies supplied the release assets.

## Schema and sampling

Raw columns: `sequence_no`, `Period ID`, `timestamp`, `premium`, `number`, `colour`, `size`, `colour_original`, `fix_note`.

ML columns comprise sample sequence; target period/timestamp/premium/number/colour/size; five preceding number/colour/size triplets; and `block_id`. The final target fields are labels/metadata, not eligible predictors for the same unresolved round. No one-hot or sine/cosine features are present in this export.

The sample retains the first seven raw columns and first 1,000 chronological rows. It drops free-text provenance fields for a compact public example. It is deterministic and contiguous, not statistically representative by random sampling. Full-data statistics must be attributed to the full-data source, not recomputed on the sample and presented as equivalent.

## Separate experimental cohorts

The 5,000-round VS Code evaluation uses an earlier snapshot, identified by its saved protocol and source SHA-256. Its 1,000 candidate features are separate from the v19 five-lag CSV. The older ChatGPT evaluation uses its 88,865-record snapshot. The Antigravity v19 scripts use the full canonical archive. These cohorts must not be pooled as if they were independent trials on the same train/test split.
