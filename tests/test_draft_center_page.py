from datetime import datetime, timezone
from io import StringIO
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import numpy as np
import pytest
import streamlit as st

from core.models.data_result import DataProvenance, DataResult, DataStatus
from core.services.dataset_registry import DatasetRegistry
from views.draft_center import DATASET_KEYS, render
from views.draft_workspace import (
    POINT_DISPLAY_FIELDS,
    POST_DRAFT_DATASET_KEYS,
    _board_table,
    _column_config,
    _detail,
    _apply_player_button,
    _open_compare,
    _render_compare,
    prepare_draft_frame,
)


def test_installed_streamlit_supports_row_button_column():
    import inspect
    assert hasattr(st.column_config, "ButtonColumn")
    signature = inspect.signature(st.column_config.ButtonColumn)
    assert {"on_click", "key", "type", "pinned", "width"}.issubset(signature.parameters)


def test_player_button_resolves_exact_sorted_or_filtered_stable_key(monkeypatch):
    fake_st = SimpleNamespace(session_state={"click": {"row": 1, "label": "Second"}})
    monkeypatch.setattr("views.draft_workspace.st", fake_st)
    _apply_player_button("click", ["registry_player_id:sorted-first", "registry_player_id:sorted-second"])
    assert fake_st.session_state["draft_detail_player_key"] == "registry_player_id:sorted-second"
    assert fake_st.session_state["draft_detail_dialog_open"] is True


def test_historical_start_and_minutes_percent_are_distinct_from_outlook():
    raw = draft_rankings().assign(minutes_2526=[3420, 1710, 0], start_rate_2526=[1, .5, 0])
    frame = prepare_draft_frame(raw, {})
    assert frame["historical_start_pct_2526"].tolist() == [100, 50, 0]
    assert frame["historical_minutes_pct_2526"].tolist() == [100, 50, 0]
    assert frame["minutes_outlook"].tolist() == raw["minutes_outlook"].tolist()


def test_default_board_exact_decision_columns_and_point_modes():
    raw = draft_rankings().assign(
        fantasy_points_2526=[200, 300, 180], ghost_points_2526=[100, 120, 110],
        understat_xg_2526=[2, 8, 4], understat_xa_2526=[3, 2, 5],
        understat_minutes_2526=[1800, 2000, 1600], minutes_2526=[1800, 2000, 1600],
        starts_2526=[20, 22, 18], weeks_available=[25, 25, 25],
    )
    frame = prepare_draft_frame(raw, {})
    expected_tail = ["Club · Pos", "Tier", "Draft Score", "ADP", "Projected Points", "Start % 25/26", "Minutes % 25/26", "Minutes Outlook", "Points", "Ghost", "xGI", "Team Strength %", "Next 5 Fixture Ease %"]
    board = _board_table(frame)
    assert board.columns[:5].tolist() == ["Rank", "Player", "Club · Pos", "Mine", "Other"]
    assert board.columns[5:].tolist() == expected_tail[1:]
    assert "Value vs ADP" not in board
    assert "Projected Minutes %" not in board
    for mode, fields in POINT_DISPLAY_FIELDS.items():
        switched = _board_table(frame, point_mode=mode)
        assert all(label in switched for _, label in fields)


def test_touched_views_have_no_deprecated_container_width():
    for path in ("views/draft_workspace.py", "views/draft_center.py", "views/identity_review.py"):
        assert "use_container_width" not in Path(path).read_text(encoding="utf-8")


def test_draft_action_columns_have_unclipped_widths():
    config = _column_config(FakeUI())
    assert config["Mine"][2]["width"] >= 68
    assert config["Other"][2]["width"] >= 72
    assert config["Mine"][2]["pinned"] is True
    assert config["Other"][2]["pinned"] is True


def test_minutes_help_matches_authoritative_builder_rules():
    source = Path("views/draft_workspace.py").read_text(encoding="utf-8")
    for text in ("40% full-season minutes share", "30% last-six minutes share", "minus 8 points", "≤20 Bench / Unknown", ">84 Locked Starter", "at least 2,200", "subtracts 15"):
        assert text in source


