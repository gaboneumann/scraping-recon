#!/usr/bin/env python3
"""
scripts/csv_to_fixture.py
Generate pytest fixtures from T2 false negative log CSV.

Reads CSV with columns: platform,url,signal,expected,actual,discovered_date,status
and generates pytest test code that can be imported and run.

Usage:
    python scripts/csv_to_fixture.py docs/T2_false_negative_log.csv
    python scripts/csv_to_fixture.py docs/T2_false_negative_log.csv --platform woocommerce
"""
from __future__ import annotations

import argparse
import csv
from pathlib import Path
from typing import Any


def csv_to_pytest_case(row: dict[str, str]) -> str:
    """
    Convert a CSV row to a pytest test case string.

    Args:
        row: Dictionary with keys: platform, url, signal, expected, actual, discovered_date, status

    Returns:
        Pytest test function as a string
    """
    platform = row["platform"].lower().replace(" ", "_")
    signal = row["signal"].lower().replace(" ", "_")
    url = row["url"]
    expected = row["expected"]
    actual = row["actual"]

    test_name = f"test_{platform}_{signal}"

    test_code = f'''@pytest.mark.real
def {test_name}() -> None:
    """
    Platform: {row["platform"]}
    URL: {url}
    Signal: {row["signal"]}
    Expected: {expected}, Actual: {actual}
    Discovered: {row["discovered_date"]}
    Status: {row["status"]}
    """
    # TODO: Implement detection logic for {row["platform"]} {row["signal"]}
    # Verify that {expected} signal is properly detected
    pass
'''
    return test_code


def generate_fixture_code(
    csv_path: Path,
    platform_filter: str | None = None,
) -> str:
    """
    Generate pytest fixture code from CSV file.

    Args:
        csv_path: Path to CSV file
        platform_filter: Optional platform name to filter by

    Returns:
        Python code with test fixtures
    """
    rows = []
    with open(csv_path) as f:
        reader = csv.DictReader(f)
        for row in reader:
            if platform_filter and row["platform"].lower() != platform_filter.lower():
                continue
            rows.append(row)

    if not rows:
        return f"# No rows found matching platform: {platform_filter}\n"

    test_cases = "\n\n".join(csv_to_pytest_case(row) for row in rows)

    header = '''"""
tests/real/test_t2_false_negatives.py
Auto-generated fixtures from T2 false negative log.
Re-run csv_to_fixture.py to regenerate.
"""
from __future__ import annotations

import pytest

'''

    return header + test_cases


def main() -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Generate pytest fixtures from T2 false negative log CSV"
    )
    parser.add_argument(
        "csv_file",
        type=Path,
        help="Path to CSV file (e.g., docs/T2_false_negative_log.csv)",
    )
    parser.add_argument(
        "--platform",
        type=str,
        default=None,
        help="Filter by platform (e.g., woocommerce)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Output file (default: stdout)",
    )

    args = parser.parse_args()

    # Verify CSV exists
    if not args.csv_file.exists():
        raise FileNotFoundError(f"CSV file not found: {args.csv_file}")

    # Generate code
    code = generate_fixture_code(args.csv_file, args.platform)

    # Output
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(code)
        print(f"Generated fixtures to: {args.output}")
    else:
        print(code)


if __name__ == "__main__":
    main()
