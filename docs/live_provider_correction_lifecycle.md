# Live provider correction lifecycle

Fantrax is authoritative for fantasy scoring, WhoScored for observed events and
validated supplements, and Understat for xG/xA. Accepted provider evidence is
never replaced before validation; immutable acquisition snapshots retain source,
timestamp, maturity, hash, and row/event counts.

Fantrax periods move from `LIVE` to `COMPLETE_PENDING_CORRECTIONS`, then to
`FINALIZED` only through explicit commissioner confirmation after a final refresh
and reconciliation. WhoScored and Understat matches move from `PRELIMINARY` to
`STABLE`; preliminary data is recheckable, while stable data is skipped unless
forced. Failed candidates retain the previous accepted cache.

`python scripts/weekly_commissioner_refresh.py --plan` is browser-free and shows
missing data, rechecks, provider maturity, and pending correction confirmation.
The ordinary command performs acquisition first and then one downstream rebuild,
semantic audit, and propagation audit. Finalization uses `--period N --finalize`,
requires a complete period, and writes an immutable finalization manifest.

Validated waiver supplements are goals, key passes, successful tackles,
interceptions, aerial wins, and successful crosses. Fantrax detailed values and
explicit zero always win. SOT remains monitored, clearances remain caveated, and
official assists never replace Fantrax fantasy assists. See
`fantrax_whoscored_scoring_semantics.md` for definitions.
