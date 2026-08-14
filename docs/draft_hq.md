# Draft HQ metric contract

Player Detail can add its stable player identity to the shared session-only comparison list. Radar calculations and controls live in the shared player comparison layer; draft ranking and interaction logic remain isolated. See [player_comparison.md](player_comparison.md).

Draft HQ inherits the global theme, shell, controls, table surface, and status vocabulary. Its buttons, queue, comparison transfer, profile, grades, downloads, rankings, and frozen artifacts remain interaction- and data-protected.

Draft HQ reads registered `draft_rankings` and the registered current Fantrax
pool through `DataManager`. Mine, Other, queue, strategy, and roster state are
browser-session values only; the view performs no file writes.

When completed grade datasets exist, Draft Grades, League Rankings, and Manager Report Cards appear before the preserved Draft Board, Compare, Queue, and My Team tabs. All grade reads use `DataManager`. See `docs/draft_grades.md`.

Draft Grades leads with the screenshot-friendly League Draft Rankings share view: four headline cards, one plain-language 12-manager table, compact manager cards, and CSV/HTML downloads. Detailed analytics remain accessible in an expander and the adjacent detailed tabs.

The Share Poster section previews the deterministic 3×4 league poster and offers direct PNG and PDF downloads. The poster is generated from registered manager/pick outputs through the poster service; Draft HQ does not reconstruct it from raw files.

## Authoritative field trace

| Display | Source and merge | Draft output | Presentation |
|---|---|---|---|
| xG | Understat `understat_xg` in registered `master_player_weekly`, resolved to Fantrax identity | `understat_xg_2526` season sum | `xg_2526`; `/90` uses positive `understat_minutes_2526` |
| xA | Understat `understat_xa` through the same identity path | `understat_xa_2526` season sum | `xa_2526`; `/90` uses positive Understat minutes |
| xGI | xG + xA | builder retains `xgi90_2526` | total requires both totals; rate is blank at zero minutes |
| Team Strength | `team_strength_2526.overall_team_rating` merged by normalized 2026/27 club | `team_strength_rating` | unique-club percentile; higher is stronger |
| Fixture Ease | `fixture_difficulty_2627.overall_fixture_ease`, next-five mean by normalized club | `fixture_ease_next_5` | unique-club percentile; higher is easier |

The fixture builder defines `fixture_difficulty = 100 - overall_fixture_ease`.
Draft Builder prefers the existing ease field and only performs this inversion
when no ease field exists. Draft HQ does not modify `fixture_score`.

## Board and player decisions

The compact default board is Rank, clickable Player, compact `Club · Pos`
identity subtext, Mine, Other, Tier, Draft Score, ADP, Projected Points,
historical Start %, historical Minutes %, projected Minutes Outlook, Points,
Ghost, xGI, Team Strength %, and Next 5 Fixture Ease %, omitting
genuinely unavailable fields. Value vs ADP and Projected Minutes % remain
optional/profile fields. Draft Score and context percentiles
use restrained progress encoding while retaining numeric values; Minutes
Outlook and Tier retain explicit labels.

Optional session-persistent groups are Core, Production, Ghost, Attacking,
Playing Time, Context, and Draft Model. The compact profile leads with rank,
score, tier, status, projection, minutes, market value, and actions, then shows
production/floor, attacking/context, playing time, deterministic strengths and
risks, model bars, and the collapsed official-score reconciliation.

Compare uses higher-is-better for score, value, projection, minutes, rates,
percentiles, and model components; rank and ADP are lower-is-better. A missing
value on either player produces no winner.

`Display Points` is a session-persistent mode shared by Points, Ghost, and xGI.
Total uses season totals. Per Game means per appearance; Per Start uses starts;
Per 90 uses positive minutes. Unsupported combinations remain blank. Native
Streamlit 1.60 provides native `ButtonColumn` row clicks, callbacks, pinning,
integer widths, and tertiary styling. Player is therefore a borderless button;
its callback resolves through the exact filtered/sorted stable-key list. Club
and Fantrax eligibility use adjacent subtext because multiline button labels
are not documented as reliable. There is no detail icon, link, query parameter,
or browser navigation. Compare displays shared deterministic tags and highlights
the stronger value cell while hiding the redundant Winner column.

## My Team definitions

My Team uses canonical league rules (16 players; 11 active; registered G/D/M/F
minimums; four active flex, four bench, one injured reserve). Maximum-cardinality
bipartite assignment fills restrictive slots before flexible slots and prefers
less-flexible players. One player can occupy at most one slot.

