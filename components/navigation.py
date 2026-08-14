"""Navigation helpers shared by the v5 application shell."""
from __future__ import annotations

from collections.abc import Iterable

from views.registry import PageDefinition


def page_titles(pages: Iterable[PageDefinition]) -> list[str]:
    return [page.title for page in pages]
