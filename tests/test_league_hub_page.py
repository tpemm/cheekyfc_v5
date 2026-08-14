from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest

from core.models.data_result import DataProvenance, DataResult, DataStatus
from views.league_hub import (
    DATASET_KEYS, HISTORICAL_HUB_CSS, format_historical_movement,
    historical_previous_rank_lookup, render,
)


class StopSignal(RuntimeError):
    pass


class FakeColumn:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False


class FakeColumnConfig:
    @staticmethod
    def NumberColumn(*args, **kwargs):
        return ("number", args, kwargs)

    @staticmethod
    def TextColumn(*args, **kwargs):
        return ("text", args, kwargs)


class FakeUI:
    column_config = FakeColumnConfig()

    def __init__(self):
        self.markdowns = []
        self.warnings = []
        self.infos = []
        self.tables = []
        self.column_calls = []
        self.chart_calls = []

    def markdown(self, value, **kwargs):
        self.markdowns.append(value)

    def warning(self, value):
        self.warnings.append(value)

    def info(self, value):
        self.infos.append(value)

    def stop(self):
        raise StopSignal()

    def columns(self, count, **kwargs):
        self.column_calls.append((count, kwargs))
        return [FakeColumn() for _ in range(count)]

    def dataframe(self, data, **kwargs):
        self.tables.append((data, kwargs))

    def plotly_chart(self, *args, **kwargs):
        self.chart_calls.append(("plotly", args, kwargs))

    def line_chart(self, *args, **kwargs):
        self.chart_calls.append(("line", args, kwargs))

    def bar_chart(self, *args, **kwargs):
        self.chart_calls.append(("bar", args, kwargs))


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
        return SimpleNamespace(season_id=season_id, finalized=self.finalized)

    def resolve_namespace(self, season_id):
        self.namespace_calls.append(season_id)
        return self.namespace


class FakeDataManager:
    def __init__(self, frames=None, results=None):
        self.frames = default_frames()
        self.frames.update(frames or {})
        self.results = results or {}
        self.calls = []

    def load_frame(self, key, season_id, namespace):
        self.calls.append((key, season_id, namespace))
        if key in self.results:
            return self.results[key]
        frame = self.frames.get(key, pd.DataFrame())
        status = DataStatus.EMPTY if frame.empty else DataStatus.AVAILABLE
        return make_result(key, frame, status=status, namespace=namespace)


def make_result(
    key,
    data,
    *,
    status=DataStatus.AVAILABLE,
    namespace="working",
    errors=(),
    warnings=(),
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
        warnings=warnings,
    )


def default_frames():
    teams = ["Third FC", "First FC", "Second FC"]
    league_table = pd.DataFrame(
        {
            "official_rank": [3, 1, 2],
            "api_team_name": teams,
            "official_record": ["1-2", "3-0", "2-1"],
            "total_starter_points": [150.0, 300.0, 225.0],
            "avg_starter_points": [50.0, 100.0, 75.0],
        }
    )
    profile = pd.DataFrame(
        {
            "api_team_name": teams,
            "season_efficiency_pct": [70.0, 90.0, 80.0],
            "ghost_points": [30.0, 9.0, 18.0],
            "weeks": [3, 3, 3],
        }
    )
    streaks = pd.DataFrame(
        {
            "api_team_name": teams,
            "result_sequence": ["LLW", "WWW", "WWL"],
            "longest_win_streak": [1, 3, 2],
            "longest_losing_streak": [2, 0, 1],
        }
    )
    awards = []
    for award in [
        "Golden Boot",
        "Golden Assist",
        "Golden Gloves",
        "Jester",
    ]:
        for rank, team in enumerate(reversed(teams), start=1):
            awards.append(
                {
                    "award_name": award,
                    "rank": rank,
                    "api_team_name": team,
                    "leaderboard_value": 10 - rank,
                }
            )
    return {
        "league_table": league_table,
        "league_hub_cards": pd.DataFrame([{"card": "legacy dependency"}]),
        "manager_profile_summary": profile,
        "manager_streaks": streaks,
        "lineup_changes": pd.DataFrame(
            {
                "view_type": ["season_summary"] * 3,
                "api_team_name": teams,
                "total_starter_changes": [4, 8, 6],
            }
        ),
        "closest_games": pd.DataFrame(
            {
                "api_team_name": teams,
                "margin": [2.0, 0.5, 1.0],
            }
        ),
        "biggest_blowouts": pd.DataFrame(
            {
                "api_team_name": teams,
                "margin": [20.0, 40.0, 30.0],
            }
        ),
        "weekly_awards": pd.DataFrame(
            {
                "fantrax_gw": [1, 2],
                "award_name": ["Jester", "Jester"],
                "api_team_name": ["Third FC", "Second FC"],
                "metric_value": [40.0, 35.0],
            }
        ),
        "award_leaderboards": pd.DataFrame(awards),
        "matchup_week_summary": pd.DataFrame(
            {
                "fantrax_gw": [1, 1, 1, 2, 2, 2],
                "api_team_name": teams * 2,
                "computed_result": ["L", "W", "W", "L", "W", "L"],
                "starter_fantasy_points": [50, 100, 75, 55, 105, 70],
            }
        ),
        "scoring_periods": pd.DataFrame(
            {
                "fantrax_gw": [1, 2],
                "period_start": ["2026-08-01", "2026-08-08"],
            }
        ),
    }


