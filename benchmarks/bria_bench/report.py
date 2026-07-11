"""Render deterministic, technical-only BRIA-Bench metrics reports."""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterator, Mapping
from decimal import Context, Decimal, ROUND_HALF_UP, localcontext
from typing import Any

from jsonschema import Draft202012Validator

from . import contracts as _contracts
from .contracts import ContractError


_SCHEMA_NAME = "metrics.schema.json"
_METRICS_SCHEMA = _contracts.load_schema(_SCHEMA_NAME)
Draft202012Validator.check_schema(_METRICS_SCHEMA)
_METRICS_VALIDATOR = Draft202012Validator(
    _METRICS_SCHEMA,
    format_checker=_contracts._FORMAT_CHECKER,
)

_DETECTION_METRICS = (
    ("expected_finding_recall", "Expected finding recall"),
    ("negative_package_false_alert_rate", "Negative package false alert rate"),
    ("location_match_rate", "Location match rate"),
    ("risk_band_agreement", "Risk band agreement"),
    ("coverage_gap_recall", "Coverage gap recall"),
    ("public_concern_location_coverage", "Public concern location coverage"),
)
_RELIABILITY_METRICS = (
    ("silent_failure_rate", "Silent failure rate"),
    ("boundary_violation_rate", "Boundary violation rate"),
    ("manifest_attack_resistance", "Manifest attack resistance"),
    ("report_contract_validity", "Report contract validity"),
    ("technical_failure_disclosure_rate", "Technical failure disclosure rate"),
    ("run_completion_rate", "Run completion rate"),
    ("atomic_output_preservation", "Atomic output preservation"),
    ("previous_result_preservation", "Previous result preservation"),
)
_CASE_DENOMINATED_RELIABILITY = (
    "silent_failure_rate",
    "boundary_violation_rate",
    "report_contract_validity",
    "run_completion_rate",
)
_CORE_DISTRIBUTIONS = (
    ("wall_time_seconds", "Wall time", "seconds"),
    ("cpu_time_seconds", "CPU time", "seconds"),
    ("peak_rss_bytes", "Peak RSS", "bytes"),
    ("output_size_bytes", "Output size", "bytes"),
)
_LLM_DISTRIBUTIONS = (
    ("llm_input_tokens", "LLM input tokens", "tokens"),
    ("llm_output_tokens", "LLM output tokens", "tokens"),
    ("llm_latency_seconds", "LLM latency", "seconds"),
    ("llm_estimated_cost_cny", "LLM estimated cost", "cny"),
)
_PROFILES = ("quick", "standard", "deep")
_HEADLINE_ELIGIBLE_TRACKS = frozenset({"blinded_challenge", "public_realism"})
_TRACKS = (
    ("regression", "Regression"),
    ("blinded_challenge", "Blinded challenge"),
    ("public_realism", "Public realism"),
    ("public_concern", "Public concern"),
    ("robustness_scale", "Robustness and scale"),
)
_TRACK_KEYS = frozenset(key for key, _ in _TRACKS)
_REPORT_INVALID_STATUSES = frozenset(
    {
        "contract_error",
        "missing_output",
        "invalid_output",
        "normalization_error",
    }
)
_CASE_VALUE_FIELDS = {
    "wall_time_seconds": "elapsed_seconds",
    "cpu_time_seconds": "cpu_seconds",
    "peak_rss_bytes": "peak_rss_bytes",
    "output_size_bytes": "output_size_bytes",
}
_SECRET_WORD = re.compile(
    r"(?:^|[^a-z0-9])(?:api[_-]?key|access[_-]?token|auth(?:orization)?|bearer|"
    r"password|passwd|private[_-]?key|secret)(?:$|[^a-z0-9])",
    re.IGNORECASE,
)
_SECRET_TOKEN = re.compile(
    r"(?:\bAKIA[0-9A-Z]{12,}\b|\bgh[pousr]_[A-Za-z0-9]{12,}\b|"
    r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b|\b(?:sk|rk)-(?:proj-)?[A-Za-z0-9_-]{12,}\b)",
    re.IGNORECASE,
)
_CREDENTIAL_ASSIGNMENT = re.compile(
    r"(?:^|[^a-z0-9])(?:token|[a-z0-9_-]+[._\s-]token|api[._\s-]?key|"
    r"password|passwd|private[._\s-]?key|secret)\s*[:=]",
    re.IGNORECASE,
)
_PROHIBITED_REPORT_LANGUAGE = re.compile(
    r"(?<![a-z0-9])(?:pass|fail|verdict)(?![a-z0-9])|"
    r"(?<![a-z0-9])(?:overall[^a-z0-9]+score|composite[^a-z0-9]+score|"
    r"weighted[^a-z0-9]+ranking)(?![a-z0-9])",
    re.IGNORECASE,
)
_EMAIL = re.compile(
    r"(?<![A-Za-z0-9._%+-])[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"
)
_ENCODED_PATH_SEPARATOR = re.compile(r"%(?:2f|5c)", re.IGNORECASE)
_VALIDATION_CONTEXT = Context(prec=100, rounding=ROUND_HALF_UP)
_FORMAT_CONTEXT = Context(prec=80, rounding=ROUND_HALF_UP)


