# Draft HQ Baseline Audit

Audit date: 2026-07-29  
Target season: 2026/27 (`2627`)  
Representative output: `data/models/draft_2627/draft_rankings_2627.csv` (688 rows, 78 columns)

## 1. Purpose and architecture

Draft HQ is a preseason decision aid for comparing the current Fantrax player pool using historical Fantrax production, projected minutes, ghost points, Understat attacking involvement, team strength, opening fixtures, and Fantrax ADP.

The page remains `views/draft_center.py`. It obtains `draft_rankings` and the optional `draft_eligibility_overrides` exclusively through `SeasonManager` and `DataManager`; it does not read files or execute producers. `DatasetRegistry` registers both datasets. The canonical producer is `analytics.draft.builder`, which currently delegates to the frozen v1.2.2 implementation in `scripts/build_draft_tool_v1_2_2_2627.py`.

No architecture, ranking output, tier output, or UI was changed by this audit.

## 2. Audit inputs

| Dataset | Role |
|---|---|
| `data/imports/draft/Fantrax-Players-Cheeky FC (7).csv` | Current Fantrax preseason player pool, ADP, Fantrax rank/projection, fantasy free-agent status |
| `data/models/draft_2627/draft_player_pool_2627.csv` | Enriched pre-ranking player pool |
| `data/models/draft_2627/draft_rankings_2627.csv` | Page source and audit population |
| `data/seasons/2526/processed/master_player_weekly_2526.csv` | Historical weekly Fantrax production and minutes |
| `data/seasons/2526/analytics_views/ghost_points_player_leaders.csv` | Authoritative historical ghost totals/averages |
| `data/reference/api_to_master_player_id_bridge_2526.csv` | Current-to-historical Fantrax identity bridge |
| `data/analytics/draft/team_strength_2526.csv` | 2025/26 team ratings |
| `data/analytics/draft/fixture_difficulty_2627.csv` | 2026/27 fixture perspectives and ease |
| `data/raw/footballdata_io/full_refresh/players` | Intended current-squad eligibility source |
| `data/imports/draft/draft_eligibility_overrides_2627.csv` | Optional curated eligibility decisions; absent in the audited snapshot |
| `data/quality/draft_2627/draft_eligibility_report_2627.csv` | Generated eligibility diagnostics; present but empty |
| `data/models/preseason_2627/player_identity_crosswalk_2627.csv` | Broader preseason identity context (920 rows), not directly consumed by the page |

The rankings file was generated on 2026-07-28. ADP is therefore only as fresh as the imported Fantrax export used by that build; the CSV has no source timestamp column or freshness assertion.

## 3. Current page behavior

### Draft Board controls

All controls operate on in-memory `draft_rankings` after page aliases are created.

| Control | Rule | Missing/fallback behavior |
|---|---|---|
| Search player | Case-insensitive literal substring on `Player` | Empty search does nothing |
| Positions | Exact membership in `Position`; multi-position strings such as `D,M` are distinct values | Clearing all returns no rows |
| Teams | Exact membership in `Team` | Clearing all returns no rows |
| Minutes outlook | Exact membership in upstream `minutes_outlook` | Absent field yields no options; clearing available options returns no rows |
| Minimum confidence | `Data Confidence >= slider`, default 25 | Missing confidence becomes zero |
| Rank range | `Rank <= 50/100/150/200/300`, default 200, or All | Missing rank becomes 9999 |
| 2025/26 history only | Prefer non-null `historical_name`; fallback to non-null points/minutes | No candidate field means no filtering |
| ADP available only | Non-null numeric `fantrax_adp` | Invalid text is coerced missing |
| Include ineligible players | Default false; uses real-world `Draft Eligible`, not Fantrax `Status=FA` | If upstream flag absent, known non-team codes are ineligible |
| Sort board by | Model Rank, ADP, Value vs ADP, Draft Score, or Ghost PPG | Missing values always last |
| Direction | Ascending default or descending | Ties break by Rank ascending, then Draft Score descending |

Default filtering additionally excludes ineligible rows. The default order is overall model rank ascending.

### Headline context cards

- Players Shown: filtered row count; detail is all 688 pool rows.
- Historical Matches: count of non-null `historical_name` in the full pool (415).
- Understat Matches: non-empty `understat_player_id` (415).
- ADP Available: non-null numeric ADP in the full pool (305).
- Average Confidence: mean `data_confidence` in the filtered rows; an empty result renders an em dash.

### Decision panels

- Best ADP Values: filtered, eligible, ADP-covered rows sorted by `value_vs_adp` descending then Draft Score descending; first 8.
- Market Reaches: the same population sorted by `value_vs_adp` ascending then Draft Score descending; first 8.
- Ghost-Point Leaders: filtered eligible rows sorted by historical `ghost_ppg_2526` descending then Draft Score descending; first 8. Missing ghost PPG sorts last. There is no page-level minutes threshold.

### Main table and download

The main table preserves the chosen filtered order. It displays rank, identity/team/position, roster status, tier, score, ADP comparison, minutes outlook, historical/ghost/underlying metrics, team/fixture context, and confidence when available. Numeric display values are rounded to one decimal; upstream stored values are not altered.

The download is exactly the displayed table after filtering, sorting, renaming, and display rounding, encoded UTF-8 with BOM as `fantrax_draft_board_2627_filtered.csv`.

### Draft Tiers

The page groups the filtered rows by the upstream `tier` label and displays player count and mean rank, Draft Score, minutes share, and confidence. It does not calculate or reorder tiers itself. Missing tier data produces an informational empty state.

### Team Draft Context

The page groups the full, unfiltered rankings pool by display team and averages available attack, defense, overall, next-5, and next-10 values. It sorts descending by Overall when present. Because team values are repeated per player, the mean normally reproduces the team value; conflicting duplicated team context would be silently averaged.

### Player Detail and explanation

The detail selector follows the current filtered/sorted board and selects the first matching row for duplicate display names. It shows rank, score, minutes, production, ghost, xG+xA, team, fixture, and confidence context. The explanation correctly states the six top-level weights and that ADP does not affect Draft Score, but it omits component subweights and percentile/missing-value behavior.

## 4. Data lineage

### Raw or source-proximate fields

