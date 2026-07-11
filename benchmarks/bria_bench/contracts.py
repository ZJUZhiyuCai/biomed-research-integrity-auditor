from __future__ import annotations

import json
import math
import re
from datetime import datetime
from decimal import Decimal
from numbers import Integral, Real
from pathlib import Path
from typing import Any, Iterator

from jsonschema import Draft202012Validator, FormatChecker
from jsonschema.exceptions import SchemaError


SCHEMA_ROOT = Path(__file__).with_name("schemas")
_SCHEMA_NAMES = frozenset(
    {
        "annotation.schema.json",
        "benchmark_manifest.schema.json",
        "metrics.schema.json",
        "observation.schema.json",
        "run_result.schema.json",
    }
)
_FORMAT_CHECKER = FormatChecker()
_PROHIBITED_METRIC_KEYS = frozenset({"score", "overall_score"})
_DATE_TIME_PATTERN = re.compile(
    r"^[0-9]{4}-[0-9]{2}-[0-9]{2}[Tt][0-9]{2}:[0-9]{2}:[0-9]{2}"
    r"(?:\.[0-9]+)?(?:[Zz]|[+-][0-9]{2}:[0-9]{2})$"
)

JsonPath = tuple[str | int, ...]


class ContractError(ValueError):
    pass


@_FORMAT_CHECKER.checks("date-time")
def _is_date_time(value: object) -> bool:
    if not isinstance(value, str):
        return True
    if _DATE_TIME_PATTERN.fullmatch(value) is None:
        return False
    try:
        parsed = datetime.fromisoformat(value.upper().replace("Z", "+00:00"))
    except ValueError:
        return False
    return parsed.tzinfo is not None and parsed.utcoffset() is not None


def load_schema(name: str) -> dict[str, Any]:
    if not isinstance(name, str) or name not in _SCHEMA_NAMES:
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


def _raise_contract_error(name: str, path: JsonPath, message: str) -> None:
    location = ".".join(str(part) for part in path) or "<root>"
    raise ContractError(f"{name}:{location}: {message}")


def _walk(value: Any, path: JsonPath = ()) -> Iterator[tuple[JsonPath, Any]]:
    yield path, value
    if isinstance(value, dict):
        for key, child in value.items():
            yield from _walk(child, path + (str(key),))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from _walk(child, path + (index,))


def _reject_non_finite_numbers(name: str, payload: Any) -> None:
    for path, value in _walk(payload):
        if isinstance(value, bool) or isinstance(value, Integral):
            continue
        if isinstance(value, Decimal):
            if not value.is_finite():
                _raise_contract_error(name, path, "numeric value must be finite")
            continue
        if not isinstance(value, Real):
            continue
        try:
            finite = math.isfinite(value)
        except (ArithmeticError, TypeError, ValueError) as exc:
            _raise_contract_error(
                name,
                path,
                f"numeric finiteness could not be determined: {type(exc).__name__}",
            )
        if not finite:
            _raise_contract_error(name, path, "numeric value must be finite")


def _as_decimal(name: str, path: JsonPath, value: Any) -> Decimal:
    try:
        if isinstance(value, Decimal):
            return value
        if isinstance(value, Integral):
            return Decimal(int(value))
        if isinstance(value, float):
            return Decimal.from_float(value)
        if isinstance(value, Real):
            numerator = getattr(value, "numerator", None)
            denominator = getattr(value, "denominator", None)
            if isinstance(numerator, Integral) and isinstance(denominator, Integral):
                return Decimal(int(numerator)) / Decimal(int(denominator))
            return Decimal(str(value))
    except (ArithmeticError, TypeError, ValueError) as exc:
        _raise_contract_error(
            name,
            path,
            f"numeric value could not be represented safely: {type(exc).__name__}",
        )
    _raise_contract_error(name, path, "value is not a supported finite number")


def _numbers_close(name: str, path: JsonPath, left: Any, right: Any) -> bool:
    try:
        left_decimal = _as_decimal(name, path, left)
        right_decimal = _as_decimal(name, path, right)
        difference = abs(left_decimal - right_decimal)
        relative_tolerance = Decimal("1e-9") * max(
            abs(left_decimal),
            abs(right_decimal),
        )
        return difference <= max(Decimal("1e-12"), relative_tolerance)
    except ContractError:
        raise
    except (ArithmeticError, TypeError, ValueError) as exc:
        _raise_contract_error(
            name,
            path,
            f"numeric values could not be compared safely: {type(exc).__name__}",
        )