def _contract_error(path: str, message: str) -> ContractError:
    return ContractError(f"{_SCHEMA_NAME}:{path}: {message}")


def _validate_schema(metrics: object) -> None:
    with localcontext(_VALIDATION_CONTEXT):
        _contracts._reject_non_finite_numbers(_SCHEMA_NAME, metrics)
        try:
            errors = sorted(
                _METRICS_VALIDATOR.iter_errors(metrics),
                key=lambda error: (
                    tuple(str(part) for part in error.path),
                    error.message,
                ),
            )
        except (ArithmeticError, TypeError, ValueError) as exc:
            raise _contract_error(
                "<root>",
                f"numeric value could not be validated safely: {type(exc).__name__}",
            ) from exc
        if errors:
            first = errors[0]
            location = ".".join(str(part) for part in first.path) or "<root>"
            raise _contract_error(location, first.message)

        try:
            _contracts._validate_metrics(_SCHEMA_NAME, metrics)
        except ContractError:
            raise
        except (ArithmeticError, TypeError, ValueError) as exc:
            raise _contract_error(
                "<root>",
                f"numeric semantics could not be evaluated safely: {type(exc).__name__}",
            ) from exc


def _is_unsafe_identifier(value: str) -> bool:
    normalized = unicodedata.normalize("NFKC", value)
    if normalized in {".", ".."}:
        return True
    if any(
        unicodedata.category(character) in {"Cc", "Cf", "Cs", "Zl", "Zp"}
        for character in normalized
    ):
        return True
    lowered = normalized.casefold()
    return bool(
        "/" in normalized
        or "\\" in normalized
        or "file:" in lowered
        or _ENCODED_PATH_SEPARATOR.search(normalized)
        or _EMAIL.search(normalized)
        or _SECRET_WORD.search(normalized)
        or _SECRET_TOKEN.search(normalized)
        or _CREDENTIAL_ASSIGNMENT.search(normalized)
        or _PROHIBITED_REPORT_LANGUAGE.search(normalized)
        or "-----begin" in lowered
    )


def _require_safe_identifier(value: str, path: str) -> None:
    if _is_unsafe_identifier(value):
        raise _contract_error(path, "unsafe identifier content is not reportable")


def _iter_distributions(
    metrics: Mapping[str, Any],
) -> Iterator[tuple[tuple[str, ...], Mapping[str, Any]]]:
    performance = metrics["performance"]
    for key, _, _ in (*_CORE_DISTRIBUTIONS, *_LLM_DISTRIBUTIONS):
        value = performance.get(key)
        if value is not None:
            yield ("performance", key), value

    profiles = performance.get("profiles", {})
    for profile in _PROFILES:
        profile_metrics = profiles.get(profile)
        if profile_metrics is None:
            continue
        for key, _, _ in _CORE_DISTRIBUTIONS:
            value = profile_metrics.get(key)
            if value is not None:
                yield ("performance", "profiles", profile, key), value

    modules = performance.get("module_seconds", {})
    for module in sorted(modules):
        yield ("performance", "module_seconds", module), modules[module]