class StopSignal(RuntimeError):
    pass


class FakeColumn:
    def __init__(self, ui):
        self.ui = ui

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def markdown(self, value, **kwargs):
        self.ui.markdown(value, **kwargs)

    def columns(self, spec, **kwargs):
        return self.ui.columns(spec, **kwargs)

    def __getattr__(self, name):
        return getattr(self.ui, name)


class FakeColumnConfig:
    @staticmethod
    def NumberColumn(*args, **kwargs):
        return ("number", args, kwargs)

    @staticmethod
    def TextColumn(*args, **kwargs):
        return ("text", args, kwargs)

    @staticmethod
    def ProgressColumn(*args, **kwargs):
        return ("progress", args, kwargs)

    @staticmethod
    def LinkColumn(*args, **kwargs):
        return ("link", args, kwargs)

    @staticmethod
    def CheckboxColumn(*args, **kwargs):
        return ("checkbox", args, kwargs)


class FakeUI:
    column_config = FakeColumnConfig()

    def __init__(self, values=None):
        self.values = values or {}
        self.markdowns = []
        self.captions = []
        self.warnings = []
        self.errors = []
        self.infos = []
        self.writes = []
        self.tables = []
        self.downloads = []
        self.controls = []
        self.session_state = {}

    def markdown(self, value, **kwargs):
        self.markdowns.append(str(value))

    def caption(self, value):
        self.captions.append(str(value))

    def warning(self, value):
        self.warnings.append(str(value))

    def error(self, value):
        self.errors.append(str(value))

    def info(self, value):
        self.infos.append(str(value))

    def write(self, value):
        self.writes.append(value)

    def stop(self):
        raise StopSignal()

    def columns(self, spec, **kwargs):
        count = spec if isinstance(spec, int) else len(spec)
        return [FakeColumn(self) for _ in range(count)]

    def text_input(self, label, **kwargs):
        self.controls.append(("text_input", label, kwargs))
        return self.values.get(label, "")

    def multiselect(self, label, options, default=None, **kwargs):
        self.controls.append(("multiselect", label, kwargs))
        return self.values.get(label, list(default or []))

    def slider(self, label, min_value, max_value, value, **kwargs):
        self.controls.append(("slider", label, kwargs))
        return self.values.get(label, value)

    def selectbox(self, label, options, index=0, **kwargs):
        values = list(options)
        self.controls.append(("selectbox", label, kwargs))
        return self.values.get(label, values[index])

    def checkbox(self, label, value=False, **kwargs):
        self.controls.append(("checkbox", label, kwargs))
        return self.values.get(label, value)

    def dataframe(self, data, **kwargs):
        self.tables.append((data.copy(), kwargs))
        return None

    def download_button(self, label, **kwargs):
        self.downloads.append((label, kwargs))

    def expander(self, *args, **kwargs):
        return FakeColumn(self)

    def tabs(self, labels):
        self.controls.append(("tabs", tuple(labels), {}))
        return [FakeColumn(self) for _ in labels]

    def button(self, label, **kwargs):
        self.controls.append(("button", label, kwargs))
        return self.values.get(label, False)

    def metric(self, label, value, **kwargs):
        self.controls.append(("metric", label, {"value": value, **kwargs}))

    def rerun(self):
        self.controls.append(("rerun", "rerun", {}))


class FakeSeasonManager:
    def __init__(self, namespace="working", finalized=False, invalid=False):
        self.namespace = namespace
        self.finalized = finalized
        self.invalid = invalid
        self.context_calls = []
        self.namespace_calls = []

    def context(self, season_id):
        self.context_calls.append(season_id)
        if self.invalid:
            raise KeyError(f"Unknown season ID: {season_id!r}")
        return SimpleNamespace(
            season_id=season_id,
            finalized=self.finalized,
        )

    def resolve_namespace(self, season_id):
        self.namespace_calls.append(season_id)
        return self.namespace