def _exception_numeric_path(payload: Any) -> JsonPath:
    for path, value in _walk(payload):
        if isinstance(value, Decimal):
            return path
        if (
            isinstance(value, Integral)
            and not isinstance(value, bool)
        ):
            try:
                if int(value).bit_length() > 4096:
                    return path
            except (ArithmeticError, TypeError, ValueError):
                return path
        if isinstance(value, Real) and not isinstance(value, (bool, int, float)):
            return path
    return ()


def _require_unique(
    name: str,
    items: list[dict[str, Any]],
    field: str,
    path: JsonPath,
) -> None:
    first_indexes: dict[Any, int] = {}
    for index, item in enumerate(items):
        value = item[field]
        if value in first_indexes:
            first_path = ".".join(
                str(part) for part in path + (first_indexes[value], field)
            )
            _raise_contract_error(
                name,
                path + (index, field),
                f"{field} must be unique; first used at {first_path}",
            )
        first_indexes[value] = index


def _validate_regions(name: str, payload: Any, path: JsonPath = ()) -> None:
    region_fields = {"x", "y", "width", "height", "coordinate_space"}
    for region_path, value in _walk(payload, path):
        if not isinstance(value, dict) or not region_fields.issubset(value):
            continue

        coordinates = {
            field: _as_decimal(name, region_path + (field,), value[field])
            for field in ("x", "y", "width", "height")
        }
        if value["coordinate_space"] == "normalized_0_1":
            for field, coordinate in coordinates.items():
                if coordinate < 0 or coordinate > 1:
                    _raise_contract_error(
                        name,
                        region_path + (field,),
                        f"{field} must be within [0, 1] for normalized_0_1 coordinates",
                    )
            if coordinates["x"] + coordinates["width"] > 1:
                _raise_contract_error(
                    name,
                    region_path + ("width",),
                    "x + width must be <= 1 for normalized_0_1 coordinates",
                )
            if coordinates["y"] + coordinates["height"] > 1:
                _raise_contract_error(
                    name,
                    region_path + ("height",),
                    "y + height must be <= 1 for normalized_0_1 coordinates",
                )
        elif value["coordinate_space"] == "pixels":
            for field, coordinate in coordinates.items():
                if coordinate < 0:
                    _raise_contract_error(
                        name,
                        region_path + (field,),
                        f"{field} must be nonnegative for pixel coordinates",
                    )


def _validate_manifest(name: str, payload: dict[str, Any]) -> None:
    _require_unique(name, payload["cases"], "case_id", ("cases",))


def _validate_annotation(name: str, payload: dict[str, Any]) -> None:
    _require_unique(
        name,
        payload["expected_observations"],
        "observation_id",
        ("expected_observations",),
    )
    _validate_regions(name, payload)


def _validate_normalized_observation(
    name: str,
    payload: dict[str, Any],
    path: JsonPath = (),
) -> None:
    _require_unique(
        name,
        payload["observations"],
        "observation_id",
        path + ("observations",),
    )
    _validate_regions(name, payload, path)


def _validate_run_result(name: str, payload: dict[str, Any]) -> None:
    normalized = payload["normalized_observation"]
    _validate_normalized_observation(name, normalized, ("normalized_observation",))
    if normalized["case_id"] != payload["case_id"]:
        _raise_contract_error(
            name,
            ("normalized_observation", "case_id"),
            "must match outer case_id",
        )

    status = payload["status"]
    timed_out = payload["telemetry"]["timed_out"]
    failure = payload["failure"]
    if status == "success":
        if failure is not None:
            _raise_contract_error(name, ("failure",), "must be null when status is success")
        if timed_out:
            _raise_contract_error(
                name,
                ("telemetry", "timed_out"),
                "must be false when status is success",
            )
    elif status == "timeout":
        if not timed_out:
            _raise_contract_error(
                name,
                ("telemetry", "timed_out"),
                "must be true when status is timeout",
            )
        if failure is None:
            _raise_contract_error(name, ("failure",), "must be non-null when status is timeout")
    else:
        if failure is None:
            _raise_contract_error(name, ("failure",), f"must be non-null when status is {status}")
        if timed_out:
            _raise_contract_error(
                name,
                ("telemetry", "timed_out"),
                "must be false unless status is timeout",
            )

    if isinstance(failure, dict) and failure.get("timed_out", timed_out) != timed_out:
        _raise_contract_error(
            name,
            ("failure", "timed_out"),
            "must match telemetry.timed_out",
        )