def _validate_safe_fields(metrics: Mapping[str, Any]) -> None:
    for key in ("schema_version", "benchmark_id", "benchmark_version"):
        _require_safe_identifier(metrics[key], key)

    for index, case in enumerate(metrics.get("case_results", [])):
        _require_safe_identifier(case["case_id"], f"case_results.{index}.case_id")
        adapter = case.get("adapter")
        if adapter is not None:
            _require_safe_identifier(adapter, f"case_results.{index}.adapter")

    modules = metrics["performance"].get("module_seconds", {})
    for module in modules:
        _require_safe_identifier(module, "performance.module_seconds.<module>")

    for path, distribution in _iter_distributions(metrics):
        for index, case_value in enumerate(distribution.get("case_values", [])):
            _require_safe_identifier(
                case_value["case_id"],
                ".".join((*path, "case_values", str(index), "case_id")),
            )


def _numbers_close(left: object, right: object, path: str) -> bool:
    with localcontext(_VALIDATION_CONTEXT):
        return _contracts._numbers_close(
            _SCHEMA_NAME, tuple(path.split(".")), left, right
        )


def _validate_distribution_case_values(
    metrics: Mapping[str, Any],
    rows_by_id: Mapping[str, Mapping[str, Any]] | None,
) -> None:
    run_count = metrics.get("run_count")
    for path_parts, distribution in _iter_distributions(metrics):
        path = ".".join(path_parts)
        count = distribution["count"]
        if run_count is not None and count > run_count:
            raise _contract_error(f"{path}.count", "cannot exceed run_count")

        case_values = distribution.get("case_values")
        if case_values is None:
            continue
        if len(case_values) != count:
            raise _contract_error(
                f"{path}.case_values", "must contain exactly count rows"
            )
        case_ids = [item["case_id"] for item in case_values]
        if len(case_ids) != len(set(case_ids)):
            raise _contract_error(
                f"{path}.case_values", "case_id values must be unique"
            )

        measured_values = sorted(
            (item["value"] for item in case_values),
            key=lambda value: _contracts._as_decimal(
                _SCHEMA_NAME, tuple((*path_parts, "case_values")), value
            ),
        )
        recorded_values = sorted(
            distribution["values"],
            key=lambda value: _contracts._as_decimal(
                _SCHEMA_NAME, tuple((*path_parts, "values")), value
            ),
        )
        if any(
            not _numbers_close(left, right, f"{path}.case_values")
            for left, right in zip(measured_values, recorded_values, strict=True)
        ):
            raise _contract_error(
                f"{path}.case_values", "values contradict the distribution values"
            )

        if rows_by_id is None:
            continue
        unknown = set(case_ids) - set(rows_by_id)
        if unknown:
            raise _contract_error(
                f"{path}.case_values", "contains a case_id absent from case_results"
            )
        case_field = (
            _CASE_VALUE_FIELDS.get(path_parts[1]) if len(path_parts) == 2 else None
        )
        if case_field is None:
            continue
        for index, item in enumerate(case_values):
            case = rows_by_id[item["case_id"]]
            if case_field in case and not _numbers_close(
                item["value"], case[case_field], f"{path}.case_values.{index}.value"
            ):
                raise _contract_error(
                    f"{path}.case_values.{index}.value",
                    f"contradicts case_results.{case_field}",
                )


