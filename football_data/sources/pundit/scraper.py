from __future__ import annotations

from pathlib import Path
from typing import Any

from bs4 import BeautifulSoup

from football_data.common.http import CachedSession
from football_data.sources.pundit.config import PAGES


def scrape_pages(raw_dir: Path, *, force: bool = False) -> dict[str, Any]:
    client = CachedSession(raw_dir=raw_dir)
    inventory: dict[str, Any] = {}

    for name, url in PAGES.items():
        result = client.download(url, f"{name}.html", force=force)
        inventory[name] = {
            "url": url,
            "file": str(result.path),
            "status_code": result.status_code,
            "content_type": result.content_type,
            "bytes": result.bytes_written,
        }

        # Save any iframe targets found on the page. This is especially
        # important for the fixture planner, which may be embedded.
        soup = BeautifulSoup(result.path.read_text(encoding="utf-8", errors="ignore"), "html.parser")
        iframe_urls = [
            frame.get("src")
            for frame in soup.find_all("iframe")
            if frame.get("src")
        ]
        inventory[name]["iframes"] = iframe_urls

        for index, iframe_url in enumerate(iframe_urls, start=1):
            if iframe_url.startswith("//"):
                iframe_url = "https:" + iframe_url
            elif iframe_url.startswith("/"):
                iframe_url = PAGES["home"].rstrip("/") + iframe_url

            try:
                iframe_result = client.download(
                    iframe_url,
                    f"{name}_iframe_{index}.html",
                    force=force,
                )
                inventory[name].setdefault("iframe_files", []).append(
                    {
                        "url": iframe_url,
                        "file": str(iframe_result.path),
                        "bytes": iframe_result.bytes_written,
                    }
                )
            except Exception as exc:
                inventory[name].setdefault("iframe_errors", []).append(
                    {"url": iframe_url, "error": f"{type(exc).__name__}: {exc}"}
                )

    return inventory
