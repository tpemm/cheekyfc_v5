"""Application-shell routing integration tests."""
from __future__ import annotations

from dataclasses import dataclass, field

import pytest

import core.legacy_renderer as shell
from core.services import SeasonManager
from views.registry import PAGE_REGISTRY


EXPECTED_NAVIGATION = (
    "League Hub",
    "2025/26 Season Archive",
    "Players",
    "Managers",
    "Cup Tournament",
    "Trades",
    "Weekly Reports",
    "History",
    "Draft HQ",
    "Award Detail",
    "Identity Review",
    "Operations Center",
    "Raw Data Browser",
    "Key Output Health",
    "Reports",
)

RENDERER_NAMES = {
    "League Hub": "render_live_league_hub",
    "2025/26 Season Archive": "render_league_hub",
    "Players": "render_players",
    "Trades": "render_coming_soon",
    "Weekly Reports": "render_coming_soon",
    "History": "render_coming_soon",
    "Award Detail": "render_awards",
    "Managers": "render_managers",
    "Cup Tournament": "render_cup_tournament",
    "Draft HQ": "render_draft_center",
    "Identity Review": "render_identity_review",
    "Operations Center": "render_update_pipeline",
    "Raw Data Browser": "render_raw_data_browser",
    "Key Output Health": "render_key_output_health",
    "Reports": "render_reports",
}


class _QueryParams(dict):
    def clear(self) -> None:
        super().clear()


@dataclass
class _Sidebar:
    owner: "_FakeUI"

    def selectbox(self, _label, options, *, index=0, **_kwargs):
        assert self.owner.season_label in options
        return self.owner.season_label

    def radio(self, _label, options, **_kwargs):
        assert self.owner.page in options
        return self.owner.page

    def __getattr__(self, _name):
        return lambda *_args, **_kwargs: None


@dataclass
class _FakeUI:
    season_label: str
    page: str
    session_state: dict = field(default_factory=dict)
    query_params: _QueryParams = field(default_factory=_QueryParams)

    def __post_init__(self):
        self.sidebar = _Sidebar(self)

    def __getattr__(self, _name):
        return lambda *_args, **_kwargs: None


def test_navigation_labels_and_order_are_unchanged():
    assert tuple(page.title for page in PAGE_REGISTRY) == EXPECTED_NAVIGATION


@pytest.mark.parametrize(
    ("season_id", "page"),
    [
        ("2526", "2025/26 Season Archive"),
        ("2627", "League Hub"),
        ("2627", "Players"),
        ("2627", "Cup Tournament"),
        ("2526", "Award Detail"),
        ("2526", "Managers"),
        ("2627", "Draft HQ"),
        ("2627", "Identity Review"),
        ("2627", "Operations Center"),
        ("2526", "Raw Data Browser"),
        ("2526", "Key Output Health"),
        ("2526", "Reports"),
    ],
)
def test_each_navigation_branch_invokes_exactly_one_renderer(
    monkeypatch, season_id, page
):
    manager = SeasonManager()
    context = manager.get(season_id)
    ui = _FakeUI(context.display_name, page)
    calls: list[tuple[str, str]] = []

    for label, renderer_name in RENDERER_NAMES.items():
        if renderer_name == "render_coming_soon":
            monkeypatch.setattr(shell, renderer_name, lambda title, selected_season: calls.append((title, selected_season)))
            continue
        monkeypatch.setattr(
            shell,
            renderer_name,
            lambda selected_season, label=label: calls.append(
                (label, selected_season)
            ),
        )

    shell.render_application(ui=ui, season_manager=manager)

    assert calls == [(page, season_id)]


def test_finalized_and_working_navigation_are_both_available():
    manager = SeasonManager()
    finalized = manager.get("2526")
    working = manager.get("2627")
    assert finalized.finalized and not finalized.mutable
    assert working.mutable and not working.finalized