def _validate_core_distributions(
    metrics: Mapping[str, Any], case_results: list[Mapping[str, Any]] | None
) -> None:
    if case_results is None:
        return
    performance = metrics["performance"]
    for metric, case_field in _CASE_VALUE_FIELDS.items():
        distribution = performance.get(metric)
        if distribution is None:
            continue
        appendix_values = [
            case[case_field] for case in case_results if case_field in case
        ]
        if not appendix_values:
            continue
        path = f"performance.{metric}"
        if distribution["count"] != len(appendix_values):
            raise _contract_error(f"{path}.count", "contradicts case_results values")
        recorded_values = sorted(
            distribution["values"],
            key=lambda value: _contracts._as_decimal(
                _SCHEMA_NAME, ("performance", metric, "values"), value
            ),
        )
        expected_values = sorted(
            appendix_values,
            key=lambda value: _contracts._as_decimal(
                _SCHEMA_NAME, ("case_results", case_field), value
            ),
        )
        if any(
            not _numbers_close(left, right, f"{path}.values")
            for left, right in zip(recorded_values, expected_values, strict=True)
        ):
            raise _contract_error(f"{path}.values", "contradicts case_results values")
        count = len(expected_values)
        expected_percentiles = {
            "p50": expected_values[max(1, (50 * count + 99) // 100) - 1],
            "p95": expected_values[max(1, (95 * count + 99) // 100) - 1],
        }
        for percentile, expected in expected_percentiles.items():
            if not _numbers_close(
                distribution[percentile], expected, f"{path}.{percentile}"
            ):
                raise _contract_error(
                    f"{path}.{percentile}",
                    f"contradicts case_results nearest-rank {percentile}",
                )


def _validate_profile_totals(metrics: Mapping[str, Any]) -> None:
    performance = metrics["performance"]
    profiles = performance.get("profiles")
    if profiles is None or set(profiles) != set(_PROFILES):
        return

    for key, _, _ in _CORE_DISTRIBUTIONS:
        if key not in performance or any(
            key not in profiles[profile] for profile in _PROFILES
        ):
            continue
        profile_count = sum(profiles[profile][key]["count"] for profile in _PROFILES)
        if profile_count != performance[key]["count"]:
            raise _contract_error(
                f"performance.profiles.{key}",
                f"profile counts must sum to performance.{key}.count",
            )

    if "over_budget_rate" not in performance or any(
        "over_budget_rate" not in profiles[profile] for profile in _PROFILES
    ):
        return
    numerator = sum(
        profiles[profile]["over_budget_rate"]["numerator"] for profile in _PROFILES
    )
    denominator = sum(
        profiles[profile]["over_budget_rate"]["denominator"] for profile in _PROFILES
    )
    overall = performance["over_budget_rate"]
    if (numerator, denominator) != (overall["numerator"], overall["denominator"]):
        raise _contract_error(
            "performance.profiles.over_budget_rate",
            "profile fractions must sum to performance.over_budget_rate",
        )


def _validate_fraction_counts(
    reliability: Mapping[str, Any], key: str, numerator: int, denominator: int
) -> None:
    fraction = reliability.get(key)
    if fraction is None:
        return
    if (fraction["numerator"], fraction["denominator"]) != (
        numerator,
        denominator,
    ):
        raise _contract_error(
            f"reliability.{key}", "contradicts derivable case_results counts"
        )


def _validate_reliability_case_rows(
    reliability: Mapping[str, Any], case_results: list[Mapping[str, Any]]
) -> None:
    denominator = len(case_results)
    for key in _CASE_DENOMINATED_RELIABILITY:
        fraction = reliability.get(key)
        if fraction is not None and fraction["denominator"] != denominator:
            raise _contract_error(
                f"reliability.{key}.denominator",
                "must equal the number of case_results rows",
            )

    _validate_fraction_counts(
        reliability,
        "run_completion_rate",
        sum(case["status"] == "success" for case in case_results),
        denominator,
    )
    contract_validity_upper_bound = sum(
        case["status"] not in _REPORT_INVALID_STATUSES for case in case_results
    )
    report_contract_validity = reliability.get("report_contract_validity")
    if (
        report_contract_validity is not None
        and report_contract_validity["numerator"] > contract_validity_upper_bound
    ):
        raise _contract_error(
            "reliability.report_contract_validity",
            "exceeds the upper bound derivable from case_results statuses",
        )
    if all("boundary_violation_count" in case for case in case_results):
        _validate_fraction_counts(
            reliability,
            "boundary_violation_rate",
            sum(case["boundary_violation_count"] > 0 for case in case_results),
            denominator,
        )
    certainly_silent = sum(
        case["reported_failure_count"] < case["technical_failure_count"]
        for case in case_results
        if "technical_failure_count" in case and "reported_failure_count" in case
    )
    silent_failure = reliability.get("silent_failure_rate")
    if silent_failure is not None and silent_failure["numerator"] < certainly_silent:
        raise _contract_error(
            "reliability.silent_failure_rate",
            "is below the lower bound derivable from case_results counts",
        )


def _validate_cross_fields(metrics: Mapping[str, Any]) -> None:
    case_results = metrics.get("case_results")
    rows_by_id = (
        {case["case_id"]: case for case in case_results}
        if case_results is not None
        else None
    )
    run_count = metrics.get("run_count")
    if (
        case_results is not None
        and run_count is not None
        and len(case_results) != run_count
    ):
        raise _contract_error("run_count", "must equal the number of case_results rows")

    for index, case in enumerate(case_results or []):
        if (
            case.get("headline_detection_eligible") is True
            and case["track"] not in _HEADLINE_ELIGIBLE_TRACKS
        ):
            raise _contract_error(
                f"case_results.{index}.headline_detection_eligible",
                "may be true only for blinded_challenge or public_realism",
            )
        matched = case.get("matched_label_count")
        expected = case.get("expected_label_count")
        if matched is not None and expected is not None and matched > expected:
            raise _contract_error(
                f"case_results.{index}.matched_label_count",
                "cannot exceed expected_label_count",
            )
        technical = case.get("technical_failure_count")
        reported = case.get("reported_failure_count")
        if technical is not None and reported is not None and reported > technical:
            raise _contract_error(
                f"case_results.{index}.reported_failure_count",
                "cannot exceed technical_failure_count",
            )

    tracks = metrics.get("tracks")
    if tracks is not None:
        for key, summary in tracks.items():
            if summary["headline_detection_eligible"]:
                if key not in _HEADLINE_ELIGIBLE_TRACKS:
                    raise _contract_error(
                        f"tracks.{key}.headline_detection_eligible",
                        "may be true only for blinded_challenge or public_realism",
                    )
                if summary["case_count"] == 0:
                    raise _contract_error(
                        f"tracks.{key}.headline_detection_eligible",
                        "requires a positive case_count",
                    )
        if run_count is not None:
            for key, summary in tracks.items():
                if summary["case_count"] > run_count:
                    raise _contract_error(
                        f"tracks.{key}.case_count", "cannot exceed run_count"
                    )
            if set(tracks) == _TRACK_KEYS:
                total = sum(summary["case_count"] for summary in tracks.values())
                if total != run_count:
                    raise _contract_error(
                        "tracks", "case_count values must sum to run_count"
                    )

        if case_results is not None:
            for key, summary in tracks.items():
                track_rows = [case for case in case_results if case["track"] == key]
                if summary["case_count"] != len(track_rows):
                    raise _contract_error(
                        f"tracks.{key}.case_count",
                        "contradicts case_results track rows",
                    )
                known_eligibility = [
                    case["headline_detection_eligible"]
                    for case in track_rows
                    if "headline_detection_eligible" in case
                ]
                recorded = summary["headline_detection_eligible"]
                if not recorded and any(known_eligibility):
                    raise _contract_error(
                        f"tracks.{key}.headline_detection_eligible",
                        "contradicts an eligible case_results row",
                    )
                if (
                    recorded
                    and len(known_eligibility) == len(track_rows)
                    and not any(known_eligibility)
                ):
                    raise _contract_error(
                        f"tracks.{key}.headline_detection_eligible",
                        "requires at least one eligible case_results row",
                    )

    if case_results is not None:
        _validate_reliability_case_rows(metrics["reliability"], case_results)
    elif run_count is not None:
        reliability = metrics["reliability"]
        for key in _CASE_DENOMINATED_RELIABILITY:
            if key in reliability and reliability[key]["denominator"] not in {
                0,
                run_count,
            }:
                raise _contract_error(
                    f"reliability.{key}.denominator",
                    "must be zero or equal run_count",
                )

    _validate_distribution_case_values(metrics, rows_by_id)
    _validate_core_distributions(metrics, case_results)
    _validate_profile_totals(metrics)


def _escape_markdown(value: object) -> str:
    text = str(value)
    text = text.replace("&", "&amp;")
    text = text.replace("\\", "&#92;")
    text = text.replace("|", "&#124;")
    text = text.replace("<", "&lt;").replace(">", "&gt;")
    return re.sub(r"([`*_\[\]])", r"\\\1", text)


def _format_number(value: object, *, places: int = 4) -> str:
    number = Decimal(str(value))
    if number and (number.adjusted() >= 12 or number.adjusted() <= -8):
        with localcontext(_FORMAT_CONTEXT):
            mantissa, exponent = format(number, f".{places}E").split("E")
        mantissa = mantissa.rstrip("0").rstrip(".")
        return f"{mantissa}E{int(exponent):+d}"

    digits = len(number.as_tuple().digits)
    exponent = number.as_tuple().exponent
    precision = max(_FORMAT_CONTEXT.prec, digits + abs(exponent) + places + 10)
    with localcontext(Context(prec=precision, rounding=ROUND_HALF_UP)):
        if number == number.to_integral_value():
            return str(int(number))
        quantum = Decimal(1).scaleb(-places)
        rounded = number.quantize(quantum, rounding=ROUND_HALF_UP)
        if rounded == 0 and number != 0:
            return f"< {format(quantum, 'f')}"
        return format(rounded, "f").rstrip("0").rstrip(".")


def _format_percentage(numerator: int, denominator: int) -> str:
    with localcontext(_FORMAT_CONTEXT):
        hundredths = (2 * numerator * 10_000 + denominator) // (2 * denominator)
    if hundredths == 0 and numerator:
        return "<0.01%"
    if hundredths == 10_000 and numerator < denominator:
        return ">99.99%"
    whole, fractional = divmod(hundredths, 100)
    if fractional == 0:
        return f"{whole}%"
    return f"{whole}.{fractional:02d}".rstrip("0") + "%"


def _format_fraction(value: Mapping[str, Any] | None) -> str:
    if value is None or value["denominator"] == 0:
        return "0 / 0 (not measured)"
    numerator = value["numerator"]
    denominator = value["denominator"]
    return f"{numerator} / {denominator} ({_format_percentage(numerator, denominator)})"


def _format_bytes(value: object) -> str:
    number = Decimal(str(value))
    units = ("B", "KiB", "MiB", "GiB", "TiB", "PiB")
    unit_index = 0
    with localcontext(_FORMAT_CONTEXT):
        while abs(number) >= 1024 and unit_index < len(units) - 1:
            number /= Decimal(1024)
            unit_index += 1
    return f"{_format_number(number)} {units[unit_index]}"


def _distribution_cells(
    distribution: Mapping[str, Any] | None, unit_kind: str
) -> tuple[str, str, str, str]:
    unit = {
        "seconds": "seconds",
        "bytes": "bytes (IEC)",
        "tokens": "tokens",
        "cny": "CNY",
    }[unit_kind]
    if distribution is None or distribution["count"] == 0:
        return "0", "not measured", "not measured", unit

    def formatted(value: object) -> str:
        if unit_kind == "bytes":
            return _format_bytes(value)
        return _format_number(value)

    return (
        str(distribution["count"]),
        formatted(distribution["p50"]),
        formatted(distribution["p95"]),
        unit,
    )


def _append_distribution_table(
    lines: list[str],
    source: Mapping[str, Any],
    definitions: tuple[tuple[str, str, str], ...],
) -> None:
    lines.extend(
        [
            "| Metric | Count | p50 | p95 | Unit |",
            "| --- | ---: | ---: | ---: | --- |",
        ]
    )
    for key, label, unit in definitions:
        count, p50, p95, rendered_unit = _distribution_cells(source.get(key), unit)
        lines.append(f"| {label} | {count} | {p50} | {p95} | {rendered_unit} |")


def _append_case_table(lines: list[str], cases: list[Mapping[str, Any]]) -> None:
    lines.extend(
        [
            "| Case ID | Track | Split | Status | Adapter | Headline detection eligible | Matched labels | Expected labels | False alerts | Technical failures | Reported failures | Boundary violations | Elapsed (seconds) | CPU (seconds) | Peak RSS | Output size |",
            "| --- | --- | --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )

    def optional(case: Mapping[str, Any], key: str) -> str:
        return _escape_markdown(case[key]) if key in case else "unavailable"

    for case in sorted(cases, key=lambda item: item["case_id"]):
        eligible = case.get("headline_detection_eligible")
        eligibility = (
            "unavailable" if eligible is None else ("yes" if eligible else "no")
        )
        elapsed = (
            _format_number(case["elapsed_seconds"])
            if "elapsed_seconds" in case
            else "unavailable"
        )
        cpu = (
            _format_number(case["cpu_seconds"])
            if "cpu_seconds" in case
            else "unavailable"
        )
        peak_rss = (
            _format_bytes(case["peak_rss_bytes"])
            if "peak_rss_bytes" in case
            else "unavailable"
        )
        output_size = (
            _format_bytes(case["output_size_bytes"])
            if "output_size_bytes" in case
            else "unavailable"
        )
        lines.append(
            "| "
            + " | ".join(
                (
                    _escape_markdown(case["case_id"]),
                    _escape_markdown(case["track"]),
                    _escape_markdown(case["split"]),
                    _escape_markdown(case["status"]),
                    optional(case, "adapter"),
                    eligibility,
                    optional(case, "matched_label_count"),
                    optional(case, "expected_label_count"),
                    optional(case, "false_alert_count"),
                    optional(case, "technical_failure_count"),
                    optional(case, "reported_failure_count"),
                    optional(case, "boundary_violation_count"),
                    elapsed,
                    cpu,
                    peak_rss,
                    output_size,
                )
            )
            + " |"
        )


def render_metrics_report(metrics: dict[str, Any]) -> str:
    """Return a deterministic Markdown report for one metrics artifact.

    Rendering reads only the supplied dictionary and module-level schema constants.
    The input dictionary is validated but never modified.
    """
    _validate_schema(metrics)
    _validate_safe_fields(metrics)
    _validate_cross_fields(metrics)

    lines = [
        "# BRIA-Bench Technical Metrics Report",
        "",
        "## Scope and benchmark version",
        "",
        "| Field | Value |",
        "| --- | --- |",
        f"| Benchmark | {_escape_markdown(metrics['benchmark_id'])} |",
        f"| Benchmark version | {_escape_markdown(metrics['benchmark_version'])} |",
        f"| Metrics schema version | {_escape_markdown(metrics['schema_version'])} |",
        f"| Recorded generation time | {_escape_markdown(metrics.get('generated_at', 'unavailable'))} |",
        f"| Recorded run count | {metrics.get('run_count', 'unavailable')} |",
        "",
        "This report presents technical benchmark measurements.",
        "",
        "## Detection and localization",
        "",
        "| Metric | Result |",
        "| --- | --- |",
    ]
    detection = metrics["detection"]
    for key, label in _DETECTION_METRICS:
        lines.append(f"| {label} | {_format_fraction(detection.get(key))} |")
    assertions = detection.get("regression_assertions")
    if assertions is None:
        assertion_result = "not measured"
    else:
        assertion_result = (
            f"{_format_fraction({'numerator': assertions['met'], 'denominator': assertions['total']})}; "
            f"not met: {assertions['not_met']}"
        )
    lines.extend(
        [
            f"| Regression assertions met | {assertion_result} |",
            "",
            "A negative control without an alert is not proof that a package is scientifically correct.",
            "",
            "## Reliability and safety",
            "",
            "| Metric | Result |",
            "| --- | --- |",
        ]
    )
    reliability = metrics["reliability"]
    for key, label in _RELIABILITY_METRICS:
        lines.append(f"| {label} | {_format_fraction(reliability.get(key))} |")
    lines.extend(
        [
            "",
            "Status is technical execution status.",
            "",
            "## Performance and cost",
            "",
            "### Overall distributions",
            "",
        ]
    )
    performance = metrics["performance"]
    _append_distribution_table(lines, performance, _CORE_DISTRIBUTIONS)
    lines.extend(
        [
            "",
            "### Budget observations",
            "",
            "| Metric | Result |",
            "| --- | --- |",
            f"| Over budget rate | {_format_fraction(performance.get('over_budget_rate'))} |",
            "",
            "### Profile distributions",
        ]
    )
    profiles = performance.get("profiles", {})
    for profile in _PROFILES:
        profile_metrics = profiles.get(profile, {})
        lines.extend(["", f"#### {profile}", ""])
        _append_distribution_table(lines, profile_metrics, _CORE_DISTRIBUTIONS)
        lines.extend(
            [
                "",
                "| Metric | Result |",
                "| --- | --- |",
                f"| Over budget rate | {_format_fraction(profile_metrics.get('over_budget_rate'))} |",
            ]
        )

    lines.extend(["", "### Module timings", ""])
    modules = performance.get("module_seconds")
    if not modules:
        lines.append("Module timing distributions: not measured.")
    else:
        lines.extend(
            [
                "| Module | Count | p50 | p95 | Unit |",
                "| --- | ---: | ---: | ---: | --- |",
            ]
        )
        for module in sorted(modules):
            count, p50, p95, unit = _distribution_cells(modules[module], "seconds")
            lines.append(
                f"| {_escape_markdown(module)} | {count} | {p50} | {p95} | {unit} |"
            )

    lines.extend(["", "### LLM distributions", ""])
    _append_distribution_table(lines, performance, _LLM_DISTRIBUTIONS)
    lines.extend(
        [
            "",
            "## Track boundaries",
            "",
            "Regression cases are excluded from headline accuracy.",
            "",
            "Public concern labels are localization references, not misconduct truth.",
            "",
            "| Track | Recorded case count | Headline detection eligibility |",
            "| --- | ---: | --- |",
        ]
    )
    tracks = metrics.get("tracks", {})
    for key, label in _TRACKS:
        summary = tracks.get(key)
        if summary is None:
            count = eligibility = "unavailable"
        else:
            count = str(summary["case_count"])
            eligibility = (
                "at least one case eligible"
                if summary["headline_detection_eligible"]
                else "no eligible case recorded"
            )
        lines.append(f"| {label} | {count} | {eligibility} |")

    lines.extend(["", "## Case-level appendix", ""])
    case_results = metrics.get("case_results")
    if case_results is None:
        lines.append("Case-level results are unavailable in this metrics artifact.")
    elif not case_results:
        lines.append("No case-level rows were recorded.")
    else:
        _append_case_table(lines, case_results)

    manifest_sha = metrics.get("manifest_sha256", "unavailable")
    lines.extend(
        [
            "",
            "## Reproduction command and hashes",
            "",
            "| Artifact | Recorded value |",
            "| --- | --- |",
            f"| Manifest SHA-256 | {manifest_sha} |",
            "",
            "```sh",
            "bria-bench report --metrics <metrics.json> --output <REPORT.md>",
            "```",
            "",
            "The benchmark run command and per-run hashes are not recorded in this metrics artifact.",
        ]
    )
    return "\n".join(lines) + "\n"


__all__ = ["render_metrics_report"]
