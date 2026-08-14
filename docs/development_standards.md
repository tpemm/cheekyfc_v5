# Development Standards

Player graphics may only use metrics declared in the comparison catalog. Missing values must remain missing, percentile direction must come from catalog metadata, and all players in one comparison must share the same prepared distribution and scale.

All new user-facing views must follow [the design system](design_system.md): use semantic tokens, the shared page shell/components, native accessible Streamlit controls, supported dataframe configuration, and chart-theme helpers. Page-local hard-coded palettes and unstable generated-class CSS selectors require explicit justification and regression coverage.

These standards apply to all future work in Fantrax Data v5.

## Architecture

- Preserve `DatasetRegistry → SeasonManager → DataManager →
  OperationsService → views`.
- Register every application dataset centrally before a view consumes it.
- Use OperationsService for state-changing workflows; never expose arbitrary
  commands or builder paths.
- Keep views presentation-only and analytics framework-independent.
- Put reusable calculations and candidate generation in domain modules.
- Pass or resolve season IDs explicitly and preserve working/snapshot isolation.
- Keep `app.py → core.legacy_renderer.render_application()` as the entry path.
- Maintain one custom sidebar; do not add Streamlit native multipage navigation.

## Data

- Never overwrite source/provider data as a shortcut.
- Generated artifacts must be reproducible from registered or documented inputs.
- Preserve provider IDs and canonical registry IDs across transformations.
- Record source, method, confidence, and timestamps where the workflow supports them.
- Preserve immutable historical and future draft-day snapshots.
- Avoid silent coercion. Normalize pandas/NumPy values at JSON and service boundaries.
- Represent missing values explicitly; do not serialize non-standard `NaN`.
- Treat user decision stores as production reference data: preserve unrelated rows.
- Invalidate DataManager reads and regenerate dependent artifacts after successful writes.

## Player identity

- Stable provider/player IDs have priority over names.
- Exact matches outrank explicit aliases and heuristics.
- Aliases must be explicit, centralized, deterministic, and auditable.
- Active status, team, position, uniqueness, and duplicate-link checks remain enforced.
- Maintain one canonical player identity; never leave avoidable active duplicates.
- Do not introduce broad nickname, mononym, transliteration, or partial-surname guessing.
- Review decisions are specific to one historical/current candidate pair.
- Ignoring one pair must not suppress every future candidate.
- Transfers require explicit distinction from identity conflicts.
- Suggestions never approve themselves.

## UI

- Views use DataManager and logical dataset keys; no direct `read_csv` or path construction.
- Views do not write CSVs or call builders.
- State-changing actions require an explicit user click and use OperationsService.
- Show clear success/failure feedback based on actual operation results.
- Successful writes regenerate dependent projections when required, invalidate
  affected datasets, and rerun so displayed state matches persisted state.
- Failed operations must not optimistically update metrics or tables.
- Preserve selected identity/player state when practical, but prioritize correctness.
- Do not redesign global styling or navigation for a page-local feature.

## Testing

- Every bug receives a regression test that fails for the original defect.
- Every new dataset receives DatasetRegistry and loading-contract coverage.
- Every new operation receives parameter, season, success, and failure tests.
- Every new page receives rendering/AppTest and architecture-boundary coverage.
- Test all state transitions, including failure and reversible cleanup.
- Preserve existing user decision files; use injected services or pair-specific,
  reversible workflows.
- Run focused tests while developing and the entire suite before completion.
- Do not change tests merely to accept broken or weakened behavior.

## Documentation

- Label functionality as Current, Planned, Proposed, or Under investigation.
- Derive dataset keys, operations, pages, and season support from code.
- Do not describe an external API capability as available without evidence.
- Update this documentation set when architectural or lifecycle contracts change.
