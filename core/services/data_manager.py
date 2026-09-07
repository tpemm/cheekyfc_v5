"""Framework-independent, read-oriented gateway to registered project data."""

from __future__ import annotations

import copy
import io
import json
import logging
import time
from collections.abc import Mapping
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from core.models.artifact_info import ArtifactInfo
from core.models.data_result import DataProvenance, DataResult, DataStatus
from core.models.dataset_definition import DatasetDefinition
from core.services.dataset_registry import DatasetRegistry
from core.services.season_manager import SeasonManager
from core.storage.local_filesystem_provider import LocalFilesystemProvider
from core.storage.storage_provider import ArtifactAccessError, StorageProvider


class DataManagerError(RuntimeError):
    """Base error for invalid or unsafe data-manager operations."""


class DatasetNotFoundError(DataManagerError, FileNotFoundError):
    """Raised when a required registered dataset is missing."""


class UnsupportedFormatError(DataManagerError):
    """Raised when a registered artifact has an unsupported format."""


class DatasetValidationError(DataManagerError):
    """Raised when an artifact cannot be parsed safely."""


_SUPPORTED_SUFFIXES = frozenset({".csv", ".json", ".parquet", ".txt", ".log"})
_TABULAR_SUFFIXES = frozenset({".csv", ".parquet"})
_SENSITIVE_NAME_PARTS = (
    "auth_state",
    "credential",
    "secret",
    "token",
)


@dataclass(slots=True)
class _CacheEntry:
    signature: tuple[int, int]
    result: DataResult[Any]