`fantrax_player_id`, `player_name`, `team_2627`, `position_2627`, `fantrax_adp`, `fantrax_overall_rank`, `fantrax_projected_points`, `fantrax_projected_ppg`, `drafted_pct`, `rostered_pct`, `fantrax_ros_pct`, `fantrax_plus_minus_pct`, `fantrax_status`, and `opening_opponent` originate in the Fantrax preseason export (with parsing/normalization).

Historical weekly totals originate in the 2025/26 master player-week dataset. Authoritative ghost totals originate in the ghost leader view. Team ratings and fixtures are separate upstream derived datasets.

### Builder-derived fields

Identity bridge fields, historical aggregates/rates, ghost rates, minutes outlook/confidence, team/fixture joins, component percentile scores, Draft Score, confidence, rank, tier, ADP value, and ADP status are produced upstream by the builder.

### Page-derived fields

The page derives display aliases (`Player`, `Team`, `Position`, `Rank`, `Draft Score`, `ADP`, `Value vs ADP`, minutes/confidence aliases), boolean eligibility fallbacks, `Roster Status`, filtered subsets, panel order, tier summary, team summary, detail tables, and the rounded download. None affects the stored ranking.

## 5. Field-level data dictionary

Missing rates and ranges below describe the audited 688-row file. “Rank” means the field affects Draft Score or ordering; “Tier” means it affects tier assignment. Tests refer to direct characterization in the current suite, not incidental page rendering.

### Identity, current market, and eligibility

| Field | Type; missing; unique/range | Source/transformation | Display / Rank / Tier / Test | Future trust |
|---|---|---|---|---|
| `fantrax_player_id` | text; 0%; 688 | Normalized Fantrax ID | detail identity only / no / no / override path | Reliable within snapshot; no duplicates |
| `player_name` | text; 0%; 688 | Fantrax Player | yes / tie context only / no / yes | Reliable label; name-only overrides remain collision-prone |
| `team_2627` | text; 0%; 20 | Normalized Fantrax Team | yes / indirectly / no / filters tested | Usable; real-world eligibility not proven |
| `position_2627` | text; 0%; 8 | Fantrax Position | yes / no / no / filter tested | Usable; multi-position values are unsplit strings |
| `fantrax_adp` | float; 55.67%; 1.6–287.9 | Fantrax ADP | yes / no / no / page fixture only | Usable with major coverage/freshness caveats |
| `fantrax_overall_rank` | int; 0%; 1–688 | Fantrax `RkOv` | no / no / no / no | Usable market metadata; currently confused by naming risk |
| `fantrax_adp_rank` | float; 55.67%; 1.6–287.9 | Alias of ADP, not an ordinal rank | no / no / no / no | Misnamed; do not treat as rank |
| `fantrax_projected_points` | float; 0%; -1–462 | Fantrax FPts | detail only if raw access / no / no / no | Usable with caveats; sentinel -1 exists |
| `fantrax_projected_ppg` | float; 0%; -1–33.5 | Fantrax FP/G | no / no / no / no | Usable with caveats; sentinel -1 exists |
| `drafted_pct` | int; 0%; 0–100 | Fantrax `%D` | no / no / no / no | Usable snapshot signal |
| `rostered_pct` | float; 100% | Unpopulated parser field | no / no / no / no | Not suitable |
| `fantrax_ros_pct` | int; 0%; 0–100 | Parsed Fantrax `Ros` | no / no / no / no | Usable snapshot signal |
| `fantrax_plus_minus_pct` | int; 0%; -28–22 | Parsed Fantrax `+/-` | no / no / no / no | Usable snapshot signal |
| `fantrax_status` | text; 0%; one value (`FA`) | Fantrax fantasy roster status | eligibility explanation only / no / no / yes | Reliable only as “undrafted”; not real-world club status |
| `opening_opponent` | text; 0%; 20 | Fantrax Opponent | no / no / no / no | Snapshot-only, not used |
| `player_name_key` | text; 0%; 688 | Normalized name | no / identity join / no / no | Usable fallback identity key |
| `is_free_agent` | bool; 0%; all false | Builder eligibility result | roster status / gates rank / gates tier / page eligibility tests | Not trustworthy in this snapshot |
| `is_draft_eligible` | bool; 0%; all true | Current squad check or fallback | filter/status / gates rank / gates tier / override tested | Not suitable until squad coverage works |
| `draft_eligibility_status` | text; 0%; one value | Eligibility explanation | indirect / no / no / override tested | Not suitable; all fallback eligible |
| `eligibility_source` | text; 0%; one value | Squad matcher source | detail/raw only / eligibility gate / tier gate / no | Not suitable; all `Fantrax fallback` |
| `squad_match_method` | float; 100% | Intended current-squad match method | no / eligibility / eligibility / no | Not suitable |
| `footballdata_player_id` | float; 100% | Intended current-squad ID | no / eligibility / eligibility / no | Not suitable |
| `footballdata_player_name` | float; 100% | Intended current-squad name | no / eligibility / eligibility / no | Not suitable |
| `current_epl_team` | text; 0%; 20 | Fallback current team | detail/raw only / eligibility context / no / no | Inherits unverified Fantrax team |

### Historical production and identity