def _validate_fraction(name: str, path: JsonPath, value: dict[str, Any]) -> None:
    numerator = value["numerator"]
    denominator = value["denominator"]
    measured = value["value"]
    if numerator > denominator:
        _raise_contract_error(name, path + ("numerator",), "must be <= denominator")
    if denominator == 0:
        if measured is not None:
            _raise_contract_error(name, path + ("value",), "must be null when denominator is zero")
        return

    expected = Decimal(numerator) / Decimal(denominator)
    if measured is None or not _numbers_close(name, path + ("value",), measured, expected):
        _raise_contract_error(
            name,
            path + ("value",),
            "must approximately equal numerator / denominator",
        )


def _validate_distribution(name: str, path: JsonPath, value: dict[str, Any]) -> None:
    count = value["count"]
    p50 = value["p50"]
    p95 = value["p95"]
    values = value["values"]
    if count != len(values):
        _raise_contract_error(name, path + ("count",), "must equal the number of values")
    if count == 0 and (p50 is not None or p95 is not None):
        _raise_contract_error(name, path + ("p50",), "p50 and p95 must be null when count is zero")
    if count > 0 and (p50 is None or p95 is None):
        _raise_contract_error(name, path + ("p50",), "p50 and p95 are required when count is positive")
    if (
        p50 is not None
        and p95 is not None
        and _as_decimal(name, path + ("p50",), p50)
        > _as_decimal(name, path + ("p95",), p95)
    ):
        _raise_contract_error(name, path + ("p50",), "must be <= p95")
    if count > 0:
        ordered = sorted(
            _as_decimal(name, path + ("values", index), item)
            for index, item in enumerate(values)
        )
        for field, percentile in (("p50", 0.50), ("p95", 0.95)):
            rank = max(1, math.ceil(percentile * count))
            expected = ordered[rank - 1]
            measured = value[field]
            if not _numbers_close(name, path + (field,), measured, expected):
                _raise_contract_error(
                    name,
                    path + (field,),
                    f"must match nearest-rank {field} computed from values",
                )


def _validate_count_summary(name: str, path: JsonPath, value: dict[str, Any]) -> None:
    if value["total"] != value["met"] + value["not_met"]:
        _raise_contract_error(name, path + ("total",), "must equal met + not_met")


def _validate_metrics(name: str, payload: dict[str, Any]) -> None:
    for path, value in _walk(payload):
        if isinstance(value, dict):
            for key in value:
                if key in _PROHIBITED_METRIC_KEYS:
                    _raise_contract_error(
                        name,
                        path + (key,),
                        f"metric key {key!r} is prohibited at every depth",
                    )
            if {"numerator", "denominator", "value"}.issubset(value):
                _validate_fraction(name, path, value)
            if {"count", "p50", "p95", "values"}.issubset(value):
                _validate_distribution(name, path, value)
            if {"met", "not_met", "total"}.issubset(value):
                _validate_count_summary(name, path, value)

    _require_unique(name, payload.get("case_results", []), "case_id", ("case_results",))


_SEMANTIC_VALIDATORS = {
    "annotation.schema.json": _validate_annotation,
    "benchmark_manifest.schema.json": _validate_manifest,
    "metrics.schema.json": _validate_metrics,
    "observation.schema.json": _validate_normalized_observation,
    "run_result.schema.json": _validate_run_result,
}


def validate_contract(name: str, payload: Any) -> None:
    schema = load_schema(name)
    _reject_non_finite_numbers(name, payload)
    try:
        Draft202012Validator.check_schema(schema)
        validator = Draft202012Validator(schema, format_checker=_FORMAT_CHECKER)
    except SchemaError as exc:
        raise ContractError(f"Invalid BRIA-Bench schema: {name}") from exc

    try:
        validation_errors = list(validator.iter_errors(payload))
    except (ArithmeticError, TypeError, ValueError) as exc:
        _raise_contract_error(
            name,
            _exception_numeric_path(payload),
            f"numeric value could not be validated safely: {type(exc).__name__}",
        )
    errors = sorted(
        validation_errors,
        key=lambda error: (tuple(str(part) for part in error.path), error.message),
    )
    if errors:
        first = errors[0]
        location = ".".join(str(part) for part in first.path) or "<root>"
        raise ContractError(f"{name}:{location}: {first.message}")

    try:
        _SEMANTIC_VALIDATORS[name](name, payload)
    except ContractError:
        raise
    except (ArithmeticError, TypeError, ValueError) as exc:
        _raise_contract_error(
            name,
            _exception_numeric_path(payload),
            f"numeric semantics could not be evaluated safely: {type(exc).__name__}",
        )
