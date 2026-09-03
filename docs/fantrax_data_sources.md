# Fantrax data-source inventory

## 2026/27 source policy

Intentional refreshes may contact Fantrax. Builds and Streamlit pages may only read validated cache/model files. The 2026/27 league ID is supplied through `FANTRAX_LEAGUE_ID_2627`; the hard-coded `rg1i70pfmdhjhvn3` references belong to the retired 2025/26 tooling and are not reused.

Authentication state is local-only. `.env`, `.streamlit/secrets.toml`, `data/raw`, `raw_data`, and `*auth_state*.json` are ignored. Never commit cookies, passwords, session storage, or the value of an authentication token.

## Repository acquisition inventory

| Component | Purpose | Input | Output/cache | HTTP/auth | Assumptions | Status and next action |
|---|---|---|---|---|---|---|
| `fantrax/api/fetch_fantrax_api_data.py` | League info, standings, roster periods | league ID, periods | legacy `raw_data/fantrax_api` JSON | Fantrax JSON; no login observed | hard-coded 2025/26 ID; 1–38 | Reusable with modification. Endpoint evidence powers `fantrax.live.acquisition`; legacy writer deprecated for 2627. |
| `fantrax/api/transform_fantrax_api_json.py` | Flatten league, matchups, standings, player info, roster/scoring settings | legacy cached JSON | legacy processed CSV | none | legacy response shape/path | Reusable as shape reference. Replaced for 2627 by pure live normalizers. |
| `fantrax/api/fetch_fantrax_api_player_ids_epl.py` and `flatten_fantrax_api_player_lookup.py` | EPL Fantrax identity lookup | `getPlayerIds?sport=EPL` | legacy lookup JSON/CSV | Fantrax JSON; no login observed | global EPL pool | Reusable with modification; current Player Registry/current player-pool export remains preferred until the endpoint is revalidated. |
| `fantrax/api/validate_fantrax_api_layer.py` | Legacy API roster, matchup, standings checks | transformed legacy CSV | validation CSV/text | none | 2025/26 columns | Reusable rule reference; replaced by live validators. |
| `fantrax/api/build_*bridge*.py` | Connect API player IDs to master IDs | API lookup/rosters/master | reference bridge/review files | none | 2025/26 identity model | Deprecated for new live data. Use Player Registry and Identity Review. |
| `fantrax/api/merge_master_with_api_rosters_v2.py` | 2025/26 manager-player, matchup, manager-week gold tables | master weekly/API roster/matchup/bridge | processed 2526 tables | none | 2025/26 columns and IDs | Reusable analytics reference only. Do not run against finalized 2526 or use as 2627 producer. |
| `fantrax/scraping/scrape_allplayers_weekly_fantrax.py` | Weekly all-player CSV export | browser league page/GW | `data/raw/fantrax/all_players_weekly` | Playwright; saved login/2FA | old league ID and dates | Proven fallback, reusable after centralized configuration and 2627 browser verification. Not called by normal builds/pages. |
| `fantrax/scraping/scrape_team_rosters_weekly_fantrax.py` | Weekly team roster/lineup CSV exports | 12 browser team pages/GW | `data/raw/fantrax/team_rosters_weekly` | Playwright; saved login/2FA | old league/team IDs, 2526 managers | Reusable with modification. Team IDs must first come from validated 2627 league metadata. |
| `fantrax/refresh/refresh_weekplayer_rawdata.py` | Coordinate weekly browser/Understat/master refresh | interactive mode/GWs | 2526 raw/processed outputs | invokes network scrapers | `SEASON_ID=2526` | Deprecated for 2627; retained for historical reference. |
| `fantrax/refresh/refresh_all_fantrax_data.py` | Legacy end-to-end refresh | interactive mode | 2526 raw, transformed, analytics, report | API + browser + Understat | hard-coded 2526 league | Deprecated for 2627; remains registered only for existing workflow compatibility. |
| `fantrax/analytics/build_master_weekly.py` and analytics builders | Weekly stats and manager analytics | cached weekly CSV/Understat | processed/analytics tables | none | 2526 schemas | Reusable with modification after 2627 weekly stats arrive. Existing League Hub definitions remain authoritative. |
| `analytics/draft/adp_refresh.py` | Validate replacement player-pool export | uploaded/current CSV | caller-controlled validated frame | none | preseason export aliases | Reusable for current player-pool import; must never target the frozen draft snapshot. |
| `data/reference/current_fantrax_player_pool_2627.csv` | Current 2627 player pool | validated Fantrax CSV export | registered reference CSV | manual/export refresh | preseason/current snapshot | Current authoritative player-pool fallback. Keep draft-day snapshot separate. |
| `archive/old_apps` and `archive/old_scripts` | Earlier UI, roster merge, weekly files | legacy files | archive only | unknown/mixed | obsolete paths | Deprecated; never production operations. |
| `fantrax/finalize/*2526.py` | Freeze historical 2025/26 data | working 2526 outputs | `data/seasons/2526` | none | completed 2526 | Historical-only and protected. Never run for live refresh. |
| `fantrax/live/*` and `scripts/refresh_live_fantrax.py` | Validated 2627 raw cache and normalized live models | external league ID; proven API responses | `data/raw/fantrax/2627`, `data/models/season_2627`, quality reports | refresh module only | centralized 2627 config | Current foundation. Transactions/player-pool browser automation intentionally pending proof. |

