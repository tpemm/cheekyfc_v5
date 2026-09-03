#!/usr/bin/env python3
"""Sanitized authenticated diagnostic for Fantrax Matchups/private requests."""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fantrax.live.config import load_live_season_config
from fantrax.live.weekly_acquisition import _auth_path


SENSITIVE = ("auth", "cookie", "credential", "password", "secret", "session", "token")


def _safe(value):
    if isinstance(value, dict):
        return {
            str(key): "[REDACTED]" if any(word in str(key).casefold() for word in SENSITIVE) else _safe(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_safe(item) for item in value]
    return value


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--period", type=int, default=1)
    parser.add_argument("--headed", action="store_true")
    parser.add_argument("--commit", action="store_true")
    args = parser.parse_args()
    config = load_live_season_config()
    league_id = config.require_league_id()
    auth = _auth_path(ROOT)
    if not auth.exists():
        print("Fantrax authentication required", file=sys.stderr)
        return 2

    from playwright.sync_api import sync_playwright

    executable = os.environ.get("FANTRAX_BROWSER_EXECUTABLE", "").strip()
    if not executable and os.name == "nt":
        candidates = (
            Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe"),
            Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"),
        )
        executable = str(next((path for path in candidates if path.exists()), ""))
    url = f"https://www.fantrax.com/fantasy/league/{league_id}/livescoring;period={args.period}"
    observations = []
    private_responses = []
    with sync_playwright() as playwright:
        launch = {"headless": not args.headed}
        if executable:
            launch["executable_path"] = executable
        browser = playwright.chromium.launch(**launch)
        context = browser.new_context(storage_state=str(auth))
        page = context.new_page()
        page.add_init_script("""() => {
            window.__fantraxLiveScoring = null;
            const originalFetch = window.fetch;
            window.fetch = async (...args) => {
                let body = typeof args[1]?.body === 'string' ? args[1].body : '';
                try { if (!body && args[0] instanceof Request) body = await args[0].clone().text(); } catch (_) {}
                const response = await originalFetch(...args);
                try { if (body.includes('getLiveScoringStats')) response.clone().json().then(data => { window.__fantraxLiveScoring = data; }); } catch (_) {}
                return response;
            };
        }""")
        cdp = context.new_cdp_session(page)
        cdp.send("Network.enable")
        scoring_request_ids = []
        def cdp_requested(event):
            request = event.get("request", {})
            if request.get("url", "").endswith("/fxpa/req") and "getLiveScoringStats" in request.get("postData", ""):
                scoring_request_ids.append(event["requestId"])
        cdp.on("Network.requestWillBeSent", cdp_requested)

        def observe(response):
            split = urlsplit(response.url)
            if split.hostname != "www.fantrax.com" or split.path != "/fxpa/req":
                return
            request_json = None
            try:
                request_json = response.request.post_data_json
            except Exception:
                pass
            observations.append({
                "method": response.request.method,
                "path": split.path,
                "status": response.status,
                "request": _safe(request_json),
            })
            private_responses.append(response)

        page.on("response", observe)
        page.goto(url, wait_until="domcontentloaded", timeout=60_000)
        page.wait_for_timeout(8_000)
        scoring_request = next(
            (
                item["request"] for item in observations
                if any(message.get("method") == "getLiveScoringStats" for message in (item.get("request") or {}).get("msgs", []))
            ),
            None,
        )
        scoring_response = None
        if scoring_request:
            scoring_index = next(
                index for index, item in enumerate(observations)
                if item.get("request") == scoring_request
            )
            try:
                scoring_response = {
                    "status": private_responses[scoring_index].status,
                    "data": private_responses[scoring_index].json(),
                }
            except Exception as exc:
                scoring_response = {"status": private_responses[scoring_index].status, "parse_error": type(exc).__name__}
        if scoring_request_ids and (not scoring_response or "data" not in scoring_response):
            try:
                network_body = cdp.send("Network.getResponseBody", {"requestId": scoring_request_ids[-1]})["body"]
                scoring_response = {"status": 200, "data": json.loads(network_body)}
            except Exception as exc:
                scoring_response = {"status": 200, "parse_error": f"CDP_{type(exc).__name__}"}
        browser_payload = page.evaluate("window.__fantraxLiveScoring")
        if browser_payload:
            scoring_response = {"status": 200, "data": browser_payload}
        result = {
            "authenticated": page.get_by_text("Login", exact=True).count() == 0,
            "league_id": league_id,
            "period": args.period,
            "page_path": urlsplit(page.url).path,
            "title": page.title(),
            "requests": observations,
            "scoring_response": _safe(scoring_response),
            "matchup_dom": page.locator("body").inner_text(),
        }
        output = config.quality_root / "fantrax_matchup_private_endpoint_diagnostic.json"
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        committed = None
        if args.commit and scoring_response and "data" in scoring_response:
            from fantrax.live.matchup_acquisition import commit_live_scoring
            committed = commit_live_scoring(scoring_response["data"], raw_root=config.raw_root, model_root=config.model_root, season_id=config.season_id, period=args.period)
        print(json.dumps({key: value for key, value in {**result, "requests": len(observations), "output": str(output.relative_to(ROOT)), "committed": committed}.items() if key not in {"scoring_response","matchup_dom"}}, ensure_ascii=False, indent=2))
        context.close()
        browser.close()
    return 0 if result["authenticated"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