Totals are summed. Historical team rates are `sum(total) * 90 /
sum(historical minutes)` over valid rows. Team Floor Score is 40% mean Ghost
Score + 35% mean Minutes Score + 25% mean Minutes Confidence; it is a roster
summary, not predicted weekly points. Need grades follow the documented
unfilled-required-slot ratios in [draft_lifecycle.md](draft_lifecycle.md).

Legal roster need remains the slot assignment. Strategic Priority is separate:
35% position baseline, 35% legal need, and 30% scarcity. Baselines are F=100,
M=95, D=40, G=0. G legal need is suppressed as a Fit input early, becomes a
warning with two roster slots left, and required in the final slot. Critical
goalkeeper scarcity can trigger an earlier warning.

Scarcity is 45% inverse fractional available depth, 30% inverse Tier 1/2 depth,
and 25% Tier Cliff. Multi-position players contribute `1 / position count` per
position. Tier Cliff is the bounded current-tier Draft Score gap plus 15 points
for each current-tier player below three; official tiers remain unchanged.

Balanced Fit Score weights are 25% Draft Score, 8% legal need, 16% strategic
priority, 9% scarcity, 7% tier cliff, 10% next-pick urgency, 7% ADP value,
5% floor, 5% attacking, 4% fixtures, and 4% club context, renormalized over available inputs. Best
Player Available, Fill Positional Needs, Safer Floor, Attacking Upside,
Favorable Fixtures, and Scarcity Aware alter only Fit Score weights.
Top-five reasons use explicit need/value/floor/attacking/fixture thresholds;
drafted players are excluded and Draft Score is never changed.

Historical Start % is retained `start_rate_2526 × 100`, whose denominator is
available 2025/26 gameweeks. Historical Minutes % is
`minutes_2526 / (38 × 90) × 100`, capped at the league maximum. Minutes Outlook
remains the existing 2026/27 projected label.

Percentile-first profile labels are Historical Fantasy Production,
Playing-Time Reliability, Ghost-Point Floor, Player Attacking Output, Club
Strength Context, and Next-5 Fixture Ease. No authoritative player defensive
event fields survive into Draft output, so no Defense Score is invented.

Session strategy defaults to 12 managers, Pick 2, snake order, and 16 rounds.
The sequence begins 2, 23, 26, 47, 50, 71, 74. Next-Pick Availability Score is
not a probability: `clip(50 + 3 × (market pick - next pick) - 0.25 × scarcity,
0, 100)`, using ADP with Rank fallback. Its inverse supplies Fit urgency. The
elite-defender exception requires Draft Score ≥85, Tier Cliff ≥60, and
nonnegative ADP value, adding 15 strategy points without changing Draft Score.

## Playing-time transparency and ADP refresh

Projected Minutes % is 40% full-season minutes share, 30% last-six minutes
share, 20% historical start rate, and 10% last-six start rate, minus eight
points for a detected transfer with history. Outlook thresholds are ≤20 Bench /
Unknown, >20–45 Rotation Risk, >45–68 Likely Rotation, >68–84 Likely Starter,
and >84 Locked Starter. No history becomes Unknown / New Arrival. Confidence is
90 at 2,200+ minutes, 75 at 1,200+, 55 for positive minutes, otherwise 25; a
transfer with history subtracts 15.

The active Fantrax preseason export is
`data/imports/draft/Fantrax-Players-Cheeky FC (7).csv`; `ADP` is the market
source. Required columns are `ID`, `Player`, `Team`, `Position`, and `ADP`;
`FPts` remains a distinct projection. The registered normalized pool is
`data/reference/current_fantrax_player_pool_2627.csv`, but the discoverable
export takes precedence for builder market fields.

```powershell
$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
New-Item -ItemType Directory -Force 'data\imports\draft\backups' | Out-Null
Copy-Item -LiteralPath 'data\imports\draft\Fantrax-Players-Cheeky FC (7).csv' -Destination "data\imports\draft\backups\Fantrax-Players-Cheeky FC (7).$stamp.csv"
Copy-Item -LiteralPath 'C:\Downloads\Fantrax-Players.csv' -Destination 'data\imports\draft\Fantrax-Players-Cheeky FC (7).csv' -Force
.\.venv\Scripts\python.exe scripts\validate_fantrax_adp.py 'data\imports\draft\Fantrax-Players-Cheeky FC (7).csv'
.\.venv\Scripts\python.exe scripts\build_draft_outputs.py
```

Missing ADP is allowed. Malformed supplied ADP, missing required columns, and
missing IDs fail; duplicate IDs and low row counts are reported. Verify known
players in Draft HQ and restore the backup if needed. This refresh updates ADP,
Value vs ADP, market context, Next-Pick Availability, and Fit inputs. It does
not require Player Registry unless identity, ID, club, position, or material
pool membership changed. Draft Score formula is unchanged.
