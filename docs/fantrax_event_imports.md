# Official Fantrax event CSV imports

Run from the project root:

```powershell
.\.venv\Scripts\python.exe -m fantrax.live.event_imports --transactions "PATH/claims.csv" --lineups "PATH/lineup.csv"
```

Both input paths are explicit. Raw exports are read only and are never copied or
committed by the importer. Outputs are `data/models/season_2627/transaction_events_2627.csv`
and `lineup_events_2627.csv`; the per-import report is
`data/quality/season_2627/event_import_quality_2627.json`. These supplemental products
do not modify live availability, player statistics, or period roster snapshots.

The inspected files contain Claim, Drop and Lineup Change. These map exactly to
CLAIM, DROP and LINEUP_CHANGE; other values remain UNKNOWN. Claim does not imply
waiver versus free-agent acquisition. Source type and all raw fields are retained.

Bid/Win contains 33 slash-separated numeric pairs and 166 blanks in the inspected
199-row claims export. The numeric pair's financial meaning is not established
by these files. `bid_component_1` and `bid_component_2` preserve order without
claiming either is a bid or winning charge. Raw Bid/Win and parse status remain
available. Priority is parsed separately without interpreting its ranking rules.

Dates are localized to America/Chicago. Invalid or ambiguous dates retain their raw
text and a quality flag. Invalid dates never group unrelated malformed events.
Slot-only D/M/F transitions do not imply Active. Unknown From/To tokens remain raw.

Player matching uses unique exact normalized names from canonical player analytics
and the registry; club disambiguates repeated names. Manager matching uses existing
normalized aliases from league teams and name history. No fuzzy matching is used.
Ambiguous/unresolved identities retain raw names with null IDs and explicit status.

Content-derived event IDs are local IDs, not identifiers supplied by Fantrax.
Hashes include season, league, product and raw source fields, with an occurrence
counter for indistinguishable repeated rows within a file. Reimporting/reordering
the same export is idempotent, while multiple same-timestamp actions are retained.
Identical events beyond the export's minute precision cannot be distinguished
across overlapping files; overlap retains the maximum observed multiplicity.

Transaction groups associate stable manager ID (or exact raw manager name when
unresolved) and exact exported timestamp. These are candidate associations, not
proof of a single atomic Fantrax transaction; all individual action rows remain.
Structural CSV errors stop import before either product is written. Row-level
parse problems are retained in `quality_flags` and counted in the report.