| Field | Type; missing; range/unique | Source/transformation | Display / Rank / Tier / Test | Future trust |
|---|---|---|---|---|
| `historical_fantrax_player_id` | text; 0%; 688 | API-to-master bridge, else current ID | no / joins history / indirect / no | Usable, but 273 rows have no named history |
| `historical_name` | text; 39.68%; 415 | Last historical name | history card/filter / no / no / page fixture | Usable identity evidence |
| `team_2526` | float; 100% | Historical team aggregation | transfer logic / minutes / indirect / no | Not suitable; total absence causes transfer detection weakness |
| `position_2526` | float; 100% | Historical position aggregation | no / no / no / no | Not suitable |
| `weeks_available` | float; 14.53%; 3–38 | Unique historical GWs | no / rate denominator / indirect / no | Usable with caveat: availability is not appearances |
| `minutes_2526` | float; 14.53%; 0–3420 | Weekly sum | detail / minutes component / indirect / no | Usable with caveats |
| `starts_2526` | float; 14.53%; 0–38 | Weekly sum or >=60-minute proxy | detail / minutes component / indirect / no | Usable with caveats |
| `fantasy_points_2526` | float; 14.53%; 0–675.5 | Weekly official points sum | detail/raw / production + confidence / indirect / no | Usable with caveats |
| `goals_2526` | float; 14.53%; 0–27 | Weekly sum | no / no / no / no | Usable context |
| `assists_2526` | float; 14.53%; 0–24 | Weekly sum | no / no / no / no | Usable context |
| `recent_minutes_6` | float; 14.53%; 0–630 | Sum over `gw >= max_gw-5` | detail / minutes / indirect / no | Usable with caveat: observed 630 exceeds nominal 540 |
| `recent_starts_6` | float; 14.53%; 0–7 | Same six-GW window | no / minutes / indirect / no | Caveat: observed 7 creates rate >1 |
| `recent_fp_6` | float; 14.53%; -5–131 | Same six-GW window | no / no / no / no | Usable context |
| `fantasy_ppg_2526` | float; 14.53%; 0–17.78 | points / weeks available | yes / 60% of production + rank tie / indirect / fixture only | Usable with caveat: per available week, not match |
| `fantasy_fp90_2526` | float; 56.10%; 0.91–45 | points / minutes × 90 | yes / 40% of production / indirect / fixture only | Incomplete; unstable at low minutes |
| `start_rate_2526` | float; 14.53%; 0–1 | starts / weeks available | no / minutes / indirect / no | Usable with denominator caveat |
| `recent_start_rate_6` | float; 14.53%; 0–1.167 | recent starts / 6 | no / minutes / indirect / no | Needs cap/duplicate-window investigation |
| `team_changed` | bool; 0%; 2 values | history exists and old team != current team | detail / minutes penalty/confidence / indirect / no | Not trustworthy because `team_2526` is entirely missing |

### Ghost and underlying attacking data

| Field | Type; missing; range | Source/transformation | Display / Rank / Tier / Test | Future trust |
|---|---|---|---|---|
| `ghost_points_2526` | float; 14.53%; 0–449.5 | authoritative total then master fallback | no / rate source / indirect / no | Usable with provenance caveat |
| `ghost_ppg_2526` | float; 14.53%; 0–12.6 | authoritative average, total/appearances, then weekly fallback | yes / 15% / indirect / fixture only | Usable with caveats |
| `ghost_points_2526_authoritative` | float; 55.23%; 0–449.5 | ghost leader total | no / fallback lineage / no / no | Reliable where present |
| `ghost_ppg_2526_authoritative` | float; 55.23%; 0–12.6 | ghost leader average | no / preferred ghost rate / indirect / no | Reliable where present |
| `ghost_appearances_2526` | float; 55.23%; 1–38 | ghost leader appearances | no / fallback denominator / indirect / no | Reliable where present |
| `ghost_source_fantasy_points_2526` | float; 55.23%; 0–675.5 | ghost leader total fantasy points | no / share denominator / no / no | Reliable where present |
| `ghost_fp90_2526` | float; 56.10%; 0.91–45 | ghost total / minutes × 90 | detail/raw only / no / no / no | Incomplete and low-minute sensitive |
| `ghost_share_pct_2526` | float; 56.10%; 18.75–200 | ghost / fantasy total × 100 | no / no / no / no | Needs investigation; >100% can be mathematically possible with negative major-event points but is unintuitive |
| `understat_xg_2526` | float; 14.53%; 0–28.8 | historical weekly sum | detail/raw / xGI rate / indirect / no | Usable with identity caveat |
| `understat_xa_2526` | float; 14.53%; 0–17.76 | historical weekly sum | detail/raw / xGI rate / indirect / no | Usable with identity caveat |
| `understat_npxg_2526` | float; 14.53%; all non-null values 0 | historical weekly sum | no / no / no / no | Not suitable |
| `understat_key_passes_2526` | float; 14.53%; 0–137 | historical weekly sum | no / no / no / no | Usable context |
| `understat_minutes_2526` | float; 14.53%; 0–3420 | historical weekly sum | no / xGI denominator / indirect / no | Usable with identity caveat |
| `understat_player_id` | numeric/text ID; 39.68%; 415 | last linked Understat ID | headline/detail / confidence / indirect / page fixture | Usable identity evidence |
| `xgi90_2526` | float; 39.68%; 0–3.657 | `(xG+xA)/Understat minutes×90`, with missing xG/xA filled 0 | yes / 15% / indirect / fixture only | Incomplete; no minimum-minutes threshold |

### Team, fixtures, minutes, scores, rank, and tier

| Field | Type; missing; range | Source/transformation | Display / Rank / Tier / Test | Future trust |
|---|---|---|---|---|
| `team_attack_rating` | float; 32.99%; 7.9–98.2 | 2025/26 team percentile composite | yes / 65% of team component / indirect / fixture only | Incomplete: only 13 distinct ratings |
| `team_defense_rating` | float; 32.99%; 24.1–100 | 2025/26 defensive composite | team table/detail / no / no / fixture only | Incomplete: display-only |
| `team_strength_rating` | float; 32.99%; 27.1–96.1 | team overall composite | yes / 35% of team component + confidence / indirect / fixture only | Incomplete: promoted/missing teams unsupported |
| `fixture_ease_next_3` | float; 23.26%; 28.07–51.5 | mean first 3 overall ease | detail / no / no / no | Incomplete |
| `fixture_ease_next_5` | float; 23.26%; 30.12–51.62 | mean first 5 overall ease | yes / 10% / indirect / fixture only | Incomplete |
| `fixture_ease_next_10` | float; 23.26%; 37.67–50.39 | mean first 10 overall ease | yes / no / no / fixture only | Incomplete |
| `projected_minutes_share` | float; 0%; 0–92 | weighted historical minutes/start score minus transfer penalty | yes / 20% / indirect / fixture only | Usable with serious new-arrival/team-change caveats |
| `minutes_outlook` | category; 0%; 6 | fixed bins; no history becomes `Unknown / New Arrival` | filter/detail / no / no / page control | Usable label, dependent on weak minutes model |
| `minutes_confidence` | int; 0%; 25–75 observed | 90/75/55/25 by historical minutes, -15 transfer | yes / confidence only / indirect / fixture only | Usable with caveats; expected 90 is absent due team-change issue |
| `production_score` | float; 0%; 0–99.9 | 60% PPG percentile + 40% FP90 percentile | detail/raw / 30% of score / indirect / no | Deterministic, but missing becomes bottom score |
| `ghost_score` | float; 0%; 0–100 | ghost PPG percentile | detail/raw / 15% / indirect / no | Deterministic, missing becomes zero |
| `attacking_score` | float; 0%; 0–100 | xGI90 percentile | detail/raw / 15% / indirect / no | Deterministic, missing becomes zero |
| `minutes_score` | float; 0%; 0–92 | projected minutes share | detail/raw / 20% / indirect / no | Deterministic, input caveats apply |
| `team_context_score` | float; 0%; 0–96 | 65% attack percentile + 35% overall percentile | detail/raw / 10% / indirect / no | Missing teams become zero |
| `fixture_score` | float; 0%; 0–96.1 | next-5 ease percentile | detail/raw / 10% / indirect / no | Missing fixtures become zero |
| `draft_score` | float; 0%; 0–92.98 | weighted component sum | yes / primary / determines rank then tier / page fixture only | Reproducible; not yet formula-tested |
| `data_confidence` | float; 0%; 11.2–88.8 | 45% minutes confidence + 25 history + 20 Understat + 10 team | yes/filter/tie-break / tie-break / indirect / fixture only | Usable indicator; does not reduce score |
| `overall_rank` | int; 0%; 1–688 | eligible rows sorted by score, confidence, PPG | yes / output / tier input / order tested | Deterministic for current unique keys, but final ties lack stable ID key |
| `tier` | category; 0%; 7 | fixed overall rank bands | yes / no / output / missing-only test | Deterministic but not value-sensitive |
| `value_vs_adp` | float; 55.67%; -513.7–256.9 | ADP minus overall rank | yes / no / no / fixture only | Usable as crude market gap |
| `adp_status` | category; 0%; 6 | thresholds ±8 and ±20 plus missing/ineligible | yes / no / no / fixture only | Usable label; threshold not tested |

