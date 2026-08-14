from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests
from dotenv import load_dotenv


BASE_URL = "https://footballdata.io/api/v1"


class FootballDataError(RuntimeError):
    """Raised when Footballdata.io returns an unusable response."""


def find_api_key() -> str:
    load_dotenv()

    candidates = [
        "FOOTBALLDATA_API_KEY",
        "FOOTBALL_DATA_API_KEY",
        "FOOTBALLDATA_IO_API_KEY",
        "FOOTBALL_DATA_IO_API_KEY",
    ]

    for name in candidates:
        value = os.getenv(name)
        if value and value.strip():
            return value.strip()

    raise FootballDataError(
        "No Footballdata.io API key was found. Add one of these to .env:\n"
        "FOOTBALLDATA_API_KEY=your_key\n"
        "FOOTBALL_DATA_API_KEY=your_key"
    )


@dataclass
class RequestResult:
    payload: dict[str, Any]
    requests_used: int | None
    requests_limit: int | None
    requests_remaining: int | None


class FootballDataClient:
    def __init__(
        self,
        api_key: str | None = None,
        timeout_seconds: int = 45,
        pause_seconds: float = 0.25,
        max_retries: int = 3,
    ) -> None:
        self.api_key = api_key or find_api_key()
        self.timeout_seconds = timeout_seconds
        self.pause_seconds = pause_seconds
        self.max_retries = max_retries
        self.session = requests.Session()
        self.session.headers.update(
            {
                "Authorization": f"Bearer {self.api_key}",
                "Accept": "application/json",
                "User-Agent": "Fantrax-Data-v4/1.0",
            }
        )

    def get(
        self,
        path: str,
        params: dict[str, Any] | None = None,
    ) -> RequestResult:
        url = f"{BASE_URL}{path}"

        last_error: Exception | None = None

        for attempt in range(1, self.max_retries + 1):
            try:
                response = self.session.get(
                    url,
                    params=params,
                    timeout=self.timeout_seconds,
                )

                if response.status_code == 429:
                    retry_after = float(response.headers.get("Retry-After", 2))
                    time.sleep(max(retry_after, 1))
                    continue

                response.raise_for_status()
                payload = response.json()

                if not isinstance(payload, dict):
                    raise FootballDataError(
                        f"Expected JSON object from {url}"
                    )

                if payload.get("success") is False:
                    raise FootballDataError(
                        f"API reported failure for {url}: {payload}"
                    )

                meta = payload.get("meta") or {}

                if self.pause_seconds:
                    time.sleep(self.pause_seconds)

                return RequestResult(
                    payload=payload,
                    requests_used=_to_int(meta.get("requests_used")),
                    requests_limit=_to_int(meta.get("requests_limit")),
                    requests_remaining=_to_int(meta.get("requests_remaining")),
                )

            except (
                requests.RequestException,
                ValueError,
                FootballDataError,
            ) as exc:
                last_error = exc

                if attempt < self.max_retries:
                    time.sleep(attempt * 1.5)
                    continue

        raise FootballDataError(
            f"Request failed after {self.max_retries} attempts: "
            f"{url} params={params}. Last error: {last_error}"
        )

    def account_usage(self) -> RequestResult:
        return self.get("/account/usage")

    def season_teams(
        self,
        season_id: int,
        page: int = 1,
        limit: int = 100,
    ) -> RequestResult:
        return self.get(
            f"/seasons/{season_id}/teams",
            {"page": page, "limit": limit},
        )

    def team_players(
        self,
        team_id: int,
        season_id: int | None = None,
        page: int = 1,
        limit: int = 100,
    ) -> RequestResult:
        params: dict[str, Any] = {
            "page": page,
            "limit": limit,
        }
        if season_id is not None:
            params["season_id"] = season_id

        return self.get(
            f"/teams/{team_id}/players",
            params,
        )

    def team_stats(
        self,
        team_id: int,
        season_id: int,
    ) -> RequestResult:
        return self.get(
            f"/teams/{team_id}/stats",
            {"season_id": season_id},
        )

    def season_matches(
        self,
        season_id: int,
        page: int = 1,
        limit: int = 100,
    ) -> RequestResult:
        return self.get(
            f"/seasons/{season_id}/matches",
            {"page": page, "limit": limit},
        )


def save_json(payload: dict[str, Any], path: str | Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    temporary.replace(path)


def load_json(path: str | Path) -> dict[str, Any]:
    path = Path(path)
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)

    if not isinstance(payload, dict):
        raise FootballDataError(f"Expected JSON object in {path}")

    return payload


def pagination_total_pages(payload: dict[str, Any]) -> int:
    meta = payload.get("meta") or {}
    pagination = meta.get("pagination") or {}

    value = _to_int(pagination.get("total_pages"))
    return max(value or 1, 1)


def _to_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
