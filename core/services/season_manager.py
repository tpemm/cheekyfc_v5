"""Season catalog and lifecycle policy for the Fantrax platform."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from config.project_paths import PROJECT_ROOT, SEASONS_CONFIG
from config.settings import DEFAULT_SEASON_ID
from core.models.season_context import SeasonContext


class SeasonCatalogError(ValueError):
    """Raised when season configuration is missing, invalid, or ambiguous."""


class SeasonMutationError(PermissionError):
    """Raised when a caller requests mutation of read-only season data."""


_SEASON_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]*$")
_VALID_NAMESPACES = frozenset({"working", "snapshot"})
_VALID_STATUSES = frozenset(
    {"preseason", "active", "finalized", "not_built", "archived"}
)

# Capability identifiers preserve the availability represented by the current
# page registry without importing Streamlit or page modules.
_PAGES_BY_SEASON: Mapping[str, tuple[str, ...]] = {
    "2526": (
        "2025/26 Season Archive",
        "Players",
        "Award Detail",
        "Managers",
        "History",
        "Operations Center",
        "Raw Data Browser",
        "Key Output Health",
        "Reports",
    ),
    "2627": (
        "League Hub",
        "Players",
        "Managers",
        "Cup Tournament",
        "Trades",
        "Weekly Reports",
        "History",
        "Draft HQ",
        "Identity Review",
        "Operations Center",
        "Raw Data Browser",
        "Key Output Health",
        "Reports",
    ),
    "all_time": (
        "Raw Data Browser",
        "Key Output Health",
        "Reports",
    ),
}

_OPERATIONS_BY_STATUS: Mapping[str, tuple[str, ...]] = {
    "preseason": (
        "refresh",
        "build_master",
        "build_analytics",
        "build_draft",
        "finalize",
    ),
    "active": (
        "refresh",
        "build_master",
        "build_analytics",
        "build_draft",
        "finalize",
    ),
    "finalized": ("validate_snapshot",),
    "not_built": (),
    "archived": ("validate_snapshot",),
}


class SeasonManager:
    """Resolve immutable season contexts from the existing JSON catalog."""

    def __init__(
        self,
        *,
        config_path: str | Path = SEASONS_CONFIG,
        project_root: str | Path = PROJECT_ROOT,
        default_season_id: str = DEFAULT_SEASON_ID,
        definitions: Mapping[str, Mapping[str, Any]] | None = None,
    ) -> None:
        self._config_path = Path(config_path)
        self._project_root = Path(project_root)
        self._default_season_id = str(default_season_id)
        self._definitions = (
            self._load_definitions()
            if definitions is None
            else self._copy_definitions(definitions)
        )
        self.validate_catalog()
        self._contexts = {
            season_id: self._build_context(season_id, definition)
            for season_id, definition in self._definitions.items()
        }

    def list_seasons(
        self,
        *,
        enabled_only: bool = False,
    ) -> tuple[SeasonContext, ...]:
        """Return configured seasons in catalog order."""

        contexts = tuple(self._contexts.values())
        if enabled_only:
            return tuple(context for context in contexts if context.enabled)
        return contexts

    def get(self, season_id: str) -> SeasonContext:
        """Return a season by canonical ID.

        Raises:
            KeyError: when the season ID is not configured.
        """

        try:
            return self._contexts[str(season_id)]
        except KeyError as exc:
            raise KeyError(f"Unknown season ID: {season_id!r}") from exc

    def resolve(self, selection: str | None = None) -> SeasonContext:
        """Resolve an ID or display name, defaulting to the viewing season."""

        if selection is None:
            return self.default_viewing_season()

        selection_text = str(selection)
        if selection_text in self._contexts:
            return self._contexts[selection_text]

        matches = tuple(
            context
            for context in self._contexts.values()
            if context.display_name == selection_text
        )
        if len(matches) == 1:
            return matches[0]
        raise KeyError(f"Unknown season ID or display name: {selection!r}")

    def default_viewing_season(self) -> SeasonContext:
        """Return the configured default season used by the current UI."""

        return self.get(self._default_season_id)

    def active_ingestion_season(self) -> SeasonContext:
        """Return the active mutable season targeted by ingestion.

        A season explicitly marked ``active`` wins. For compatibility with the
        existing catalog, if none is active the last enabled mutable season is
        selected.
        """

        active = tuple(
            context
            for context in self._contexts.values()
            if context.status == "active" and context.enabled
        )
        if len(active) == 1:
            return active[0]
        if len(active) > 1:
            raise SeasonCatalogError("More than one enabled season is active")

        candidates = tuple(
            context
            for context in self._contexts.values()
            if context.enabled
            and context.mutable
            and context.season_id != "all_time"
        )
        if candidates:
            return candidates[-1]
        raise SeasonCatalogError("No enabled mutable ingestion season is configured")

    def context(self, season_id: str) -> SeasonContext:
        """Alias for :meth:`get` for dependency-injection call sites."""

        return self.get(season_id)

    def supports_page(self, season_id: str, page_key: str) -> bool:
        """Return whether the season exposes a page capability."""

        return page_key in self.get(season_id).supported_pages

    def supports_operation(self, season_id: str, operation_key: str) -> bool:
        """Return whether the season exposes an operation capability."""

        return operation_key in self.get(season_id).supported_operations

    def resolve_namespace(
        self,
        season_id: str,
        requested: str | None = None,
    ) -> str:
        """Resolve the default or explicitly requested data namespace."""

        context = self.get(season_id)
        if requested is None:
            return context.namespace
        if requested not in _VALID_NAMESPACES:
            valid = ", ".join(sorted(_VALID_NAMESPACES))
            raise ValueError(f"Unknown namespace {requested!r}; expected one of {valid}")
        return requested

    def assert_mutable(
        self,
        season_id: str,
        namespace: str | None = None,
    ) -> None:
        """Raise unless the requested season namespace may be changed."""

        context = self.get(season_id)
        resolved_namespace = self.resolve_namespace(season_id, namespace)
        if resolved_namespace == "snapshot":
            raise SeasonMutationError(
                f"Season {season_id!r} snapshot data is immutable"
            )
        if not context.mutable:
            raise SeasonMutationError(f"Season {season_id!r} is immutable")

    def validate_catalog(self) -> None:
        """Validate configuration structure and lifecycle consistency."""

        if not self._definitions:
            raise SeasonCatalogError("Season catalog is empty")

        labels: set[str] = set()
        active_ids: list[str] = []

        for season_id, definition in self._definitions.items():
            if not isinstance(season_id, str) or not _SEASON_ID_PATTERN.fullmatch(
                season_id
            ):
                raise SeasonCatalogError(
                    f"Invalid season ID {season_id!r}; use lowercase identifiers"
                )
            if not isinstance(definition, dict):
                raise SeasonCatalogError(
                    f"Season {season_id!r} configuration must be an object"
                )

            missing = {
                field
                for field in ("label", "status", "enabled", "data_ready")
                if field not in definition
            }
            if missing:
                names = ", ".join(sorted(missing))
                raise SeasonCatalogError(
                    f"Season {season_id!r} is missing required fields: {names}"
                )

            label = definition["label"]
            status = definition["status"]
            if not isinstance(label, str) or not label.strip():
                raise SeasonCatalogError(
                    f"Season {season_id!r} label must be non-empty text"
                )
            if label in labels:
                raise SeasonCatalogError(f"Duplicate season label: {label!r}")
            labels.add(label)

            if status not in _VALID_STATUSES:
                allowed = ", ".join(sorted(_VALID_STATUSES))
                raise SeasonCatalogError(
                    f"Season {season_id!r} has invalid status {status!r}; "
                    f"expected one of {allowed}"
                )
            for field in ("enabled", "data_ready"):
                if not isinstance(definition[field], bool):
                    raise SeasonCatalogError(
                        f"Season {season_id!r} field {field!r} must be boolean"
                    )

            if status == "active" and definition["enabled"]:
                active_ids.append(season_id)
            if status == "finalized" and not definition["data_ready"]:
                raise SeasonCatalogError(
                    f"Finalized season {season_id!r} must be data-ready"
                )

        if len(active_ids) > 1:
            raise SeasonCatalogError(
                "More than one enabled season is active: " + ", ".join(active_ids)
            )
        if self._default_season_id not in self._definitions:
            raise SeasonCatalogError(
                f"Default season {self._default_season_id!r} is not configured"
            )
        if not self._definitions[self._default_season_id]["enabled"]:
            raise SeasonCatalogError(
                f"Default season {self._default_season_id!r} is disabled"
            )

    def _load_definitions(self) -> dict[str, dict[str, Any]]:
        try:
            payload = json.loads(self._config_path.read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            raise SeasonCatalogError(
                f"Season configuration not found: {self._config_path}"
            ) from exc
        except json.JSONDecodeError as exc:
            raise SeasonCatalogError(
                f"Season configuration is not valid JSON: {self._config_path}"
            ) from exc

        if not isinstance(payload, dict):
            raise SeasonCatalogError("Season configuration root must be an object")
        return self._copy_definitions(payload)

    @staticmethod
    def _copy_definitions(
        definitions: Mapping[str, Mapping[str, Any]],
    ) -> dict[str, dict[str, Any]]:
        return {
            str(season_id): dict(definition)
            for season_id, definition in definitions.items()
        }

    def _build_context(
        self,
        season_id: str,
        definition: Mapping[str, Any],
    ) -> SeasonContext:
        finalized = definition["status"] == "finalized"
        mutable = bool(definition["enabled"]) and not finalized
        namespace = "snapshot" if finalized else "working"

        pages = _PAGES_BY_SEASON.get(
            season_id,
            self._default_pages(definition),
        )
        operations = (
            _OPERATIONS_BY_STATUS[definition["status"]]
            if definition["enabled"]
            else ()
        )

        return SeasonContext(
            season_id=season_id,
            display_name=definition["label"],
            status=definition["status"],
            enabled=definition["enabled"],
            data_ready=definition["data_ready"],
            namespace=namespace,
            working_root=self._project_root / "data",
            snapshot_root=self._project_root / "data" / "seasons" / season_id,
            finalized=finalized,
            mutable=mutable,
            supported_pages=pages,
            supported_operations=operations,
        )

    @staticmethod
    def _default_pages(definition: Mapping[str, Any]) -> tuple[str, ...]:
        operations_pages = (
            "Operations Center",
            "Raw Data Browser",
            "Key Output Health",
            "Reports",
        )
        if definition["data_ready"]:
            return (
                "League Hub",
                "Award Detail",
                "Managers",
                *operations_pages,
            )
        return operations_pages
