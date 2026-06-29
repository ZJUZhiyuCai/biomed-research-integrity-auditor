"""JSON contract validation helpers."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class ContractError(ValueError):
    """Raised when an audit pipeline object violates its contract."""


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def validate_instance(instance: dict[str, Any], schema_path: Path, label: str) -> None:
    schema = load_json(schema_path)
    try:
        from jsonschema import validate  # type: ignore
    except Exception as exc:  # noqa: BLE001 - dependency/import failures must stop the audit.
        raise ContractError(
            f"{label} cannot be schema-validated because jsonschema is unavailable or failed to import"
        ) from exc

    try:
        validate(instance=instance, schema=schema)
    except Exception as exc:  # noqa: BLE001 - surface jsonschema details as contract failure.
        raise ContractError(f"{label} failed schema validation: {exc}") from exc

    if schema_path.name == "detector_output.schema.json":
        for idx, candidate in enumerate(instance.get("candidates", []), start=1):
            if "risk_level" in candidate or "calibrated_risk_level" in candidate:
                raise ContractError(f"{label}.candidates[{idx}] contains final risk field")
