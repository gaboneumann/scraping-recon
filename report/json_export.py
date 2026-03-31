"""
report/json_export.py
Serializes a ReconReport to JSON string or file.
"""
from __future__ import annotations

import json
from pathlib import Path

from models.schemas import ReconReport


def to_json(report: ReconReport, indent: int = 2) -> str:
    """Return the report as a formatted JSON string."""
    return report.model_dump_json(indent=indent)


def save_json(report: ReconReport, path: str) -> None:
    """Write the report as JSON to a file."""
    Path(path).write_text(to_json(report), encoding="utf-8")
