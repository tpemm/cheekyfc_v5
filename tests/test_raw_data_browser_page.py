from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest

from core.models.artifact_info import ArtifactInfo
from core.models.data_result import DataProvenance, DataResult, DataStatus
from views.raw_data_browser import render


class StopSignal(RuntimeError):
    pass


class FakeColumn:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False


class FakeUI:
    def __init__(self, values=None):
        self.values = values or {}
        self.markdowns = []
        self.writes = []
        self.warnings = []
        self.errors = []
        self.captions = []
        self.subheaders = []
        self.tables = []
        self.downloads = []
        self.controls = []

    def markdown(self, value, **kwargs):
        self.markdowns.append(str(value))

    def write(self, value):
        self.writes.append(str(value))

    def warning(self, value):
        self.warnings.append(str(value))

    def error(self, value):
        self.errors.append(str(value))

    def caption(self, value):
        self.captions.append(str(value))

    def subheader(self, value):
        self.subheaders.append(str(value))

    def columns(self, spec):
        count = spec if isinstance(spec, int) else len(spec)
        return [FakeColumn() for _ in range(count)]

    def text_input(self, label, **kwargs):
        self.controls.append(("text_input", label, kwargs))
        return self.values.get(label, "")

    def multiselect(self, label, options, default=None, **kwargs):
        self.controls.append(("multiselect", label, list(options), kwargs))
        return self.values.get(label, list(default or []))

    def selectbox(self, label, options, **kwargs):
        values = list(options)
        self.controls.append(("selectbox", label, values, kwargs))
        return self.values.get(label, values[0])

    def slider(self, label, min_value, max_value, value, **kwargs):
        self.controls.append(("slider", label, kwargs))
        return self.values.get(label, value)

    def dataframe(self, data, **kwargs):
        self.tables.append((data.copy(), kwargs))

    def download_button(self, label, **kwargs):
        self.downloads.append((label, kwargs))

    def stop(self):
        raise StopSignal()


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
    def __init__(self, artifacts=None, results=None):
        self.artifacts = tuple(artifacts if artifacts is not None else sample_artifacts())
        self.results = results or {}
        self.catalog_calls = []
        self.relative_calls = []
        self.preview_calls = []

    def catalog(self, season_id, namespace, filters):
        self.catalog_calls.append((season_id, namespace, filters))
        return self.artifacts

    def project_relative_artifact_path(self, path, season_id, namespace):
        self.relative_calls.append((path, season_id, namespace))
        return f"data/{namespace}/{path.name}"

    def preview_artifact(
        self,
        artifact,
        season_id,
        namespace,
        *,
        row_limit,
        column_limit,
    ):
        self.preview_calls.append(
            (artifact, season_id, namespace, row_limit, column_limit)
        )
        if artifact.name in self.results:
            result = self.results[artifact.name]
            if isinstance(result, Exception):
                raise result
            return result
        return make_result(
            artifact,
            pd.DataFrame(
                {
                    "name": ["Ada", "Bea", "Cia"],
                    "score": [3, 2, 1],
                }
            ).head(row_limit),
            namespace=namespace,
        )


def artifact(
    name,
    *,
    suffix=".csv",
    size=1024,
    minute=0,
    dataset_key=None,
    namespace="working",
):
    return ArtifactInfo(
        path=Path(f"/project/data/{name}"),
        name=name,
        suffix=suffix,
        size_bytes=size,
        modified_time=datetime(2026, 7, 29, 12, minute, tzinfo=timezone.utc),
        is_file=True,
        dataset_key=dataset_key,
        namespace=namespace,
        season_id="2526",
    )


def sample_artifacts(namespace="working"):
    return [
        artifact(
            "older.csv",
            minute=1,
            dataset_key="league_table",
            namespace=namespace,
        ),
        artifact(
            "newer.json",
            suffix=".json",
            minute=2,
            namespace=namespace,
        ),
        artifact(
            "report.txt",
            suffix=".txt",
            minute=0,
            namespace=namespace,
        ),
    ]


def make_result(
    selected_artifact,
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
            dataset_key=selected_artifact.dataset_key or "catalog_artifact",
            requested_key=selected_artifact.dataset_key or "catalog_artifact",
            season_id="2526",
            namespace=namespace,
            resolved_path=selected_artifact.path,
            format=selected_artifact.suffix.lstrip("."),
            modified_time=selected_artifact.modified_time,
            size_bytes=selected_artifact.size_bytes,
        ),
        validation_errors=errors,
    )


def test_valid_browser_renders_existing_controls_metadata_and_preview():
    ui = FakeUI(values={"Open file": "data/working/older.csv"})
    data = FakeDataManager()
    render(
        "2526",
        data_manager=data,
        season_manager=FakeSeasonManager(),
        ui=ui,
    )

    assert "Raw Data Browser" in "\n".join(ui.markdowns)
    assert ui.subheaders == ["Files", "Preview / Filter"]
    labels = [item[1] for item in ui.controls]
    assert labels == [
        "Search file paths",
        "File type",
        "Status",
        "Open file",
        "Preview row limit",
        "Search within loaded rows",
        "Columns to show",
    ]
    assert len(ui.tables) == 2
    assert data.catalog_calls[0][2]["recursive"] is True


@pytest.mark.parametrize("namespace", ["working", "snapshot"])
def test_season_manager_owns_namespace(namespace):
    artifacts = sample_artifacts(namespace)
    data = FakeDataManager(artifacts)
    seasons = FakeSeasonManager(namespace)
    render("2526", data_manager=data, season_manager=seasons, ui=FakeUI())
    assert seasons.namespace_calls == ["2526"]
    assert data.catalog_calls[0][1] == namespace
    assert data.preview_calls[0][2] == namespace


