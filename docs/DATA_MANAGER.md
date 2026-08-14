# DataManager

## Status

DataManager was implemented in Sprint 1.2 and became the read-only artifact
boundary for all migrated Streamlit pages during Sprints 2.0–2.7. Existing
physical data layouts and producer outputs remain unchanged.

Implementation:

- result models: `core/models/data_result.py`
- artifact model: `core/models/artifact_info.py`
- storage interface: `core/storage/storage_provider.py`
- local provider: `core/storage/local_filesystem_provider.py`
- service: `core/services/data_manager.py`
- tests: `tests/test_data_manager.py` and
  `tests/test_local_filesystem_provider.py`

## Responsibilities

DataManager is the framework-independent, read-oriented gateway to registered
project data. It:

- resolves canonical definitions and aliases through DatasetRegistry;
- resolves seasons and working/snapshot policy through SeasonManager;
- constructs paths only from season roots and registered templates;
- loads CSV, JSON, Parquet, TXT, and log-style text;
- distinguishes available, missing, empty, and invalid results;
- returns provenance for every load;
- validates registered required columns;
- supports registered dataset families;
- inspects artifact metadata;
- catalogs safe artifacts under approved roots;
- creates bounded previews;
- caches data in memory with defensive copies;
- invalidates cache entries explicitly or when source metadata changes.

It does not calculate analytics, call APIs, execute subprocesses, trigger
refreshes, import Streamlit, or expose a public write method.

## Page loading rule

Page modules request registered datasets through logical keys. The Raw Data
Browser may use `catalog()` and `preview_artifact()` for safe, bounded
inspection of artifacts without dedicated definitions. Pages do not build
artifact paths, call pandas readers, scan directories, or bypass containment
checks.

Operations remain outside DataManager. Operational pages use
OperationsService for execution and DataManager only for read-only status or
result artifacts.

## Dependencies

```text
DatasetRegistry ----\
                     \
SeasonManager --------> DataManager
                       /
StorageProvider ------/
```

- DatasetRegistry owns logical keys, aliases, filenames, subdirectories,
  schemas, and family declarations.
- SeasonManager owns season validity, roots, and working/snapshot resolution.
- StorageProvider owns low-level read-only storage access.
- pandas is imported only by DataManager for CSV and Parquet parsing.
- Standard-library logging is injected until LoggingService is implemented.

DataManager never chooses the active season independently.

## Storage Abstraction

### StorageProvider

The minimal read-only contract provides:

- `normalize(path)`
- `exists(path)`
- `stat(path)`
- `read_bytes(path)`
- `read_text(path, encoding)`
- `list_files(root, pattern=None, recursive=False)`

It contains no pandas, registry, season, page, or analytics logic.

### LocalFilesystemProvider

The production local implementation:

- normalizes paths to absolute `Path` objects;
- performs safe existence and metadata checks;
- reads text and bytes;
- lists files in deterministic case-insensitive path order;
- returns an empty tuple for a missing listing root;
- raises `ArtifactAccessError` for inaccessible or invalid roots.

It is read-only.

## Result Models

### DataStatus

| Status | Meaning |
| --- | --- |
| `available` | Artifact loaded and passed initial validation |
| `missing` | Optional artifact or family is absent |
| `empty` | Artifact exists but has no usable content |
| `invalid` | Artifact loaded but failed registered validation |
| `stale` | Reserved for future freshness policy |
| `unsupported` | Reserved for structured external reporting; unsupported registered formats currently raise |

### DataProvenance

Every DataResult records:

- canonical and requested dataset keys;
- season ID;
- resolved working or snapshot namespace;
- absolute resolved path;
- detected format;
- UTC modification time;
- size in bytes;
- whether an alias was used;
- whether a compatibility fallback was used.

Sprint 1.2 does not implement physical fallback paths, so `fallback_used` is
always false.

### DataResult

DataResult is immutable and contains:

- status;
- loaded data or `None`;
- provenance;
- validation errors;
- warnings.

The result object is immutable, but pandas DataFrames remain naturally mutable.
DataManager therefore returns a deep defensive DataFrame copy for every load,
including cache hits.

### ArtifactInfo

ArtifactInfo is immutable metadata for catalog and inspection:

- normalized path and name;
- suffix;
- size and UTC modification time;
- file indicator;
- known dataset key when identifiable;
- namespace and season ID.

## Public API

### `resolve_path(dataset_key, season_id, namespace=None)`

Resolves a singular artifact or registered family pattern. Unknown dataset or
season identifiers propagate the registry/season `KeyError`.

### `exists(dataset_key, season_id, namespace=None)`

Checks a singular file or whether a family has at least one member.

