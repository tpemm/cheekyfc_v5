# Fantrax and WhoScored scoring semantics

GW1 validation uses exact provider-ID mappings and detailed rostered Fantrax
player-period rows. Fantrax remains authoritative. Derived WhoScored values may
only fill missing waiver components; explicit Fantrax values, including zero,
always win.

Provider-supported definitions validated in the current sample:

- accurate crosses: `Pass` carrying the `Cross` qualifier with outcome
  `Successful`; attempts partition exactly into successful and unsuccessful;
- tackles won: `Tackle` with outcome `Successful`, distinct from all attempts;
- shots on target: `Goal` plus `SavedShot` without the explicit `Blocked`
  qualifier; posts, missed shots, and blocked shots are excluded;
- official assist: supplying event carrying `IntentionalGoalAssist`, not the
  broader `IntentionalAssist` shot-context qualifier.

Accurate crosses and successful tackles reproduce Fantrax CoS and TkW exactly in
GW1. The supported SOT definition reaches 98.73% with two residual observations,
so its derivation and residual evidence remain visible in quality outputs.
Clearances retain `CAVEAT_SUPPLEMENT`: totals balance, but 13 player observations
differ, consistent with provider classification or correction allocation rather
than an evidenced alternative event definition.

Fantrax AT remains a fantasy-assist concept. WhoScored and Understat official
assists remain separately named provider observations. Event-sequence categories
are diagnostic and are not a production fantasy-assist algorithm.