class FakeDataManager:
    def __init__(self, rankings=None, overrides=None, results=None):
        self.frames = {
            "draft_rankings": (
                draft_rankings() if rankings is None else rankings
            ),
            "draft_eligibility_overrides": (
                pd.DataFrame() if overrides is None else overrides
            ),
            "current_fantrax_player_pool": pd.DataFrame(),
        }
        self.results = results or {}
        self.calls = []

    def load_frame(self, key, season_id, namespace):
        self.calls.append((key, season_id, namespace))
        if key in self.results:
            return self.results[key]
        frame = self.frames[key]
        status = DataStatus.EMPTY if frame.empty else DataStatus.AVAILABLE
        return make_result(key, frame, status=status, namespace=namespace)


def make_result(
    key,
    data,
    *,
    status=DataStatus.AVAILABLE,
    namespace="working",
    errors=(),
):
    return DataResult(
        status=status,
        data=data,
        provenance=DataProvenance(
            dataset_key=key,
            requested_key=key,
            season_id="2627",
            namespace=namespace,
            resolved_path=Path(f"/project/{namespace}/{key}.csv"),
            format="csv",
            modified_time=datetime(2026, 7, 29, tzinfo=timezone.utc),
            size_bytes=128,
        ),
        validation_errors=errors,
    )


def draft_rankings():
    return pd.DataFrame(
        {
            "player_name": ["Defender One", "Forward Two", "Mid Three"],
            "fantrax_player_id": ["d1", "f2", "m3"],
            "team_2627": ["ARS", "MCI", "LIV"],
            "position_2627": ["D", "F", "M"],
            "fantrax_position_eligibility": ["D,M", "F", "M,F"],
            "overall_rank": [2, 1, 3],
            "draft_score": [80.0, 90.0, 70.0],
            "fantrax_adp": [10.0, 3.0, 20.0],
            "fantrax_projected_points": [250.0, 300.5, 225.0],
            "value_vs_adp": [8.0, 2.0, 17.0],
            "projected_minutes_share": [90, 95, 80],
            "minutes_confidence": [85, 90, 75],
            "data_confidence": [80, 95, 70],
            "is_draft_eligible": [True, True, True],
            "is_free_agent": [False, False, False],
            "minutes_outlook": [
                "Likely Starter",
                "Locked Starter",
                "Likely Rotation",
            ],
            "historical_name": ["Defender One", "Forward Two", "Mid Three"],
            "understat_player_id": ["u1", "u2", "u3"],
            "fantasy_ppg_2526": [8.0, 12.0, 7.0],
            "ghost_ppg_2526": [5.0, 4.0, 6.0],
            "fantasy_fp90_2526": [9.0, 13.0, 8.0],
            "xgi90_2526": [0.2, 0.8, 0.4],
            "tier": ["Tier 2", "Tier 1", "Tier 3"],
            "adp_status": ["Value", "Fair", "Value"],
            "team_attack_rating": [80, 95, 90],
            "team_defense_rating": [90, 85, 80],
            "team_strength_rating": [85, 92, 88],
            "fixture_ease_next_3": [60, 70, 65],
            "fixture_ease_next_5": [62, 72, 66],
            "fixture_ease_next_10": [64, 74, 68],
        }
    )


def main_board(ui):
    return next(data for data, kwargs in ui.tables if kwargs.get("height") == 650)


def test_valid_draft_data_renders_existing_sections_and_controls():
    ui = FakeUI()
    data = FakeDataManager()
    render(
        "2627",
        data_manager=data,
        season_manager=FakeSeasonManager(),
        ui=ui,
    )
    assert [call[0] for call in data.calls] == [*DATASET_KEYS, *POST_DRAFT_DATASET_KEYS]
    assert "Draft HQ" in "\n".join(ui.markdowns)
    labels = [control[1] for control in ui.controls]
    assert "Search player" in labels
    assert "Positions" in labels
    assert "Clubs" in labels
    assert len(main_board(ui)) == 3


@pytest.mark.parametrize(
    "status",
    [DataStatus.MISSING, DataStatus.EMPTY, DataStatus.INVALID],
)
def test_unavailable_required_rankings_preserve_warning_and_stop(status):
    ui = FakeUI()
    result = make_result(
        "draft_rankings",
        None if status is not DataStatus.INVALID else pd.DataFrame(),
        status=status,
        errors=("invalid rankings",) if status is DataStatus.INVALID else (),
    )
    with pytest.raises(StopSignal):
        render(
            "2627",
            data_manager=FakeDataManager(results={"draft_rankings": result}),
            season_manager=FakeSeasonManager(),
            ui=ui,
        )
    assert any("Draft rankings are missing or empty" in item for item in ui.warnings)


