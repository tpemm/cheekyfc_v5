from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from core.models.artifact_info import ArtifactInfo
from core.models.data_result import DataProvenance, DataResult, DataStatus
from views.reports import (
    RECENT_REPORTS_FAMILY_KEY,
    STABLE_REPORT_KEYS,
    render,
)


class StopSignal(RuntimeError):
    pass


class FakeUI:
    def __init__(self, selected=None):
        self.selected = selected
        self.markdowns = []
        self.writes = []
        self.warnings = []
        self.errors = []
        self.options = []
        self.captions = []
        self.text_areas = []
        self.stopped = False

    def markdown(self, value, **kwargs):
        self.markdowns.append((value, kwargs))

    def write(self, value):
        self.writes.append(value)

    def warning(self, value):
        self.warnings.append(value)

    def error(self, value):
        self.errors.append(value)

    def stop(self):
        self.stopped = True
        raise StopSignal()

    def selectbox(self, label, options):
        self.options = list(options)
        return self.selected or self.options[0]

    def caption(self, value):
        self.captions.append(value)

    def text_area(self, label, value, height):
        self.text_areas.append((label, value, height))


class FakeSeasonManager:
    def __init__(self, namespace="working", invalid=False):
        self.namespace = namespace
        self.invalid = invalid
        self.context_calls = []
        self.namespace_calls = []

    def context(self, season_id):
        self.context_calls.append(season_id)
        if self.invalid:
            raise KeyError(f"Unknown season ID: {season_id!r}")
        return SimpleNamespace(season_id=season_id)

    def resolve_namespace(self, season_id):
        self.namespace_calls.append(season_id)
        return self.namespace


class FakeDataManager:
    def __init__(self, probes=None, contents=None, recent=None):
        self.probes = probes or {}
        self.contents = contents or {}
        self.recent = recent if recent is not None else default_recent()
        self.probe_calls = []
        self.relative_calls = []
        self.inspect_family_calls = []
        self.artifact_relative_calls = []
        self.load_text_calls = []
        self.load_family_calls = []

    def probe(self, key, season_id, namespace):
        self.probe_calls.append((key, season_id, namespace))
        return self.probes.get(
            key,
            make_result(key, season_id, namespace, data=None),
        )

    def project_relative_path(self, key, season_id, namespace):
        self.relative_calls.append((key, season_id, namespace))
        return f"data/{namespace}/{key}.txt"

    def inspect_family(self, key, season_id, namespace):
        self.inspect_family_calls.append((key, season_id, namespace))
        return tuple(self.recent)

    def project_relative_artifact_path(self, path, season_id, namespace):
        self.artifact_relative_calls.append((path, season_id, namespace))
        return f"data/{namespace}/reports/{path.name}"

    def load_text(self, key, season_id, namespace, encoding, errors):
        self.load_text_calls.append(
            (key, season_id, namespace, encoding, errors)
        )
        return self.contents.get(
            key,
            make_result(key, season_id, namespace, data=f"contents:{key}"),
        )

    def load_family(self, key, season_id, namespace, filters):
        self.load_family_calls.append((key, season_id, namespace, filters))
        member = filters["name"]
        result = self.contents.get(
            member,
            make_result(key, season_id, namespace, data=f"contents:{member}"),
        )
        return make_result(
            key,
            season_id,
            namespace,
            data=(result,),
        )


def make_result(
    key,
    season_id="2627",
    namespace="working",
    *,
    status=DataStatus.AVAILABLE,
    data="report contents",
    errors=(),
    warnings=(),
):
    return DataResult(
        status=status,
        data=data,
        provenance=DataProvenance(
            dataset_key=key,
            requested_key=key,
            season_id=season_id,
            namespace=namespace,
            resolved_path=Path(f"/project/data/{key}.txt"),
            format="txt",
            modified_time=datetime(2026, 7, 29, tzinfo=timezone.utc),
            size_bytes=128,
        ),
        validation_errors=errors,
        warnings=warnings,
    )


def artifact(name, minutes):
    modified = datetime(2026, 7, 29, tzinfo=timezone.utc) + timedelta(
        minutes=minutes
    )
    return ArtifactInfo(
        path=Path(f"/project/data/reports/{name}"),
        name=name,
        suffix=".txt",
        size_bytes=100,
        modified_time=modified,
        is_file=True,
        dataset_key=RECENT_REPORTS_FAMILY_KEY,
        namespace="working",
        season_id="2627",
    )


def default_recent():
    return [
        artifact("older.txt", 1),
        artifact("newer.txt", 2),
    ]


def render_page(
    *,
    namespace="working",
    probes=None,
    contents=None,
    recent=None,
    selected=None,
):
    ui = FakeUI(selected)
    seasons = FakeSeasonManager(namespace)
    data = FakeDataManager(probes, contents, recent)
    render(
        "2627" if namespace == "working" else "2526",
        data_manager=data,
        season_manager=seasons,
        ui=ui,
    )
    return ui, seasons, data


