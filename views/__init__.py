"""Page registration package for Fantrax Data v5."""

from .registry import PAGE_REGISTRY, PageDefinition, get_page, pages_for_season

__all__ = ["PAGE_REGISTRY", "PageDefinition", "get_page", "pages_for_season"]
