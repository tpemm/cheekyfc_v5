# Sprint 9.8D.1 — Ghost reconciliation

Current fallback Ghost now starts from official Fantrax FPts and removes only the centrally configured goal, assist, and eligible clean-sheet awards. Existing application-derived Ghost from Fantrax components retains precedence.

The scoring configuration awards a midfielder nine points per goal for goals one and two and six per assist. SOT and KP remain in Ghost because only the configured G/AT/CS categories are subtracted.

Resolution hierarchy:

1. `FANTRAX_COMPONENT_DERIVED`
2. `DERIVED_FROM_RETURNS_EXACT_ASSIST`
3. `DERIVED_FROM_RETURNS_OFFICIAL_ASSIST_FALLBACK`
4. `PARTIAL_DERIVED` when return evidence is incomplete
5. `MISSING`

Jack Hinshelwood is the canary: 28.5 FPts minus 18 goal points and one midfielder clean-sheet point equals 9.5 Ghost. This result propagates through the canonical match log, season summary, Overview, and Match Analysis.

The component-derived comparison population contains 157 observations. The configured return derivation agrees exactly on 117 (74.5%), with MAE 0.605 and 40 mismatches. The mismatch population documents differences from the older application formula; it does not change the commissioner-defined FPts-minus-G/AT/CS method.

No historical Ghost source was rewritten. Current rebuild remains part of `build_current_player_participation.py`, already invoked by the commissioner refresh workflow.
