"""Audited Fantrax-to-FPL player name aliases for the 2026/27 registry."""

from __future__ import annotations

from analytics.draft.reliability import normalize_text


# Keep display names here so the source remains easy to review and audit.
PLAYER_ALIASES_2627: tuple[tuple[str, str], ...] = (
    ("Ehor Yarmolyuk", "Yehor Yarmoliuk"),
    ("Valentino Livramento", "Tino Livramento"),
    ("Djordje Petrovic", "Đorđe Petrović"),
    ("Danny Ballard", "Daniel Ballard"),
    ("Eli Kroupi", "Junior Kroupi"),
    ("Mateus Goncalo Espanha Fernandes", "Mateus Fernandes"),
    ("Reinildo", "Reinildo Mandava"),
    ("Alisson", "Alisson Becker"),
    ("Richarlison", "Richarlison de Andrade"),
)


PLAYER_ALIAS_LOOKUP_2627: dict[str, str] = {
    normalize_text(source_name): normalize_text(target_name)
    for source_name, target_name in PLAYER_ALIASES_2627
}