def markdown_text(ui):
    return "\n".join(ui.markdowns)


def rendered_table(ui):
    styled = ui.tables[0][0]
    return styled.data if hasattr(styled, "data") else styled


def test_valid_datasets_render_and_use_data_manager_only():
    ui = FakeUI()
    data = FakeDataManager()
    seasons = FakeSeasonManager()

    render("2627", data_manager=data, season_manager=seasons, ui=ui)

    assert [call[0] for call in data.calls] == list(DATASET_KEYS)
    assert all(call[2] == "working" for call in data.calls)
    assert len(ui.tables) == 1
    assert "League Hub" in markdown_text(ui)


@pytest.mark.parametrize("namespace", ["working", "snapshot"])
def test_namespace_is_owned_by_season_manager(namespace):
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


def test_missing_optional_dataset_does_not_block_rendering():
    data = FakeDataManager(
        results={
            "league_hub_cards": make_result(
                "league_hub_cards",
                None,
                status=DataStatus.MISSING,
            )
        }
    )
    ui = FakeUI()

    render("2627", data_manager=data, season_manager=FakeSeasonManager(), ui=ui)

    assert len(ui.tables) == 1


def test_missing_required_league_table_uses_existing_warning_and_stop():
    data = FakeDataManager(
        results={
            "league_table": make_result(
                "league_table",
                None,
                status=DataStatus.MISSING,
            )
        }
    )
    ui = FakeUI()

    with pytest.raises(StopSignal):
        render(
            "2627",
            data_manager=data,
            season_manager=FakeSeasonManager(),
            ui=ui,
        )

    assert ui.warnings == ["The league table is missing for this season."]


def test_invalid_dataset_displays_validation_message_and_continues():
    data = FakeDataManager(
        results={
            "league_hub_cards": make_result(
                "league_hub_cards",
                pd.DataFrame(),
                status=DataStatus.INVALID,
                errors=("bad card schema",),
            )
        }
    )
    ui = FakeUI()

    render("2627", data_manager=data, season_manager=FakeSeasonManager(), ui=ui)

    assert ui.warnings == ["bad card schema"]
    assert len(ui.tables) == 1


def test_league_table_is_ordered_by_official_rank():
    ui = FakeUI()
    render(
        "2627",
        data_manager=FakeDataManager(),
        season_manager=FakeSeasonManager(),
        ui=ui,
    )

    assert rendered_table(ui)["Team"].tolist() == [
        "First FC",
        "Second FC",
        "Third FC",
    ]


def test_summary_cards_preserve_metrics_and_order():
    ui = FakeUI()
    render(
        "2627",
        data_manager=FakeDataManager(),
        season_manager=FakeSeasonManager(),
        ui=ui,
    )
    output = markdown_text(ui)

    assert output.index("Next Gameweek") < output.index("Manager of the Month")
    assert output.index("Manager of the Month") < output.index("Latest Jester")
    assert "GW 3" in output
    assert "First FC" in output
    assert "Second FC" in output