def test_missing_optional_eligibility_overrides_does_not_block_page():
    ui = FakeUI()
    render(
        "2627",
        data_manager=FakeDataManager(),
        season_manager=FakeSeasonManager(),
        ui=ui,
    )
    assert len(main_board(ui)) == 3


@pytest.mark.parametrize("namespace", ["working", "snapshot"])
def test_season_manager_owns_working_and_snapshot_resolution(namespace):
    data = FakeDataManager()
    seasons = FakeSeasonManager(
        namespace=namespace,
        finalized=namespace == "snapshot",
    )
    render("2627", data_manager=data, season_manager=seasons, ui=FakeUI())
    assert seasons.namespace_calls == ["2627"]
    assert {call[2] for call in data.calls} == {namespace}


def test_invalid_season_stops_before_data_loading():
    data = FakeDataManager()
    with pytest.raises(KeyError, match="Unknown season"):
        render(
            "bad",
            data_manager=data,
            season_manager=FakeSeasonManager(invalid=True),
            ui=FakeUI(),
        )
    assert data.calls == []


def test_default_ranking_order_is_model_rank_ascending():
    ui = FakeUI()
    render(
        "2627",
        data_manager=FakeDataManager(),
        season_manager=FakeSeasonManager(),
        ui=ui,
    )
    assert main_board(ui)["Player"].tolist() == [
        "Forward Two",
        "Defender One",
        "Mid Three",
    ]


@pytest.mark.parametrize(
    ("sort_by", "direction", "expected"),
    [
        ("ADP", "Ascending", ["Forward Two", "Defender One", "Mid Three"]),
        ("ADP", "Descending", ["Mid Three", "Defender One", "Forward Two"]),
        ("Draft Score", "Ascending", ["Mid Three", "Defender One", "Forward Two"]),
    ],
)
def test_sort_controls_change_actual_displayed_board(sort_by, direction, expected):
    ui = FakeUI(values={"Sort board by": sort_by, "Direction": direction})
    render(
        "2627", data_manager=FakeDataManager(),
        season_manager=FakeSeasonManager(), ui=ui,
    )
    assert main_board(ui)["Player"].tolist() == expected


def test_page_adp_sort_uses_999_only_for_board_display_and_sorting():
    rankings = pd.concat(
        [
            draft_rankings(),
            draft_rankings().iloc[[0]].assign(
                player_name="Missing NaN", fantrax_player_id="n1", fantrax_adp=np.nan
            ),
            draft_rankings().iloc[[0]].assign(
                player_name="Missing None", fantrax_player_id="n2", fantrax_adp=None
            ),
            draft_rankings().iloc[[0]].assign(
                player_name="Missing NA", fantrax_player_id="n3", fantrax_adp=pd.NA
            ),
            draft_rankings().iloc[[0]].assign(
                player_name="Missing Blank", fantrax_player_id="n4",
                fantrax_adp="", value_vs_adp=np.nan,
            ),
        ],
        ignore_index=True,
    )
    rankings.loc[rankings["player_name"].eq("Defender One"), "fantrax_adp"] = "10.5"
    ui = FakeUI(values={"Sort board by": "ADP", "Direction": "Ascending"})
    render(
        "2627", data_manager=FakeDataManager(rankings=rankings),
        season_manager=FakeSeasonManager(), ui=ui,
    )
    board = main_board(ui)
    assert board["ADP"].dtype.kind == "f"
    assert board["Player"].tolist()[-4:] == [
        "Missing NaN", "Missing None", "Missing NA", "Missing Blank"
    ]
    assert board.loc[board["Player"].str.startswith("Missing"), "ADP"].eq(999.0).all()
    prepared = prepare_draft_frame(rankings, {})
    missing = prepared[prepared["Player"].eq("Missing Blank")].iloc[0]
    assert pd.isna(missing["fantrax_adp"])
    assert pd.isna(missing["ADP"])
    assert pd.isna(missing["Value vs ADP"])
    assert rankings.loc[rankings["player_name"].eq("Missing Blank"), "fantrax_adp"].iat[0] == ""

    download = ui.downloads[0][1]["data"].decode("utf-8-sig")
    downloaded = pd.read_csv(StringIO(download))
    assert pd.isna(downloaded.loc[
        downloaded["Player"].eq("Missing Blank"), "ADP"
    ].iat[0])


