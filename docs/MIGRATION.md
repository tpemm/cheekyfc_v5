# Migration checklist

1. Back up the current project folder.
2. Copy the contents of this package into the project root.
3. Keep the existing `data`, `raw_data`, `processed_data`, and `reports` folders.
4. Activate the Python 3.12 environment.
5. Run `python -m compileall app config fantrax fantrax.py`.
6. Run `python fantrax.py app` and confirm the 2025/26 dashboard loads.
7. Run `python fantrax.py analytics` only after the app test succeeds.
8. Initialize Git and push after both tests pass.

The old flat `scripts` folder is no longer used by the new command center. Keep it temporarily as a rollback copy, then archive or remove it after validation.
