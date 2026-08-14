"""Intentional network boundary for proven Fantrax JSON endpoints only."""

from __future__ import annotations

import json
from typing import Any, Callable
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from urllib.error import HTTPError


BASE_URL = "https://www.fantrax.com/fxea/general"
PROVEN_ENDPOINTS = {
    "league_metadata": "getLeagueInfo",
    "standings": "getStandings",
    "rosters": "getTeamRosters",
}


class FantraxAccessError(PermissionError):
    """The proven endpoint requires league visibility or supported credentials."""


def fetch_json(request_type: str, league_id: str, *, period: int | None = None, timeout: int = 30, opener: Callable[..., Any] = urlopen) -> Any:
    try:
        endpoint = PROVEN_ENDPOINTS[request_type]
    except KeyError as exc:
        raise ValueError(f"No proven Fantrax endpoint is registered for {request_type!r}") from exc
    parameters: dict[str, Any] = {"leagueId": league_id}
    if request_type == "rosters":
        if period is None:
            raise ValueError("Roster refresh requires a scoring period")
        parameters["period"] = int(period)
    request = Request(
        f"{BASE_URL}/{endpoint}?{urlencode(parameters)}",
        headers={"User-Agent": "FantraxDataV5/7.0", "Accept": "application/json"},
    )
    try:
        with opener(request, timeout=timeout) as response:
            payload=json.loads(response.read().decode("utf-8"))
            status=getattr(response,"status",None) or getattr(response,"getcode",lambda:None)()
            shape=f"object keys={list(payload)[:12]}" if isinstance(payload,dict) else f"list rows={len(payload)}"
            print(f"FANTRAX_RESPONSE endpoint={endpoint} status={status or 'success'} shape={shape}")
            return payload
    except HTTPError as exc:
        if exc.code in {401,403}:
            raise FantraxAccessError(
                f"Fantrax returned HTTP {exc.code}. Confirm the league is public or configure a supported authenticated session credential."
            ) from exc
        raise


def validate_api_payload(payload: Any) -> None:
    if not isinstance(payload, (dict, list)) or not payload:
        raise ValueError("Fantrax response is empty or has an unexpected shape")
    if isinstance(payload, dict) and payload.get("error"):
        raise ValueError(f"Fantrax returned an error: {payload['error']}")
