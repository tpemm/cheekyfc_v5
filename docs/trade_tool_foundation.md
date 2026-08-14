# Trade Tool foundation

The Trade Tool is not implemented in Sprint 7.0. It must consume registered datasets through DataManager.

Currently available inputs include the Player Registry, draft-day projection/rank/value, current Fantrax player pool, normalized current ownership, roster and period history, manager/team identity, and the transaction schema. Frozen draft data remains immutable context.

Player valuation still requires current fantasy production and rates, ghost floor, current xGI, minutes security, form, rest-of-season projection, club/fixture strength, position scarcity, and complete ownership. Manager context still requires current optimized XI, positional need, bench depth, incoming/outgoing simulations, and eligibility flexibility. Trade history requires a proven transaction source with stable transaction IDs, both managers, timestamps, players exchanged, before/after rosters, value at trade time, and later-performance snapshots.

No trade recommendation should run until source coverage and identity quality are explicit. Missing ADP or value inputs must remain missing, never sentinel-filled.
