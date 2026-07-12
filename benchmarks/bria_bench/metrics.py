"""Aggregate BRIA-Bench detection, reliability, and performance metrics.

``aggregate_metrics`` accepts JSON-friendly case bundles with four required keys:
``manifest_case``, ``annotation``, ``run_result``, and ``match_result``.  The match
result may be a :class:`MatchResult` or its ``to_dict()`` representation.  Optional
evaluation facts are ``regression_assertions`` (a list of booleans),
``attack_resisted``, ``atomic_output_preserved``, ``previous_output_preserved``,
and ``over_budget``.  Presence makes an optional boolean fact applicable.

Facts are never inferred from prose.  In particular, a failed eligible negative
control is conservatively counted as an alerted package, because it did not
produce evidence that the package was clean.  Failed regression runs retain all
provided assertion denominators but treat every assertion as not met.

The evaluator must call ``select_evaluation_labels(manifest_case, annotation)``
and produce ``match_result`` with ``match_labels(selected_labels, observations,
roles=("recall_label", "coverage_gap"))``.  The selector applies track and scope
boundaries before one-to-one assignment; ``negative_guardrail`` and
``reference_only`` labels are intentionally outside the matcher partition.
"""

from __future__ import annotations

import math
import unicodedata
from collections import defaultdict
from collections.abc import Mapping, Sequence
from decimal import Decimal
from numbers import Integral, Real
from typing import Any

from .contracts import validate_contract
from .matching import MatchResult, match_labels


_TRACKS = (
    "regression",
    "blinded_challenge",
    "public_realism",
    "public_concern",
    "robustness_scale",
)
_PROFILES = ("quick", "standard", "deep")
_EVALUATED_MATCH_ROLES = ("recall_label", "coverage_gap")
_SUCCESS = "success"
_REPORT_INVALID_STATUSES = {
    "contract_error",
    "missing_output",
    "invalid_output",
    "normalization_error",
}
_BUNDLE_KEYS = {
    "manifest_case",
    "annotation",
    "run_result",
    "match_result",
    "regression_assertions",
    "attack_resisted",
    "atomic_output_preserved",
    "previous_output_preserved",
    "over_budget",
}


def _fraction(numerator: int, denominator: int) -> dict[str, int | float | None]:
    return {
        "numerator": numerator,
        "denominator": denominator,
        "value": numerator / denominator if denominator else None,
    }


def _distribution(items: Sequence[tuple[str, int | float]]) -> dict[str, Any]:
    case_values = [
        {"case_id": case_id, "value": value}
        for case_id, value in sorted(items, key=lambda item: (item[0], item[1]))
    ]
    values = sorted(value for _, value in items)
    count = len(values)

    def percentile(proportion: float) -> int | float | None:
        if not values:
            return None
        return values[max(1, math.ceil(proportion * count)) - 1]

    return {
        "count": count,
        "p50": percentile(0.50),
        "p95": percentile(0.95),
        "values": values,
        "case_values": case_values,
    }