def test_final_board_adp_descending_uses_visible_999_sort_value():
    rankings = pd.concat(
        [
            draft_rankings(),
            draft_rankings().iloc[[0]].assign(
                player_name="Missing Blank", fantrax_player_id="n4", fantrax_adp=""
            ),
        ],
        ignore_index=True,
    )
    ui = FakeUI(values={"Sort board by": "ADP", "Direction": "Descending"})
    render(
        "2627", data_manager=FakeDataManager(rankings=rankings),
        season_manager=FakeSeasonManager(), ui=ui,
    )
    board = main_board(ui)
    assert board["Player"].tolist() == [
        "Missing Blank", "Mid Three", "Defender One", "Forward Two"
    ]
    assert board.iloc[0]["ADP"] == 999.0


def test_multi_position_filter_matches_any_fantrax_eligibility():
    ui = FakeUI(values={"Positions": ["M"]})
    render(
        "2627", data_manager=FakeDataManager(),
        season_manager=FakeSeasonManager(), ui=ui,
    )
    assert main_board(ui)["Player"].tolist() == ["Defender One", "Mid Three"]


def test_position_filter_and_player_search_are_applied():
    ui = FakeUI(
        values={
            "Positions": ["D"],
            "Search player": "defender",
        }
    )
    render(
        "2627",
        data_manager=FakeDataManager(),
        season_manager=FakeSeasonManager(),
        ui=ui,
    )
    assert main_board(ui)["Player"].tolist() == ["Defender One"]


def test_empty_filtered_results_preserve_existing_empty_states():
    ui = FakeUI(values={"Search player": "not present"})
    render(
        "2627",
        data_manager=FakeDataManager(),
        season_manager=FakeSeasonManager(),
        ui=ui,
    )
    assert main_board(ui).empty
    assert "No available players match the current filters." in ui.infos


def test_missing_optional_columns_are_handled():
    rankings = draft_rankings().drop(
        columns=[
            "tier",
            "team_attack_rating",
            "team_defense_rating",
            "team_strength_rating",
            "fixture_ease_next_5",
            "fixture_ease_next_10",
        ]
    )
    ui = FakeUI()
    render(
        "2627",
        data_manager=FakeDataManager(rankings=rankings),
        season_manager=FakeSeasonManager(),
        ui=ui,
    )
    assert not main_board(ui).empty


def test_duplicate_players_do_not_crash_or_change_ranking_rows():
    rankings = pd.concat(
        [draft_rankings(), draft_rankings().iloc[[0]]],
        ignore_index=True,
    )
    ui = FakeUI()
    render(
        "2627",
        data_manager=FakeDataManager(rankings=rankings),
        season_manager=FakeSeasonManager(),
        ui=ui,
    )
    assert len(main_board(ui)) == 4


def test_download_preserves_filename_format_and_filtered_content():
    ui = FakeUI(values={"Positions": ["F"]})
    render(
        "2627",
        data_manager=FakeDataManager(),
        season_manager=FakeSeasonManager(),
        ui=ui,
    )
    label, kwargs = ui.downloads[0]
    content = kwargs["data"].decode("utf-8-sig")
    assert label == "Download filtered draft board"
    assert kwargs["file_name"] == "fantrax_draft_board_2627_filtered.csv"
    assert kwargs["mime"] == "text/csv"
    assert "Forward Two" in content
    assert "Defender One" not in content


