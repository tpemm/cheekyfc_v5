from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import requests


DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/150.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}


@dataclass
class DownloadResult:
    url: str
    path: Path
    status_code: int
    content_type: str
    bytes_written: int


class CachedSession:
    def __init__(
        self,
        raw_dir: Path,
        timeout: int = 45,
        delay_seconds: float = 1.0,
    ) -> None:
        self.raw_dir = Path(raw_dir)
        self.raw_dir.mkdir(parents=True, exist_ok=True)
        self.timeout = timeout
        self.delay_seconds = delay_seconds
        self.session = requests.Session()
        self.session.headers.update(DEFAULT_HEADERS)

    def download(
        self,
        url: str,
        filename: str,
        *,
        force: bool = False,
    ) -> DownloadResult:
        path = self.raw_dir / filename

        if path.exists() and not force:
            return DownloadResult(
                url=url,
                path=path,
                status_code=200,
                content_type="cached",
                bytes_written=path.stat().st_size,
            )

        response = self.session.get(url, timeout=self.timeout)
        response.raise_for_status()
        path.write_bytes(response.content)
        time.sleep(self.delay_seconds)

        return DownloadResult(
            url=url,
            path=path,
            status_code=response.status_code,
            content_type=response.headers.get("content-type", ""),
            bytes_written=len(response.content),
        )
