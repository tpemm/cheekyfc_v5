# WhoScored eight-match validation

All eight selected late-2025/26 matches are resolved and cached. The sample
contains 11 clubs, 232 unique provider players, 320 lineup rows, and 11,890
events. All payloads retain the same match, home/away, formation, player,
rating, event, qualifier, and coordinate structures.

Provider event `id` is unique within a match and is the normalized event key.
The sequence `eventId` is not unique across teams and remains separate. No
normalized duplicate rows occur.

Starting formations are 4231, 352, 442, 3421, and 4222. Tactical codes are GK,
DR, DC, DL, DMC, DMR, DML, MC, MR, ML, AMC, AMR, AML, FW, and Sub. `Sub` is a
squad state rather than a role.

Ratings are minute-keyed histories. Final rating is the value at the greatest
numeric minute key. Unused substitutes have no rating. The sample has 68 paired
SubstitutionOn/Off changes. Exact minutes are not derived because expanded
minutes include stoppage time.

The sample contains 172 explicit KeyPass qualifiers, 270 TakeOns (114
successful), and 362 Aerial player-events. Aerials form 181 timestamp pairs,
each with one winner and one loser: two player observations per physical duel.

All 32 club/half groups have non-negative median pass progression and shots
cluster near x=100, supporting left-to-right attacking normalization. The
development SVG is an Event Activity Map, not tracking data.

Identity maps 198/232 provider players (85.34%) through exact WhoScored name
plus historical Understat club roster, followed by explicit registry ID. The
34 unresolved players remain unmapped. All 11 teams map deterministically.

The analytical table has 279 mapped player-match rows. Fantrax period points
align for all 279 because each sampled club has one fixture in its period.
Understat exact player-match coverage is 227/279; missing squad/substitute rows
remain missing rather than zero.

WhoScored exposes manager names for every club-match but no stable provider
manager ID. Names are preserved as observed context; production tenure identity
remains unresolved.