def test_optional_eligibility_override_is_applied():
    overrides = pd.DataFrame(
        {
            "fantrax_player_id": ["d1"],
            "player_name": ["Defender One"],
            "is_draft_eligible": ["false"],
            "reason": ["Not in current EPL"],
        }
    )
    ui = FakeUI()
    render(
        "2627",
        data_manager=FakeDataManager(overrides=overrides),
        season_manager=FakeSeasonManager(),
        ui=ui,
    )
    assert "Defender One" not in main_board(ui)["Player"].tolist()


def test_registered_draft_definitions_include_optional_override():
    registry = DatasetRegistry()
    definition = registry.get("draft_eligibility_overrides")
    assert definition.required is False
    assert definition.working_subdirectory == "imports/draft"


def test_exactly_four_requested_workspace_tabs_render():
    ui = FakeUI()
    render(
        "2627", data_manager=FakeDataManager(),
        season_manager=FakeSeasonManager(), ui=ui,
    )
    tabs = [item for item in ui.controls if item[0] == "tabs"]
    assert tabs == [(
        "tabs", ("Draft Board", "Compare Players", "My Queue", "My Team"), {}
    )]


def test_completed_results_put_grade_views_before_preserved_live_tabs():
    data = FakeDataManager()
    data.frames.update({
        "draft_manager_grades": pd.DataFrame({"overall_rank": [1], "manager": ["Manager A"], "overall_grade": ["A"], "letter_grade": ["A"], "overall_score": [64.0], "raw_analytical_score": [64.0], "league_relative_score": [94.0], "draft_slot": [2], "draft_identity": ["Most Balanced"], "top_category": ["value"], "main_concern": ["floor"], "draft_value_score": [90.0], "best_xi_projected_points": [3000.0], "bench_projected_points": [500.0], "best_pick": ["Forward Two"], "biggest_reach": ["Forward Two"]}),
        "draft_pick_grades": pd.DataFrame({"manager": ["Manager A"], "round": [1], "overall_pick": [2], "player": ["Forward Two"], "pick_grade": [95.0], "projected_points": [300.0], "adp": [2.0], "total_fantasy_points": [200.0], "ghost_points": [100.0], "minutes_2526": [1800.0], "starts_2526": [20.0], "weeks_available": [30.0], "projected_minutes_share": [90.0]}),
        "draft_category_scores": pd.DataFrame({"manager": ["Manager A"], "category": ["value"], "score": [65.0], "league_rank": [1], "league_percentile": [100.0], "calibrated_category_score": [80.0], "category_letter_grade": ["B-"], "weight": [.2], "contribution": [13.0]}),
        "draft_awards": pd.DataFrame({"award": ["Biggest Steal", "Biggest Reach"], "winner": ["A", "B"], "value": [10, -10], "reason": ["value", "reach"]}),
    })
    ui = FakeUI()
    render("2627", data_manager=data, season_manager=FakeSeasonManager(), ui=ui)
    tabs = next(item for item in ui.controls if item[0] == "tabs")
    assert tabs[1][:3] == ("Draft Grades", "League Rankings", "Manager Report Cards")
    assert tabs[1][-4:] == ("Draft Board", "Compare Players", "My Queue", "My Team")
    assert any("2026/27 League Draft Rankings" in text for text in ui.markdowns)
    share_table = next(table for table, _ in ui.tables if "Projected Starting XI Points" in table)
    assert "Raw Analytical Score" not in share_table
    assert {"Main Strength", "Main Concern"}.issubset(share_table)
    assert {item[0] for item in ui.downloads}.issuperset({"Download share CSV", "Download standalone HTML"})
    metric_labels = [item[1] for item in ui.controls if item[0] == "metric"]
    assert {"League-Relative Score", "Raw Analytical Score"}.issubset(metric_labels)


def test_main_board_places_and_pins_live_actions_beside_identity():
    ui = FakeUI()
    render(
        "2627", data_manager=FakeDataManager(),
        season_manager=FakeSeasonManager(), ui=ui,
    )
    board, kwargs = next(
        (data, config) for data, config in ui.tables
        if config.get("height") == 650
    )
    assert "Club · Pos" in board
    assert "Fantrax Pos" not in board
    assert "Canonical Position" not in board
    assert board.columns[:5].tolist() == ["Rank", "Player", "Club · Pos", "Mine", "Other"]
    config = kwargs["column_config"]
    pinned = {
        name for name, value in config.items()
        if value[2].get("pinned") is True
    }
    assert pinned == {"Rank", "Player", "Mine", "Other"}
    assert config["Player"][0] == "text"