def test_missing_profile_metrics_still_render_as_empty_values():
    frames = default_frames()
    frames["manager_profile_summary"] = pd.DataFrame()
    frames["league_table"] = frames["league_table"].assign(
        weeks=3,
        ghost_points=pd.NA,
    )
    ui = FakeUI()

    render(
        "2627",
        data_manager=FakeDataManager(frames=frames),
        season_manager=FakeSeasonManager(),
        ui=ui,
    )

    assert len(ui.tables) == 1
    assert rendered_table(ui)["Efficiency"].isna().all()


def test_awards_and_highlights_preserve_order():
    ui = FakeUI()
    render(
        "2627",
        data_manager=FakeDataManager(),
        season_manager=FakeSeasonManager(),
        ui=ui,
    )
    output = markdown_text(ui)
    titles = [
        "Golden Boot",
        "Playmaker",
        "Golden Glove",
        "Jester",
        "Biggest Blowout",
        "Closest Game",
        "Longest Win Streak",
        "Longest Losing Streak",
    ]

    positions = [output.index(f'reward-title">{title}') for title in titles]
    assert positions == sorted(positions)


def test_historical_movement_compares_final_rank_to_prior_completed_week():
    frames=default_frames()
    frames["league_table"]=frames["league_table"].assign(official_rank=[1,2,3])
    ui=FakeUI()
    render("2526",data_manager=FakeDataManager(frames=frames),season_manager=FakeSeasonManager(namespace="snapshot",finalized=True),ui=ui)
    movement=dict(zip(rendered_table(ui)["Team"],rendered_table(ui)["Move"]))
    assert movement=={"Third FC":"\u25b22","First FC":"\u25bc1","Second FC":"\u25bc1"}


def test_historical_movement_ignores_future_incomplete_rows_and_unchanged_is_dash():
    matchup=default_frames()["matchup_week_summary"]
    incomplete=matchup.iloc[:3].assign(fantrax_gw=3,computed_result=pd.NA)
    lookup=historical_previous_rank_lookup(pd.concat([matchup,incomplete],ignore_index=True))
    assert lookup=={"First FC":1,"Second FC":2,"Third FC":3}
    assert format_historical_movement(1,1)=="\u2014"


def test_award_card_polish_emphasizes_winner_without_layout_changes():
    ui=FakeUI()
    render("2526",data_manager=FakeDataManager(),season_manager=FakeSeasonManager(namespace="snapshot",finalized=True),ui=ui)
    output=markdown_text(ui)
    assert output.count('class="summary-card"')==3
    assert output.count('class="reward-card"')==8
    assert output.count("award-name award-first")==6
    assert output.index("Final League Table") < output.index("Season Awards") < output.index("Weekly Scoring") < output.index("League-Position History")
    assert "text-transform:uppercase" in HISTORICAL_HUB_CSS
    assert "font-variant-numeric:tabular-nums" in HISTORICAL_HUB_CSS


def test_empty_award_dataset_preserves_empty_state_and_no_chart_widgets():
    ui = FakeUI()
    render(
        "2627",
        data_manager=FakeDataManager(
            frames={"award_leaderboards": pd.DataFrame()}
        ),
        season_manager=FakeSeasonManager(),
        ui=ui,
    )

    assert ui.infos == ["No season award leaderboards are available yet."]
    assert ui.chart_calls == []


def test_finalized_snapshot_card_says_season_complete():
    ui = FakeUI()
    render(
        "2627",
        data_manager=FakeDataManager(),
        season_manager=FakeSeasonManager(
            namespace="snapshot",
            finalized=True,
        ),
        ui=ui,
    )

    assert "Season complete" in markdown_text(ui)
    assert "Champion" in markdown_text(ui)


def test_page_has_no_direct_filesystem_or_pandas_reader_calls():
    source = Path("views/league_hub.py").read_text(encoding="utf-8")
    forbidden = [
        "Path(",
        "glob(",
        "os.path",
        "pd.read_csv",
        "pd.read_parquet",
        "pd.read_json",
    ]
    assert all(token not in source for token in forbidden)


def test_legacy_renderer_delegates_league_hub():
    source = Path("core/legacy_renderer.py").read_text(encoding="utf-8")
    branch = source.split('if page == "League Hub":', 1)[1].split(
        'elif page == "Award Detail":',
        1,
    )[0]

    assert "render_league_hub(CURRENT_SEASON_ID)" in branch
    assert "load_csv_cached" not in branch