## 6. Draft Score methodology

The builder converts most raw components to cross-sectional percentile scores:

`percentile(x) = 100 × rank_pct(x, method="average")`

Missing numeric values receive percentile zero. There is no position-specific normalization, minimum-minutes threshold, winsorization, cap beyond the natural percentile scale, or imputation to league average.

Components:

- `Production = 0.60 × pct(fantasy_ppg_2526) + 0.40 × pct(fantasy_fp90_2526)`
- `Minutes = projected_minutes_share`
- `Ghost = pct(ghost_ppg_2526)`
- `Attacking = pct(xgi90_2526)`
- `Team = 0.65 × pct(team_attack_rating) + 0.35 × pct(team_strength_rating)`
- `Fixtures = pct(fixture_ease_next_5)`
- `Draft Score = round(0.30×Production + 0.20×Minutes + 0.15×Ghost + 0.15×Attacking + 0.10×Team + 0.10×Fixtures, 2)`

ADP, position, Fantrax projections, team defense, confidence, and eligibility do not enter Draft Score. Team and fixture context affect players only through their team joins. Confidence is a rank tie-break, not a score weight.

### Worked examples

The component columns are stored rounded to one decimal while Draft Score was calculated from unrounded components. Contributions below use the stored component values, so their displayed sum can differ by a few hundredths.

| Player | Rank | Production 30% | Minutes 20% | Ghost 15% | Attack 15% | Team 10% | Fixtures 10% | Stored score |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Bruno Fernandes | 1 | 99.9×.30 = 29.97 | 86.1×.20 = 17.22 | 99.8×.15 = 14.97 | 97.3×.15 = 14.60 | 81.6×.10 = 8.16 | 80.7×.10 = 8.07 | 92.98 |
| Kaide Gordon | 345 | 14.6×.30 = 4.38 | 0×.20 = 0 | 24.4×.15 = 3.66 | 0×.15 = 0 | 73.5×.10 = 7.35 | 88.3×.10 = 8.83 | 24.23 |
| Ashley Young | 688 | 0 | 0 | 0 | 0 | 0 | 0 | 0.00 |

The middle example demonstrates that missing history can still rank through team and fixture context. The low example demonstrates the current zero-floor behavior.

## 7. Tier methodology

Tiers are overall, not position-specific. After eligible players are ordered, fixed inclusive rank bands are applied with `pandas.cut`:

- Tier 1: ranks 1–12
- Tier 2: 13–36
- Tier 3: 37–72
- Tier 4: 73–120
- Tier 5: 121–180
- Tier 6: 181–300
- Deep: 301+

The method does not use score gaps, quantiles, value cliffs, or position. Labels and boundaries are deterministic. Ties in Draft Score are broken by confidence and then PPG; an exact remaining tie relies on input/sort stability because player ID is not an explicit final key. Ineligible or missing-rank rows receive no tier. Empty positions are irrelevant because tiering is overall. Boundaries are stable in rank count but not stable in player quality.

## 8. ADP value and market reach

ADP comes directly from the preseason Fantrax export. It is a decimal pick number, not an integer rank. `fantrax_adp_rank` is merely an alias of that decimal ADP.

`Value vs ADP = fantrax_adp - overall_rank`

Positive values mean the model ranks a player earlier than the market (value); negative values mean the model ranks the player later (reach). Labels are:

- Strong value: >= +20
- Value: +8 through < +20
- Near market: > -8 through < +8
- Reach: <= -8 through > -20
- Major reach: <= -20
- ADP unavailable or Not draft eligible as applicable

Missing ADP produces no comparison and is excluded from both decision panels. Duplicate rows are not deduplicated. Page panels exclude ineligible rows, although the audited snapshot marks all rows eligible.

Coverage is 305/688 (44.33%); 383 rows lack ADP. No freshness timestamp is embedded. The immediate priority is trustworthy eligibility and identity, not a new value formula. Later evaluation should compare percentage/round-normalized difference and tier difference before adding replacement value; absolute gap should remain the baseline comparator until approved. Position-adjusted or replacement-value comparisons require stable position handling and a replacement model.

## 9. Ghost-point methodology

The authoritative upstream definition is:

`ghost_points = fantasy_points - (goal points + assist points + clean-sheet points + goals-against points)`

The major-event components use position-specific league scoring, so exclusions are position-consistent upstream. Goals-against penalties are subtracted as a signed component; removing a negative penalty can make ghost points exceed total fantasy points.

Draft uses 2025/26 historical values only. It prefers authoritative season total and average from `ghost_points_player_leaders`; otherwise it calculates authoritative total/appearances; otherwise it uses the master-week aggregation. Draft Score and the leader panel use `ghost_ppg_2526`, not projected ghost points, a blend, season total, per-start, or per-90. The builder also creates total, per-90, and share fields, but the page leader panel does not use them.