def test_default_board_excludes_session_drafted_player():
    ui = FakeUI()
    ui.session_state["draft_player_statuses"] = {
        "fantrax_player_id:f2": "Drafted by Me"
    }
    render(
        "2627", data_manager=FakeDataManager(),
        season_manager=FakeSeasonManager(), ui=ui,
    )
    assert "Forward Two" not in main_board(ui)["Player"].tolist()


def test_player_details_use_in_app_view_state_not_url_navigation():
    source = Path("views/draft_workspace.py").read_text(encoding="utf-8")
    assert "LinkColumn" not in source
    assert "query_params" not in source
    assert "ButtonColumn" in source
    assert 'type="tertiary"' in source
    assert 'click["row"]' in source
    assert '"draft_detail_player_key"' in source


def test_compare_action_transfers_current_player_and_requests_compare_tab():
    ui = FakeUI()
    row = pd.Series({"Player": "Mid Three"})
    _open_compare(ui, row)
    assert ui.session_state["draft_compare_pending_player"] == "Mid Three"
    assert ui.session_state["draft_compare_clear_player_2"] is True
    assert ui.session_state["draft_workspace_pending_tab"] == "Compare Players"
    assert ("rerun", "rerun", {}) in ui.controls


def test_compare_view_applies_pending_player_before_player_one_widget():
    ui = FakeUI()
    ui.session_state["draft_compare_pending_player"] = "Mid Three"
    _render_compare(ui, prepare_draft_frame(draft_rankings(), {}))
    assert ui.session_state["compare_player_1"] == "Mid Three"
    assert "draft_compare_pending_player" not in ui.session_state
    assert "Player 1 is ready. Choose a challenger" in ui.infos[-1]


def test_compare_page_leaves_player_two_empty_by_default():
    ui = FakeUI()
    _render_compare(ui, prepare_draft_frame(draft_rankings(), {}))
    player_2 = next(
        control for control in ui.controls
        if control[0] == "selectbox" and control[1] == "Player 2"
    )
    assert player_2[2]["key"] == "compare_player_2"
    assert any("Choose a challenger" in message for message in ui.infos)


def test_player_detail_uses_formatted_metrics_and_progress_visualization():
    row = prepare_draft_frame(draft_rankings(), {}).iloc[0]
    row["fantasy_per90_2526"] = 13.921052631578947
    row["production_score"] = 82.3
    row["minutes_score"] = 75.0
    ui = FakeUI()
    _detail(ui, row, "test_detail")
    metric_values = [
        item[2]["value"] for item in ui.controls if item[0] == "metric"
    ]
    assert "13.9" in metric_values
    assert all("13.921052631578947" not in str(value) for value in metric_values)
    model = next(
        table for table, config in ui.tables
        if config.get("column_config", {}).get("Score", (None,))[0] == "progress"
    )
    assert set(model.columns) == {"Component", "Score"}


def test_page_has_no_filesystem_readers_or_operation_execution():
    source = Path("views/draft_center.py").read_text(encoding="utf-8")
    forbidden = [
        "Path(",
        "pathlib",
        "glob(",
        "os.path",
        "os.listdir",
        "os.scandir",
        "subprocess",
        "runpy",
        "pd.read_csv",
        "pd.read_parquet",
        "pd.read_json",
        "pd.read_excel",
        "pd.read_pickle",
        "pd.read_feather",
        "load_csv_cached",
    ]
    assert all(token not in source for token in forbidden)


def test_legacy_renderer_delegates_draft_analytics():
    source = Path("core/legacy_renderer.py").read_text(encoding="utf-8")
    branch = source.split('elif page == "Draft HQ":', 1)[1].split(
        'elif page == "Update Pipeline":',
        1,
    )[0]
    assert "render_draft_center(CURRENT_SEASON_ID)" in branch
    assert "load_csv_cached" not in branch