### `project_relative_path(dataset_key, season_id, namespace=None)`

Returns the registered resolved path relative to the project root for
presentation. It uses the same containment checks as normal resolution and
performs no filesystem inspection.

### `project_relative_artifact_path(path, season_id, namespace=None)`

Returns a project-relative display path for an already resolved family member.
The member must remain below the selected season namespace root.

### `probe(dataset_key, season_id, namespace=None)`

Returns availability, empty-file status, format, metadata, and provenance
without loading contents. Unlike `load()`, a missing required dataset is a
structured `missing` result so diagnostics pages can report every missing
contract in one pass.

### `load(dataset_key, season_id, namespace=None, options=None)`

Loads a singular artifact based on its registered suffix. Family definitions
must use `load_family()`.

Supported options:

- `encoding` for CSV/JSON/text decoding;
- `csv` mapping passed to `pandas.read_csv`;
- `parquet` mapping passed to `pandas.read_parquet`.

Unknown options raise `DataManagerError`.

### `load_frame(...)`

Loads only CSV or Parquet definitions.

### `load_json(...)`

Loads only JSON definitions.

### `load_text(..., encoding=None, errors=None)`

Loads only TXT or log definitions.

The optional decoding error policy supports compatibility behavior such as
`errors="replace"`. Text loading preserves Python universal-newline behavior.

### `load_family(..., filters=None)`

Loads every unique family member in deterministic path order. The implemented
filters are exact `name`, `name_contains`, positive `limit`, and normal
format-specific load `options`. No matches return a `missing` DataResult whose
data is an empty tuple.

### `inspect_family(..., filters=None)`

Returns deterministic ArtifactInfo metadata for registered family members
without loading their contents. It supports exact `name` and
`name_contains` filters.

### `inspect(...)`

Returns ArtifactInfo for a singular artifact. A missing optional artifact
returns `None`; a missing required artifact raises DatasetNotFoundError.

### `validate(...)`

Loads the artifact and applies the same initial validation contract. It is a
separate public seam for future validation expansion.

### `catalog(season_id, namespace=None, filters=None)`

Recursively lists safe supported artifacts under exactly one approved working
or snapshot root.

Filters:

- `recursive` boolean;
- `name_contains`;
- `suffixes`.

### `preview(..., row_limit=100, column_limit=50)`

Returns a bounded defensive preview:

- DataFrames are limited by rows and columns;
- JSON lists are limited by item count;
- text is limited by line count;
- warnings explain applied limits.

Limits must be positive.

### `preview_artifact(artifact, season_id, namespace=None, ...)`

Returns a bounded preview for an `ArtifactInfo` previously discovered through
`catalog()`. The artifact must remain within the requested working or snapshot
root and must match the requested season and namespace metadata. This supports
safe read-only inspection of both registered and unregistered catalog files
without exposing filesystem loading to presentation code.

CSV reads apply the row bound while parsing. DataFrames, JSON lists, and text
receive the same defensive row, item, line, and column limits as registered
previews.

### `invalidate(dataset_key=None, season_id=None)`

Clears:

- the entire cache;
- one canonical/aliased dataset;
- one season;
- or the intersection of dataset and season.

No save, write, or mutation API exists.

## Path Resolution

DatasetDefinition gained four backward-compatible optional metadata fields in
Sprint 1.2:

- `working_subdirectory`;
- `snapshot_subdirectory`;
- `required_columns`;
- `family`.

Existing constructor calls remain valid because all fields have defaults.
Core registry definitions now declare their physical subdirectories.

Resolution is:

```text
SeasonContext working_root or snapshot_root
    + registered working/snapshot subdirectory template
    + registered filename template
```

Only `{season_id}` is currently supplied to templates. The normalized result
must remain below the selected approved root.

Examples:

```text
master_player_weekly + 2627 + working
    -> <project>/data/processed/master_player_weekly_2627.csv

master_player_weekly + 2526 + snapshot
    -> <project>/data/seasons/2526/processed/master_player_weekly_2526.csv

draft_rankings + 2627 + working
    -> <project>/data/models/draft_2627/draft_rankings_2627.csv
```

DataManager does not search for alternative filenames. Aliases resolve logical
keys only. Future physical fallbacks must be explicit registry metadata and
must set provenance `fallback_used`.

## Namespace Behavior

The `namespace` argument uses SeasonManager lifecycle namespaces:

- `working`
- `snapshot`

DatasetDefinition's namespace is a logical dataset grouping such as processed,
analytics, reference, draft, or reports. It does not override lifecycle
selection.

Finalized seasons default to snapshot reads. Mutable seasons default to working
reads. Explicit snapshot reads are allowed for any valid season. DataManager
has no public write API, so finalized snapshots cannot be mutated through it.

