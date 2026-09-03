# Fixture intelligence

The fixture architecture is Club Registry → Canonical Matches → Team Fixtures → Team/Player Context. Runtime identity resolution is exact alias lookup only.

Fantrax periods are assigned by kickoff timestamp falling inside authoritative `getLeagueInfo.scoringPeriods` start/end windows. Nominal Premier League rounds are never used as the period mapping. This naturally permits blank periods, rescheduled matches, and multiple club matches in one period. The presently cached periods are stale and therefore produce blank 2026/27 mappings.

Sprint 9.0.1 corrected the cache path to `data/raw/fantrax/2627/league/league_metadata_2627_latest.json`. The authoritative 38 current-season windows now map every presently cached league match by kickoff time. Fixtures with no valid scheduled timestamp remain unresolved; cup rows remain excluded.

Sofascore is now schedule authority and maps all 380 fixtures. Raw ClubElo fields are architecturally available but currently empty because acquisition timed out. The established generic ease method is preserved for 314 of 760 team rows; missing later-season ease is reported rather than synthesized. Sprint 9.1 should combine validated raw ClubElo baseline, venue, and actual Fantrax production allowed by position with transparent sample shrinkage.

Sprint 9.1 adds the observed and derived components without producing final positional FDR: raw opponent positional production, samples, windows, venue, attack/defense observations, playing time, and rest/congestion. Prediction remains a later explicit layer.

Existing generic fixture ease is preserved from the registered preseason fixture-strength output. Sprint 9.1 should calculate transparent position baselines (GK/DEF/MID/FWD) from Fantrax points and Ghost points allowed per match, use minimum-sample shrinkage toward league average, publish home/away and sample counts, and expose each component. Goals, assists, key passes, shots, defensive-action opportunity, aerials, clean-sheet probability, and recent/season splits should be added only after coverage tests prove their source fields. Cup/European matches may inform congestion but must never enter Premier League FDR observations.