There is no Draft-specific position adjustment or minutes threshold. Missing ghost PPG becomes percentile zero in Draft Score and sorts last in the panel. Coverage is 588/688 for the final fallback field (85.47%) but only 308/688 for the authoritative fields (44.77%).

## 10. Team and fixture context

### Team strength

Team data is built from 2025/26 FootballData.io team statistics using percentile composites:

- Attack: 35% xG for/match, 25% goals for/match, 15% shots/match, 15% shots on target/match, 10% possession.
- Defense: 40% inverse xG against/match, 30% inverse goals against/match, 20% clean-sheet percentage, 10% inverse loss percentage.
- Control: 45% possession, 25% corners for/match, 15% fouls drawn/match, 15% points/game.
- Overall: 45% Attack + 40% Defense + 15% Control.
- Team rank: overall descending, minimum-rank tie method.

Missing metric values receive a neutral 50 inside the team builder. The audited draft output has context for only 461/688 players and 13 distinct team ratings. Missing teams receive zero percentiles in Draft Score. There is no promoted-team proxy or expected-opportunity field. Defense and team rank are display-only/not attached respectively; attack and overall affect Draft Score.

### Fixtures

For each 2026/27 fixture and team perspective:

- Attacker ease = 55% team win probability + 45% inverse opponent defense.
- Defender ease = 55% team win probability + 45% inverse opponent attack.
- Overall ease = 50% team win probability + 50% inverse opponent overall.
- Difficulty = 100 - overall ease.

Missing opponent ratings become 50. Draft attaches the chronological mean of overall ease for the first 3, 5, and 10 fixtures. Only next-5 affects Draft Score; all three are displayed in detail and next-5/10 in the board/team table. Coverage is 528/688 (76.74%). There is no position-specific choice between attacker and defender ease. Update frequency is rebuild-driven; no automatic freshness assertion exists.

## 11. Identity and eligibility

### Identity rules

Fantrax IDs are normalized by removing punctuation and case. The API-to-master bridge maps the current ID to a historical master ID, with current ID fallback. Historical data is then joined by the bridged ID. Current-squad eligibility attempts exact normalized ID/name/team matching, then constrained fuzzy name matching. Page overrides match normalized Fantrax ID and/or exact casefolded display name; builder overrides use similar rules and can set team, eligibility, reason, and an override marker.

The page does not deduplicate records. It tolerates duplicates and player detail selects the first matching display name. Current output has no duplicate Fantrax IDs and no duplicate display names.

### Coverage counts

| Measure | Count | Rate |
|---|---:|---:|
| Total draft rows | 688 | 100% |
| Unique Fantrax IDs | 688 | 100% |
| Unique display names | 688 | 100% |
| Named historical mappings | 415 | 60.32% |
| Unresolved/no named historical identity | 273 | 39.68% |
| Understat identities | 415 | 60.32% |
| Duplicate ID groups / rows | 0 / 0 | 0% |
| Duplicate name groups / rows | 0 / 0 | 0% |
| Marked real-world ineligible | 0 | 0% |
| Excluded by default | 0 | 0% |
| Included/changed through overrides | 0 | 0% |
| Missing ADP | 383 | 55.67% |
| Missing named historical data | 273 | 39.68% |
| Missing historical aggregate points/minutes | 100 | 14.53% |
| Missing Fantrax projection field | 0 | 0% |

The difference between 415 named historical matches and 588 non-null aggregates is itself a quality warning: unmatched merge rows have numeric zero-like aggregates but no trusted identity name. Numeric non-nullness must not be treated as successful historical linkage.

### Eligibility finding

The audited ranking has `is_draft_eligible=True`, `is_free_agent=False`, and `eligibility_source="Fantrax fallback"` for every row. The current-squad match columns are entirely missing and the eligibility report is an empty file. Consequently, the page’s “real-world eligibility” mechanism is implemented but the representative output does not validate EPL eligibility. Fantrax `Status=FA` correctly is not used as a real-world exclusion because it means every preseason player is undrafted.

## 12. Data-quality assessment

| Domain | Classification | Main caveat |
|---|---|---|
| Identity | Usable with caveats | IDs are unique, but only 60.32% have named historical/Understat links |
| Fantrax availability | Reliable | `Status=FA` consistently means fantasy free agent; it must not imply EPL eligibility |
| Position | Usable with caveats | Complete but multi-position strings are not exploded or position-adjusted |
| ADP | Incomplete | 44.33% coverage and no embedded freshness timestamp |
| Historical scoring | Usable with caveats | 85.47% numeric coverage but only 60.32% named mappings; per-week denominator |
| Ghost points | Usable with caveats | Final fallback coverage is high; authoritative coverage is 44.77%; no minutes threshold |
| Minutes | Usable with caveats | 85.47% historical coverage; transfer detection is compromised and new players score zero |
| xG/xA | Incomplete | 60.32% xGI90 coverage; no minutes floor; npxG field is unusable |
| Fixture context | Incomplete | 76.74% player coverage; no promoted-team strategy or position-specific ease |
| Team context | Incomplete | 67.01% player coverage and only 13 team ratings |
| Draft Score | Usable with caveats | Reproducible but missing data becomes zero, with no position/minutes normalization or direct tests |
| Tiers | Usable with caveats | Deterministic fixed overall rank buckets, not score gaps or positional tiers |
| Real-world eligibility | Not currently suitable | All 688 rows pass via fallback; squad diagnostics are empty |

## 13. Existing test coverage

`tests/test_draft_center_page.py` currently characterizes:

- required/optional dataset loading and working/snapshot namespace ownership;
- existing section/control rendering;
- default model-rank ordering;
- position and search filtering;
- empty states and missing optional columns;
- duplicate-row tolerance;
- filtered download name/content;
- a negative eligibility override;
- registry definition and page architecture boundary.

Registry tests validate model classification and general registry behavior. Architecture tests protect the canonical wrapper. There are no direct builder characterization tests for Draft Score, component percentile missingness, tier boundaries, ADP labels, current-squad eligibility, identity bridge duplicates, missing projections, promoted teams, position behavior, final tie determinism, or page-download equivalence across all filters.

Highest-value missing tests:

1. Exact Draft Score components and output for a small fixed frame, including missing inputs.
2. Tier boundary ranks 12/13, 36/37, 300/301 and ineligible/missing score behavior.
3. ADP gaps and all label thresholds, including missing ADP and ineligible rows.
4. Complete versus incomplete squad-cache eligibility and override precedence.
5. Bridge/current ID duplicates and deterministic final ordering with exact ties.
6. New arrival/missing projection and promoted-team fallback characterization.
7. Multi-position and position-specific views.
8. Download order/values exactly matching the displayed board under compound filters.

No new tests were necessary to document the baseline; changing producer imports solely to make the legacy script unit-testable would exceed this sprint’s behavioral-change tolerance.

## 14. Known weaknesses and preserved strengths

Preserve:

- transparent six-component score and separate market comparison;
- full filtering/search/sort/download workflow;
- decision panels, tier summary, team context, and player detail;
- real-world eligibility concept separated from Fantrax fantasy status;
- DataManager/registry/season architecture and defensive empty states.

Highest-priority weaknesses:

1. Real-world eligibility is not functioning in the representative output.
2. Team coverage is 13-rating/67%; promoted and missing teams fall to zero in ranking.
3. Identity evidence covers only 60%, while zero-filled aggregates obscure the distinction.
4. The minutes/transfer model is compromised by a fully missing historical-team field; recent starts can exceed six.
5. Missing data is treated as bottom-of-pool performance, not uncertainty, while confidence does not temper score.
6. ADP is sparse and has no auditable freshness.
7. Tiering is an arbitrary overall rank bucket and ignores score cliffs/position.
8. The score, tiers, and market labels lack direct producer tests.

## 15. Recommended feature priorities

The smallest high-value sequence is reliability before feature expansion. Scarcity, auction values, sleepers, live draft mode, roster construction, and AI insight would compound current eligibility/identity/team weaknesses and should wait.

### Sprint 3.1 — Eligibility, identity, and baseline reliability

- Objective: make the current 688-row population and every score input auditable without changing the approved formula.
- User value: users can trust who is draftable and understand missing-data risk.
- Dependencies: complete current EPL squad cache, identity bridge, current transfer/promoted-team list.
- Datasets: Fantrax pool, FootballData.io squads, identity crosswalk/bridge, eligibility overrides, quality reports.
- Calculations: coverage flags and validation diagnostics only; preserve score/tier outputs pending approval.
- UI: at most non-invasive coverage warnings after data is corrected; no redesign.
- Tests: eligibility complete/incomplete cache, override precedence, duplicate identity, exact score/tier/ADP characterization, deterministic ordering.
- Risks: correcting eligibility and identity will legitimately change ranking population/order; require a reviewed rebuild and before/after artifact.

### Sprint 3.2 — Minutes, role, and promoted/new-player coverage

- Objective: establish reliable minutes/role inputs for returning players, transfers, promoted players, and new arrivals.
- User value: fewer zero-score newcomers and fewer false starter assumptions.
- Dependencies: Sprint 3.1 identities/teams; current squads and role/projection source.
- Datasets: historical minutes/starts, current squads, transfers, Fantrax projections, promoted-team/player histories.
- Calculations: capped recent rates, explicit new-arrival priors and role confidence proposals; formula changes require approval.
- UI: clearer risk/coverage explanation in existing detail surfaces.
- Tests: transfer detection, six-GW cap, no-history players, promoted teams, missing projections.
- Risks: subjective priors and source freshness.

### Sprint 3.3 — Position-aware value and tier research

- Objective: validate positional views, replacement baselines, scarcity, and score-gap tier options offline.
- User value: value comparisons reflect roster constraints rather than only overall rank.
- Dependencies: stable positions and reliable minutes/eligibility.
- Datasets: rankings, league roster/position rules, ADP, historical draft/waiver availability if obtainable.
- Calculations: replacement value, positional rank, tier-gap candidates, round-normalized ADP comparison.
- UI: proposed positional view/tier visualization only after method approval.
- Tests: multi-position policy, replacement baselines, stable ties/boundaries.
- Risks: double-counting eligibility and overfitting league-specific replacement levels.

### Sprint 3.4 — Draft board workflow

- Objective: add watchlist, hide-drafted state, and draft history before full live roster optimization.
- User value: turns the reliable board into a usable draft-room tool.
- Dependencies: stable player IDs and rankings.
- Datasets: rankings plus session/persisted draft events.
- Calculations: availability state and pick history; no score changes.
- UI: watchlist and drafted controls, explicit reset/export.
- Tests: state transitions, undo/reset, identity persistence, export consistency.
- Risks: Streamlit session loss and concurrent-user isolation.

### Sprint 3.5 — Team construction

- Objective: track rosters, positional limits, team needs, and legal squad construction.
- User value: recommendations respond to the user’s actual roster.
- Dependencies: Sprint 3.3 position/replacement policy and Sprint 3.4 draft event state.
- Datasets: draft events, league rules, rankings.
- Calculations: slot eligibility, roster needs, replacement/need adjustment kept separate from baseline score.
- UI: roster panel and constraints.
- Tests: multi-position assignment, limits, undo, completed rosters.
- Risks: ambiguous multi-position optimization and mixing personalized recommendations with baseline rank.

### Sprint 3.6 — Value, sleeper, and risk analysis

- Objective: expose approved sleeper, reach, floor/ceiling, and risk indicators.
- User value: makes tradeoffs actionable after underlying data is trustworthy.
- Dependencies: reliable ADP history/freshness, role confidence, replacement model.
- Datasets: ADP snapshots, historical production, minutes, ghost, xG/xA, team/fixture, draft outcomes if available.
- Calculations: tier/round value, sleeper rules, downside/ceiling bands, risk flags; validate offline first.
- UI: compact indicators and comparison mode, not opaque AI rankings.
- Tests: thresholds, missingness, stability, explanations, no baseline-score mutation.
- Risks: false precision, hindsight bias, and correlated signals.

## 16. Explicit freeze list

Until separately approved, preserve exactly:

- the six Draft Score top-level weights (30/20/15/15/10/10);
- production subweights (60% PPG, 40% FP90);
- team subweights (65% attack, 35% overall);
- percentile method (`rank(pct=True, method="average")`, missing to zero);
- projected-minutes formula, bins, transfer penalty, and confidence thresholds;
- data-confidence weights (45% minutes confidence, +25 history, +20 Understat, +10 team);
- ranking order keys (eligibility, score, confidence, PPG);
- fixed tier boundaries and labels;
- `ADP - overall_rank` value formula and ±8/±20 labels;
- historical ghost PPG selection/fallback;
- next-5 overall fixture ease as the fixture score input;
- default eligibility filtering and the separation of Fantrax `FA` from real-world eligibility.