def test_invalid_season_stops_before_catalog():
    data = FakeDataManager()
    with pytest.raises(KeyError, match="Unknown season"):
        render(
            "bad",
            data_manager=data,
            season_manager=FakeSeasonManager(invalid=True),
            ui=FakeUI(),
        )
    assert data.catalog_calls == []


def test_empty_catalog_preserves_no_files_state():
    ui = FakeUI()
    with pytest.raises(StopSignal):
        render(
            "2526",
            data_manager=FakeDataManager(artifacts=[]),
            season_manager=FakeSeasonManager(),
            ui=ui,
        )
    assert ui.warnings == ["No data files found."]


def test_catalog_ordering_is_newest_then_relative_path():
    ui = FakeUI()
    render(
        "2526",
        data_manager=FakeDataManager(),
        season_manager=FakeSeasonManager(),
        ui=ui,
    )
    assert ui.tables[0][0]["relative_path"].tolist() == [
        "data/working/newer.json",
        "data/working/older.csv",
        "data/working/report.txt",
    ]


def test_file_search_and_type_filter_update_dataset_selection():
    ui = FakeUI(
        values={
            "Search file paths": "report",
            "File type": ["txt"],
        }
    )
    render(
        "2526",
        data_manager=FakeDataManager(),
        season_manager=FakeSeasonManager(),
        ui=ui,
    )
    selector = next(item for item in ui.controls if item[1] == "Open file")
    assert selector[2] == ["data/working/report.txt"]


@pytest.mark.parametrize(
    ("name", "suffix", "value", "expected_columns"),
    [
        ("table.csv", ".csv", pd.DataFrame({"a": [1]}), ["a"]),
        ("table.parquet", ".parquet", pd.DataFrame({"a": [1]}), ["a"]),
        ("items.json", ".json", [{"a": 1}], ["a"]),
        ("report.txt", ".txt", "one\ntwo", ["line_number", "text"]),
    ],
)
def test_supported_preview_types(name, suffix, value, expected_columns):
    selected = artifact(name, suffix=suffix)
    data = FakeDataManager(
        artifacts=[selected],
        results={name: make_result(selected, value)},
    )
    ui = FakeUI()
    render(
        "2526",
        data_manager=data,
        season_manager=FakeSeasonManager(),
        ui=ui,
    )
    assert ui.tables[1][0].columns.tolist() == expected_columns


def test_row_limit_selected_columns_and_search_are_preserved():
    selected = artifact("table.csv")
    result = make_result(
        selected,
        pd.DataFrame(
            {"name": ["Ada", "Bea", "Cia"], "score": [1, 2, 3]}
        ),
    )
    ui = FakeUI(
        values={
            "Preview row limit": 100,
            "Columns to show": ["name"],
            "Search within loaded rows": "Bea",
        }
    )
    data = FakeDataManager(
        artifacts=[selected],
        results={"table.csv": result},
    )
    render(
        "2526",
        data_manager=data,
        season_manager=FakeSeasonManager(),
        ui=ui,
    )
    assert data.preview_calls[0][3] == 100
    assert ui.tables[1][0].to_dict("records") == [{"name": "Bea"}]


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        (DataStatus.MISSING, "Selected dataset is missing."),
        (DataStatus.EMPTY, "Could not load file preview."),
        (DataStatus.INVALID, "invalid artifact"),
    ],
)
def test_missing_empty_and_invalid_preview_states(status, expected):
    selected = artifact("bad.csv")
    result = make_result(
        selected,
        None,
        status=status,
        errors=("invalid artifact",) if status is DataStatus.INVALID else (),
    )
    ui = FakeUI()
    with pytest.raises(StopSignal):
        render(
            "2526",
            data_manager=FakeDataManager(
                artifacts=[selected],
                results={"bad.csv": result},
            ),
            season_manager=FakeSeasonManager(),
            ui=ui,
        )
    assert expected in (ui.errors + ui.warnings)


def test_download_uses_displayed_rows_and_existing_filename():
    selected = artifact("table.csv")
    ui = FakeUI(values={"Search within loaded rows": "Bea"})
    render(
        "2526",
        data_manager=FakeDataManager(artifacts=[selected]),
        season_manager=FakeSeasonManager(),
        ui=ui,
    )
    label, kwargs = ui.downloads[0]
    content = kwargs["data"].decode("utf-8-sig")
    assert label == "Download displayed rows as CSV"
    assert kwargs["file_name"] == "filtered_table.csv"
    assert kwargs["mime"] == "text/csv"
    assert "Bea" in content
    assert "Ada" not in content


def test_page_has_no_direct_filesystem_reader_or_write_operations():
    source = Path("views/raw_data_browser.py").read_text(encoding="utf-8")
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
        "load_preview",
        "scan_data_files",
        ".write_",
        ".delete",
        ".rename",
    ]
    assert all(token not in source for token in forbidden)


def test_legacy_renderer_delegates_raw_data_browser():
    source = Path("core/legacy_renderer.py").read_text(encoding="utf-8")
    branch = source.split('elif page == "Raw Data Browser":', 1)[1].split(
        'elif page == "Key Output Health":',
        1,
    )[0]
    assert "render_raw_data_browser(CURRENT_SEASON_ID)" in branch
    assert "scan_data_files" not in branch
