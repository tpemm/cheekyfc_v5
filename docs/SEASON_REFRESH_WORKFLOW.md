# Season Refresh Workflow

## Normal weekly update

1. Open **Operations**.
2. Click **SMART REFRESH**.
3. If prompted, run `python scripts/refresh_desktop_sources.py` on the commissioner desktop.
4. Return to Operations and click **SMART REFRESH** again.
5. Confirm **REFRESH COMPLETE**.

The current gameweek is acquired/rebuilt and remains awaiting stability when complete. The previous gameweek is rechecked for provider corrections and becomes finalization-ready only through the existing stability rules. Older finalized gameweeks are protected and are never silently rewritten. Provider `CACHE_HIT` and `NO_ACTION_REQUIRED` results are successful outcomes.

## Install

Use the activated project `.venv`:

```powershell
python -m pip install -r requirements-desktop.txt
python -m playwright install chromium
```

For tests/development, use `python -m pip install -r requirements-dev.txt`.
Desktop requirements include the existing app and football acquisition requirements
plus Playwright; dev adds pytest. Streamlit still uses only `requirements.txt`.

## Safe GitHub publishing

Weekly command: `python scripts/refresh_desktop_sources.py`

Validation only: `python scripts/refresh_desktop_sources.py --publish-dry-run`

The weekly command publishes after all acquisition/build/reconciliation stages
and the previous-GW check succeed. Existing weekly quality validations are the
publish gate; the full pytest suite is not run every week. Finalized previous
GWs are skipped, and the command never requests finalization.

Publishing requires commissioner role and explicit
`COMMISSIONER_REFRESH_ENABLED=true` in the existing local machine configuration
or environment. It fetches `origin/main`, requires main at the remote HEAD, and
blocks on unrelated tracked edits, untracked source files, existing staged
changes, or any unpushed commits. Review and commit source changes separately
before weekly publishing. The publisher never stashes, resets, rebases or
force-pushes. A push failure leaves its local commit for manual review/recovery;
the next run reports that unpushed commit.

`config/refresh_publish_manifest.json` freezes exact current-season model,
reference and quality/evidence paths from deployment
`dfb7282af90a8b3654c6ef366b0efeb6df4f2b27`, plus the desktop completion marker.
Gameweek templates extend the same deployed validation/correction filenames
only for the current and previous GW. No directory globs are used. Historical
products, raw caches, local snapshots, diagnostics and credentials are excluded.
New canonical product filenames or a new season require manifest review.
Untracked data outside the manifest remains local; changed tracked files outside
it block publishing and are listed explicitly.

The dry-run uses the cached season plan and fetches Git metadata, but performs
no authentication, acquisition, rebuild, data writes, staging, commit or push.
Its eligibility is conditional on a future successful refresh; it does not
certify that current data passed a new refresh. Successful publication prints
the verified commit hash. Then open Streamlit and click **SMART REFRESH**.