## Authoritative source matrix

| Domain | Primary | Fallback | Method / expected content | Frequency | Limitation |
|---|---|---|---|---|---|
| League metadata | `getLeagueInfo` | saved league settings export/manual inspection | JSON: league, teams, roster/draft/scoring settings, matchup schedule | before season; after settings changes | 2627 response must be captured and shape-verified |
| Manager/team metadata | teams within `getLeagueInfo` | standings/team roster export | manager/team IDs and names, draft slot | weekly or on rename | manager IDs may vary by payload shape |
| Current rosters | `getTeamRosters` latest period | proven team roster CSV exporter | team/player IDs, status, eligibility | daily/after transactions | API lineup labels require 2627 verification |
| Player ownership | normalized current rosters | current player-pool CSV | one owner/status per player | with roster refresh | complete free-agent rows require player pool |
| Free-agent status | current player-pool CSV | all-player weekly export | ownership/availability/status | daily/weekly | not supplied by proven league endpoints |
| Weekly lineups | period `getTeamRosters` | team roster weekly CSV | starter/bench/IR state | after lineup lock/final | API status vocabulary needs observation |
| Matchups | `getLeagueInfo.matchups` | Fantrax matchup export/manual cache | period, home/away IDs | schedule change; weekly scores if present | scores may require separate proven export |
| Scores | completed matchup payload or roster starter totals later | matchup CSV | home/away score | after each period | source shape not yet captured for 2627 |
| Standings | `getStandings` | Fantrax standings export | rank, record, points for/against | daily/weekly | actual scoring terminology is preserved; fields not fabricated |
| Transactions/adds/drops/trades | validated Fantrax transaction export when supplied | browser export after proof | IDs, timestamp, type, sides, bid/priority | daily | no proven endpoint/scraper currently exists; automation blocked |
| Player pool | registered current Fantrax export | proven all-player browser CSV | IDs, names, club, eligibility, ADP, projection, ownership | daily/weekly | refresh adapter still needed |
| Scoring-period history | cached roster/matchup periods | proven weekly CSV archives | period-level roster, lineup, score | after each period | historical API availability must be verified |
| Draft results | registered completed-draft import/frozen outputs | Fantrax draft export if later captured | overall pick, manager, player | immutable post-draft | existing Draft HQ artifacts remain authoritative |

No undocumented Fantrax transaction endpoint has been added.
# 2026/27 live endpoint validation — 2026-08-03

League `o1wb36vdmrp1z5t8` responded successfully without cookies, a Fantrax user-secret ID, or another authenticated credential. The proven project endpoints returned:

- `getLeagueInfo`: HTTP success; object with league dates/settings, 12-entry `teamInfo`, 697-entry `playerInfo`, and 38 scoring, roster, and matchup periods.
- `getStandings`: HTTP success; list with 12 standings rows.
- `getTeamRosters?period=1`: HTTP success; object containing `period` and a 12-team `rosters` map. Each team has `teamName`, `salaryCap`, and `rosterItems`; roster items use `id`, `position`, and `status`.

The response is public for this league. The normalizer supports this observed shape while retaining the pre-existing fixture shape. No undocumented endpoints were introduced.
# 2026/27 player performance

The modern API audit is recorded in `fantrax_player_stats_audit.md`. Only `getLeagueInfo`, `getStandings`, and `getTeamRosters` are proven. Weekly fantasy/event values remain `EXPORT_FALLBACK`; xG/xA/xGI remain `UNDERSTAT_PRIMARY`. A scoring definition from `getLeagueInfo` must not be mistaken for player-stat observations.

Understat is also an approved supplemental factual source for appearances, minutes, goals, assists, shots, key passes, and cards. Present Fantrax values—including zero—win. Understat never supplies fantasy points, Ghost Points, or Fantrax-only defensive/scoring events.

The 2026/27 weekly source is the proven authenticated Players/team-roster CSV export, now stored transactionally per Fantrax period. Normal refresh is incremental; full missing-period acquisition is an explicit advanced backfill.
# Fixture-period use

`getLeagueInfo.scoringPeriods` is authoritative for mapping match timestamps into Fantrax periods. Nominal Premier League gameweek is not a substitute. The cached file audited on 2026-08-19 contains 2025/26 dates and is rejected for 2026/27 mapping.

The active source is now the validated live-season cache for league `o1wb36vdmrp1z5t8`, refreshed by `scripts/refresh_live_fantrax.py` and materialized as `data/reference/fantrax_scoring_periods_2627.csv`. The retired `raw_data/fantrax_api/league_info.json` is not used.

Fantrax remains the fantasy and scoring-period authority; it is not the season-schedule authority. Cached soccerdata Sofascore fixtures are mapped into Fantrax periods strictly by kickoff timestamp.

Fantrax completed player-period facts are the sole fantasy input to positional production allowed. Supplemental xG or tactical sources never overwrite Fantrax fantasy points or Ghost values.
# WhoScored supplemental boundary

WhoScored does not replace Fantrax scoring. Exact match alignment is allowed
only for a club with one fixture in the Fantrax period; multi-fixture periods
remain ambiguous unless a match-granular Fantrax source is available.
