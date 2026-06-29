"""JSON contract validation helpers with a small built-in fallback."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class ContractError(ValueError):
    """Raised when an audit pipeline object violates its contract."""


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _fallback_validate_required(instance: dict[str, Any], schema: dict[str, Any], label: str) -> None:
    for field in schema.get("required", []):
        if field not in instance:
            raise ContractError(f"{label} missing required field: {field}")
    properties = schema.get("properties", {})
    for field, spec in properties.items():
        if field in instance and "enum" in spec and instance[field] not in spec["enum"]:
            raise ContractError(f"{label}.{field}={instance[field]!r} not in enum {spec['enum']!r}")


def _fallback_validate_detector_output(instance: dict[str, Any], schema: dict[str, Any], label: str) -> None:
    _fallback_validate_required(instance, schema, label)
    candidate_schema = schema.get("$defs", {}).get("candidate", {})
    for idx, candidate in enumerate(instance.get("candidates", []), start=1):
        if "risk_level" in candidate or "calibrated_risk_level" in candidate:
            raise ContractError(f"{label}.candidates[{idx}] contains final risk field")
        _fallback_validate_required(candidate, candidate_schema, f"{label}.candidates[{idx}]")


def validate_instance(instance: dict[str, Any], schema_path: Path, label: str) -> None:
    schema = load_json(schema_path)
    try:
        from jsonschema import validate  # type: ignore
    except Exception:
        if schema_path.name == "detector_output.schema.json":
            _fallback_validate_detector_output(instance, schema, label)
        else:
            _fallback_validate_required(instance, schema, label)
        return

    try:
        validate(instance=instance, schema=schema)
    except Exception as exc:  # noqa: BLE001 - surface jsonschema details as contract failure.
        raise ContractError(f"{label} failed schema validation: {exc}") from exc

    if schema_path.name == "detector_output.schema.json":
        for idx, candidate in enumerate(instance.get("candidates", []), start=1):
            if "risk_level" in candidate or "calibrated_risk_level" in candidate:
                raise ContractError(f"{label}.candidates[{idx}] contains final risk field")
