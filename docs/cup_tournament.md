# Cheeky FC Cup

The Cup is a configurable knockout overlay. Managers continue playing normal Fantrax league matchups; Cup results read the official manager fantasy score from configured gameweeks and require no separate lineup or HTTP request.

## Default 2026/27 format

The registered configuration is `data/reference/cup_configuration_2627.csv`: 12 teams, four byes, seeding after GW20, then Opening Round GW22, Quarterfinals GW26, Semifinals GW31, and Championship GW38. Gameweeks, team count, byes, reseeding, score source, and tiebreak method are fields rather than engine constants.

Seeds 5–12 play 5v12, 6v11, 7v10, and 8v9. Seeds 1–4 receive byes. After every completed round, survivors are sorted by frozen seed and paired highest against lowest. Third place is disabled.

## Artifacts and immutability

Registered artifacts are `cup_configuration`, `cup_seed_snapshot`, `cup_schedule`, `cup_matchups`, `cup_results`, and `cup_records`. The seed snapshot includes manager identity, seed, league rank, league points, points scored, snapshot week, and timestamp. Initialize refuses to overwrite an existing snapshot; build/rebuild only update derived bracket artifacts.

Every matchup stores seeds, manager identities/names, week, scores, winner, status, winner path, and next matchup ID when the following round exists. States are Waiting for week, Live, Upcoming when no current period is known, and Final.

Ties currently use official fantasy score, then higher frozen seed. Bench points and replay are future-supported configuration concepts but are not fabricated.

## Operations and integration

OperationsService registers Initialize Cup, Build Cup Bracket, Rebuild Cup, and Validate Cup. The shared script reads only local registered data. Operations Center exposes the actions; Initialize disables after the snapshot exists.

Cup Tournament is a primary 2026/27 page. League Hub shows Cup status/countdown, and live Manager profiles expose Cup record/history. Before seeding, the page explains that the top four after GW20 receive byes and does not project a bracket.

Future season archives can retain the results and records artifacts. Configuration filenames and registered templates are season-scoped, so later seasons can change schedules without code changes.