Any data correction that changes inputs may change outputs even if these formulas remain frozen. Such a rebuild should be reviewed as an input correction, not silently presented as no ranking change.

## 17. Verification record

- Full suite: `187 passed` in 12.82 seconds using `.\.venv\Scripts\python.exe -m pytest`.
- Streamlit AppTest: 2026/27 Draft HQ completed with zero uncaught exceptions.
- AppTest confirmed all existing controls, all six named content sections, eight dataframes, and the filtered-download control.
- Default main board contained 200 rows because the existing default rank limit is 200; its first five were Bruno Fernandes, Dominik Szoboszlai, Erling Haaland, Antoine Semenyo, and Virgil van Dijk at ranks 1–5.
- Streamlit emitted existing `use_container_width` deprecation notices and automatically repaired mixed-type detail-table Arrow serialization; neither was an uncaught application exception.
- No code, source dataset, ranking output, tier output, or application UI was modified.

## 18. Sprint 3.1 results — eligibility, identity, and baseline reliability

Completed 2026-07-29. This section preserves the Sprint 3.0 baseline above as historical context.

### Root cause and squad-source result

The producer did invoke eligibility classification, but all 20 cached FootballData.io 2026/27 player files contained an empty `players` array. Each request had used season ID `103535`; the only populated probe omitted the season filter and covered just 11 Bournemouth players, so it was not a defensible league source. The old classifier returned immediately when the normalized squad frame was empty. That caused:

- no per-player diagnostics;
- an empty eligibility report;
- all 688 players retaining the initial Fantrax-derived eligible value;
- the opaque `Fantrax fallback` source on every output row.

The corrected classifier always emits one diagnostic per Fantrax row and a club-coverage report. The expected source contains these 20 target clubs: ARS, AVL, BHA, BOU, BRF, CHE, COV, CRY, EVE, FUL, HUL, IPS, LEE, LIV, MCI, MUN, NEW, NOT, SUN, and TOT. All 20 cache files are present, including the target promoted clubs, but each has zero players; therefore 0/20 clubs meet the completeness threshold of 15 players.

The producer now labels every row `Unresolved: squad source incomplete`, identifies the source as `FootballData.io incomplete cache`, and records the reason. Conservative inclusion is preserved: unresolved players remain visible and ranked, but are no longer represented as confirmed squad matches. Fantrax `Status=FA` remains strictly fantasy availability.

Current eligibility counts:

| Status | Count |
|---|---:|
| Confirmed matched eligible | 0 |
| Confirmed ineligible | 0 |
| Override eligible | 0 |
| Override ineligible | 0 |
| Unresolved due incomplete squad source | 688 |
| Included in browsing/ranking | 688 |

Override precedence is now: normalized Fantrax ID when provided; otherwise one unique normalized name; then the current-squad result; finally unresolved inclusion. A conflicting supplied ID/name or ambiguous name-only match is not applied and is reported. Overrides preserve reason and can correct the current team.

### Identity and historical input correction

The historical merge has 588 normalized current/bridged IDs present in the 2025/26 master dataset. Sprint 3.0 counted only the 415 rows with a populated historical display name, understating valid ID linkage. The producer now emits:

- `has_historical_identity`;
- `has_historical_data`;
- `historical_match_status`;
- `historical_match_method`;
- `historical_match_confidence`.

All 588 matched historical IDs are explicit matches even when the historical name field is absent. The remaining 100 rows are classified as `no 2025/26 record for bridged ID`; they remain unresolved/no-record rather than being asserted as confirmed new arrivals. Consequently, confirmed legitimate no-history is 0 and unresolved/no-record is 100 pending a richer current-squad/arrival source.

Historical aggregates for those 100 rows remain null. Genuine matched zero production remains numeric zero. `data_confidence` now uses `has_historical_data`, rather than merely checking whether a numeric aggregate is non-null.

The historical aggregation now selects the latest non-empty value by gameweek after retaining the last duplicate player-week row:

- team candidates start with `avail_team`, then `mgr_team` and `fantrax_team_name`;
- position candidates start with `avail_position`, then `mgr_position` and `fantrax_position`.

This populated `team_2526` and `position_2526` for all 588 historical matches, versus 0 before. Existing transfer detection now identifies 32 players whose normalized historical and current teams differ. The minutes-transfer penalty itself was not changed.

Team normalization was corrected for FootballData/Fantrax forms including BRF, FUL, IPS, NOT, and `FC`/`AFC` suffixes. This increased team-context coverage from 461 to 558 and fixture coverage from 528 to 653 without changing either context formula.

### Determinism and formula characterization

The canonical frozen calculations now live in `analytics/draft/model.py`; eligibility and override behavior lives in `analytics/draft/reliability.py`. The existing command entry point remains `analytics.draft.builder`, and the legacy CLI delegates corrected behavior to these canonical modules.

Normalized Fantrax player ID was added as an ascending, non-semantic final tie-break after eligibility, Draft Score, confidence, and historical PPG. Shuffling exactly tied inputs now produces identical output without changing any non-tied ordering.

Focused producer tests cover:

- all six Draft Score components, production/team subweights, percentile average ties, missing percentile zero, and two-decimal output;
- proof that ADP and confidence do not enter Draft Score;
- eligibility, score, confidence, PPG, and stable-ID ordering;
- all tier boundaries from 12/13 through 300/301 and ineligible null rank/tier;
- ADP positive/negative/missing/decimal cases and the ±8/±20 thresholds;
- incomplete and complete squad sources, exact/fuzzy matches, confirmed non-EPL classification, and override ambiguity/precedence;
- current team aliases;
- duplicate historical weeks, latest team/position, transfer detection, and no-history null preservation.

The Draft Score weights, component transformations, tier boundaries, ADP formula/status thresholds, fixture input, and page layout remain unchanged.

### Before/after comparison

The review artifact is `reports/draft_analytics_sprint_3_1_comparison.csv`.