def test_valid_report_rendering_and_text_preview():
    ui, _, data = render_page()

    assert "Reports" in ui.markdowns[0][0]
    assert ui.writes == ["View validation, refresh, and analytics reports."]
    assert ui.text_areas == [
        ("Report contents", "contents:finalization_validation_report", 750)
    ]
    assert data.load_text_calls[0][-2:] == ("utf-8", "replace")


def test_expected_report_ordering_preserves_stable_then_recent():
    ui, _, _ = render_page()

    assert ui.options[:5] == [
        f"data/working/{key}.txt" for key in STABLE_REPORT_KEYS
    ]
    assert ui.options[5:] == [
        "data/working/reports/newer.txt",
        "data/working/reports/older.txt",
    ]


@pytest.mark.parametrize(
    "key",
    ["formation_report", "api_merge_report"],
)
def test_missing_stable_report_is_omitted(key):
    missing = make_result(
        key,
        status=DataStatus.MISSING,
        data=None,
        warnings=("Optional dataset is missing.",),
    )

    ui, _, _ = render_page(probes={key: missing})

    assert f"data/working/{key}.txt" not in ui.options


def test_all_missing_reports_preserve_empty_state():
    probes = {
        key: make_result(key, status=DataStatus.MISSING, data=None)
        for key in STABLE_REPORT_KEYS
    }
    ui = FakeUI()
    seasons = FakeSeasonManager()
    data = FakeDataManager(probes=probes, recent=[])

    with pytest.raises(StopSignal):
        render(
            "2627",
            data_manager=data,
            season_manager=seasons,
            ui=ui,
        )

    assert ui.warnings == ["No reports found yet."]
    assert ui.stopped


def test_empty_report_renders_blank_existing_preview():
    empty = make_result(
        "finalization_validation_report",
        status=DataStatus.EMPTY,
        data=None,
        errors=("Artifact is empty.",),
    )

    ui, _, _ = render_page(
        contents={"finalization_validation_report": empty}
    )

    assert ui.text_areas == [("Report contents", "", 750)]


def test_invalid_report_displays_validation_message():
    invalid = make_result(
        "finalization_validation_report",
        status=DataStatus.INVALID,
        data="partial report",
        errors=("Report validation failed.",),
    )

    ui, _, _ = render_page(
        contents={"finalization_validation_report": invalid}
    )

    assert ui.errors == ["Report validation failed."]
    assert ui.text_areas[0][1] == "partial report"


def test_recent_family_member_preview_uses_registered_family():
    selected = "data/working/reports/newer.txt"

    ui, _, data = render_page(selected=selected)

    assert ui.text_areas[0][1] == "contents:newer.txt"
    assert data.load_family_calls[0][0] == RECENT_REPORTS_FAMILY_KEY
    assert data.load_family_calls[0][3]["name"] == "newer.txt"


@pytest.mark.parametrize(
    ("namespace", "season_id"),
    [("working", "2627"), ("snapshot", "2526")],
)
def test_namespace_resolution_and_data_manager_interactions(
    namespace,
    season_id,
):
    _, seasons, data = render_page(namespace=namespace)

    assert seasons.context_calls == [season_id]
    assert seasons.namespace_calls == [season_id]
    assert [call[0] for call in data.probe_calls] == list(STABLE_REPORT_KEYS)
    assert all(call[2] == namespace for call in data.probe_calls)
    assert data.inspect_family_calls == [
        (RECENT_REPORTS_FAMILY_KEY, season_id, namespace)
    ]


def test_invalid_season_propagates_before_data_access():
    ui = FakeUI()
    seasons = FakeSeasonManager(invalid=True)
    data = FakeDataManager()

    with pytest.raises(KeyError, match="Unknown season ID"):
        render(
            "invalid",
            data_manager=data,
            season_manager=seasons,
            ui=ui,
        )

    assert data.probe_calls == []


def test_page_has_no_direct_filesystem_or_pandas_loading():
    source = Path("views/reports.py").read_text(encoding="utf-8")

    forbidden = (
        "read_csv",
        "read_parquet",
        "Path(",
        ".exists(",
        ".stat(",
        ".glob(",
        "os.path",
    )
    assert not any(token in source for token in forbidden)


def test_legacy_renderer_delegates_reports_branch():
    source = Path("core/legacy_renderer.py").read_text(encoding="utf-8")
    branch = source.split('elif page == "Reports":', 1)[1]

    assert "render_reports(CURRENT_SEASON_ID)" in branch
    assert "report_paths =" not in branch
    assert "refresh_reports.glob" not in branch
