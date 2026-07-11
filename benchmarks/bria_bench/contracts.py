from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError


SCHEMA_ROOT = Path(__file__).with_name("schemas")


class ContractError(ValueError):
    pass


def load_schema(name: str) -> dict[str, Any]:
    if not isinstance(name, str) or not name or Path(name).name != name:
        raise ContractError(f"Unknown BRIA-Bench schema: {name}")

    path = SCHEMA_ROOT / name
    try:
        schema_root = SCHEMA_ROOT.resolve(strict=True)
        resolved = path.resolve(strict=True)
    except (OSError, RuntimeError, ValueError) as exc:
        raise ContractError(f"Unknown BRIA-Bench schema: {name}") from exc

    if resolved.parent != schema_root or path.is_symlink() or not path.is_file():
        raise ContractError(f"Unknown BRIA-Bench schema: {name}")

    try:
        schema = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ContractError(f"Invalid BRIA-Bench schema: {name}") from exc
    if not isinstance(schema, dict):
        raise ContractError(f"Invalid BRIA-Bench schema: {name}")
    return schema


def validate_contract(name: str, payload: Any) -> None:
    schema = load_schema(name)
    try:
        Draft202012Validator.check_schema(schema)
        validator = Draft202012Validator(schema)
    except SchemaError as exc:
        raise ContractError(f"Invalid BRIA-Bench schema: {name}") from exc

    errors = sorted(
        validator.iter_errors(payload),
        key=lambda error: (tuple(str(part) for part in error.path), error.message),
    )
    if errors:
        first = errors[0]
        location = ".".join(str(part) for part in first.path) or "<root>"
        raise ContractError(f"{name}:{location}: {first.message}")
