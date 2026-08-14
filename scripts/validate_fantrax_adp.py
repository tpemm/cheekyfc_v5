"""Validate a Fantrax preseason export without modifying it."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from analytics.draft.adp_refresh import validate_adp_export


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("path", type=Path)
    args = parser.parse_args()
    report = validate_adp_export(pd.read_csv(args.path))
    print(f"Rows: {report['rows']}")
    print(f"Numeric ADP: {report.get('adp_numeric', 0)}")
    print(f"Missing ADP: {report['missing_adp']} (allowed)")
    print(f"Malformed ADP: {report['malformed_adp']}")
    print(f"Duplicate ID rows: {report['duplicate_ids']}")
    for warning in report["warnings"]:
        print(f"WARNING: {warning}")
    for error in report["errors"]:
        print(f"ERROR: {error}")
    print("VALID" if report["valid"] else "INVALID")
    return 0 if report["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
