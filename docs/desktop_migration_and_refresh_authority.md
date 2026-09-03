# Desktop migration and refresh authority

GitHub is the authority for code, tests, safe configuration, schemas, and methodology. After an explicit handoff, the desktop is the only authoritative live-data writer. The laptop remains a development/client machine that may read synchronized data and perform normal Git and test work.

## Initial migration

1. On the laptop, run the full tests and build `migration_exports/fantrax_data_v5_gw2_desktop_migration.zip`.
2. Commit and push code and safe configuration only. Transfer the ignored ZIP separately; retain the laptop repository and data as rollback.
3. Clone the exact commit on the desktop. Create Python 3.13 environment with `py -3.13 -m venv .venv`, activate it, and run `python -m pip install -r requirements.txt`.
4. Install the browser with `python -m playwright install chromium`.
5. Run `python scripts/import_desktop_migration_package.py <zip> --check`, then rerun without `--check`.
6. Run `python scripts/validate_desktop_migration.py` before any network refresh. An exact package/source commit is preferred; a mismatch produces a warning.
7. Create local, ignored machine configuration from `config/local_machine.env.example`, with commissioner/true values. Export those variables in the desktop shell or environment.
8. Authenticate Fantrax fresh using the existing Operations Center/Fantrax headed browser workflow. Never copy `storage_state.json`, cookies, or browser binaries.
9. Run the app smoke tests and full tests, then `python scripts/weekly_commissioner_refresh.py --season 2627 --plan`.
10. Perform one controlled refresh. Review provider changes separately from pre-refresh migration hashes. A machine change does not finalize GW2.
11. Only after validation, declare the desktop authoritative and set the laptop’s ignored local role to client/false. Verify a laptop refresh is rejected before writes.

## Ongoing workflow

Both machines may develop code through normal Git branches. Machine role governs live-data writes, not Git. The desktop refreshes and validates data, then builds a client package with `python scripts/build_desktop_migration_package.py --type client`. The laptop validates/imports that package and never reacquires providers.

Use packages—not simultaneous OneDrive writes—to synchronize data. OneDrive may transport or back up an export, but only one working tree may write live caches/models.

## Rollback

Keep the repaired laptop checkpoint and data untouched until the desktop completes a controlled refresh. If desktop validation fails, stop desktop writes, retain the package and diagnostics, and continue using the laptop commissioner configuration. Do not copy authentication state between machines.