## Supported Formats

| Suffix | Result data |
| --- | --- |
| `.csv` | pandas DataFrame |
| `.parquet` | pandas DataFrame |
| `.json` | decoded Python JSON value |
| `.txt` | string |
| `.log` | string |

CSV and Parquet loading preserve source columns and values according to pandas
parsing. DataManager does not rename, normalize, coerce, or calculate fields.

Unsupported formats raise `UnsupportedFormatError`.

## Missing, Empty, Invalid, and Corrupt Data

The error contract is consistent:

- Missing required dataset: raises `DatasetNotFoundError`.
- Missing optional dataset: returns `DataStatus.MISSING`.
- Zero-byte artifact: returns `DataStatus.EMPTY`.
- Parsed empty table/collection/text: returns `DataStatus.EMPTY`.
- Missing registered required columns: returns `DataStatus.INVALID` with
  explicit column names.
- Malformed CSV/JSON/Parquet or another parse failure: raises
  `DatasetValidationError`.
- Filesystem permission/access failure: raises `ArtifactAccessError`.
- Unknown keys and seasons: existing registry/season errors propagate.

Expected absence stays structured. Corruption and invalid service contracts are
not silently converted to missing results.

## Caching

The in-memory cache key includes:

- canonical dataset key;
- season ID;
- lifecycle namespace;
- resolved path;
- normalized relevant load options.

Each cache entry records source modification time in nanoseconds and size.
A mismatch causes an automatic reload. `invalidate()` provides explicit
control.

DataFrames are deep-copied both when stored and when returned. Other values are
deep-copied. Two callers never receive the same cached mutable object.

Definitions with `cacheable=False` bypass the cache.

## Dataset Families

A family is explicitly declared with:

- `family=True`;
- a wildcard filename template;
- registered working/snapshot subdirectories.

Wildcard templates are rejected for singular definitions. DataManager lists
only below the registered family directory, removes no files, and relies on the
storage provider's deterministic unique listing.

No filename is synthesized beyond the registered wildcard template.

## Catalog Safety

Catalog scans are restricted to the SeasonContext's working or snapshot root.
They never scan the repository root.

Allowed suffixes:

- CSV
- JSON
- Parquet
- TXT
- LOG

Excluded:

- dotfiles and files inside dot-directories;
- `.env`;
- lock files;
- names/paths containing `auth_state`;
- names/paths containing credential, secret, or token markers;
- unsupported binary/media/archive formats;
- anything resolving outside the approved root.

Catalog returns metadata only and never reads artifact contents.

## Exceptions

| Exception | Purpose |
| --- | --- |
| `DataManagerError` | Invalid DataManager contract or use |
| `DatasetNotFoundError` | Missing required dataset |
| `UnsupportedFormatError` | Unsupported or mismatched format |
| `DatasetValidationError` | Artifact parsing/corruption failure |
| `ArtifactAccessError` | Storage access or permission failure |

DatasetRegistry and SeasonManager exceptions are reused rather than wrapped or
duplicated.

## Examples

```python
manager = DataManager()

league = manager.load_frame("league_table", "2526")
draft = manager.preview(
    "draft_rankings",
    "2627",
    row_limit=25,
    column_limit=12,
)
reports = manager.catalog(
    "2526",
    filters={"suffixes": [".txt"]},
)
```

These calls do not alter remaining legacy application loaders. Key Output
Health adopted the service in Sprint 2.0, followed by Reports in Sprint 2.1
and League Hub in Sprint 2.2. League Hub uses `load_frame()` for all eleven
registered inputs and required no page-specific DataManager capability.
Managers followed in Sprint 2.3, using the same generic `load_frame()` API for
sixteen registered inputs without adding manager-specific service methods.
Award Detail followed in Sprint 2.4 with five registered inputs and the same
generic `load_frame()` contract.
Draft HQ followed in Sprint 2.5 with registered rankings and optional
eligibility overrides, also using only `load_frame()`.
Raw Data Browser followed in Sprint 2.6 using `catalog()`,
`project_relative_artifact_path()`, and `preview_artifact()`.

## Deferred Capabilities

The following are intentionally deferred:

- Streamlit page integration;
- public or operations-facing writers;
- snapshot manifest hash verification;
- freshness/staleness policy;
- physical legacy fallback paths;
- a complete schema framework;
- remote/object storage providers;
- persistent or distributed caching;
- LoggingService integration;
- operation-triggered cache invalidation;
- dataset-specific page loader methods.

Snapshot manifest verification needs a versioned manifest contract and is not
forced into the minimal Sprint 1.2 reader.
