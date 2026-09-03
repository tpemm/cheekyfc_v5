# Team manager context

Manager identity is designed as a stable internal ID plus club tenure intervals
(`tenure_start` inclusive, `tenure_end` inclusive). A team-match maps only when
exactly one tenure contains its date. This supports season, tenure, current
manager, and pre/post-change slicing without mixing tactical eras.

The interval mapper and boundary behavior are implemented and tested. A
production `team_manager_tenures` dataset was not created because no
authoritative historical manager source was available in the repository and
the WhoScored sample was not acquired.

The eight acquired payloads expose `managerName` for all 16 club-match sides.
Those names are preserved in normalized match context, but the provider does
not expose a stable manager ID in this payload. They are therefore not promoted
to production manager tenure identities.