def _json_safe_numbers(value: Any, path: str = "result") -> Any:
    if isinstance(value, dict):
        return {
            key: _json_safe_numbers(item, f"{path}.{key}")
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [
            _json_safe_numbers(item, f"{path}[{index}]")
            for index, item in enumerate(value)
        ]
    if isinstance(value, bool) or value is None or isinstance(value, str):
        return value
    if isinstance(value, Integral):
        return int(value)
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise ValueError(f"{path} must be finite and JSON-safe")
        if value == value.to_integral_value():
            return int(value)
        converted = float(value)
        if not math.isfinite(converted):
            raise ValueError(f"{path} cannot be represented as a finite JSON number")
        return converted
    if isinstance(value, float):
        return value
    if isinstance(value, Real):
        converted = float(value)
        if not math.isfinite(converted):
            raise ValueError(f"{path} cannot be represented as a finite JSON number")
        return converted
    return value


def _require_mapping(value: object, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{name} must be an object")
    return value


def select_evaluation_labels(
    manifest_case: Mapping[str, Any], annotation: Mapping[str, Any]
) -> list[Mapping[str, Any]]:
    """Return the exact annotation-order label partition Task 7 must match.

    Use the returned list directly with ``match_labels(...,
    roles=("recall_label", "coverage_gap"))``.  Track-specific scope filtering is
    applied before matching so labels outside an evaluated metric cannot consume
    observations in the shared one-to-one assignment.
    """
    manifest_case = _require_mapping(manifest_case, "manifest_case")
    annotation = _require_mapping(annotation, "annotation")
    track = manifest_case.get("track")
    labels = annotation.get("expected_observations")
    if not isinstance(labels, list):
        raise ValueError("annotation.expected_observations must be an array")

    if track in {"blinded_challenge", "public_realism"}:
        roles = _EVALUATED_MATCH_ROLES
        scopes = {None, "headline_detection"}
    elif track == "public_concern":
        roles = ("recall_label",)
        scopes = {"localization_only"}
    elif track == "regression":
        roles = _EVALUATED_MATCH_ROLES
        scopes = {None, "regression_only"}
    elif track == "robustness_scale":
        roles = _EVALUATED_MATCH_ROLES
        scopes = {None, "reliability_only"}
    else:
        raise ValueError(f"unsupported benchmark track: {track!r}")

    selected: list[Mapping[str, Any]] = []
    for raw_label in labels:
        label = _require_mapping(raw_label, "expected observation")
        if label.get("role") in roles and label.get("evaluation_scope") in scopes:
            selected.append(label)
    return selected


def _require_bool(bundle: Mapping[str, Any], key: str) -> bool | None:
    if key not in bundle:
        return None
    value = bundle[key]
    if not isinstance(value, bool):
        raise ValueError(f"{key} must be boolean when present")
    return value


def _match_payload(value: object) -> Mapping[str, Any]:
    if isinstance(value, MatchResult):
        payload = value.to_dict()
    else:
        payload = _require_mapping(value, "match_result")
    required = {
        "matches",
        "unmatched_label_ids",
        "unmatched_observation_ids",
        "assignment_ambiguous",
    }
    if not required.issubset(payload):
        raise ValueError("match_result is missing required fields")
    if not isinstance(payload["assignment_ambiguous"], bool):
        raise ValueError("match_result.assignment_ambiguous must be boolean")
    for key in ("matches", "unmatched_label_ids", "unmatched_observation_ids"):
        if not isinstance(payload[key], (list, tuple)):
            raise ValueError(f"match_result.{key} must be an array")
    return payload


def _match_rows(
    payload: Mapping[str, Any], *, require_location: bool = True
) -> list[Mapping[str, Any]]:
    rows: list[Mapping[str, Any]] = []
    label_ids: set[str] = set()
    observation_ids: set[str] = set()
    for raw in payload["matches"]:
        row = _require_mapping(raw, "match_result.matches item")
        label_id = row.get("label_id")
        observation_id = row.get("observation_id")
        compatibility = row.get("compatibility")
        if not isinstance(label_id, str) or not label_id:
            raise ValueError("matched label_id must be a non-empty string")
        if not isinstance(observation_id, str) or not observation_id:
            raise ValueError("matched observation_id must be a non-empty string")
        if label_id in label_ids or observation_id in observation_ids:
            raise ValueError("match_result matches must be one-to-one")
        compatibility = _require_mapping(compatibility, "match compatibility")
        for key in (
            "compatible",
            "issue_compatible",
            "location_compatible",
            "risk_compatible",
        ):
            if not isinstance(compatibility.get(key), bool):
                raise ValueError(f"match compatibility {key} must be boolean")
        required_true = (
            ("compatible", "issue_compatible", "location_compatible")
            if require_location
            else ("issue_compatible",)
        )
        for key in required_true:
            if not compatibility[key]:
                raise ValueError(f"selected match compatibility {key} must be true")
        label_ids.add(label_id)
        observation_ids.add(observation_id)
        rows.append(row)
    return rows


def _canonical_event_component(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).casefold()
    parts: list[str] = []
    pending_separator = False
    for character in normalized:
        if character.isalnum():
            if pending_separator and parts:
                parts.append("_")
            parts.append(character)
            pending_separator = False
        else:
            pending_separator = True
    return "".join(parts)


def _event_parts(
    event: Mapping[str, Any], default_module: str
) -> tuple[str, str | None]:
    module = _canonical_event_component(str(event.get("module") or default_module))
    if not module:
        module = _canonical_event_component(default_module)
    for field in ("failure_type", "category", "status"):
        detail = event.get(field)
        if isinstance(detail, str) and detail.strip():
            normalized_detail = _canonical_event_component(detail)
            if normalized_detail:
                return module, normalized_detail
    return module, None


def _failure_events(
    run: Mapping[str, Any],
) -> tuple[set[tuple[str, str | None]], set[tuple[str, str | None]]]:
    normalized = run["normalized_observation"]
    actual = {
        _event_parts(_require_mapping(item, "technical failure"), "runtime")
        for item in normalized["technical_failures"]
    }
    if run["status"] != _SUCCESS:
        failure = _require_mapping(run["failure"], "run failure")
        actual.add(_event_parts(failure, "runtime"))
    reported = {
        _event_parts(_require_mapping(item, "reported technical failure"), "runtime")
        for item in normalized["reported_technical_failures"]
    }
    return actual, reported


def _is_disclosed(
    event: tuple[str, str | None], reported: set[tuple[str, str | None]]
) -> bool:
    module, detail = event
    if detail is not None:
        return event in reported
    return any(reported_module == module for reported_module, _ in reported)


def _validate_bundle(
    bundle: Mapping[str, Any],
) -> tuple[Mapping[str, Any], Mapping[str, Any], Mapping[str, Any], Mapping[str, Any]]:
    manifest_case = _require_mapping(bundle.get("manifest_case"), "manifest_case")
    annotation = _require_mapping(bundle.get("annotation"), "annotation")
    run = _require_mapping(bundle.get("run_result"), "run_result")
    match = _match_payload(bundle.get("match_result"))

    validate_contract(
        "benchmark_manifest.schema.json",
        {
            "schema_version": "1.0.0",
            "benchmark_id": "bundle-validation",
            "benchmark_version": "0.0.0",
            "cases": [manifest_case],
        },
    )
    validate_contract("annotation.schema.json", annotation)
    validate_contract("run_result.schema.json", run)
    case_ids = {manifest_case["case_id"], annotation["case_id"], run["case_id"]}
    if len(case_ids) != 1:
        raise ValueError(
            "manifest, annotation, and run result case_id values must match"
        )

    selected_labels = select_evaluation_labels(manifest_case, annotation)
    label_ids = {item["observation_id"] for item in selected_labels}
    observations = run["normalized_observation"]["observations"]
    observation_ids = {
        item["observation_id"] for item in observations
    }
    rows = _match_rows(match)
    if any(row["label_id"] not in label_ids for row in rows):
        raise ValueError("match_result references an unknown label")
    if any(row["observation_id"] not in observation_ids for row in rows):
        raise ValueError("match_result references an unknown observation")
    for key, valid_ids in (
        ("unmatched_label_ids", label_ids),
        ("unmatched_observation_ids", observation_ids),
    ):
        values = match[key]
        if any(not isinstance(item, str) or item not in valid_ids for item in values):
            kind = "label" if key == "unmatched_label_ids" else "observation"
            raise ValueError(f"match_result.{key} contains an unknown {kind} id")
        if len(values) != len(set(values)):
            raise ValueError(f"match_result.{key} contains duplicates")
    matched_label_ids = {row["label_id"] for row in rows}
    matched_observation_ids = {row["observation_id"] for row in rows}
    unmatched_label_ids = set(match["unmatched_label_ids"])
    unmatched_observation_ids = set(match["unmatched_observation_ids"])
    if matched_label_ids & unmatched_label_ids:
        raise ValueError("matched and unmatched label ids must be disjoint")
    if matched_observation_ids & unmatched_observation_ids:
        raise ValueError("matched and unmatched observation ids must be disjoint")
    if matched_label_ids | unmatched_label_ids != label_ids:
        raise ValueError("match_result must account for every label exactly once")
    if matched_observation_ids | unmatched_observation_ids != observation_ids:
        raise ValueError("match_result must account for every observation exactly once")

    canonical = match_labels(
        selected_labels,
        observations,
        roles=_EVALUATED_MATCH_ROLES,
    ).to_dict()
    canonical_rows = _match_rows(canonical)
    supplied_by_pair = {
        (row["label_id"], row["observation_id"]): row for row in rows
    }
    canonical_by_pair = {
        (row["label_id"], row["observation_id"]): row for row in canonical_rows
    }
    if set(supplied_by_pair) != set(canonical_by_pair):
        raise ValueError("match_result selected pairs differ from canonical selected pairs")
    if set(match["unmatched_label_ids"]) != set(canonical["unmatched_label_ids"]):
        raise ValueError("match_result unmatched labels differ from canonical partition")
    if set(match["unmatched_observation_ids"]) != set(
        canonical["unmatched_observation_ids"]
    ):
        raise ValueError("match_result unmatched observations differ from canonical partition")
    if match["assignment_ambiguous"] != canonical["assignment_ambiguous"]:
        raise ValueError(
            "match_result assignment_ambiguous differs from canonical assignment_ambiguous"
        )
    for pair, canonical_row in canonical_by_pair.items():
        supplied_compatibility = supplied_by_pair[pair]["compatibility"]
        canonical_compatibility = canonical_row["compatibility"]
        for key in (
            "compatible",
            "issue_compatible",
            "location_compatible",
            "risk_compatible",
        ):
            if supplied_compatibility[key] != canonical_compatibility[key]:
                raise ValueError(
                    f"match_result compatibility {key} differs from canonical match"
                )
    return manifest_case, annotation, run, canonical


def aggregate_metrics(
    *,
    cases: Sequence[Mapping[str, Any]],
    benchmark_id: str,
    benchmark_version: str,
    manifest_sha256: str | None = None,
    reproduction: Mapping[str, Any] | None = None,
    generated_at: str | None = None,
    schema_version: str = "1.0.0",
) -> dict[str, Any]:
    """Aggregate validated case bundles into a metrics-schema payload.

    ``reproduction`` is optional for focused unit fixtures.  CLI-produced public
    metrics must supply it so every rendered number can be traced to the exact
    run-result artifacts and sealed benchmark inputs.
    """
    if isinstance(cases, (str, bytes)) or not isinstance(cases, Sequence):
        raise ValueError("cases must be an array of case bundles")
    for name, value in (
        ("benchmark_id", benchmark_id),
        ("benchmark_version", benchmark_version),
        ("schema_version", schema_version),
    ):
        if not isinstance(value, str) or not value:
            raise ValueError(f"{name} must be a non-empty string")

    prepared: list[
        tuple[
            Mapping[str, Any],
            Mapping[str, Any],
            Mapping[str, Any],
            Mapping[str, Any],
            Mapping[str, Any],
        ]
    ] = []
    seen: set[str] = set()
    for raw_bundle in cases:
        bundle = _require_mapping(raw_bundle, "case bundle")
        unknown_keys = set(bundle) - _BUNDLE_KEYS
        if unknown_keys:
            raise ValueError(f"case bundle has unknown keys: {sorted(unknown_keys)!r}")
        manifest_case, annotation, run, match = _validate_bundle(bundle)
        case_id = manifest_case["case_id"]
        if case_id in seen:
            raise ValueError(f"duplicate case bundle: {case_id}")
        seen.add(case_id)
        assertions = bundle.get("regression_assertions", [])
        if not isinstance(assertions, (list, tuple)) or any(
            not isinstance(item, bool) for item in assertions
        ):
            raise ValueError("regression_assertions must be an array of booleans")
        for key in (
            "attack_resisted",
            "atomic_output_preserved",
            "previous_output_preserved",
            "over_budget",
        ):
            _require_bool(bundle, key)
        prepared.append((bundle, manifest_case, annotation, run, match))
    prepared.sort(key=lambda item: item[1]["case_id"])

    detection_counts = defaultdict(int)
    reliability_counts = defaultdict(int)
    regression_met = regression_total = 0
    telemetry_values: dict[str, list[tuple[str, int | float]]] = defaultdict(list)
    profile_values: dict[str, dict[str, list[tuple[str, int | float]]]] = {
        profile: defaultdict(list) for profile in _PROFILES
    }
    module_values: dict[str, list[tuple[str, int | float]]] = defaultdict(list)
    llm_values: dict[str, list[tuple[str, int | float]]] = defaultdict(list)
    track_counts = defaultdict(int)
    track_eligible = defaultdict(bool)
    case_results: list[dict[str, Any]] = []

    for bundle, manifest_case, annotation, run, full_match in prepared:
        case_id = manifest_case["case_id"]
        track = manifest_case["track"]
        status = run["status"]
        normalized = run["normalized_observation"]
        evaluated_labels = select_evaluation_labels(manifest_case, annotation)
        issue_match = match_labels(
            evaluated_labels,
            normalized["observations"],
            roles=_EVALUATED_MATCH_ROLES,
            require_location=False,
        ).to_dict()
        issue_rows = _match_rows(issue_match, require_location=False)
        successful_rows = issue_rows if status == _SUCCESS else []
        rows_by_label = {row["label_id"]: row for row in successful_rows}
        attribution_ambiguous = status == _SUCCESS and (
            full_match["assignment_ambiguous"]
            or issue_match["assignment_ambiguous"]
        )
        eligible = (
            track in {"blinded_challenge", "public_realism"}
            and manifest_case.get("headline_eligible") is True
            and annotation["review_status"]
            in {"controlled_ground_truth", "independent_adjudicated"}
            and not attribution_ambiguous
        )
        track_counts[track] += 1
        track_eligible[track] = track_eligible[track] or eligible

        headline_labels = [
            label
            for label in evaluated_labels
            if label["role"] == "recall_label"
            and label.get("evaluation_scope") in (None, "headline_detection")
        ]
        coverage_labels = [
            label
            for label in evaluated_labels
            if label["role"] == "coverage_gap"
            and label.get("evaluation_scope") in (None, "headline_detection")
        ]
        matched_headline = sum(
            label["observation_id"] in rows_by_label for label in headline_labels
        )
        matched_coverage = sum(
            label["observation_id"] in rows_by_label
            and rows_by_label[label["observation_id"]]["compatibility"][
                "location_compatible"
            ]
            for label in coverage_labels
        )

        if eligible:
            if annotation["negative_control"]:
                detection_counts["negative_denominator"] += 1
                if status != _SUCCESS or normalized["observations"]:
                    detection_counts["negative_numerator"] += 1
            else:
                detection_counts["recall_numerator"] += matched_headline
                detection_counts["recall_denominator"] += len(headline_labels)
                detection_counts["location_numerator"] += sum(
                    bool(
                        rows_by_label[label["observation_id"]]["compatibility"][
                            "location_compatible"
                        ]
                    )
                    for label in headline_labels
                    if label["observation_id"] in rows_by_label
                )
                detection_counts["location_denominator"] += matched_headline
                detection_counts["risk_numerator"] += sum(
                    bool(row["compatibility"]["risk_compatible"])
                    for row in rows_by_label.values()
                    if row["label_id"]
                    in {label["observation_id"] for label in headline_labels}
                )
                detection_counts["risk_denominator"] += matched_headline
                detection_counts["coverage_numerator"] += matched_coverage
                detection_counts["coverage_denominator"] += len(coverage_labels)

        if (
            track == "public_concern"
            and annotation["review_status"]
            in {
                "controlled_ground_truth",
                "independent_adjudicated",
            }
            and not attribution_ambiguous
        ):
            detection_counts["concern_numerator"] += sum(
                label["observation_id"] in rows_by_label
                and rows_by_label[label["observation_id"]]["compatibility"][
                    "location_compatible"
                ]
                for label in evaluated_labels
            )
            detection_counts["concern_denominator"] += len(evaluated_labels)

        if track == "regression":
            assertions = bundle.get("regression_assertions", [])
            if status == _SUCCESS:
                regression_met += sum(assertions)
            regression_total += len(assertions)

        actual_events, reported_events = _failure_events(run)
        disclosed_count = sum(
            _is_disclosed(event, reported_events) for event in actual_events
        )
        reliability_counts["cases"] += 1
        reliability_counts["silent_cases"] += disclosed_count < len(actual_events)
        reliability_counts["actual_events"] += len(actual_events)
        reliability_counts["disclosed_events"] += disclosed_count
        reliability_counts["boundary_cases"] += bool(normalized["boundary_violations"])
        reliability_counts["completed"] += status == _SUCCESS
        reliability_counts["contract_valid"] += (
            status not in _REPORT_INVALID_STATUSES and not normalized["contract_errors"]
        )

        for fact, prefix in (
            ("attack_resisted", "attack"),
            ("atomic_output_preserved", "atomic"),
            ("previous_output_preserved", "previous"),
        ):
            value = _require_bool(bundle, fact)
            if value is not None:
                reliability_counts[f"{prefix}_denominator"] += 1
                reliability_counts[f"{prefix}_numerator"] += value

        telemetry = run["telemetry"]
        profile = manifest_case["scan_profile"]
        for source, target in (
            ("elapsed_seconds", "wall_time_seconds"),
            ("cpu_seconds", "cpu_time_seconds"),
            ("peak_rss_bytes", "peak_rss_bytes"),
            ("output_size_bytes", "output_size_bytes"),
        ):
            if source in telemetry:
                telemetry_values[target].append((case_id, telemetry[source]))
                profile_values[profile][target].append((case_id, telemetry[source]))
        for module, seconds in sorted(telemetry.get("module_seconds", {}).items()):
            module_values[module].append((case_id, seconds))
        llm = telemetry.get("llm")
        if llm is not None:
            for source, target in (
                ("input_tokens", "llm_input_tokens"),
                ("output_tokens", "llm_output_tokens"),
                ("latency_seconds", "llm_latency_seconds"),
                ("estimated_cost_cny", "llm_estimated_cost_cny"),
            ):
                if source in llm:
                    llm_values[target].append((case_id, llm[source]))
        over_budget = _require_bool(bundle, "over_budget")
        if over_budget is not None:
            reliability_counts["budget_denominator"] += 1
            reliability_counts["budget_numerator"] += over_budget
            profile_values[profile]["budget"].append((case_id, int(over_budget)))

        case_results.append(
            {
                "case_id": case_id,
                "track": track,
                "split": manifest_case["split"],
                "status": status,
                "adapter": run["adapter"],
                "headline_detection_eligible": eligible,
                "matched_label_count": len(successful_rows),
                "expected_label_count": len(evaluated_labels),
                "false_alert_count": (
                    len(issue_match["unmatched_observation_ids"])
                    if status == _SUCCESS
                    else int(annotation["negative_control"])
                ),
                "technical_failure_count": len(actual_events),
                "reported_failure_count": len(reported_events),
                "boundary_violation_count": len(normalized["boundary_violations"]),
                "elapsed_seconds": telemetry["elapsed_seconds"],
                "cpu_seconds": telemetry["cpu_seconds"],
                "peak_rss_bytes": telemetry["peak_rss_bytes"],
                **(
                    {"output_size_bytes": telemetry["output_size_bytes"]}
                    if "output_size_bytes" in telemetry
                    else {}
                ),
            }
        )

    detection = {
        "expected_finding_recall": _fraction(
            detection_counts["recall_numerator"], detection_counts["recall_denominator"]
        ),
        "negative_package_false_alert_rate": _fraction(
            detection_counts["negative_numerator"],
            detection_counts["negative_denominator"],
        ),
        "location_match_rate": _fraction(
            detection_counts["location_numerator"],
            detection_counts["location_denominator"],
        ),
        "risk_band_agreement": _fraction(
            detection_counts["risk_numerator"], detection_counts["risk_denominator"]
        ),
        "coverage_gap_recall": _fraction(
            detection_counts["coverage_numerator"],
            detection_counts["coverage_denominator"],
        ),
        "public_concern_location_coverage": _fraction(
            detection_counts["concern_numerator"],
            detection_counts["concern_denominator"],
        ),
        "regression_assertions": {
            "met": regression_met,
            "not_met": regression_total - regression_met,
            "total": regression_total,
        },
    }
    reliability = {
        "silent_failure_rate": _fraction(
            reliability_counts["silent_cases"], reliability_counts["cases"]
        ),
        "boundary_violation_rate": _fraction(
            reliability_counts["boundary_cases"], reliability_counts["cases"]
        ),
        "manifest_attack_resistance": _fraction(
            reliability_counts["attack_numerator"],
            reliability_counts["attack_denominator"],
        ),
        "report_contract_validity": _fraction(
            reliability_counts["contract_valid"], reliability_counts["cases"]
        ),
        "technical_failure_disclosure_rate": _fraction(
            reliability_counts["disclosed_events"], reliability_counts["actual_events"]
        ),
        "run_completion_rate": _fraction(
            reliability_counts["completed"], reliability_counts["cases"]
        ),
        "atomic_output_preservation": _fraction(
            reliability_counts["atomic_numerator"],
            reliability_counts["atomic_denominator"],
        ),
        "previous_result_preservation": _fraction(
            reliability_counts["previous_numerator"],
            reliability_counts["previous_denominator"],
        ),
    }
    performance = {
        metric: _distribution(telemetry_values[metric])
        for metric in (
            "wall_time_seconds",
            "cpu_time_seconds",
            "peak_rss_bytes",
            "output_size_bytes",
        )
    }
    performance["over_budget_rate"] = _fraction(
        reliability_counts["budget_numerator"], reliability_counts["budget_denominator"]
    )
    performance["profiles"] = {
        profile: {
            **{
                metric: _distribution(profile_values[profile][metric])
                for metric in (
                    "wall_time_seconds",
                    "cpu_time_seconds",
                    "peak_rss_bytes",
                    "output_size_bytes",
                )
            },
            "over_budget_rate": _fraction(
                sum(value for _, value in profile_values[profile]["budget"]),
                len(profile_values[profile]["budget"]),
            ),
        }
        for profile in _PROFILES
    }
    performance["module_seconds"] = {
        module: _distribution(values)
        for module, values in sorted(module_values.items())
    }
    performance.update(
        {metric: _distribution(values) for metric, values in sorted(llm_values.items())}
    )

    result: dict[str, Any] = {
        "schema_version": schema_version,
        "benchmark_id": benchmark_id,
        "benchmark_version": benchmark_version,
        "run_count": len(prepared),
        "detection": detection,
        "reliability": reliability,
        "performance": performance,
        "tracks": {
            track: {
                "case_count": track_counts[track],
                "headline_detection_eligible": track_eligible[track],
            }
            for track in _TRACKS
        },
        "case_results": case_results,
    }
    if manifest_sha256 is not None:
        result["manifest_sha256"] = manifest_sha256
    if reproduction is not None:
        result["reproduction"] = dict(reproduction)
    if generated_at is not None:
        result["generated_at"] = generated_at
    result = _json_safe_numbers(result)
    validate_contract("metrics.schema.json", result)
    return result