class DataManager:
    """Resolve, load, validate, inspect, and preview registered artifacts."""

    def __init__(
        self,
        registry: DatasetRegistry | None = None,
        season_manager: SeasonManager | None = None,
        storage: StorageProvider | None = None,
        logger: logging.Logger | None = None,
    ) -> None:
        self._registry = registry or DatasetRegistry()
        self._seasons = season_manager or SeasonManager()
        self._storage = storage or LocalFilesystemProvider()
        self._logger = logger or logging.getLogger(__name__)
        self._cache: dict[tuple[Any, ...], _CacheEntry] = {}

    def resolve_path(
        self,
        dataset_key: str,
        season_id: str,
        namespace: str | None = None,
    ) -> Path:
        """Resolve a registered dataset to a safe physical artifact path."""

        definition = self._registry.get(dataset_key)
        context = self._seasons.context(season_id)
        resolved_namespace = self._seasons.resolve_namespace(season_id, namespace)
        root = (
            context.snapshot_root
            if resolved_namespace == "snapshot"
            else context.working_root
        )
        subdirectory_template = (
            definition.snapshot_subdirectory
            if resolved_namespace == "snapshot"
            else definition.working_subdirectory
        )
        if subdirectory_template is None:
            raise DataManagerError(
                f"Dataset {definition.key!r} has no {resolved_namespace} "
                "subdirectory contract"
            )

        format_values = {"season_id": context.season_id}
        try:
            subdirectory = subdirectory_template.format(**format_values)
            filename = definition.filename_template.format(**format_values)
        except (KeyError, ValueError) as exc:
            raise DataManagerError(
                f"Invalid path template for dataset {definition.key!r}"
            ) from exc

        normalized_root = self._storage.normalize(root)
        resolved = self._storage.normalize(normalized_root / subdirectory / filename)
        if not resolved.is_relative_to(normalized_root):
            raise DataManagerError(
                f"Dataset {definition.key!r} resolves outside its approved root"
            )

        requested_key = str(dataset_key)
        if requested_key != definition.key:
            self._logger.info(
                "dataset_alias_resolved",
                extra={
                    "requested_key": requested_key,
                    "dataset_key": definition.key,
                },
            )
        self._logger.debug(
            "dataset_resolved",
            extra={
                "dataset_key": definition.key,
                "season_id": context.season_id,
                "namespace": resolved_namespace,
            },
        )
        return resolved

    def exists(
        self,
        dataset_key: str,
        season_id: str,
        namespace: str | None = None,
    ) -> bool:
        definition = self._registry.get(dataset_key)
        path = self.resolve_path(dataset_key, season_id, namespace)
        if definition.family:
            return bool(
                self._storage.list_files(
                    path.parent,
                    path.name,
                    recursive=False,
                )
            )
        return self._storage.exists(path)

    def project_relative_path(
        self,
        dataset_key: str,
        season_id: str,
        namespace: str | None = None,
    ) -> str:
        """Return a registered artifact path relative to the project root."""

        context = self._seasons.context(season_id)
        path = self.resolve_path(dataset_key, season_id, namespace)
        project_root = self._storage.normalize(context.working_root).parent
        try:
            return str(path.relative_to(project_root))
        except ValueError as exc:
            raise DataManagerError(
                f"Dataset {dataset_key!r} does not resolve below the project root"
            ) from exc

    def project_relative_artifact_path(
        self,
        artifact_path: str | Path,
        season_id: str,
        namespace: str | None = None,
    ) -> str:
        """Return a safe project-relative path for a resolved family member."""

        context = self._seasons.context(season_id)
        resolved_namespace = self._seasons.resolve_namespace(season_id, namespace)
        approved_root = (
            context.snapshot_root
            if resolved_namespace == "snapshot"
            else context.working_root
        )
        normalized_root = self._storage.normalize(approved_root)
        normalized_path = self._storage.normalize(artifact_path)
        if not normalized_path.is_relative_to(normalized_root):
            raise DataManagerError(
                "Artifact path resolves outside the approved season namespace"
            )
        project_root = self._storage.normalize(context.working_root).parent
        try:
            return str(normalized_path.relative_to(project_root))
        except ValueError as exc:
            raise DataManagerError(
                "Artifact path does not resolve below the project root"
            ) from exc

    def probe(
        self,
        dataset_key: str,
        season_id: str,
        namespace: str | None = None,
    ) -> DataResult[None]:
        """Inspect availability without loading artifact contents.

        Unlike ``load()``, a missing required artifact is returned as a
        structured missing result so health and diagnostics surfaces can report
        all missing contracts in one pass.
        """

        definition = self._registry.get(dataset_key)
        if definition.family:
            raise DataManagerError(
                f"Dataset {definition.key!r} is a family; use load_family()"
            )
        resolved_namespace = self._seasons.resolve_namespace(season_id, namespace)
        path = self.resolve_path(dataset_key, season_id, resolved_namespace)
        suffix = path.suffix.lower()
        if suffix not in _SUPPORTED_SUFFIXES:
            provenance = self._provenance(
                definition, dataset_key, season_id, resolved_namespace, path, None
            )
            return DataResult(
                status=DataStatus.UNSUPPORTED,
                data=None,
                provenance=provenance,
                validation_errors=(f"Unsupported artifact format: {suffix}",),
            )
        if not self._storage.exists(path):
            provenance = self._provenance(
                definition, dataset_key, season_id, resolved_namespace, path, None
            )
            message = (
                "Required dataset is missing."
                if definition.required
                else "Optional dataset is missing."
            )
            return DataResult(
                status=DataStatus.MISSING,
                data=None,
                provenance=provenance,
                validation_errors=(message,) if definition.required else (),
                warnings=(message,) if not definition.required else (),
            )

        stat = self._storage.stat(path)
        provenance = self._provenance(
            definition, dataset_key, season_id, resolved_namespace, path, stat
        )
        if stat.st_size == 0:
            return DataResult(
                status=DataStatus.EMPTY,
                data=None,
                provenance=provenance,
                validation_errors=("Artifact is empty.",),
            )
        return DataResult(
            status=DataStatus.AVAILABLE,
            data=None,
            provenance=provenance,
        )

    def load(
        self,
        dataset_key: str,
        season_id: str,
        namespace: str | None = None,
        options: Mapping[str, Any] | None = None,
    ) -> DataResult[Any]:
        """Load a singular dataset in its registered format."""

        definition = self._registry.get(dataset_key)
        if definition.family:
            raise DataManagerError(
                f"Dataset {definition.key!r} is a family; use load_family()"
            )
        resolved_namespace = self._seasons.resolve_namespace(season_id, namespace)
        path = self.resolve_path(dataset_key, season_id, resolved_namespace)
        return self._load_path(
            definition=definition,
            requested_key=dataset_key,
            season_id=season_id,
            namespace=resolved_namespace,
            path=path,
            options=options,
        )

    def load_frame(
        self,
        dataset_key: str,
        season_id: str,
        namespace: str | None = None,
        options: Mapping[str, Any] | None = None,
    ) -> DataResult[pd.DataFrame]:
        """Load a registered CSV or Parquet dataset."""

        path = self.resolve_path(dataset_key, season_id, namespace)
        if path.suffix.lower() not in _TABULAR_SUFFIXES:
            raise UnsupportedFormatError(
                f"Dataset {dataset_key!r} is not a tabular artifact"
            )
        return self.load(dataset_key, season_id, namespace, options)

    def load_json(
        self,
        dataset_key: str,
        season_id: str,
        namespace: str | None = None,
    ) -> DataResult[Any]:
        """Load a registered JSON dataset."""

        self._assert_suffix(dataset_key, season_id, namespace, {".json"})
        return self.load(dataset_key, season_id, namespace)

    def load_text(
        self,
        dataset_key: str,
        season_id: str,
        namespace: str | None = None,
        encoding: str | None = None,
        errors: str | None = None,
    ) -> DataResult[str]:
        """Load a registered text or log artifact."""

        self._assert_suffix(dataset_key, season_id, namespace, {".txt", ".log"})
        options: dict[str, Any] = {}
        if encoding:
            options["encoding"] = encoding
        if errors:
            options["text_errors"] = errors
        return self.load(dataset_key, season_id, namespace, options)

    def load_family(
        self,
        dataset_key: str,
        season_id: str,
        namespace: str | None = None,
        filters: Mapping[str, Any] | None = None,
    ) -> DataResult[tuple[DataResult[Any], ...]]:
        """Load a registered file family in deterministic path order."""

        definition = self._registry.get(dataset_key)
        if not definition.family:
            raise DataManagerError(
                f"Dataset {definition.key!r} is not registered as a family"
            )
        resolved_namespace = self._seasons.resolve_namespace(season_id, namespace)
        family_path = self.resolve_path(dataset_key, season_id, resolved_namespace)
        files = self._storage.list_files(
            family_path.parent,
            family_path.name,
            recursive=False,
        )
        family_filters = filters or {}
        exact_name = family_filters.get("name")
        if exact_name is not None:
            files = tuple(path for path in files if path.name == str(exact_name))
        name_contains = str(family_filters.get("name_contains", "")).casefold()
        if name_contains:
            files = tuple(
                path for path in files if name_contains in path.name.casefold()
            )
        limit = family_filters.get("limit")
        if limit is not None:
            if not isinstance(limit, int) or limit < 1:
                raise ValueError("Family limit must be a positive integer")
            files = files[:limit]
        load_options = family_filters.get("options")
        if load_options is not None and not isinstance(load_options, Mapping):
            raise DataManagerError("Family load options must be a mapping")

        provenance = self._provenance(
            definition,
            dataset_key,
            season_id,
            resolved_namespace,
            family_path,
            None,
        )
        if not files:
            return DataResult(
                status=DataStatus.MISSING,
                data=(),
                provenance=provenance,
                warnings=("No artifacts matched the registered family.",),
            )

        members = tuple(
            self._load_path(
                definition=definition,
                requested_key=dataset_key,
                season_id=season_id,
                namespace=resolved_namespace,
                path=path,
                options=load_options,
            )
            for path in files
        )
        statuses = {member.status for member in members}
        status = (
            DataStatus.AVAILABLE
            if statuses == {DataStatus.AVAILABLE}
            else DataStatus.INVALID
        )
        return DataResult(status=status, data=members, provenance=provenance)

    def inspect_family(
        self,
        dataset_key: str,
        season_id: str,
        namespace: str | None = None,
        filters: Mapping[str, Any] | None = None,
    ) -> tuple[ArtifactInfo, ...]:
        """Return metadata for registered family members without loading them."""

        definition = self._registry.get(dataset_key)
        if not definition.family:
            raise DataManagerError(
                f"Dataset {definition.key!r} is not registered as a family"
            )
        resolved_namespace = self._seasons.resolve_namespace(season_id, namespace)
        family_path = self.resolve_path(dataset_key, season_id, resolved_namespace)
        files = self._storage.list_files(
            family_path.parent,
            family_path.name,
            recursive=False,
        )
        family_filters = filters or {}
        exact_name = family_filters.get("name")
        if exact_name is not None:
            files = tuple(path for path in files if path.name == str(exact_name))
        name_contains = str(family_filters.get("name_contains", "")).casefold()
        if name_contains:
            files = tuple(
                path for path in files if name_contains in path.name.casefold()
            )
        return tuple(
            self._artifact_info(
                path,
                dataset_key=definition.key,
                namespace=resolved_namespace,
                season_id=season_id,
            )
            for path in files
        )

    def inspect(
        self,
        dataset_key: str,
        season_id: str,
        namespace: str | None = None,
    ) -> ArtifactInfo | None:
        """Return filesystem metadata for a singular registered artifact."""

        definition = self._registry.get(dataset_key)
        if definition.family:
            raise DataManagerError(
                f"Dataset {definition.key!r} is a family; inspect its members"
            )
        resolved_namespace = self._seasons.resolve_namespace(season_id, namespace)
        path = self.resolve_path(dataset_key, season_id, resolved_namespace)
        if not self._storage.exists(path):
            if definition.required:
                raise DatasetNotFoundError(
                    f"Required dataset {definition.key!r} is missing: {path}"
                )
            return None
        return self._artifact_info(
            path,
            dataset_key=definition.key,
            namespace=resolved_namespace,
            season_id=season_id,
        )

    def validate(
        self,
        dataset_key: str,
        season_id: str,
        namespace: str | None = None,
    ) -> DataResult[Any]:
        """Load and apply the definition's initial validation contract."""

        return self.load(dataset_key, season_id, namespace)

    def catalog(
        self,
        season_id: str,
        namespace: str | None = None,
        filters: Mapping[str, Any] | None = None,
    ) -> tuple[ArtifactInfo, ...]:
        """List safe supported artifacts below one approved season root."""

        context = self._seasons.context(season_id)
        resolved_namespace = self._seasons.resolve_namespace(season_id, namespace)
        root = (
            context.snapshot_root
            if resolved_namespace == "snapshot"
            else context.working_root
        )
        options = filters or {}
        recursive = bool(options.get("recursive", True))
        name_contains = str(options.get("name_contains", "")).casefold()
        requested_suffixes = {
            self._normalize_suffix(str(suffix))
            for suffix in options.get("suffixes", _SUPPORTED_SUFFIXES)
        }
        safe_suffixes = requested_suffixes & _SUPPORTED_SUFFIXES

        known_paths = self._known_paths(season_id, resolved_namespace)
        artifacts: list[ArtifactInfo] = []
        for path in self._storage.list_files(root, recursive=recursive):
            if not self._is_safe_catalog_path(path, root):
                continue
            if path.suffix.lower() not in safe_suffixes:
                continue
            if name_contains and name_contains not in path.name.casefold():
                continue
            normalized = self._storage.normalize(path)
            artifacts.append(
                self._artifact_info(
                    normalized,
                    dataset_key=known_paths.get(normalized),
                    namespace=resolved_namespace,
                    season_id=season_id,
                )
            )
        return tuple(artifacts)

    def preview(
        self,
        dataset_key: str,
        season_id: str,
        namespace: str | None = None,
        *,
        row_limit: int = 100,
        column_limit: int = 50,
    ) -> DataResult[Any]:
        """Load a safe bounded preview without changing source values."""

        if row_limit < 1 or column_limit < 1:
            raise ValueError("row_limit and column_limit must be positive")
        result = self.load(dataset_key, season_id, namespace)
        data = result.data
        warnings = list(result.warnings)

        if isinstance(data, pd.DataFrame):
            if len(data) > row_limit:
                warnings.append(f"Preview limited to {row_limit} rows.")
            if len(data.columns) > column_limit:
                warnings.append(f"Preview limited to {column_limit} columns.")
            data = data.iloc[:row_limit, :column_limit].copy(deep=True)
        elif isinstance(data, list):
            if len(data) > row_limit:
                warnings.append(f"Preview limited to {row_limit} items.")
            data = copy.deepcopy(data[:row_limit])
        elif isinstance(data, str):
            lines = data.splitlines()
            if len(lines) > row_limit:
                warnings.append(f"Preview limited to {row_limit} lines.")
            data = "\n".join(lines[:row_limit])

        return replace(result, data=data, warnings=tuple(warnings))

    def preview_artifact(
        self,
        artifact: ArtifactInfo,
        season_id: str,
        namespace: str | None = None,
        *,
        row_limit: int = 100,
        column_limit: int = 500,
    ) -> DataResult[Any]:
        """Load a bounded preview for one safe artifact returned by ``catalog``."""

        if row_limit < 1 or column_limit < 1:
            raise ValueError("row_limit and column_limit must be positive")

        context = self._seasons.context(season_id)
        resolved_namespace = self._seasons.resolve_namespace(season_id, namespace)
        root = (
            context.snapshot_root
            if resolved_namespace == "snapshot"
            else context.working_root
        )
        path = self._storage.normalize(artifact.path)
        if (
            artifact.season_id not in {None, season_id}
            or artifact.namespace not in {None, resolved_namespace}
            or not self._is_safe_catalog_path(path, root)
        ):
            raise DataManagerError(
                "Artifact is outside the requested season namespace"
            )

        if artifact.dataset_key is not None:
            definition = self._registry.get(artifact.dataset_key)
        else:
            definition = DatasetDefinition(
                key="catalog_artifact",
                display_name=artifact.name,
                description="Safe artifact discovered through DataManager.catalog().",
                classification="catalog",
                namespace=resolved_namespace,
                filename_template=artifact.name,
                producer=None,
                consumers=("data browser",),
                schema_name=None,
            )

        options: dict[str, Any] | None = None
        if path.suffix.lower() == ".csv":
            options = {"csv": {"nrows": row_limit}}
        result = self._load_path(
            definition=definition,
            requested_key=artifact.dataset_key or definition.key,
            season_id=season_id,
            namespace=resolved_namespace,
            path=path,
            options=options,
        )
        data = result.data
        warnings = list(result.warnings)
        if isinstance(data, pd.DataFrame):
            if len(data) > row_limit:
                warnings.append(f"Preview limited to {row_limit} rows.")
            if len(data.columns) > column_limit:
                warnings.append(f"Preview limited to {column_limit} columns.")
            data = data.iloc[:row_limit, :column_limit].copy(deep=True)
        elif isinstance(data, list):
            if len(data) > row_limit:
                warnings.append(f"Preview limited to {row_limit} items.")
            data = copy.deepcopy(data[:row_limit])
        elif isinstance(data, str):
            lines = data.splitlines()
            if len(lines) > row_limit:
                warnings.append(f"Preview limited to {row_limit} lines.")
            data = "\n".join(lines[:row_limit])
        return replace(result, data=data, warnings=tuple(warnings))

    def invalidate(
        self,
        dataset_key: str | None = None,
        season_id: str | None = None,
    ) -> None:
        """Invalidate all cache entries or those matching key and/or season."""

        canonical_key = (
            self._registry.get(dataset_key).key if dataset_key is not None else None
        )
        if canonical_key is None and season_id is None:
            self._cache.clear()
            return

        self._cache = {
            key: entry
            for key, entry in self._cache.items()
            if not (
                (canonical_key is None or key[0] == canonical_key)
                and (season_id is None or key[1] == season_id)
            )
        }

    def _load_path(
        self,
        *,
        definition: DatasetDefinition,
        requested_key: str,
        season_id: str,
        namespace: str,
        path: Path,
        options: Mapping[str, Any] | None,
    ) -> DataResult[Any]:
        suffix = path.suffix.lower()
        if suffix not in _SUPPORTED_SUFFIXES:
            self._logger.warning(
                "dataset_unsupported_format",
                extra={"dataset_key": definition.key, "suffix": suffix},
            )
            raise UnsupportedFormatError(
                f"Unsupported format {suffix!r} for dataset {definition.key!r}"
            )

        if not self._storage.exists(path):
            provenance = self._provenance(
                definition, requested_key, season_id, namespace, path, None
            )
            if definition.required:
                raise DatasetNotFoundError(
                    f"Required dataset {definition.key!r} is missing: {path}"
                )
            return DataResult(
                status=DataStatus.MISSING,
                data=None,
                provenance=provenance,
                warnings=("Optional dataset is missing.",),
            )

        stat = self._storage.stat(path)
        signature = (stat.st_mtime_ns, stat.st_size)
        cache_key = (
            definition.key,
            season_id,
            namespace,
            str(path),
            self._freeze_options(options),
        )
        if definition.cacheable:
            cached = self._cache.get(cache_key)
            if cached is not None and cached.signature == signature:
                self._logger.debug(
                    "dataset_cache_hit",
                    extra={"dataset_key": definition.key, "season_id": season_id},
                )
                return self._copy_result(cached.result)

        provenance = self._provenance(
            definition, requested_key, season_id, namespace, path, stat
        )
        if stat.st_size == 0:
            result = DataResult(
                status=DataStatus.EMPTY,
                data=None,
                provenance=provenance,
                validation_errors=("Artifact is empty.",),
            )
            self._store_cache(cache_key, signature, definition, result)
            return self._copy_result(result)

        started = time.perf_counter()
        try:
            parse_options = options
            if definition.key == "league_active_player_weekly" and suffix == ".csv":
                # Published canonical CSV: use the Python CSV parser consistently
                # across hosted/local pandas builds; preserve identifier strings.
                parse_options = dict(options or {})
                csv_options = dict(parse_options.get("csv", {}))
                csv_options.setdefault("engine", "python")
                csv_options.setdefault("dtype", {"manager_id": str, "fantrax_player_id": str})
                parse_options["csv"] = csv_options
            data = self._parse(path, suffix, parse_options)
        except (ArtifactAccessError, PermissionError):
            raise
        except Exception as exc:
            self._logger.error(
                "dataset_parse_failed",
                extra={"dataset_key": definition.key, "suffix": suffix},
            )
            raise DatasetValidationError(
                f"Could not parse dataset {definition.key!r}: {path} ({type(exc).__name__}: {exc})"
            ) from exc

        validation_errors = self._validation_errors(definition, data)
        empty = self._is_empty(data)
        status = (
            DataStatus.INVALID
            if validation_errors
            else DataStatus.EMPTY
            if empty
            else DataStatus.AVAILABLE
        )
        result = DataResult(
            status=status,
            data=data,
            provenance=provenance,
            validation_errors=validation_errors,
        )
        self._logger.debug(
            "dataset_loaded",
            extra={
                "dataset_key": definition.key,
                "season_id": season_id,
                "duration_ms": round((time.perf_counter() - started) * 1000, 3),
                "status": status.value,
            },
        )
        self._store_cache(cache_key, signature, definition, result)
        return self._copy_result(result)

    def _parse(
        self,
        path: Path,
        suffix: str,
        options: Mapping[str, Any] | None,
    ) -> Any:
        settings = dict(options or {})
        encoding = str(settings.pop("encoding", "utf-8-sig"))
        if suffix == ".csv":
            csv_options = dict(settings.pop("csv", {}))
            csv_options.setdefault("encoding", encoding)
            self._reject_unknown_options(settings)
            return pd.read_csv(io.BytesIO(self._storage.read_bytes(path)), **csv_options)
        if suffix == ".parquet":
            parquet_options = dict(settings.pop("parquet", {}))
            self._reject_unknown_options(settings)
            return pd.read_parquet(
                io.BytesIO(self._storage.read_bytes(path)),
                **parquet_options,
            )
        if suffix == ".json":
            self._reject_unknown_options(settings)
            return json.loads(self._storage.read_text(path, encoding=encoding))
        if suffix in {".txt", ".log"}:
            text_errors = str(settings.pop("text_errors", "strict"))
            self._reject_unknown_options(settings)
            text = self._storage.read_bytes(path).decode(
                encoding,
                errors=text_errors,
            )
            return text.replace("\r\n", "\n").replace("\r", "\n")
        raise UnsupportedFormatError(f"Unsupported artifact format: {suffix}")

    @staticmethod
    def _reject_unknown_options(options: Mapping[str, Any]) -> None:
        if options:
            names = ", ".join(sorted(options))
            raise DataManagerError(f"Unsupported load options: {names}")

    @staticmethod
    def _validation_errors(
        definition: DatasetDefinition,
        data: Any,
    ) -> tuple[str, ...]:
        if not definition.required_columns:
            return ()
        if not isinstance(data, pd.DataFrame):
            return (
                f"Schema {definition.schema_name or definition.key!r} requires "
                "tabular data.",
            )
        missing = tuple(
            column
            for column in definition.required_columns
            if column not in data.columns
        )
        if not missing:
            return ()
        return ("Missing required columns: " + ", ".join(missing),)

    @staticmethod
    def _is_empty(data: Any) -> bool:
        if isinstance(data, pd.DataFrame):
            return data.empty
        if isinstance(data, (dict, list, tuple, str, bytes)):
            return len(data) == 0
        return data is None

    def _provenance(
        self,
        definition: DatasetDefinition,
        requested_key: str,
        season_id: str,
        namespace: str,
        path: Path,
        stat: Any | None,
    ) -> DataProvenance:
        return DataProvenance(
            dataset_key=definition.key,
            requested_key=requested_key,
            season_id=season_id,
            namespace=namespace,
            resolved_path=self._storage.normalize(path),
            format=path.suffix.lower().lstrip("*."), 
            modified_time=(
                datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc)
                if stat is not None
                else None
            ),
            size_bytes=stat.st_size if stat is not None else None,
            alias_used=requested_key != definition.key,
            fallback_used=False,
        )

    def _artifact_info(
        self,
        path: Path,
        *,
        dataset_key: str | None,
        namespace: str,
        season_id: str,
    ) -> ArtifactInfo:
        stat = self._storage.stat(path)
        return ArtifactInfo(
            path=self._storage.normalize(path),
            name=path.name,
            suffix=path.suffix.lower(),
            size_bytes=stat.st_size,
            modified_time=datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc),
            is_file=True,
            dataset_key=dataset_key,
            namespace=namespace,
            season_id=season_id,
        )

    def _known_paths(self, season_id: str, namespace: str) -> dict[Path, str]:
        known: dict[Path, str] = {}
        for definition in self._registry.list_all():
            if definition.family:
                continue
            path = self.resolve_path(definition.key, season_id, namespace)
            known[self._storage.normalize(path)] = definition.key
        return known

    def _is_safe_catalog_path(self, path: Path, root: Path) -> bool:
        normalized_root = self._storage.normalize(root)
        normalized = self._storage.normalize(path)
        if not normalized.is_relative_to(normalized_root):
            return False
        relative_parts = normalized.relative_to(normalized_root).parts
        lowered_parts = tuple(part.casefold() for part in relative_parts)
        if any(part.startswith(".") for part in relative_parts):
            return False
        if normalized.suffix.lower() == ".lock":
            return False
        joined = "/".join(lowered_parts)
        return not any(marker in joined for marker in _SENSITIVE_NAME_PARTS)

    def _assert_suffix(
        self,
        dataset_key: str,
        season_id: str,
        namespace: str | None,
        allowed: set[str],
    ) -> None:
        suffix = self.resolve_path(dataset_key, season_id, namespace).suffix.lower()
        if suffix not in allowed:
            raise UnsupportedFormatError(
                f"Dataset {dataset_key!r} has format {suffix!r}, "
                f"expected one of {sorted(allowed)}"
            )

    def _store_cache(
        self,
        key: tuple[Any, ...],
        signature: tuple[int, int],
        definition: DatasetDefinition,
        result: DataResult[Any],
    ) -> None:
        if definition.cacheable:
            self._cache[key] = _CacheEntry(signature, self._copy_result(result))

    @staticmethod
    def _copy_result(result: DataResult[Any]) -> DataResult[Any]:
        data = result.data
        if isinstance(data, pd.DataFrame):
            copied = data.copy(deep=True)
        else:
            copied = copy.deepcopy(data)
        return replace(result, data=copied)

    @classmethod
    def _freeze_options(cls, value: Any) -> Any:
        if isinstance(value, Mapping):
            return tuple(
                sorted((str(key), cls._freeze_options(item)) for key, item in value.items())
            )
        if isinstance(value, (list, tuple, set, frozenset)):
            return tuple(cls._freeze_options(item) for item in value)
        try:
            hash(value)
        except TypeError:
            return repr(value)
        return value

    @staticmethod
    def _normalize_suffix(suffix: str) -> str:
        return suffix.lower() if suffix.startswith(".") else f".{suffix.lower()}"
