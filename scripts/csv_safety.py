"""Helpers for human-facing CSV exports.

CSV files in the QC packet are often opened in spreadsheet software. Prefix
formula-like cells so package-controlled text is displayed as text instead of
being evaluated as a spreadsheet formula.
"""

from __future__ import annotations

from typing import Any, Iterable, Mapping


FORMULA_PREFIXES = ("=", "+", "-", "@")
LEADING_IGNORED_BY_SPREADSHEETS = " \t\r\n\ufeff"


def csv_safe_cell(value: Any) -> Any:
    if value is None:
        return ""
    if not isinstance(value, str):
        return value
    stripped = value.lstrip(LEADING_IGNORED_BY_SPREADSHEETS)
    if stripped.startswith(FORMULA_PREFIXES):
        return "'" + value
    return value


def csv_safe_row(row: Mapping[str, Any], fieldnames: Iterable[str]) -> dict[str, Any]:
    return {key: csv_safe_cell(row.get(key, "")) for key in fieldnames}