| Measure | Sprint 3.0 | Sprint 3.1 |
|---|---:|---:|
| Player rows | 688 | 688 |
| Ranked/included | 688 | 688 |
| Confirmed eligibility | 0 | 0 |
| Auditable unresolved eligibility | 0 | 688 |
| Historical ID/data matches | obscured (415 named; 588 numeric) | 588 explicit |
| Historical names | 415 | 415 |
| No historical record for bridged ID | not explicit | 100 |
| Historical team populated | 0 | 588 |
| Historical position populated | 0 | 588 |
| Transfers detected | unreliable | 32 |
| Understat links | 415 | 415 |
| Team context | 461 | 558 |
| Fixture context | 528 | 653 |
| ADP | 305 | 305 |

No player entered or left the population because the current squad source cannot yet support confirmed exclusions. Input corrections changed 670 Draft Scores, 669 ranks, and 51 tiers. These are not formula changes: they result primarily from corrected team-code joins, repaired historical team/position inputs, the existing transfer penalty becoming functional, and cross-sectional percentile redistribution.

Largest rank increases:

| Player | Before | After | Increase |
|---|---:|---:|---:|
| Nicolas Dominguez | 495 | 334 | 161 |
| Ryan Yates | 500 | 342 | 158 |
| Nicolo Savona | 497 | 341 | 156 |
| Jordan Henderson | 492 | 343 | 149 |
| James Mcatee | 456 | 322 | 134 |

Largest rank decreases:

| Player | Before | After | Decrease |
|---|---:|---:|---:|
| Mohamed Belloumi | 597 | 655 | 58 |
| Haji Wright | 631 | 683 | 52 |
| Ephron Mason-Clark | 632 | 682 | 50 |
| Kyle Joseph | 608 | 658 | 50 |
| Merlin Rohl | 467 | 515 | 48 |

### Quality artifacts and remaining issues

Generated artifacts:

- `data/quality/draft_2627/draft_eligibility_report_2627.csv`: 688 populated player diagnostics;
- `data/quality/draft_2627/draft_identity_report_2627.csv`: 688 identity/history rows;
- `data/quality/draft_2627/draft_squad_coverage_2627.csv`: 20 club coverage rows;
- `data/quality/draft_2627/draft_override_report_2627.csv`: override diagnostics (header-only/empty when no override file is supplied);
- `reports/draft_analytics_sprint_3_1_comparison.csv`: before/after rankings.

Draft HQ now shows one concise, non-blocking warning when unresolved eligibility exists. It is based on producer status fields, gives the unresolved count, and explicitly distinguishes Fantrax FA from EPL eligibility.

Remaining weaknesses:

1. A populated 20-club current-player source is still required before anyone can be confirmed eligible or ineligible.
2. The 100 IDs with no 2025/26 record cannot yet be separated confidently into new arrival, promoted player, academy player, or linkage defect.
3. Historical names and Understat links remain at 415 even though 588 Fantrax historical IDs match.
4. Team and fixture context remain incomplete at 558 and 653 respectively.
5. Refresh/freshness metadata is available at club-cache level but is not yet a formal dataset contract.

Sprint 3.2 should focus on obtaining/validating the populated current-squad source and classifying the 100 no-record players, then improve minutes/role inputs for transfers, promoted players, academy players, and new arrivals. No scarcity or workflow features should precede that work.

### Sprint 3.1 verification

- Full suite: 216 tests passed in 13.29 seconds.
- New focused Draft producer coverage: 29 tests.
- AppTest: zero uncaught exceptions.
- Existing controls, six named sections, 200-row default board, filtered download, and page architecture boundary remain intact.
- The permitted warning reports 688 unresolved current-squad confirmations and does not block browsing.
- Default rebuilt top five: Bruno Fernandes, Dominik Szoboszlai, Erling Haaland, Virgil van Dijk, and Igor Thiago.
- Formula changes: none.
- Tier-method changes: none.
- ADP-method changes: none.
- UI changes: one minimal incomplete-eligibility warning; no layout changes.

## 19. Sprint 3.2 migration — Player Registry Foundation

Completed 2026-07-29. The reusable architecture is documented in `docs/PLAYER_REGISTRY_ARCHITECTURE.md`.

Official FPL replaced FootballData.io as the default current-player provider. The cached `bootstrap-static` snapshot contains 564 active players and all 20 target clubs. Refresh is an explicit operation; registry and Draft builds consume only the cached CSV.

The canonical registry contains 847 rows:

| Coverage | Count |
|---|---:|
| Active FPL players | 564 |
| Fantrax-linked rows | 688 |
| FPL-linked rows | 564 |
| Historical names / Understat links | 415 / 415 |
| Confirmed | 422 |
| Transferred | 76 |
| New EPL Arrival | 66 |
| Historical Only | 249 |
| FPL-only confirmed | 159 |
| Unresolved | 34 |

Current matching distribution:

| Method | Count | Confidence |
|---|---:|---:|
| Exact normalized name + club | 392 | 95 |
| Exact normalized name | 7 | 90 |
| Unique fuzzy within club | 6 | 75 |
| FPL-only identity | 159 | 97 |
| Unresolved current match | 283 | 0 |

The 283 unresolved current matches include 249 defensible `Historical Only` records and 34 fully unresolved rows. Ambiguous matches are not accepted.

Draft now consumes registry identity/current-team fields. Of 688 Fantrax rows, 439 remain draft-eligible (405 FPL-linked plus 34 conservatively included unresolved) and 249 Historical Only rows are excluded by default. The page warning consequently fell from 688 unresolved squad confirmations to 34 unresolved registry identities.

No Draft Score, production, team, fixture, confidence, rank, tier, or ADP formula changed. Ranking changes are input-population changes caused by replacing the incomplete squad source with the canonical FPL-backed registry.

Sprint 3.2 verification:

- 232 tests passed in 15.66 seconds, including new provider, cache, matcher, registry, ambiguity, transfer, deterministic-build, operation, and Draft-consumption tests.
- Draft HQ AppTest completed with zero uncaught exceptions.
- All existing controls, six named sections, filtered download, and default 200-row board remain.
- The remaining warning is non-blocking and reports 34 unresolved registry identities.
- The rebuilt eligible Draft population is 439; 249 Historical Only records are now excluded by default.
- `reports/player_registry_sprint_3_2_draft_comparison.csv` records the migration comparison.
- Current top five: Dominik Szoboszlai, Erling Haaland, Virgil van Dijk, Enzo Fernandez, and Cody Gakpo.
