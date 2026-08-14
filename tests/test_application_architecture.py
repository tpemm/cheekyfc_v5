"""Cross-cutting architecture rules for the completed page migration."""
from __future__ import annotations

import ast
from pathlib import Path

from core.services import DatasetRegistry, SeasonManager


PAGE_DIR = Path("views")
PAGE_MODULES = tuple(
    PAGE_DIR / name
    for name in (
        "key_output_health.py",
        "reports.py",
        "league_hub.py",
        "managers.py",
        "awards.py",
        "draft_center.py",
        "identity_review.py",
        "raw_data_browser.py",
        "update_pipeline.py",
    )
)

FORBIDDEN_PAGE_TOKENS = (
    "from pathlib",
    "import pathlib",
    "Path(",
    "glob(",
    "os.path",
    "os.listdir",
    "os.scandir",
    "pd.read_csv",
    "pd.read_parquet",
    "pd.read_json",
    "pd.read_excel",
    "pd.read_pickle",
    "pd.read_feather",
    "subprocess",
    "runpy",
    "os.system",
    "Popen(",
)


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
    return imported


def test_all_page_modules_obey_artifact_and_execution_boundaries():
    for path in PAGE_MODULES:
        source = path.read_text(encoding="utf-8")
        violations = [token for token in FORBIDDEN_PAGE_TOKENS if token in source]
        assert not violations, f"{path}: prohibited tokens {violations}"

        imports = _imports(path)
        assert not any(name.startswith("fantrax.refresh") for name in imports)
        assert not any(name.startswith("fantrax.analytics") for name in imports)
        assert "core.legacy_renderer" not in imports


def test_foundation_services_do_not_depend_on_pages_or_streamlit():
    for path in Path("core/services").glob("*.py"):
        imports = _imports(path)
        assert not any(name == "streamlit" or name.startswith("streamlit.") for name in imports)
        assert not any(name == "pages" or name.startswith("pages.") for name in imports)


def test_models_do_not_depend_on_services_or_pages():
    for path in Path("core/models").glob("*.py"):
        imports = _imports(path)
        assert not any(name.startswith("core.services") for name in imports)
        assert not any(name == "pages" or name.startswith("pages.") for name in imports)


def test_data_manager_remains_read_only_and_has_no_operation_api():
    source = Path("core/services/data_manager.py").read_text(encoding="utf-8")
    prohibited = (
        "def run_builder",
        "def execute_pipeline",
        "def refresh_data",
        "def run_script",
        "def build_rankings",
        "subprocess",
    )
    assert not [token for token in prohibited if token in source]


def test_registry_and_season_catalog_validate_as_the_sources_of_truth():
    registry = DatasetRegistry()
    assert registry.validate() is None
    assert len(registry.list_all()) == len({item.key for item in registry.list_all()})

    manager = SeasonManager()
    assert manager.validate_catalog() is None
    assert manager.get("2526").finalized is True
    assert manager.get("2627").mutable is True


def test_operations_service_has_no_ui_or_arbitrary_shell_boundary():
    source = Path("core/services/operations_service.py").read_text(encoding="utf-8")
    assert "streamlit" not in source
    assert "shell=True" not in source
    run_parameters = {
        argument.arg
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.FunctionDef) and node.name == "run"
        for argument in (*node.args.args, *node.args.kwonlyargs)
    }
    assert not {"command", "script_path", "executable_path", "working_directory"} & run_parameters
