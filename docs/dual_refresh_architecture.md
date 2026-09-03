# Dual refresh architecture

## Core Refresh

The hosted Operations Center action **Refresh League** invokes only registered, bounded Fantrax/API acquisition and cached model builders. It does not import or execute WhoScored, Selenium, Chrome, or historical acquisition. Failed refreshes retain previously valid cache data. Schedule and other lightweight cache-derived products may be incorporated only through this same registered boundary.

## Weekly Advanced Refresh

WhoScored is a local commissioner workflow:

```powershell
.\.venv\Scripts\Activate.ps1
python scripts\weekly_advanced_refresh.py --season 2526 --session-backed
```

The workflow resolves the canonical schedule, selects only completed and provider-resolved matches, validates existing caches, acquires missing matches through isolated workers, writes a separate weekly manifest, rebuilds normalized/advanced products, and refreshes quality evidence. It handles blank, partial, double, postponed, and rescheduled gameweeks by selecting matches rather than assuming ten fixtures. Reruns are resumable because each valid match cache is skipped.

Use `--plan` to inspect coverage without opening Chrome or rebuilding models. Visible Chrome windows are expected. Keep the project computer awake until the summary is written.

## One-time historical acquisition

Planning command:

```powershell
python scripts\acquire_whoscored_season.py --season 2526
```

Authorized execution command for the future acquisition sprint:

```powershell
python scripts\acquire_whoscored_season.py --season 2526 --execute --session-backed
```

The target is the finalized 380-match Understat schedule joined exactly to 380 cached WhoScored provider IDs. Thirty existing valid caches are skipped. Successful matches persist independently, so the command may be rerun after interruption.

## Status and recovery

The Operations page derives Core, WhoScored, schedule/Understat, advanced-model, identity, and quality status from real files and manifests. The hosted page displays advanced status and the local command but exposes no scraper action.

If a weekly run is interrupted, rerun the same command. Do not delete valid match directories. Failed or invalid caches remain visible in the weekly acquisition manifest. Use force acquisition only for a specifically reviewed match.

## Promotion path

Raw atomic caches flow into normalized match, team-match, lineup, event, and player-match staging products. Provider IDs are resolved through the permanent identity layer. Manager-aware position, role, formation, spatial, and transparent team-event products follow. After full-season quality validation, an explicitly authorized promotion sprint may feed positional fantasy allowed, team matchup, and player matchup builders. Finalized 2025/26 production tables are not replaced automatically.

For 2026/27, generate the season manifest from the current completed schedule and run the same weekly command. Understat refresh remains a separate proven source workflow; WhoScored never fabricates xG/xA/xGI.
