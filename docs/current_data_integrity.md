# Current-season data integrity

Current display names use the approved canonical name, then the current Fantrax
name, then a provider name only when both are unavailable. Null supplemental
joins never replace a valid name. Identity repair is restricted to stable IDs or
a unique normalized name plus current canonical club; accents, apostrophes, and
hyphens normalize for matching, while ambiguous matches remain unresolved.

Fantrax remains authoritative for fantasy points, fantasy assists, and exported
detailed components. WhoScored supplies observed events, roles, formations,
ratings, and provider-specific metrics. Understat supplies xG, xA, and xGI.
Current GW1 validation approves WhoScored key passes, aerial wins, and
interceptions as missing-value supplements. Clearances are caveated; shots on
target, raw tackles, and official assists remain source-specific; raw crosses do
not replace accurate crosses. Explicit Fantrax zero always wins, and no provider
observation remains missing rather than becoming zero.

Weekly lifecycle:

1. During an active GW, run the normal commissioner refresh as desired.
2. After matches end, refresh the same period. Each acquisition creates an
   immutable timestamped snapshot and reconciliation against the prior snapshot.
3. Keep the period `COMPLETE_PENDING_CORRECTIONS` while Fantrax corrections may
   still occur. Terminal football-match status is not a Fantrax finalization
   signal.
4. After the commissioner confirms the correction window has closed, run
   `python scripts/weekly_commissioner_refresh.py --period N --finalize`. This
   performs one final refresh and diff before recording explicit finalization.

The ordinary command remains `python scripts/weekly_commissioner_refresh.py`;
it rebuilds identity, correction, metric-validation, unified, and status outputs
without manual CSV editing.
