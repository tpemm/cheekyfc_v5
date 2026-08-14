from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pandas as pd
from bs4 import BeautifulSoup, Tag


TEAM_HEADING_RE = re.compile(r"^(.*?)\s+Predicted Lineup$", re.I)
DATE_RE = re.compile(r"Lineup Last Updated:\s*(.+)", re.I)
FIXTURE_RE = re.compile(r"Fixture\s*[–-]\s*(.*?)\s*\(([HhAa])\)", re.I)
PAGE_DATE_RE = re.compile(r"Page Last Updated:\s*(.+)", re.I)


def clean_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def parse_percent(value: str) -> float | None:
    text = clean_text(value)
    if not text or text.upper() == "TBD":
        return None
    match = re.search(r"(\d+(?:\.\d+)?)", text)
    return float(match.group(1)) if match else None


def _next_table(heading: Tag, *, skip: int = 0) -> Tag | None:
    count = 0
    for node in heading.find_all_next():
        if node.name in {"h2", "h3"}:
            break
        if node.name == "table":
            if count == skip:
                return node
            count += 1
    return None


def _table_rows(table: Tag | None) -> list[list[str]]:
    if table is None:
        return []
    rows: list[list[str]] = []
    for tr in table.find_all("tr"):
        cells = [clean_text(td.get_text(" ", strip=True)) for td in tr.find_all(["th", "td"])]
        if cells:
            rows.append(cells)
    return rows


def parse_predicted_lineups(path: Path) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    html = path.read_text(encoding="utf-8", errors="ignore")
    soup = BeautifulSoup(html, "html.parser")
    page_text = clean_text(soup.get_text(" ", strip=True))

    page_updated = None
    match = PAGE_DATE_RE.search(page_text)
    if match:
        page_updated = clean_text(match.group(1).split(" Arsenal Predicted Lineup")[0])

    player_records: list[dict[str, Any]] = []
    team_records: list[dict[str, Any]] = []
    warnings: list[str] = []

    headings = []
    for heading in soup.find_all(["h2", "h3"]):
        match = TEAM_HEADING_RE.match(clean_text(heading.get_text(" ", strip=True)))
        if match:
            headings.append((heading, clean_text(match.group(1))))

    for heading, team in headings:
        section_parts: list[str] = []
        for node in heading.find_all_next():
            if node is not heading and node.name in {"h2", "h3"}:
                break
            if isinstance(node, Tag):
                text = clean_text(node.get_text(" ", strip=True))
                if text:
                    section_parts.append(text)
        section_text = " ".join(section_parts)

        lineup_updated = None
        updated_match = DATE_RE.search(section_text)
        if updated_match:
            lineup_updated = clean_text(
                updated_match.group(1).split("Fixture")[0]
            )

        opponent = None
        home_away = None
        fixture_match = FIXTURE_RE.search(section_text)
        if fixture_match:
            opponent = clean_text(fixture_match.group(1))
            home_away = fixture_match.group(2).upper()

        first_table = _next_table(heading, skip=0)
        second_table = _next_table(heading, skip=1)

        starter_rows = _table_rows(first_table)
        potential_rows = _table_rows(second_table)

        def add_rows(rows: list[list[str]], status: str) -> int:
            added = 0
            for row in rows:
                if not row:
                    continue
                if row[0].lower() in {"player", "potential starters"}:
                    continue
                if len(row) < 2:
                    continue

                player = clean_text(row[0])
                position = clean_text(row[1]) if len(row) > 1 else ""
                start_text = clean_text(row[2]) if len(row) > 2 else ""

                if not player or player.lower() in {"pos", "start %"}:
                    continue

                player_records.append(
                    {
                        "source": "Fantasy Football Pundit",
                        "team": team,
                        "player": player.title() if player.isupper() else player,
                        "position": position,
                        "lineup_status": status,
                        "predicted_starter": status == "Predicted Starter",
                        "potential_starter": status == "Potential Starter",
                        "start_percent_text": start_text,
                        "start_percent": parse_percent(start_text),
                        "opponent": opponent,
                        "home_away": home_away,
                        "lineup_last_updated": lineup_updated,
                        "page_last_updated": page_updated,
                    }
                )
                added += 1
            return added

        starter_count = add_rows(starter_rows, "Predicted Starter")
        potential_count = add_rows(potential_rows, "Potential Starter")

        if starter_count != 11:
            warnings.append(
                f"{team}: expected 11 predicted starters, parsed {starter_count}."
            )

        team_records.append(
            {
                "team": team,
                "opponent": opponent,
                "home_away": home_away,
                "predicted_starters": starter_count,
                "potential_starters": potential_count,
                "lineup_last_updated": lineup_updated,
                "page_last_updated": page_updated,
            }
        )

    players = pd.DataFrame(player_records)
    teams = pd.DataFrame(team_records)

    summary = {
        "teams_found": int(len(teams)),
        "players_found": int(len(players)),
        "predicted_starters_found": int(
            players["predicted_starter"].sum()
        ) if not players.empty else 0,
        "potential_starters_found": int(
            players["potential_starter"].sum()
        ) if not players.empty else 0,
        "page_last_updated": page_updated,
        "warnings": warnings,
    }
    return players, teams, summary


def parse_fixture_page(path: Path) -> tuple[pd.DataFrame, dict[str, Any]]:
    """
    Parse ordinary HTML tables from the fixture page or its downloaded iframe.

    The site currently embeds its fixture planner. If the embedded document
    renders as a table, pandas.read_html will capture it. If it is a Google
    visualization requiring JavaScript, the report will clearly flag that so
    we can add a dedicated Google Sheets export parser next.
    """
    try:
        tables = pd.read_html(str(path))
    except ValueError:
        tables = []

    usable: list[pd.DataFrame] = []
    for index, table in enumerate(tables):
        table = table.copy()
        table.columns = [clean_text(c) for c in table.columns]
        table.insert(0, "table_index", index)
        usable.append(table)

    if not usable:
        return pd.DataFrame(), {
            "tables_found": 0,
            "rows_found": 0,
            "warning": (
                "No static fixture table was found. Inspect the iframe URL in "
                "pundit_page_inventory.json; it may require a Google Sheets "
                "CSV export or browser rendering."
            ),
        }

    combined = pd.concat(usable, ignore_index=True, sort=False)
    return combined, {
        "tables_found": len(usable),
        "rows_found": int(len(combined)),
        "columns": list(combined.columns),
    }
