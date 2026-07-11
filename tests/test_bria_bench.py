from __future__ import annotations

import copy
import json
import os
import re
import signal
import sys
import tempfile
import time
import unittest
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

from jsonschema import Draft202012Validator
import tomllib

import benchmarks.bria_bench.hashing as hashing_module
import benchmarks.bria_bench.matching as matching_module
from benchmarks.bria_bench import ContractError, __version__, validate_contract
from benchmarks.bria_bench.contracts import SCHEMA_ROOT, load_schema
from benchmarks.bria_bench.hashing import HashingError, hash_file, hash_tree
from benchmarks.bria_bench.matching import (
    Compatibility,
    Match,
    MatchResult,
    label_observation_compatible,
    match_labels,
)
from benchmarks.bria_bench.metrics import aggregate_metrics
from benchmarks.bria_bench.normalize import normalize_audit_output
from benchmarks.bria_bench.registry import (
    RegistryError,
    freeze_manifest,
    load_manifest,
    resolve_case_paths,
    resolve_inside,
    verify_frozen_case,
)
import benchmarks.bria_bench.runtime as runtime_module
from benchmarks.bria_bench.runtime import RuntimeResult, run_monitored, write_json_atomic


SCHEMA_NAMES = (
    "benchmark_manifest.schema.json",
    "annotation.schema.json",
    "observation.schema.json",
    "run_result.schema.json",
    "metrics.schema.json",
)


def minimal_manifest() -> dict[str, object]:
    return {
        "schema_version": "1.0.0",
        "benchmark_id": "bria-bench-dev",
        "benchmark_version": "0.1.0",
        "cases": [
            {
                "case_id": "dev_001",
                "track": "blinded_challenge",
                "split": "dev",
                "package_path": "cases/dev_001",
                "annotation_path": "annotations/dev/dev_001.json",
                "mode": "internal_presubmission",
                "scan_profile": "quick",
                "redistributable": True,
                "license": "CC0-1.0",
            }
        ],
    }


def minimal_annotation() -> dict[str, object]:
    return {
        "case_id": "dev_001",
        "negative_control": False,
        "review_status": "controlled_ground_truth",
        "expected_observations": [
            {
                "observation_id": "label_001",
                "role": "recall_label",
                "issue_family": "image_local_reuse",
                "location": {
                    "text": "Figure 1A",
                    "terms": ["figure 1a"],
                },
                "risk_range": ["R2", "R3"],
                "benign_explanations": ["The panels may share an acquisition field."],
                "required_materials": ["Original image files and assembly history"],
            }
        ],
    }


def minimal_observation() -> dict[str, object]:
    return {
        "case_id": "dev_001",
        "observations": [
            {
                "observation_id": "obs_001",
                "source_finding_id": "F-1",
                "issue_family": "image_local_reuse",
                "location": "Figure 1A",
                "risk_level": "R2",
                "summary": "Two regions warrant source-image comparison.",
            }
        ],
        "technical_failures": [],
        "reported_technical_failures": [],
        "boundary_violations": [],
        "contract_errors": [],
    }


def minimal_run_result() -> dict[str, object]:
    return {
        "case_id": "dev_001",
        "adapter": "full",
        "status": "success",
        "hashes": {
            "package_sha256": "a" * 64,
            "runner_sha256": "b" * 64,
        },
        "cache_key": "c" * 64,
        "telemetry": {
            "elapsed_seconds": 1.25,
            "cpu_seconds": 0.75,
            "peak_rss_bytes": 1024,
            "timed_out": False,
        },
        "output_paths": {"case_output": "results/dev_001"},
        "normalized_observation": minimal_observation(),
        "failure": None,
    }


def failure_details(category: str = "process_error", *, timed_out: bool = False) -> dict[str, object]:
    return {
        "category": category,
        "message": f"Run ended with {category}.",
        "timed_out": timed_out,
    }


def metric_case(case_id: str, status: str = "success") -> dict[str, object]:
    return {
        "case_id": case_id,
        "track": "blinded_challenge",
        "split": "dev",
        "status": status,
    }


def minimal_metrics() -> dict[str, object]:
    return {
        "schema_version": "1.0.0",
        "benchmark_id": "bria-bench-dev",
        "benchmark_version": "0.1.0",
        "detection": {
            "expected_finding_recall": {
                "numerator": 1,
                "denominator": 1,
                "value": 1.0,
            }
        },
        "reliability": {
            "silent_failure_rate": {
                "numerator": 0,
                "denominator": 1,
                "value": 0.0,
            }
        },
        "performance": {
            "wall_time_seconds": {
                "count": 1,
                "p50": 1.25,
                "p95": 1.25,
                "values": [1.25],
            }
        },
    }


def metric_bundle(
    case_id: str,
    *,
    negative: bool = False,
    status: str = "success",
    matched: bool = False,
    track: str = "blinded_challenge",
    review_status: str = "controlled_ground_truth",
    scope: str | None = None,
    profile: str = "quick",
) -> dict[str, object]:
    manifest_case = copy.deepcopy(minimal_manifest()["cases"][0])
    manifest_case.update(
        {
            "case_id": case_id,
            "track": track,
            "scan_profile": profile,
            "headline_eligible": True,
        }
    )
    annotation = copy.deepcopy(minimal_annotation())
    annotation["case_id"] = case_id
    annotation["negative_control"] = negative
    annotation["review_status"] = review_status
    label = annotation["expected_observations"][0]
    if scope is not None:
        label["evaluation_scope"] = scope
    if negative:
        annotation["expected_observations"] = []

    run_result = copy.deepcopy(minimal_run_result())
    run_result["case_id"] = case_id
    run_result["normalized_observation"]["case_id"] = case_id
    run_result["status"] = status
    if status != "success":
        run_result["failure"] = failure_details(status)
        run_result["normalized_observation"]["observations"] = []
    elif negative:
        run_result["normalized_observation"]["observations"] = []

    matches: tuple[Match, ...] = ()
    unmatched_labels: tuple[str, ...] = () if negative else ("label_001",)
    unmatched_observations: tuple[str, ...] = (
        ("obs_001",) if not negative and status == "success" else ()
    )
    if matched:
        compatibility = Compatibility(
            compatible=True,
            issue_compatible=True,
            location_compatible=True,
            risk_compatible=True,
            score=(1,),
        )
        matches = (Match("label_001", "obs_001", compatibility),)
        unmatched_labels = ()
        unmatched_observations = ()
    return {
        "manifest_case": manifest_case,
        "annotation": annotation,
        "run_result": run_result,
        "match_result": MatchResult(
            matches=matches,
            unmatched_label_ids=unmatched_labels,
            unmatched_observation_ids=unmatched_observations,
            candidate_edges=matches,
            assignment_ambiguous=False,
        ),
    }


class BriaBenchContractTests(unittest.TestCase):
    def payloads(self) -> dict[str, dict[str, object]]:
        return {
            "benchmark_manifest.schema.json": minimal_manifest(),
            "annotation.schema.json": minimal_annotation(),
            "observation.schema.json": minimal_observation(),
            "run_result.schema.json": minimal_run_result(),
            "metrics.schema.json": minimal_metrics(),
        }

    def test_package_exports_contract_api_and_version(self) -> None:
        self.assertEqual(__version__, "0.1.0")
        self.assertTrue(issubclass(ContractError, ValueError))
        self.assertTrue(callable(validate_contract))

    def test_every_schema_loads_and_is_valid_draft_2020_12(self) -> None:
        self.assertEqual(
            {path.name for path in SCHEMA_ROOT.glob("*.schema.json")},
            set(SCHEMA_NAMES),
        )
        for name in SCHEMA_NAMES:
            with self.subTest(schema=name):
                schema = load_schema(name)
                self.assertIsInstance(schema, dict)
                Draft202012Validator.check_schema(schema)

    def test_minimal_payloads_pass(self) -> None:
        for name, payload in self.payloads().items():
            with self.subTest(schema=name):
                validate_contract(name, payload)

    def test_unknown_top_level_keys_fail(self) -> None:
        for name, payload in self.payloads().items():
            with self.subTest(schema=name):
                invalid = copy.deepcopy(payload)
                invalid["unexpected"] = True
                with self.assertRaises(ContractError):
                    validate_contract(name, invalid)

    def test_manifest_controlled_vocabularies(self) -> None:
        manifest = minimal_manifest()
        case = manifest["cases"][0]
        assert isinstance(case, dict)
        vocabularies = {
            "track": (
                "regression",
                "blinded_challenge",
                "public_realism",
                "public_concern",
                "robustness_scale",
            ),
            "split": ("dev", "test", "reference"),
            "mode": (
                "internal_presubmission",
                "external_public_material",
                "response_to_concern",
            ),
            "scan_profile": ("quick", "standard", "deep"),
        }
        for field, values in vocabularies.items():
            for value in values:
                with self.subTest(field=field, value=value):
                    candidate = copy.deepcopy(manifest)
                    candidate["cases"][0][field] = value
                    validate_contract("benchmark_manifest.schema.json", candidate)

            invalid = copy.deepcopy(manifest)
            invalid["cases"][0][field] = "not-controlled"
            with self.assertRaises(ContractError):
                validate_contract("benchmark_manifest.schema.json", invalid)

    def test_manifest_accepts_frozen_metadata(self) -> None:
        manifest = minimal_manifest()
        manifest["frozen_at"] = "2026-07-11T00:00:00Z"
        manifest["cases"][0]["expected_sha256"] = "d" * 64
        manifest["cases"][0]["annotation_sha256"] = "e" * 64
        validate_contract("benchmark_manifest.schema.json", manifest)

    def test_manifest_rejects_invalid_frozen_at_format(self) -> None:
        manifest = minimal_manifest()
        manifest["frozen_at"] = "not-a-date"
        with self.assertRaisesRegex(ContractError, "frozen_at"):
            validate_contract("benchmark_manifest.schema.json", manifest)

    def test_manifest_rejects_duplicate_case_ids(self) -> None:
        manifest = minimal_manifest()
        manifest["cases"].append(copy.deepcopy(manifest["cases"][0]))
        with self.assertRaisesRegex(ContractError, r"cases\.1\.case_id:.*unique"):
            validate_contract("benchmark_manifest.schema.json", manifest)

    def test_annotation_review_statuses_and_observation_roles(self) -> None:
        annotation = minimal_annotation()
        for status in (
            "controlled_ground_truth",
            "independent_pending",
            "independent_adjudicated",
            "ambiguous",
        ):
            with self.subTest(review_status=status):
                candidate = copy.deepcopy(annotation)
                candidate["review_status"] = status
                validate_contract("annotation.schema.json", candidate)

        for role in (
            "recall_label",
            "coverage_gap",
            "negative_guardrail",
            "reference_only",
        ):
            with self.subTest(role=role):
                candidate = copy.deepcopy(annotation)
                candidate["expected_observations"][0]["role"] = role
                validate_contract("annotation.schema.json", candidate)

    def test_annotation_rejects_accusation_keys_in_controlled_objects(self) -> None:
        for key in ("misconduct", "fraud", "fake", "guilty"):
            candidates = []

            top_level = minimal_annotation()
            top_level[key] = True
            candidates.append(top_level)

            expected_observation = minimal_annotation()
            expected_observation["expected_observations"][0][key] = True
            candidates.append(expected_observation)

            nested_location = minimal_annotation()
            nested_location["expected_observations"][0]["location"][key] = True
            candidates.append(nested_location)

            for depth, candidate in enumerate(candidates):
                with self.subTest(key=key, depth=depth):
                    with self.assertRaises(ContractError):
                        validate_contract("annotation.schema.json", candidate)

    def test_annotation_rejects_duplicate_observation_ids(self) -> None:
        annotation = minimal_annotation()
        annotation["expected_observations"].append(
            copy.deepcopy(annotation["expected_observations"][0])
        )
        with self.assertRaisesRegex(
            ContractError,
            r"expected_observations\.1\.observation_id:.*unique",
        ):
            validate_contract("annotation.schema.json", annotation)

    def test_annotation_rejects_accusation_key_inside_region(self) -> None:
        for key in ("misconduct", "fraud", "fake", "guilty"):
            with self.subTest(key=key):
                annotation = minimal_annotation()
                region = {
                    "x": 0,
                    "y": 0,
                    "width": 0.5,
                    "height": 0.5,
                    "coordinate_space": "normalized_0_1",
                    key: True,
                }
                annotation["expected_observations"][0]["location"]["region"] = region
                with self.assertRaises(ContractError):
                    validate_contract("annotation.schema.json", annotation)

    def test_annotation_requires_nonempty_observation_and_location_lists(self) -> None:
        for field in ("benign_explanations", "required_materials"):
            with self.subTest(field=field):
                annotation = minimal_annotation()
                annotation["expected_observations"][0][field] = []
                with self.assertRaises(ContractError):
                    validate_contract("annotation.schema.json", annotation)

        for field in ("terms", "columns", "rows"):
            with self.subTest(location_field=field):
                annotation = minimal_annotation()
                annotation["expected_observations"][0]["location"][field] = []
                with self.assertRaises(ContractError):
                    validate_contract("annotation.schema.json", annotation)

        for field in ("columns", "rows"):
            with self.subTest(normalized_location_field=field):
                observation = minimal_observation()
                observation["observations"][0]["location"] = {field: []}
                with self.assertRaises(ContractError):
                    validate_contract("observation.schema.json", observation)

    def test_regions_require_coordinate_space_and_validate_coordinates(self) -> None:
        invalid_regions = (
            {"x": 0, "y": 0, "width": 0.5, "height": 0.5},
            {
                "x": 1.1,
                "y": 0,
                "width": 0,
                "height": 0.5,
                "coordinate_space": "normalized_0_1",
            },
            {
                "x": 0.75,
                "y": 0,
                "width": 0.5,
                "height": 0.5,
                "coordinate_space": "normalized_0_1",
            },
            {
                "x": 0,
                "y": 0.75,
                "width": 0.5,
                "height": 0.5,
                "coordinate_space": "normalized_0_1",
            },
            {
                "x": -1,
                "y": 0,
                "width": 10,
                "height": 10,
                "coordinate_space": "pixels",
            },
        )
        for index, region in enumerate(invalid_regions):
            with self.subTest(region=index):
                annotation = minimal_annotation()
                annotation["expected_observations"][0]["location"]["region"] = region
                with self.assertRaises(ContractError):
                    validate_contract("annotation.schema.json", annotation)

        for region in (
            {
                "x": 0.5,
                "y": 0.5,
                "width": 0.5,
                "height": 0.5,
                "coordinate_space": "normalized_0_1",
            },
            {
                "x": 0,
                "y": 0,
                "width": 1,
                "height": 1,
                "coordinate_space": "pixels",
            },
        ):
            with self.subTest(valid_region=region["coordinate_space"]):
                annotation = minimal_annotation()
                annotation["expected_observations"][0]["location"]["region"] = region
                validate_contract("annotation.schema.json", annotation)

    def test_regions_require_positive_width_and_height(self) -> None:
        for coordinate_space in ("normalized_0_1", "pixels"):
            for dimension in ("width", "height"):
                for schema_name in ("annotation.schema.json", "observation.schema.json"):
                    with self.subTest(
                        schema=schema_name,
                        coordinate_space=coordinate_space,
                        dimension=dimension,
                    ):
                        region = {
                            "x": 0,
                            "y": 0,
                            "width": 0.5 if coordinate_space == "normalized_0_1" else 1,
                            "height": 0.5 if coordinate_space == "normalized_0_1" else 1,
                            "coordinate_space": coordinate_space,
                        }
                        region[dimension] = 0
                        if schema_name == "annotation.schema.json":
                            payload = minimal_annotation()
                            payload["expected_observations"][0]["location"]["region"] = region
                        else:
                            payload = minimal_observation()
                            payload["observations"][0]["location"] = {"region": region}
                        with self.assertRaises(ContractError):
                            validate_contract(schema_name, payload)

    def test_normalized_region_semantics_apply_standalone_and_in_run_result(self) -> None:
        invalid_region = {
            "x": 0.8,
            "y": 0,
            "width": 0.3,
            "height": 0.5,
            "coordinate_space": "normalized_0_1",
        }
        observation = minimal_observation()
        observation["observations"][0]["location"] = {"region": invalid_region}
        with self.assertRaisesRegex(ContractError, r"observations\.0\.location\.region\.width"):
            validate_contract("observation.schema.json", observation)

        run_result = minimal_run_result()
        run_result["normalized_observation"]["observations"][0]["location"] = {
            "region": invalid_region
        }
        with self.assertRaisesRegex(
            ContractError,
            r"normalized_observation\.observations\.0\.location\.region\.width",
        ):
            validate_contract("run_result.schema.json", run_result)

    def test_normalized_observations_require_unique_ids(self) -> None:
        payload = minimal_observation()
        payload["observations"].append(copy.deepcopy(payload["observations"][0]))
        with self.assertRaisesRegex(
            ContractError,
            r"observations\.1\.observation_id:.*unique",
        ):
            validate_contract("observation.schema.json", payload)

    def test_run_result_case_id_matches_normalized_payload(self) -> None:
        payload = minimal_run_result()
        payload["normalized_observation"]["case_id"] = "different_case"
        with self.assertRaisesRegex(
            ContractError,
            r"normalized_observation\.case_id:.*outer case_id",
        ):
            validate_contract("run_result.schema.json", payload)

    def test_run_result_success_requires_null_failure_and_not_timed_out(self) -> None:
        failure_payload = minimal_run_result()
        failure_payload["failure"] = failure_details()
        with self.assertRaisesRegex(ContractError, r"failure:.*null"):
            validate_contract("run_result.schema.json", failure_payload)

        timeout_payload = minimal_run_result()
        timeout_payload["telemetry"]["timed_out"] = True
        with self.assertRaisesRegex(ContractError, r"telemetry\.timed_out:.*false"):
            validate_contract("run_result.schema.json", timeout_payload)

    def test_run_result_timeout_requires_flag_and_failure(self) -> None:
        missing_flag = minimal_run_result()
        missing_flag["status"] = "timeout"
        missing_flag["failure"] = failure_details("timeout", timed_out=True)
        with self.assertRaisesRegex(ContractError, r"telemetry\.timed_out:.*true"):
            validate_contract("run_result.schema.json", missing_flag)

        missing_failure = minimal_run_result()
        missing_failure["status"] = "timeout"
        missing_failure["telemetry"]["timed_out"] = True
        with self.assertRaisesRegex(ContractError, r"failure:.*non-null"):
            validate_contract("run_result.schema.json", missing_failure)

    def test_other_non_success_run_states_require_coherent_failure(self) -> None:
        statuses = set(
            load_schema("run_result.schema.json")["properties"]["status"]["enum"]
        ) - {"success", "timeout"}
        for status in statuses:
            with self.subTest(status=status):
                payload = minimal_run_result()
                payload["status"] = status
                with self.assertRaisesRegex(ContractError, r"failure:.*non-null"):
                    validate_contract("run_result.schema.json", payload)

        payload = minimal_run_result()
        payload["status"] = "process_error"
        payload["telemetry"]["timed_out"] = True
        payload["failure"] = failure_details()
        with self.assertRaisesRegex(ContractError, r"telemetry\.timed_out:.*false"):
            validate_contract("run_result.schema.json", payload)

        malformed = minimal_run_result()
        malformed["status"] = "process_error"
        malformed["failure"] = failure_details()
        malformed["failure"]["message"] = ""
        with self.assertRaises(ContractError):
            validate_contract("run_result.schema.json", malformed)

    def test_run_result_accepts_coherent_non_success_states(self) -> None:
        statuses = set(
            load_schema("run_result.schema.json")["properties"]["status"]["enum"]
        ) - {"success", "timeout"}
        for status in statuses:
            with self.subTest(status=status):
                payload = minimal_run_result()
                payload["status"] = status
                payload["failure"] = failure_details(status)
                validate_contract("run_result.schema.json", payload)

        timeout = minimal_run_result()
        timeout["status"] = "timeout"
        timeout["telemetry"]["timed_out"] = True
        timeout["failure"] = failure_details("timeout", timed_out=True)
        validate_contract("run_result.schema.json", timeout)

    def test_run_result_failure_timeout_flag_must_match_telemetry(self) -> None:
        payload = minimal_run_result()
        payload["status"] = "process_error"
        payload["failure"] = failure_details(timed_out=True)
        with self.assertRaisesRegex(ContractError, r"failure\.timed_out:.*match"):
            validate_contract("run_result.schema.json", payload)

    def test_embedded_run_observation_contract_matches_standalone_schema(self) -> None:
        observation_schema = load_schema("observation.schema.json")
        run_schema = load_schema("run_result.schema.json")
        embedded = run_schema["$defs"]["normalizedObservation"]
        for key in ("type", "required", "properties", "additionalProperties"):
            with self.subTest(section=key):
                self.assertEqual(embedded[key], observation_schema[key])

        shared_definitions = (
            "observation",
            "technicalFailure",
            "boundaryViolation",
            "contractError",
            "location",
            "region",
            "riskLevel",
            "stringList",
        )
        for name in shared_definitions:
            with self.subTest(definition=name):
                self.assertEqual(run_schema["$defs"][name], observation_schema["$defs"][name])

    def test_metrics_rejects_composite_score_fields(self) -> None:
        for key in ("score", "overall_score"):
            with self.subTest(key=key):
                payload = minimal_metrics()
                payload[key] = 1.0
                with self.assertRaises(ContractError):
                    validate_contract("metrics.schema.json", payload)

    def test_metrics_recursively_rejects_composite_score_keys(self) -> None:
        distribution = {
            "count": 1,
            "p50": 0.1,
            "p95": 0.1,
            "values": [0.1],
        }
        for key in ("score", "overall_score"):
            with self.subTest(key=key):
                payload = minimal_metrics()
                payload["performance"]["module_seconds"] = {key: distribution}
                with self.assertRaisesRegex(ContractError, key):
                    validate_contract("metrics.schema.json", payload)

    def test_metrics_rejects_duplicate_case_ids(self) -> None:
        payload = minimal_metrics()
        payload["case_results"] = [metric_case("dev_001"), metric_case("dev_001")]
        with self.assertRaisesRegex(
            ContractError,
            r"case_results\.1\.case_id:.*unique",
        ):
            validate_contract("metrics.schema.json", payload)

    def test_contracts_recursively_reject_non_finite_numbers(self) -> None:
        for label, non_finite in (
            ("nan", float("nan")),
            ("positive_infinity", float("inf")),
            ("negative_infinity", float("-inf")),
        ):
            payloads: list[tuple[str, dict[str, object], str]] = []

            manifest = minimal_manifest()
            manifest["cases"][0]["redistributable"] = non_finite
            payloads.append(
                ("benchmark_manifest.schema.json", manifest, "cases.0.redistributable")
            )

            annotation = minimal_annotation()
            annotation["expected_observations"][0]["location"]["region"] = {
                "x": non_finite,
                "y": 0,
                "width": 0.5,
                "height": 0.5,
                "coordinate_space": "normalized_0_1",
            }
            payloads.append(
                (
                    "annotation.schema.json",
                    annotation,
                    "expected_observations.0.location.region.x",
                )
            )

            observation = minimal_observation()
            observation["observations"][0]["confidence"] = non_finite
            payloads.append(
                ("observation.schema.json", observation, "observations.0.confidence")
            )

            run_result = minimal_run_result()
            run_result["telemetry"]["elapsed_seconds"] = non_finite
            payloads.append(
                ("run_result.schema.json", run_result, "telemetry.elapsed_seconds")
            )

            metrics = minimal_metrics()
            metrics["performance"]["wall_time_seconds"]["values"][0] = non_finite
            payloads.append(
                (
                    "metrics.schema.json",
                    metrics,
                    "performance.wall_time_seconds.values.0",
                )
            )

            for schema_name, payload, path in payloads:
                with self.subTest(value=label, schema=schema_name):
                    with self.assertRaisesRegex(
                        ContractError,
                        rf"{re.escape(path)}:.*finite",
                    ):
                        validate_contract(schema_name, payload)

    def test_numeric_preflight_handles_huge_ints_and_decimals_without_crashing(self) -> None:
        huge_integer = 10**10000
        metrics = minimal_metrics()
        metrics["run_count"] = huge_integer
        validate_contract("metrics.schema.json", metrics)

        observation = minimal_observation()
        observation["observations"][0]["confidence"] = huge_integer
        with self.assertRaisesRegex(
            ContractError,
            r"observations\.0\.confidence:.*numeric",
        ):
            validate_contract("observation.schema.json", observation)

        for value in (Decimal("NaN"), Decimal("Infinity"), Decimal("-Infinity")):
            with self.subTest(value=str(value)):
                run_result = minimal_run_result()
                run_result["telemetry"]["elapsed_seconds"] = value
                with self.assertRaisesRegex(
                    ContractError,
                    r"telemetry\.elapsed_seconds:.*finite",
                ):
                    validate_contract("run_result.schema.json", run_result)

        run_result = minimal_run_result()
        run_result["telemetry"]["elapsed_seconds"] = Decimal("1.25")
        validate_contract("run_result.schema.json", run_result)

        annotation = minimal_annotation()
        annotation["expected_observations"][0]["location"]["region"] = {
            "x": Decimal("0.25"),
            "y": 0,
            "width": 0.5,
            "height": 0.5,
            "coordinate_space": "normalized_0_1",
        }
        validate_contract("annotation.schema.json", annotation)

    def test_metric_case_status_uses_run_result_status_enum(self) -> None:
        run_schema = load_schema("run_result.schema.json")
        metrics_schema = load_schema("metrics.schema.json")
        run_statuses = run_schema["properties"]["status"]["enum"]
        metric_statuses = metrics_schema["$defs"]["caseResult"]["properties"]["status"][
            "enum"
        ]
        self.assertEqual(metric_statuses, run_statuses)

        payload = minimal_metrics()
        payload["case_results"] = [metric_case("dev_001", status="unknown")]
        with self.assertRaises(ContractError):
            validate_contract("metrics.schema.json", payload)

    def test_metric_fraction_semantics(self) -> None:
        invalid_fractions = (
            {"numerator": 2, "denominator": 1, "value": 1.0},
            {"numerator": 0, "denominator": 0, "value": 0.0},
            {"numerator": 1, "denominator": 3, "value": 0.5},
        )
        for index, fraction in enumerate(invalid_fractions):
            with self.subTest(fraction=index):
                payload = minimal_metrics()
                payload["detection"]["expected_finding_recall"] = fraction
                with self.assertRaises(ContractError):
                    validate_contract("metrics.schema.json", payload)

        payload = minimal_metrics()
        payload["detection"]["expected_finding_recall"] = {
            "numerator": 1,
            "denominator": 3,
            "value": (1 / 3) + 1e-12,
        }
        validate_contract("metrics.schema.json", payload)

        payload["detection"]["expected_finding_recall"] = {
            "numerator": 0,
            "denominator": 0,
            "value": None,
        }
        validate_contract("metrics.schema.json", payload)

    def test_metric_count_summary_total_matches_parts(self) -> None:
        payload = minimal_metrics()
        payload["detection"]["regression_assertions"] = {
            "met": 2,
            "not_met": 1,
            "total": 4,
        }
        with self.assertRaisesRegex(ContractError, r"regression_assertions\.total"):
            validate_contract("metrics.schema.json", payload)

        payload["detection"]["regression_assertions"]["total"] = 3
        validate_contract("metrics.schema.json", payload)

    def test_percentile_summary_semantics(self) -> None:
        invalid_summaries = (
            {"count": 2, "p50": 2.0, "p95": 1.0, "values": [1.0, 2.0]},
            {"count": 2, "p50": 1.0, "p95": 1.0, "values": [1.0]},
            {"count": 0, "p50": 0.0, "p95": 0.0, "values": []},
            {"count": 4, "p50": 2.5, "p95": 4.0, "values": [4.0, 1.0, 3.0, 2.0]},
            {"count": 4, "p50": 2.0, "p95": 3.5, "values": [4.0, 1.0, 3.0, 2.0]},
        )
        for index, summary in enumerate(invalid_summaries):
            with self.subTest(summary=index):
                payload = minimal_metrics()
                payload["performance"]["wall_time_seconds"] = summary
                with self.assertRaises(ContractError):
                    validate_contract("metrics.schema.json", payload)

        payload = minimal_metrics()
        payload["performance"]["wall_time_seconds"] = {
            "count": 0,
            "p50": None,
            "p95": None,
            "values": [],
        }
        validate_contract("metrics.schema.json", payload)

        payload["performance"]["wall_time_seconds"] = {
            "count": 4,
            "p50": 2.0 + 1e-12,
            "p95": 4.0,
            "values": [4.0, 1.0, 3.0, 2.0],
        }
        validate_contract("metrics.schema.json", payload)

    def test_schema_filename_resolution_is_safe(self) -> None:
        for name in (
            "../annotation.schema.json",
            "schemas/annotation.schema.json",
            "/tmp/annotation.schema.json",
            "Annotation.schema.json",
            "missing.schema.json",
        ):
            with self.subTest(name=name):
                with self.assertRaisesRegex(ContractError, "Unknown BRIA-Bench schema"):
                    load_schema(name)

    def test_validation_error_identifies_nested_payload_path(self) -> None:
        payload = minimal_manifest()
        payload["cases"][0]["track"] = "unknown"
        with self.assertRaisesRegex(
            ContractError,
            r"benchmark_manifest\.schema\.json:cases\.0\.track:",
        ):
            validate_contract("benchmark_manifest.schema.json", payload)


class BriaBenchRegistryTests(unittest.TestCase):
    def setUp(self) -> None:
        self._temporary = tempfile.TemporaryDirectory()
        self.root = Path(os.path.realpath(self._temporary.name))
        (self.root / "cases" / "dev_001").mkdir(parents=True)
        (self.root / "cases" / "dev_001" / "payload.bin").write_bytes(b"alpha")
        (self.root / "annotations" / "dev").mkdir(parents=True)
        (self.root / "annotations" / "dev" / "dev_001.json").write_text(
            "not JSON and intentionally not parsed",
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        self._temporary.cleanup()

    def manifest(self, *, cases: list[dict[str, object]] | None = None) -> dict[str, object]:
        payload = minimal_manifest()
        payload["cases"] = cases or payload["cases"]
        return payload

    def case(self, case_id: str = "dev_001") -> dict[str, object]:
        return {
            "case_id": case_id,
            "track": "blinded_challenge",
            "split": "dev",
            "package_path": "cases/dev_001",
            "annotation_path": "annotations/dev/dev_001.json",
            "mode": "internal_presubmission",
            "scan_profile": "quick",
            "redistributable": True,
            "license": "CC0-1.0",
        }

    def write_manifest(self, name: str, payload: dict[str, object]) -> Path:
        path = self.root / name
        path.write_text(json.dumps(payload), encoding="utf-8")
        return path

    def require_secure_hashing(self) -> None:
        if not hashing_module.secure_hashing_supported():
            self.skipTest("secure descriptor-relative hashing primitives are unavailable")

    def test_secure_hashing_capability_gate_fails_closed(self) -> None:
        with patch.object(hashing_module, "_SECURE_HASHING_SUPPORTED", False):
            self.assertFalse(hashing_module.secure_hashing_supported())
            with self.assertRaisesRegex(HashingError, "requires POSIX"):
                hash_tree(self.root / "cases" / "dev_001")

    def test_tree_hash_is_stable_content_sensitive_and_root_name_independent(self) -> None:
        self.require_secure_hashing()
        left = self.root / "left-name"
        right = self.root / "right-name"
        for package in (left, right):
            (package / "nested").mkdir(parents=True)
            (package / "b.txt").write_bytes(b"beta\n")
            (package / "nested" / "a.txt").write_bytes(b"alpha\n")
        (left / "empty-only").mkdir()

        first = hash_tree(left)
        self.assertEqual(first, hash_tree(left))
        self.assertEqual(first, hash_tree(right))
        (left / "nested" / "a.txt").write_bytes(b"changed\n")
        self.assertNotEqual(first, hash_tree(left))

    def test_tree_hash_rejects_root_and_nested_symlinks(self) -> None:
        self.require_secure_hashing()
        outside_file = self.root / "outside.txt"
        outside_file.write_bytes(b"outside")
        outside_dir = self.root / "outside-dir"
        outside_dir.mkdir()
        (outside_dir / "payload").write_bytes(b"outside")

        for name, target in (
            ("file-link", outside_file),
            ("directory-link", outside_dir),
            ("broken-link", self.root / "missing-target"),
        ):
            with self.subTest(name=name):
                package = self.root / name
                package.mkdir()
                try:
                    (package / "link").symlink_to(target)
                except (NotImplementedError, OSError) as exc:
                    self.skipTest(f"symlink creation unavailable: {exc}")
                with self.assertRaises(HashingError):
                    hash_tree(package)

        root_link = self.root / "root-link"
        try:
            root_link.symlink_to(self.root / "cases" / "dev_001", target_is_directory=True)
        except (NotImplementedError, OSError) as exc:
            self.skipTest(f"symlink creation unavailable: {exc}")
        with self.assertRaises(HashingError):
            hash_tree(root_link)

    def test_tree_hash_rejects_same_size_replacement_before_open(self) -> None:
        self.require_secure_hashing()
        payload = self.root / "cases" / "dev_001" / "payload.bin"
        replacement = self.root / "replacement-before-open.bin"
        replacement.write_bytes(b"bravo")
        real_open = hashing_module.os.open

        def replace_before_open(
            path: str | os.PathLike[str],
            flags: int,
            *,
            dir_fd: int | None = None,
        ) -> int:
            if path == payload.name:
                os.replace(replacement, payload)
            return real_open(path, flags, dir_fd=dir_fd)

        with patch.object(hashing_module.os, "open", side_effect=replace_before_open):
            with self.assertRaisesRegex(HashingError, "changed"):
                hash_tree(self.root / "cases" / "dev_001")

    def test_hashing_rejects_symlinked_ancestor(self) -> None:
        self.require_secure_hashing()
        target = self.root / "ancestor-target"
        target.mkdir()
        (target / "package").mkdir()
        (target / "package" / "payload.bin").write_bytes(b"payload")
        (target / "annotation.json").write_text("sealed", encoding="utf-8")
        ancestor = self.root / "ancestor-link"
        try:
            ancestor.symlink_to(target, target_is_directory=True)
        except (NotImplementedError, OSError) as exc:
            self.skipTest(f"symlink creation unavailable: {exc}")

        with self.assertRaisesRegex(HashingError, "symlink|securely open|changed before open"):
            hash_tree(ancestor / "package")
        with self.assertRaisesRegex(HashingError, "symlink|securely open|changed before open"):
            hash_file(ancestor / "annotation.json")

    def test_hashing_rejects_ancestor_swap_between_stat_and_open(self) -> None:
        self.require_secure_hashing()
        ancestor = self.root / "swap-ancestor"
        (ancestor / "package").mkdir(parents=True)
        (ancestor / "package" / "payload.bin").write_bytes(b"old")
        replacement = self.root / "replacement-ancestor"
        (replacement / "package").mkdir(parents=True)
        (replacement / "package" / "payload.bin").write_bytes(b"new")
        moved = self.root / "moved-ancestor"
        real_open = hashing_module.os.open
        swapped = False

        def swap_before_component(path: str | os.PathLike[str], *args: object, **kwargs: object) -> int:
            nonlocal swapped
            if path == "swap-ancestor" and not swapped:
                os.rename(ancestor, moved)
                os.replace(replacement, ancestor)
                swapped = True
            return real_open(path, *args, **kwargs)

        with patch.object(hashing_module.os, "open", side_effect=swap_before_component):
            with self.assertRaisesRegex(HashingError, "swap-ancestor|changed"):
                hash_tree(ancestor / "package")

    def test_tree_hash_bounds_file_descriptors_under_lowered_limit(self) -> None:
        self.require_secure_hashing()
        try:
            import resource
        except ImportError:
            self.skipTest("resource module unavailable")
        package = self.root / "many-files"
        package.mkdir()
        for index in range(220):
            (package / f"file-{index:03d}.txt").write_bytes(str(index).encode("ascii"))
        original_soft, original_hard = resource.getrlimit(resource.RLIMIT_NOFILE)
        target = 128 if original_hard == resource.RLIM_INFINITY else min(128, original_hard)
        if target < 32:
            self.skipTest("file descriptor hard limit is too low")
        try:
            if original_soft > target:
                resource.setrlimit(resource.RLIMIT_NOFILE, (target, original_hard))
            hash_tree(package)
        except (OSError, ValueError) as exc:
            self.skipTest(f"unable to lower file descriptor limit: {exc}")
        finally:
            resource.setrlimit(resource.RLIMIT_NOFILE, (original_soft, original_hard))

    def test_tree_hash_rejects_same_size_in_place_mutation_after_streaming(self) -> None:
        self.require_secure_hashing()
        payload = self.root / "cases" / "dev_001" / "payload.bin"
        real_read = hashing_module.os.read
        mutated = False

        def mutate_after_first_read(descriptor: int, count: int) -> bytes:
            nonlocal mutated
            chunk = real_read(descriptor, count)
            if chunk and not mutated:
                mutated = True
                payload.write_bytes(b"bravo")
                current = os.lstat(payload)
                os.utime(
                    payload,
                    ns=(current.st_atime_ns, current.st_mtime_ns + 1),
                    follow_symlinks=False,
                )
            return chunk

        with patch.object(
            hashing_module.os,
            "read",
            side_effect=mutate_after_first_read,
        ):
            with self.assertRaisesRegex(HashingError, "changed"):
                hash_tree(self.root / "cases" / "dev_001")

    def test_tree_hash_rejects_same_size_replacement_after_close(self) -> None:
        self.require_secure_hashing()
        payload = self.root / "cases" / "dev_001" / "payload.bin"
        replacement = self.root / "replacement-after-close.bin"
        replacement.write_bytes(b"bravo")
        real_fstat = hashing_module.os.fstat
        calls = 0

        def replace_after_stream_fstat(descriptor: int) -> os.stat_result:
            nonlocal calls
            calls += 1
            result = real_fstat(descriptor)
            if calls == 2:
                os.replace(replacement, payload)
            return result

        with patch.object(
            hashing_module.os,
            "fstat",
            side_effect=replace_after_stream_fstat,
        ):
            with self.assertRaisesRegex(HashingError, "changed"):
                hash_tree(self.root / "cases" / "dev_001")

    def test_final_verification_rejects_file_replacement_after_hashing(self) -> None:
        self.require_secure_hashing()
        package = self.root / "cases" / "dev_001"
        payload = package / "payload.bin"
        replacement = self.root / "replacement-after-hash.bin"
        replacement.write_bytes(b"new!!")
        real_hash_file = hashing_module._hash_file_record

        def hash_then_replace(
            digest: object,
            record: object,
            file_fd: int,
            parent_fd: int,
        ) -> None:
            real_hash_file(digest, record, file_fd, parent_fd)
            os.replace(replacement, payload)

        with patch.object(hashing_module, "_hash_file_record", side_effect=hash_then_replace):
            with self.assertRaisesRegex(HashingError, "payload.bin"):
                hash_tree(package)

    def test_final_verification_rejects_nested_directory_path_replacement(self) -> None:
        self.require_secure_hashing()
        package = self.root / "cases" / "dev_001"
        nested = package / "nested-final"
        nested.mkdir()
        replacement = self.root / "replacement-nested-final"
        replacement.mkdir()
        real_list_names = hashing_module._list_names
        nested_list_calls = 0

        def enumerate_then_replace(fd: int, relative: str) -> tuple[str, ...]:
            nonlocal nested_list_calls
            names = real_list_names(fd, relative)
            if relative == "nested-final":
                nested_list_calls += 1
                if nested_list_calls == 3:
                    nested.rmdir()
                    os.replace(replacement, nested)
            return names

        with patch.object(
            hashing_module,
            "_list_names",
            side_effect=enumerate_then_replace,
        ):
            with self.assertRaisesRegex(HashingError, "nested-final"):
                hash_tree(package)

    def test_tree_hash_rejects_directory_entry_additions_and_deletions(self) -> None:
        self.require_secure_hashing()
        package = self.root / "cases" / "dev_001"
        root_identity = (os.stat(package).st_dev, os.stat(package).st_ino)
        real_listdir = hashing_module.os.listdir

        for change in ("addition", "deletion"):
            with self.subTest(change=change):
                calls = 0

                def changing_listdir(fd: int) -> list[str]:
                    nonlocal calls
                    names = list(real_listdir(fd))
                    identity = os.fstat(fd)
                    if (identity.st_dev, identity.st_ino) == root_identity:
                        calls += 1
                        if calls == 2:
                            if change == "addition":
                                names.append("appeared-during-traversal")
                            else:
                                names.remove("payload.bin")
                    return names

                with patch.object(hashing_module.os, "listdir", side_effect=changing_listdir):
                    with self.assertRaisesRegex(HashingError, "entries changed"):
                        hash_tree(package)

    def test_tree_hash_rejects_nested_directory_swap(self) -> None:
        self.require_secure_hashing()
        package = self.root / "cases" / "dev_001"
        nested = package / "nested-swap"
        nested.mkdir()
        replacement = self.root / "replacement-nested"
        replacement.mkdir()
        nested_identity = (os.stat(nested).st_dev, os.stat(nested).st_ino)
        real_listdir = hashing_module.os.listdir
        calls = 0

        def swap_nested(fd: int) -> list[str]:
            nonlocal calls
            names = list(real_listdir(fd))
            identity = os.fstat(fd)
            if (identity.st_dev, identity.st_ino) == nested_identity:
                calls += 1
                if calls == 2:
                    nested.rmdir()
                    os.replace(replacement, nested)
            return names

        with patch.object(hashing_module.os, "listdir", side_effect=swap_nested):
            with self.assertRaisesRegex(HashingError, "nested-swap"):
                hash_tree(package)

    def test_tree_hash_rejects_root_path_swap_after_traversal(self) -> None:
        self.require_secure_hashing()
        package = self.root / "swap-root"
        package.mkdir()
        replacement = self.root / "replacement-root"
        replacement.mkdir()
        real_listdir = hashing_module.os.listdir
        root_identity = (os.stat(package).st_dev, os.stat(package).st_ino)
        calls = 0

        def swap_root(fd: int) -> list[str]:
            nonlocal calls
            names = list(real_listdir(fd))
            identity = os.fstat(fd)
            if (identity.st_dev, identity.st_ino) == root_identity:
                calls += 1
                if calls == 2:
                    package.rmdir()
                    os.replace(replacement, package)
            return names

        with patch.object(hashing_module.os, "listdir", side_effect=swap_root):
            with self.assertRaisesRegex(HashingError, "swap-root"):
                hash_tree(package)

    def test_tree_hash_enforces_nfc_and_casefold_filename_policy(self) -> None:
        self.require_secure_hashing()
        package = self.root / "cases" / "dev_001"
        decomposed = "e\u0301.txt"
        (package / decomposed).write_text("decomposed", encoding="utf-8")
        if decomposed not in os.listdir(package):
            self.skipTest("filesystem normalizes filenames before hashing")
        with self.assertRaisesRegex(HashingError, "NFC-normalized"):
            hash_tree(package)

        collision = self.root / "casefold-collision"
        collision.mkdir()
        try:
            (collision / "A").write_text("A", encoding="utf-8")
            (collision / "a").write_text("a", encoding="utf-8")
        except OSError as exc:
            self.skipTest(f"filesystem does not support case-distinct names: {exc}")
        if set(os.listdir(collision)) != {"A", "a"}:
            self.skipTest("filesystem does not preserve case-distinct names")
        with self.assertRaisesRegex(HashingError, "casefold-collide"):
            hash_tree(collision)

    def test_resolver_rejects_empty_absolute_traversal_and_symlink_paths(self) -> None:
        outside = self.root / "outside"
        outside.mkdir()
        (outside / "package").mkdir()
        try:
            (self.root / "link").symlink_to(outside, target_is_directory=True)
        except (NotImplementedError, OSError) as exc:
            self.skipTest(f"symlink creation unavailable: {exc}")
        for value in ("", Path(""), Path("."), "/tmp/absolute", "../private", "link/package"):
            with self.subTest(value=value):
                with self.assertRaises(RegistryError):
                    resolve_inside(self.root, value)

    def test_resolver_requires_package_directory_and_annotation_file(self) -> None:
        case = self.case()
        package, annotation = resolve_case_paths(self.root, case)
        self.assertTrue(package.is_dir())
        self.assertTrue(annotation.is_file())

        missing_package = dict(case, package_path="cases/missing")
        with self.assertRaisesRegex(RegistryError, "package"):
            resolve_case_paths(self.root, missing_package)
        missing_annotation = dict(case, annotation_path="annotations/dev/missing.json")
        with self.assertRaisesRegex(RegistryError, "annotation"):
            resolve_case_paths(self.root, missing_annotation)

    def test_load_manifest_preserves_order_and_does_not_parse_annotation(self) -> None:
        source = self.write_manifest("source.json", self.manifest())
        loaded = load_manifest(source)
        self.assertEqual([item["case_id"] for item in loaded["cases"]], ["dev_001"])

    def test_load_manifest_rejects_duplicate_ids_and_enforces_frozen_metadata(self) -> None:
        first = self.case("first")
        second = self.case("second")
        duplicate = self.write_manifest(
            "duplicate.json",
            self.manifest(cases=[first, dict(first)]),
        )
        with self.assertRaises(RegistryError):
            load_manifest(duplicate)

        source = self.write_manifest("source.json", self.manifest(cases=[first, second]))
        with self.assertRaisesRegex(RegistryError, "frozen_at"):
            load_manifest(source, require_frozen=True)

        incomplete = self.manifest(cases=[first, second])
        incomplete["frozen_at"] = "2026-07-11T00:00:00Z"
        incomplete_path = self.write_manifest("incomplete.json", incomplete)
        with self.assertRaisesRegex(RegistryError, "expected_sha256"):
            load_manifest(incomplete_path, require_frozen=True)

        incomplete["cases"][0]["expected_sha256"] = "a" * 64
        incomplete_path.write_text(json.dumps(incomplete), encoding="utf-8")
        with self.assertRaisesRegex(RegistryError, "annotation_sha256"):
            load_manifest(incomplete_path, require_frozen=True)

        invalid_hash = self.manifest(cases=[first])
        invalid_hash["cases"][0]["expected_sha256"] = "A" * 64
        invalid_hash_path = self.write_manifest("invalid-hash.json", invalid_hash)
        with self.assertRaises(RegistryError):
            load_manifest(invalid_hash_path)

    def test_freeze_preserves_case_order_and_verifies_frozen_case(self) -> None:
        self.require_secure_hashing()
        first = self.case("first")
        second = self.case("second")
        second["package_path"] = "cases/dev_001"
        second["annotation_path"] = "annotations/dev/dev_001.json"
        source = self.write_manifest("source.json", self.manifest(cases=[first, second]))
        output = self.root / "frozen.json"
        freeze_manifest(source, output, "2026-07-11T00:00:00Z")

        frozen = load_manifest(output, require_frozen=True)
        self.assertEqual(
            [item["case_id"] for item in frozen["cases"]],
            ["first", "second"],
        )
        actual = verify_frozen_case(self.root, frozen["cases"][0])
        self.assertEqual(actual, frozen["cases"][0]["expected_sha256"])

        annotation = self.root / "annotations" / "dev" / "dev_001.json"
        annotation.write_text("changed annotation bytes", encoding="utf-8")
        with self.assertRaisesRegex(RegistryError, "annotation hash mismatch"):
            verify_frozen_case(self.root, frozen["cases"][0])

        mismatch = dict(frozen["cases"][0], expected_sha256="0" * 64)
        with self.assertRaisesRegex(RegistryError, "Case ID first.*expected.*actual"):
            verify_frozen_case(self.root, mismatch)

    def test_freeze_fsyncs_containing_directory_after_replace(self) -> None:
        self.require_secure_hashing()
        source = self.write_manifest("source.json", self.manifest())
        output = self.root / "frozen.json"
        with patch("benchmarks.bria_bench.registry._fsync_directory") as fsync_directory:
            freeze_manifest(source, output, "2026-07-11T00:00:00Z")
        fsync_directory.assert_called_once_with(output.parent)

    def test_directory_fsync_error_surfaces_and_restores_previous_output(self) -> None:
        self.require_secure_hashing()
        source = self.write_manifest("source.json", self.manifest())
        output = self.root / "frozen.json"
        output.write_text('{"status":"old"}\n', encoding="utf-8")
        before = output.read_bytes()
        with patch(
            "benchmarks.bria_bench.registry._fsync_directory",
            side_effect=OSError(5, "I/O error"),
        ):
            with self.assertRaisesRegex(RegistryError, "fsync manifest directory"):
                freeze_manifest(source, output, "2026-07-11T00:00:00Z")
        self.assertEqual(output.read_bytes(), before)
        self.assertEqual(list(self.root.glob(".frozen.json.*.bak")), [])

    def test_directory_fsync_restore_failure_preserves_and_reports_backup(self) -> None:
        self.require_secure_hashing()
        source = self.write_manifest("source.json", self.manifest())
        output = self.root / "frozen.json"
        output.write_text('{"status":"old"}\n', encoding="utf-8")
        real_replace = os.replace
        replace_sources: list[Path] = []

        def replace_then_fail_restore(source_path: str | os.PathLike[str], destination: str | os.PathLike[str]) -> None:
            replace_sources.append(Path(source_path))
            if len(replace_sources) == 1:
                real_replace(source_path, destination)
                return
            raise OSError("restore failed")

        with patch(
            "benchmarks.bria_bench.registry._fsync_directory",
            side_effect=OSError(5, "I/O error"),
        ), patch.object(
            os,
            "replace",
            side_effect=replace_then_fail_restore,
        ):
            with self.assertRaisesRegex(RegistryError, "restore previous output") as caught:
                freeze_manifest(source, output, "2026-07-11T00:00:00Z")

        backup = replace_sources[1]
        self.assertTrue(backup.exists())
        self.assertIn(str(backup), str(caught.exception))
        backup.unlink()

    def test_failed_freeze_serialization_and_replace_preserve_previous_output(self) -> None:
        self.require_secure_hashing()
        source = self.write_manifest("source.json", self.manifest())
        output = self.root / "frozen.json"
        output.write_text('{"status":"old"}\n', encoding="utf-8")
        before = output.read_text(encoding="utf-8")

        with patch("benchmarks.bria_bench.registry.json.dump", side_effect=TypeError("boom")):
            with self.assertRaises(TypeError):
                freeze_manifest(source, output, "2026-07-11T00:00:00Z")
        self.assertEqual(output.read_text(encoding="utf-8"), before)
        self.assertEqual(list(self.root.glob(".frozen.json.*.tmp")), [])

        with patch(
            "benchmarks.bria_bench.registry.os.replace",
            side_effect=OSError("replace failed"),
        ):
            with self.assertRaises(OSError):
                freeze_manifest(source, output, "2026-07-11T00:00:00Z")
        self.assertEqual(output.read_text(encoding="utf-8"), before)
        self.assertEqual(list(self.root.glob(".frozen.json.*.tmp")), [])

    def test_close_chain_attempts_all_descriptors_after_close_failure(self) -> None:
        attempted: list[int] = []

        def close_with_one_failure(descriptor: int) -> None:
            attempted.append(descriptor)
            if descriptor == 3:
                raise OSError("injected close failure")

        with patch.object(hashing_module.os, "close", side_effect=close_with_one_failure):
            with self.assertRaises(HashingError):
                hashing_module._close_chain([1, 2, 3], "test descriptor chain")
        self.assertEqual(attempted, [3, 2, 1])

    def test_load_frozen_checks_shape_only_and_verify_detects_stale_package(self) -> None:
        self.require_secure_hashing()
        source = self.write_manifest("source.json", self.manifest())
        output = self.root / "frozen.json"
        freeze_manifest(source, output, "2026-07-11T00:00:00Z")

        frozen = load_manifest(output, require_frozen=True)
        (self.root / "cases" / "dev_001" / "payload.bin").write_bytes(b"stale")
        loaded_again = load_manifest(output, require_frozen=True)
        self.assertEqual(loaded_again, frozen)
        with self.assertRaisesRegex(RegistryError, "package hash mismatch"):
            verify_frozen_case(self.root, loaded_again["cases"][0])

    def test_registry_error_preserves_case_and_underlying_path_context(self) -> None:
        case = self.case("context_case")
        case["package_path"] = "cases/missing"
        source = self.write_manifest("context.json", self.manifest(cases=[case]))
        with self.assertRaisesRegex(RegistryError, "context_case.*package"):
            load_manifest(source)

        case["expected_sha256"] = "a" * 64
        case["annotation_sha256"] = "b" * 64
        with self.assertRaisesRegex(RegistryError, "context_case.*package") as caught:
            verify_frozen_case(self.root, case)
        self.assertIsNotNone(caught.exception.__cause__)


class BriaBenchRuntimeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path(tempfile.mkdtemp(prefix="bria-runtime-"))
        self.addCleanup(lambda: __import__("shutil").rmtree(self.root, ignore_errors=True))

    @staticmethod
    def python_command(source: str) -> list[str]:
        return [sys.executable, "-c", source]

    def run_python(
        self,
        source: str,
        *,
        timeout_seconds: float = 5.0,
        tail_bytes: int = 4096,
        poll_interval_seconds: float = 0.01,
    ) -> RuntimeResult:
        return run_monitored(
            self.python_command(source),
            self.root,
            timeout_seconds,
            tail_bytes=tail_bytes,
            poll_interval_seconds=poll_interval_seconds,
        )

    def test_success_captures_bounded_stdout_and_stderr_tails(self) -> None:
        result = self.run_python(
            "import os; os.write(1, b'out-' + b'A' * 200); os.write(2, b'err-' + b'B' * 200)",
            tail_bytes=17,
        )

        self.assertEqual(result.status, "success")
        self.assertEqual(result.returncode, 0)
        self.assertFalse(result.timed_out)
        self.assertEqual(result.stdout_tail, "A" * 17)
        self.assertEqual(result.stderr_tail, "B" * 17)
        self.assertGreater(result.elapsed_seconds, 0.0)
        self.assertGreaterEqual(result.cpu_seconds, 0.0)
        self.assertGreaterEqual(result.peak_rss_bytes, 0)
        self.assertTrue(result.cleanup_complete)
        self.assertEqual(result.cleanup_errors, ())
        self.assertEqual(result.to_dict()["status"], "success")
        self.assertEqual(result.to_dict()["cleanup_errors"], [])

    def test_nonzero_exit_is_process_error(self) -> None:
        result = self.run_python("import sys; sys.stderr.write('failed'); sys.exit(7)")

        self.assertEqual(result.status, "process_error")
        self.assertEqual(result.returncode, 7)
        self.assertIn("failed", result.stderr_tail)
        self.assertFalse(result.timed_out)

    def test_spawn_os_error_is_returned_as_process_error_data(self) -> None:
        with patch.object(runtime_module.subprocess, "Popen", side_effect=OSError("spawn failed")):
            result = run_monitored(["does-not-matter"], self.root, 1.0)

        self.assertEqual(result.status, "process_error")
        self.assertIsNone(result.returncode)
        self.assertIn("spawn failed", result.stderr_tail)
        self.assertFalse(result.timed_out)

    def test_huge_output_does_not_deadlock_and_tails_remain_bounded(self) -> None:
        source = (
            "import os\n"
            "for _ in range(64):\n"
            "    os.write(1, b'o' * 65536)\n"
            "    os.write(2, b'e' * 65536)\n"
        )
        result = self.run_python(source, timeout_seconds=8.0, tail_bytes=128)

        self.assertEqual(result.status, "success")
        self.assertLessEqual(len(result.stdout_tail.encode()), 128)
        self.assertLessEqual(len(result.stderr_tail.encode()), 128)
        self.assertEqual(result.stdout_tail, "o" * 128)
        self.assertEqual(result.stderr_tail, "e" * 128)

    @unittest.skipUnless(os.name == "posix", "process identity tests require POSIX")
    def test_child_rss_contributes_to_peak(self) -> None:
        child_code = (
            "import time\n"
            "buf = bytearray(48 * 1024 * 1024)\n"
            "for offset in range(0, len(buf), 4096):\n"
            "    buf[offset] = 1\n"
            "time.sleep(1.2)"
        )
        source = (
            "import subprocess, sys, time\n"
            f"child = subprocess.Popen([sys.executable, '-c', {child_code!r}])\n"
            "child.wait()\n"
            "raise SystemExit(child.returncode)\n"
        )
        result = self.run_python(source, timeout_seconds=5.0)

        self.assertEqual(result.status, "success")
        self.assertEqual(result.returncode, 0)
        self.assertFalse(result.timed_out)
        self.assertGreater(result.peak_rss_bytes, 24 * 1024 * 1024)

    @unittest.skipUnless(os.name == "posix", "process identity tests require POSIX")
    def test_child_cpu_contributes(self) -> None:
        child_code = (
            "import time; end = time.monotonic() + 0.7; x = 0\n"
            "while time.monotonic() < end: x += 1"
        )
        source = (
            "import subprocess, sys\n"
            f"child = subprocess.Popen([sys.executable, '-c', {child_code!r}])\n"
            "child.wait()\n"
        )
        result = self.run_python(source, timeout_seconds=5.0)

        self.assertEqual(result.status, "success")
        self.assertGreater(result.cpu_seconds, 0.15)

    @unittest.skipUnless(os.name == "posix", "signal tests require POSIX")
    def test_timeout_kills_term_ignoring_descendant(self) -> None:
        child_code = (
            "import os, signal, time; signal.signal(signal.SIGTERM, signal.SIG_IGN); "
            "print('child|' + str(os.getpid()) + '|' + "
            "str(__import__('psutil').Process().create_time()), flush=True); time.sleep(30)"
        )
        source = (
            "import os, signal, subprocess, sys, time\n"
            f"child = subprocess.Popen([sys.executable, '-c', {child_code!r}])\n"
            "print('parent|' + str(child.pid) + '|' + str(__import__('psutil').Process(child.pid).create_time()), flush=True)\n"
            "def on_term(signum, frame): child.wait()\n"
            "signal.signal(signal.SIGTERM, on_term)\n"
            "while True: time.sleep(1)\n"
        )
        result = self.run_python(source, timeout_seconds=0.2, tail_bytes=512)

        self.assertEqual(result.status, "timeout")
        self.assertTrue(result.timed_out)
        identity_lines = [line for line in result.stdout_tail.splitlines() if line.startswith("child|")]
        self.assertTrue(identity_lines)
        _, pid_text, create_time_text = identity_lines[0].split("|", 2)
        pid = int(pid_text)
        create_time = float(create_time_text)

        deadline = time.monotonic() + 2.0
        while time.monotonic() < deadline:
            try:
                process = runtime_module.psutil.Process(pid)
                same_identity = process.create_time() == create_time
                if not same_identity or not process.is_running():
                    break
            except runtime_module.psutil.NoSuchProcess:
                break
            time.sleep(0.02)
        else:
            self.fail("term-ignoring descendant still exists with the recorded identity")

    @unittest.skipUnless(os.name == "posix", "process group tests require POSIX")
    def test_root_exit_waits_for_and_kills_term_ignoring_descendant(self) -> None:
        child_code = (
            "import os, signal, time; signal.signal(signal.SIGTERM, signal.SIG_IGN); "
            "print('child|' + str(os.getpid()) + '|' + "
            "str(__import__('psutil').Process().create_time()), flush=True); time.sleep(30)"
        )
        source = (
            "import subprocess, sys\n"
            f"child = subprocess.Popen([sys.executable, '-c', {child_code!r}])\n"
            "print('parent|' + str(child.pid), flush=True)\n"
            "raise SystemExit(0)\n"
        )
        result = self.run_python(source, timeout_seconds=0.3, tail_bytes=512)

        self.assertEqual(result.status, "timeout")
        self.assertEqual(result.returncode, 0)
        self.assertTrue(result.timed_out)
        self.assertTrue(result.cleanup_complete)
        self.assertEqual(result.cleanup_errors, ())
        child_line = next(line for line in result.stdout_tail.splitlines() if line.startswith("child|"))
        _, pid_text, create_time_text = child_line.split("|", 2)
        self.assert_identity_gone(int(pid_text), float(create_time_text))

    @unittest.skipUnless(os.name == "posix", "process group tests require POSIX")
    def test_startup_identity_race_still_tracks_and_cleans_child(self) -> None:
        child_code = "import signal, time; signal.signal(signal.SIGTERM, signal.SIG_IGN); time.sleep(30)"
        source = (
            "import subprocess, sys\n"
            f"child = subprocess.Popen([sys.executable, '-c', {child_code!r}])\n"
            "print('child|' + str(child.pid) + '|' + str(__import__('psutil').Process(child.pid).create_time()), flush=True)\n"
            "raise SystemExit(0)\n"
        )
        original_identity = runtime_module._identity
        identity_calls = 0

        def fail_initial_identity(process: object) -> tuple[int, float] | None:
            nonlocal identity_calls
            identity_calls += 1
            if identity_calls == 1:
                return None
            return original_identity(process)  # type: ignore[arg-type]

        result: RuntimeResult | None = None
        forced_identity: tuple[int, float] | None = None
        try:
            with patch.object(runtime_module, "_identity", side_effect=fail_initial_identity):
                result = self.run_python(source, timeout_seconds=0.3, tail_bytes=512)

            self.assertGreaterEqual(identity_calls, 2)
            self.assertEqual(result.status, "timeout")
            self.assertTrue(result.timed_out)
            self.assertTrue(result.cleanup_complete)
            self.assertEqual(result.cleanup_errors, ())
            child_line = next(line for line in result.stdout_tail.splitlines() if line.startswith("child|"))
            _, pid_text, create_time_text = child_line.split("|", 2)
            forced_identity = (int(pid_text), float(create_time_text))
            self.assert_identity_gone(*forced_identity)
        finally:
            if result is not None and forced_identity is None:
                for line in result.stdout_tail.splitlines():
                    parts = line.split("|")
                    if len(parts) != 3 or parts[0] != "child":
                        continue
                    try:
                        forced_identity = (int(parts[1]), float(parts[2]))
                    except ValueError:
                        continue
                    break
            if forced_identity is not None:
                pid, create_time = forced_identity
                try:
                    process = runtime_module.psutil.Process(pid)
                    if process.create_time() == create_time:
                        os.kill(pid, signal.SIGKILL)
                except (OSError, runtime_module.psutil.Error):
                    pass
                self.assert_identity_gone(pid, create_time)

    def run_with_discovery_failure(self, process_iter: object) -> None:
        marker = self.root / "discovery-identities.txt"
        child_code = "import signal, time; signal.signal(signal.SIGTERM, signal.SIG_IGN); time.sleep(30)"
        source = (
            "import os, subprocess, sys\n"
            f"child = subprocess.Popen([sys.executable, '-c', {child_code!r}])\n"
            "identities = (f'child|{child.pid}|{__import__(\"psutil\").Process(child.pid).create_time()}\\n' "
            "f'root|{os.getpid()}|{__import__(\"psutil\").Process().create_time()}\\n')\n"
            f"with open({str(marker)!r}, 'w', encoding='utf-8') as handle: handle.write(identities)\n"
            "print(identities, end='', flush=True)\n"
            "raise SystemExit(0)\n"
        )
        result: RuntimeResult | None = None
        identities: list[tuple[int, float]] = []
        try:
            with patch.object(runtime_module.psutil, "process_iter", side_effect=process_iter):
                result = self.run_python(source, timeout_seconds=0.3, tail_bytes=1024)

            self.assertEqual(result.status, "timeout")
            self.assertTrue(result.timed_out)
            self.assertFalse(result.cleanup_complete)
            self.assertTrue(
                any("discovery/verification incomplete" in error for error in result.cleanup_errors)
            )
            self.assertEqual(len(result.cleanup_errors), len(set(result.cleanup_errors)))
        finally:
            if marker.exists():
                for line in marker.read_text(encoding="utf-8").splitlines():
                    parts = line.split("|")
                    if len(parts) != 3:
                        continue
                    try:
                        identities.append((int(parts[1]), float(parts[2])))
                    except ValueError:
                        pass
            if result is not None:
                for line in result.stdout_tail.splitlines():
                    parts = line.split("|")
                    if len(parts) != 3:
                        continue
                    try:
                        identity = (int(parts[1]), float(parts[2]))
                    except ValueError:
                        continue
                    if identity not in identities:
                        identities.append(identity)
            for pid, create_time in identities:
                try:
                    process = runtime_module.psutil.Process(pid)
                    if process.create_time() == create_time:
                        os.kill(pid, signal.SIGKILL)
                except (OSError, runtime_module.psutil.Error):
                    pass
                self.assert_identity_gone(pid, create_time)

    @unittest.skipUnless(os.name == "posix", "process group tests require POSIX")
    def test_process_iter_access_denied_is_disclosed_and_group_is_cleaned(self) -> None:
        def denied_process_iter() -> object:
            raise runtime_module.psutil.AccessDenied(pid=os.getpid())

        self.run_with_discovery_failure(denied_process_iter)

    @unittest.skipUnless(os.name == "posix", "process group tests require POSIX")
    def test_process_iter_generator_access_denied_is_disclosed_and_group_is_cleaned(self) -> None:
        def late_denied_process_iter() -> object:
            if False:
                yield None
            raise runtime_module.psutil.AccessDenied(pid=os.getpid())

        self.run_with_discovery_failure(late_denied_process_iter)

    @unittest.skipUnless(os.name == "posix", "process group tests require POSIX")
    def test_root_exit_waits_for_finite_descendant(self) -> None:
        child_code = "import time; time.sleep(0.35)"
        source = (
            "import subprocess, sys\n"
            f"child = subprocess.Popen([sys.executable, '-c', {child_code!r}])\n"
            "raise SystemExit(0)\n"
        )
        result = self.run_python(source, timeout_seconds=2.0)

        self.assertEqual(result.status, "success")
        self.assertEqual(result.returncode, 0)
        self.assertFalse(result.timed_out)
        self.assertTrue(result.cleanup_complete)
        self.assertGreater(result.elapsed_seconds, 0.25)

    @unittest.skipUnless(os.name == "posix", "process group tests require POSIX")
    def test_nonzero_root_waits_for_finite_descendant_without_leaking(self) -> None:
        child_code = "import time; time.sleep(0.35)"
        source = (
            "import subprocess, sys\n"
            f"child = subprocess.Popen([sys.executable, '-c', {child_code!r}])\n"
            "raise SystemExit(7)\n"
        )
        result = self.run_python(source, timeout_seconds=2.0)

        self.assertEqual(result.status, "process_error")
        self.assertEqual(result.returncode, 7)
        self.assertFalse(result.timed_out)
        self.assertTrue(result.cleanup_complete)
        self.assertGreater(result.elapsed_seconds, 0.25)

    @unittest.skipUnless(os.name == "posix", "process group tests require POSIX")
    def test_cleanup_signal_failure_is_disclosed_and_fixture_is_force_cleaned(self) -> None:
        child_code = (
            "import os, signal, time; signal.signal(signal.SIGTERM, signal.SIG_IGN); "
            "print('child|' + str(os.getpid()) + '|' + "
            "str(__import__('psutil').Process().create_time()), flush=True); time.sleep(30)"
        )
        source = (
            "import os, signal, subprocess, sys, time\n"
            f"child = subprocess.Popen([sys.executable, '-c', {child_code!r}])\n"
            "print('parent|' + str(os.getpid()) + '|' + str(__import__('psutil').Process().create_time()), flush=True)\n"
            "signal.signal(signal.SIGTERM, signal.SIG_IGN)\n"
            "time.sleep(2.0)\n"
        )
        result: RuntimeResult | None = None
        forced_identities: list[tuple[int, float]] = []
        try:
            with patch.object(
                runtime_module,
                "_signal_process_group",
                return_value="injected process-group signal failure",
            ), patch.object(
                runtime_module,
                "_signal_identity",
                return_value="injected identity signal failure",
            ):
                result = self.run_python(source, timeout_seconds=0.2, tail_bytes=512)

            self.assertEqual(result.status, "timeout")
            self.assertFalse(result.cleanup_complete)
            self.assertTrue(result.cleanup_errors)
            self.assertTrue(
                any("injected process-group signal failure" in error for error in result.cleanup_errors)
            )
            self.assertTrue(any("surviv" in error for error in result.cleanup_errors))
        finally:
            if result is not None:
                for line in result.stdout_tail.splitlines():
                    parts = line.split("|")
                    if len(parts) != 3:
                        continue
                    try:
                        pid = int(parts[1])
                        create_time = float(parts[2])
                        process = runtime_module.psutil.Process(pid)
                        if process.create_time() == create_time:
                            forced_identities.append((pid, create_time))
                            os.kill(pid, signal.SIGKILL)
                    except (ValueError, OSError, runtime_module.psutil.Error):
                        pass
            for pid, create_time in forced_identities:
                self.assert_identity_gone(pid, create_time)

    def test_packaging_declares_bria_bench_runtime_and_schema_data(self) -> None:
        project_root = Path(__file__).resolve().parents[1]
        with (project_root / "pyproject.toml").open("rb") as stream:
            config = tomllib.load(stream)
        setuptools = config["tool"]["setuptools"]
        self.assertIn("benchmarks.bria_bench", setuptools["packages"])
        self.assertEqual(
            setuptools["package-data"]["benchmarks.bria_bench"],
            ["schemas/*.json"],
        )

    def assert_identity_gone(self, pid: int, create_time: float) -> None:
        deadline = time.monotonic() + 2.0
        while time.monotonic() < deadline:
            try:
                process = runtime_module.psutil.Process(pid)
                if process.create_time() != create_time or not process.is_running():
                    return
            except runtime_module.psutil.NoSuchProcess:
                return
            time.sleep(0.02)
        self.fail(f"process {pid} still exists with the recorded identity")

    def test_invalid_configuration_raises_value_error(self) -> None:
        with self.assertRaises(ValueError):
            run_monitored([], self.root, 1.0)
        with self.assertRaises(ValueError):
            run_monitored(["true"], self.root, 0.0)
        with self.assertRaises(ValueError):
            run_monitored(["true"], self.root, float("nan"))
        with self.assertRaises(ValueError):
            run_monitored(["true"], self.root, 1.0, tail_bytes=0)
        with self.assertRaises(ValueError):
            run_monitored(["true"], self.root / "missing", 1.0)
        invalid_cwd = self.root / "file"
        invalid_cwd.write_text("not a directory", encoding="utf-8")
        with self.assertRaises(ValueError):
            run_monitored(["true"], invalid_cwd, 1.0)

    def test_write_json_atomic_preserves_previous_file_on_serialization_error(self) -> None:
        output = self.root / "result.json"
        output.write_text('{"old": true}\n', encoding="utf-8")

        with self.assertRaises(TypeError):
            write_json_atomic(output, {"bad": object()})

        self.assertEqual(output.read_text(encoding="utf-8"), '{"old": true}\n')
        self.assertEqual(list(self.root.glob(".result.json.*.tmp")), [])

    def test_write_json_atomic_creates_nested_output_directory(self) -> None:
        output = self.root / "nested" / "results" / "result.json"

        write_json_atomic(output, {"created": True})

        self.assertEqual(json.loads(output.read_text(encoding="utf-8")), {"created": True})
        self.assertEqual(list(output.parent.glob(".result.json.*.tmp")), [])

    def test_write_json_atomic_serialization_error_does_not_create_parent(self) -> None:
        output = self.root / "nested" / "results" / "result.json"

        with self.assertRaises(TypeError):
            write_json_atomic(output, {"bad": object()})

        self.assertFalse(output.parent.exists())

    def test_write_json_atomic_preserves_previous_file_on_replace_error(self) -> None:
        output = self.root / "result.json"
        output.write_text('{"old": true}\n', encoding="utf-8")

        with patch.object(runtime_module.os, "replace", side_effect=OSError("replace failed")):
            with self.assertRaises(OSError):
                write_json_atomic(output, {"new": True})

        self.assertEqual(output.read_text(encoding="utf-8"), '{"old": true}\n')
        self.assertEqual(list(self.root.glob(".result.json.*.tmp")), [])

    def test_write_json_atomic_preserves_backup_when_fsync_restore_fails(self) -> None:
        output = self.root / "result.json"
        output.write_text('{"old": true}\n', encoding="utf-8")
        original_replace = runtime_module.os.replace
        replace_calls = 0

        def replace_with_restore_failure(source: Path, destination: Path) -> None:
            nonlocal replace_calls
            replace_calls += 1
            if replace_calls == 2:
                raise OSError("restore failed")
            original_replace(source, destination)

        try:
            with patch.object(
                runtime_module,
                "_fsync_directory",
                side_effect=OSError("fsync failed"),
            ), patch.object(
                runtime_module.os,
                "replace",
                side_effect=replace_with_restore_failure,
            ):
                with self.assertRaisesRegex(OSError, "backup preserved at") as caught:
                    write_json_atomic(output, {"new": True})

            backups = list(self.root.glob(".result.json.*.bak"))
            self.assertEqual(len(backups), 1)
            self.assertIn(str(backups[0]), str(caught.exception))
        finally:
            for backup in self.root.glob(".result.json.*.bak"):
                backup.unlink(missing_ok=True)


class BriaBenchNormalizationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.output_dir = Path(self.temp_dir.name) / "audit-output"
        self.output_dir.mkdir()
        self.package_dir = Path(self.temp_dir.name) / "package"
        self.package_dir.mkdir()
        self.staging_dir = Path(self.temp_dir.name) / ".audit.staging-test"
        self.staging_dir.mkdir()

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def write_fixture(
        self,
        *,
        findings: list[dict[str, object]] | None = None,
        coverage: dict[str, object] | None = None,
        pipeline: dict[str, object] | None = None,
        report: str | None = "This audit does not establish fraud and is not a misconduct verdict.",
    ) -> None:
        summary = {
            "audit_mode": "internal_presubmission",
            "case_id": "dev_001",
            "scan_profile": "standard",
            "execution_mode": "parallel",
            "materials_reviewed": ["manuscript.pdf", "source_data/Figure_1.xlsx"],
            "materials_missing": [],
            "overall_risk": "R2",
            "misconduct_verdict_present": False,
            "risk_caps_applied": ["Candidate evidence requires contextual review."],
            "positive_provenance": [],
            "traceability_gaps": [],
            "findings": findings or [],
        }
        default_coverage: dict[str, object] = {
            "modules_executed": ["statistics", "image.local_patch"],
            "modules_not_executed": [],
            "detector_failures": [],
            "audit_coverage_gap": False,
            "workstreams": [],
        }
        default_pipeline: dict[str, object] = {
            "package": str(self.package_dir),
            "output_dir": str(self.output_dir),
            "candidate_count": len(findings or []),
            "finding_count": len(findings or []),
            "workstreams": [],
        }
        (self.output_dir / "AUDIT_JSON_SUMMARY.json").write_text(
            json.dumps(summary, ensure_ascii=False), encoding="utf-8"
        )
        (self.output_dir / "coverage.json").write_text(
            json.dumps(coverage if coverage is not None else default_coverage),
            encoding="utf-8",
        )
        (self.output_dir / "pipeline_summary.json").write_text(
            json.dumps(pipeline if pipeline is not None else default_pipeline),
            encoding="utf-8",
        )
        if report is not None:
            (self.output_dir / "audit-report.md").write_text(report, encoding="utf-8")

    def test_statistics_finding_preserves_human_fields_and_exact_location(self) -> None:
        finding = {
            "finding_id": "F-STAT-1",
            "detector": "stats.consistency_check",
            "finding_type": "SD-SEM mismatch in reported numeric values",
            "location": "Figure_3.xlsx#Sheet1:control<->treated",
            "risk_level": "R2",
            "evidence_type": "numeric_consistency_candidate",
            "summary": "The whole-column additive shift warrants source-data review.",
            "recommended_action": "Re-run the source calculation.",
            "benign_explanations_considered": ["A transcription or rounding issue."],
            "required_materials_to_resolve": ["Original workbook and analysis code"],
        }
        self.write_fixture(findings=[finding])

        normalized = normalize_audit_output("dev_001", self.output_dir)

        observation = normalized["observations"][0]
        self.assertEqual(observation["issue_family"], "statistics_or_numeric")
        self.assertEqual(observation["location"], finding["location"])
        self.assertEqual(observation["source_finding_id"], "F-STAT-1")
        self.assertEqual(observation["source_detector"], "stats.consistency_check")
        self.assertEqual(observation["recommended_action"], finding["recommended_action"])

    def test_issue_family_routes_are_specific_before_generic(self) -> None:
        finding_types = [
            ("global image near-duplicate reuse cluster", "image_global_similarity"),
            ("local patch reuse", "image_local_reuse"),
            ("same-image copy-move candidate", "image_copy_move"),
            ("keypoint geometric image match", "image_keypoint_geometry"),
            ("splice JPEG ghost noise-CFA triage", "image_splice_forensics_triage"),
            ("OME channel metadata verification gap", "image_channel_metadata_gap"),
            ("pseudoreplication and digit statistics", "statistics_or_numeric"),
            ("package internal text overlap", "text_overlap"),
            ("methodology reporting readiness standard", "methodology_or_reporting"),
            ("unsupported material coverage completeness gap", "material_or_coverage_gap"),
            ("unrecognized reviewable concern", "other_reviewable_observation"),
        ]
        findings = [
            {
                "finding_id": f"F-{index:02d}",
                "detector": "detector.test",
                "finding_type": finding_type,
                "location": {"text": f"Figure {index + 1}A", "panel": "A"},
                "risk_level": "R1",
                "evidence_type": "candidate",
            }
            for index, (finding_type, _) in enumerate(finding_types)
        ]
        self.write_fixture(findings=findings)

        normalized = normalize_audit_output("dev_001", self.output_dir)

        actual = {
            item["finding_type"]: item["issue_family"]
            for item in normalized["observations"]
        }
        self.assertEqual(dict(finding_types), {key: actual[key] for key, _ in finding_types})

    def test_actual_producer_keys_route_before_detector_name_fuzziness(self) -> None:
        producer_findings = [
            {
                "finding_id": "F-GLOBAL",
                "detector": "image.local_patch_reuse",
                "candidate_type": "image_reuse_cluster",
                "finding_type": "whole-image similarity candidate",
                "contextual_tag": "cross_context",
                "risk_cap_tags": ["candidate_evidence"],
                "location": "Figure 1A",
                "risk_level": "R2",
                "evidence_type": "candidate",
            },
            {
                "finding_id": "F-COPY",
                "detector": "image.local_patch_reuse",
                "candidate_type": "same_image_copy_move",
                "finding_type": "local patch reuse detector result",
                "contextual_tag": "same_image_copy_move",
                "risk_cap_tags": ["same_image_copy_move"],
                "risk_caps_applied": ["missing source data cap: R1"],
                "location": "Figure 2B",
                "risk_level": "R2",
                "evidence_type": "candidate",
            },
            {
                "finding_id": "F-COVERAGE",
                "detector": "stats.consistency_check",
                "candidate_type": "audit_coverage_gap",
                "finding_type": "source data extraction gap",
                "location": "Figure_3.xlsx",
                "risk_level": "R1",
                "evidence_type": "audit_coverage_gap",
            },
            {
                "finding_id": "F-LITERATURE",
                "detector": "text.text_overlap_screen",
                "candidate_type": "external_literature_search_gap",
                "finding_type": "external search unavailable",
                "location": "Methods",
                "risk_level": "R1",
                "evidence_type": "coverage_gap",
            },
            {
                "finding_id": "F-SOURCE-ONLY",
                "detector": "image.global_near_duplicate",
                "candidate_type": "source data extraction gap",
                "location": "Figure_3.xlsx",
                "risk_level": "R1",
                "evidence_type": "coverage_gap",
            },
            {
                "finding_id": "F-RAW",
                "detector": "image.global_near_duplicate",
                "candidate_type": "unresolved_fig_raw_similarity",
                "finding_type": "unresolved figure to raw similarity",
                "location": "Figure 4C",
                "risk_level": "R1",
                "evidence_type": "traceability_gap",
            },
            {
                "finding_id": "F-UNREADABLE",
                "detector": "image.global_near_duplicate",
                "candidate_type": "unreadable_image_file",
                "finding_type": "image material unavailable",
                "location": "Figure 5A",
                "risk_level": "R1",
                "evidence_type": "coverage_gap",
            },
        ]
        self.write_fixture(findings=producer_findings)

        normalized = normalize_audit_output("dev_001", self.output_dir)

        families = {item["source_finding_id"]: item["issue_family"] for item in normalized["observations"]}
        self.assertEqual(families["F-GLOBAL"], "image_global_similarity")
        self.assertEqual(families["F-COPY"], "image_copy_move")
        for finding_id in ("F-COVERAGE", "F-LITERATURE", "F-SOURCE-ONLY", "F-RAW", "F-UNREADABLE"):
            self.assertEqual(families[finding_id], "material_or_coverage_gap")

    def test_current_detector_candidate_types_route_by_producer_family(self) -> None:
        candidate_families = {
            "audit_coverage_gap": "material_or_coverage_gap",
            "image_reuse_cluster": "image_global_similarity",
            "image_similarity_candidate": "image_global_similarity",
            "keypoint_geometric_match": "image_keypoint_geometry",
            "local_patch_reuse": "image_local_reuse",
            "same_image_copy_move": "image_copy_move",
            "splice_forensics_triage_signal": "image_splice_forensics_triage",
            "channel_metadata_verification_gap": "image_channel_metadata_gap",
            "pseudoreplication_candidate": "statistics_or_numeric",
            "weak_statistical_signal": "statistics_or_numeric",
            "statistical_consistency_candidate": "statistics_or_numeric",
            "text_overlap_candidate": "text_overlap",
            "methods_boilerplate_overlap": "text_overlap",
            "self_overlap_candidate": "text_overlap",
            "external_text_match_candidate": "text_overlap",
            "external_literature_search_gap": "material_or_coverage_gap",
        }
        findings = [
            {
                "finding_id": f"TYPE-{index:02d}",
                "detector": (
                    "text.text_overlap_screen"
                    if "text" in candidate_type or "overlap" in candidate_type
                    else "producer.detector"
                ),
                "candidate_type": candidate_type,
                "finding_type": candidate_type,
                "location": {"text": f"producer record {index + 1}"},
                "risk_level": "R1",
                "evidence_type": "candidate",
            }
            for index, candidate_type in enumerate(candidate_families)
        ]
        findings.extend(
            [
                {
                    "finding_id": "TYPE-TECHNICAL",
                    "detector": "image.local_patch",
                    "candidate_type": "detector_execution_failure",
                    "finding_type": "detector_execution_failure",
                    "location": "image.local_patch",
                    "risk_level": "R1",
                    "evidence_type": "technical_failure",
                },
                {
                    "finding_id": "TYPE-TRACEABILITY",
                    "detector": "contextual_joiner",
                    "candidate_type": "expected_traceability",
                    "finding_type": "expected_traceability",
                    "location": "Figure 1A",
                    "risk_level": "R1",
                    "evidence_type": "positive_provenance",
                },
            ]
        )
        self.write_fixture(findings=findings)

        normalized = normalize_audit_output("dev_001", self.output_dir)

        actual = {
            item["source_finding_id"]: item["issue_family"]
            for item in normalized["observations"]
        }
        for index, (candidate_type, expected_family) in enumerate(candidate_families.items()):
            self.assertEqual(actual[f"TYPE-{index:02d}"], expected_family)
        self.assertNotIn("TYPE-TECHNICAL", actual)
        self.assertNotIn("TYPE-TRACEABILITY", actual)
        self.assertTrue(
            any(item["module"] == "image.local_patch" for item in normalized["technical_failures"])
        )

    def test_explicit_domain_route_beats_risk_cap_prose(self) -> None:
        self.write_fixture(
            findings=[
                {
                    "finding_id": "F-COPY-RISK",
                    "candidate_type": "same_image_copy_move",
                    "finding_type": "copy move candidate",
                    "risk_caps_applied": ["missing source data cap: R1"],
                    "location": "Figure 6A",
                    "risk_level": "R2",
                    "evidence_type": "candidate",
                }
            ]
        )

        normalized = normalize_audit_output("dev_001", self.output_dir)

        self.assertEqual(normalized["observations"][0]["issue_family"], "image_copy_move")

    def test_technical_failures_are_separate_stable_and_deduplicated(self) -> None:
        coverage = {
            "detector_failures": [
                {"module": "image.local_patch", "failure_type": "timeout", "message": "timed out"},
                "image.local_patch: timeout",
            ],
            "audit_coverage_gap": True,
            "audit_coverage_gap_message": "The deep image screen was not completed.",
            "workstreams": [
                {"name": "image_integrity", "status": "failed", "errors": ["image.local_patch: timeout"]},
                {"name": "statistics", "status": "completed", "errors": []},
            ],
        }
        pipeline = {
            "package": str(self.package_dir),
            "workstreams": [
                {"name": "image_integrity", "status": "failed", "errors": ["image.local_patch: timeout"]}
            ],
            "producer_failures": [
                {"module": "report.assembler", "failure_type": "execution_failure", "message": "report failed"}
            ],
        }
        self.write_fixture(coverage=coverage, pipeline=pipeline)

        normalized = normalize_audit_output("dev_001", self.output_dir)

        failures = normalized["technical_failures"]
        identities = {(item["module"], item.get("failure_type")) for item in failures}
        self.assertIn(("image.local_patch", "timeout"), identities)
        self.assertIn(("audit.coverage", "audit_coverage_gap"), identities)
        self.assertIn(("report.assembler", "execution_failure"), identities)
        self.assertEqual(len(failures), len(identities))
        self.assertEqual(normalized["observations"], [])

    def test_bare_reported_flag_is_not_reported_until_module_failure_is_disclosed(self) -> None:
        coverage = {
            "detector_failures": [{"module": "image.local_patch", "reported": True}],
            "audit_coverage_gap": False,
        }
        self.write_fixture(coverage=coverage)
        undisclosed = normalize_audit_output("dev_001", self.output_dir)
        self.assertEqual(undisclosed["reported_technical_failures"], [])

        (self.output_dir / "audit-report.md").write_text(
            "The image.local_patch detector failed with a timeout.", encoding="utf-8"
        )
        disclosed = normalize_audit_output("dev_001", self.output_dir)
        self.assertEqual(len(disclosed["reported_technical_failures"]), 1)
        self.assertEqual(disclosed["reported_technical_failures"][0]["module"], "image.local_patch")

    def test_missing_and_malformed_required_artifacts_are_disclosed(self) -> None:
        self.write_fixture()
        (self.output_dir / "AUDIT_JSON_SUMMARY.json").write_text("{bad", encoding="utf-8")
        (self.output_dir / "coverage.json").unlink()
        (self.output_dir / "pipeline_summary.json").write_text("[]", encoding="utf-8")

        normalized = normalize_audit_output("dev_001", self.output_dir)
        errors = json.dumps(normalized["contract_errors"])
        failures = json.dumps(normalized["technical_failures"])
        for name in ("AUDIT_JSON_SUMMARY.json", "coverage.json", "pipeline_summary.json"):
            self.assertIn(name, errors)
            self.assertIn(name, failures)

    def test_missing_or_malformed_human_report_is_disclosed(self) -> None:
        self.write_fixture(report=None)

        missing = normalize_audit_output("dev_001", self.output_dir)
        self.assertTrue(any("audit-report.md" in item["message"] for item in missing["contract_errors"]))
        self.assertTrue(
            any(
                item["module"] == "report" and item["failure_type"] == "missing_artifact"
                for item in missing["technical_failures"]
            )
        )

        self.write_fixture()
        (self.output_dir / "audit-report.md").write_bytes(b"\xff\xfe")
        malformed = normalize_audit_output("dev_001", self.output_dir)
        self.assertTrue(any("audit-report.md" in item["message"] for item in malformed["contract_errors"]))
        self.assertTrue(
            any(
                item["module"] == "report" and item["failure_type"] == "malformed_artifact"
                for item in malformed["technical_failures"]
            )
        )

    def test_reported_failure_attribution_stays_within_clause(self) -> None:
        self.write_fixture(
            coverage={"detector_failures": [{"module": "image.local_patch"}]},
            pipeline={
                "package": str(self.package_dir),
                "producer_failures": ["report.assembler: execution_failure"],
            },
            report="image.local_patch completed; report.assembler failed.",
        )

        normalized = normalize_audit_output("dev_001", self.output_dir)

        reported_modules = {item["module"] for item in normalized["reported_technical_failures"]}
        self.assertNotIn("image.local_patch", reported_modules)
        self.assertIn("report.assembler", reported_modules)

    def test_failure_disclosure_uses_clause_polarity_for_generic_semantics(self) -> None:
        positive_reports = (
            "The image.local_patch detector failed to run.",
            "The image.local_patch detector timed out.",
            "The image.local_patch detector encountered an error.",
        )
        negative_reports = (
            "The image.local_patch detector completed without timeout or failure.",
            "The image.local_patch detector did not fail.",
            "No timeout occurred in image.local_patch.",
            "The image.local_patch detector completed successfully.",
        )
        for report in positive_reports:
            with self.subTest(report=report):
                self.write_fixture(
                    coverage={"detector_failures": [{"module": "image.local_patch", "failure_type": "timeout"}]},
                    report=report,
                )
                normalized = normalize_audit_output("dev_001", self.output_dir)
                self.assertEqual(len(normalized["reported_technical_failures"]), 1)
        for report in negative_reports:
            with self.subTest(report=report):
                self.write_fixture(
                    coverage={"detector_failures": [{"module": "image.local_patch", "failure_type": "timeout"}]},
                    report=report,
                )
                normalized = normalize_audit_output("dev_001", self.output_dir)
                self.assertEqual(normalized["reported_technical_failures"], [])

    def test_case_id_mismatch_quarantines_all_summary_findings(self) -> None:
        finding = {
            "finding_id": "FOREIGN-1",
            "finding_type": "numeric consistency candidate",
            "location": "Table 1",
            "risk_level": "R1",
            "evidence_type": "candidate",
        }
        self.write_fixture(findings=[finding])
        summary_path = self.output_dir / "AUDIT_JSON_SUMMARY.json"
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        summary["case_id"] = "other_case"
        summary_path.write_text(json.dumps(summary), encoding="utf-8")

        normalized = normalize_audit_output("dev_001", self.output_dir)

        self.assertEqual(normalized["observations"], [])
        self.assertTrue(any("case_id" in item["message"] for item in normalized["contract_errors"]))
        self.assertTrue(any(item["module"] == "producer" for item in normalized["technical_failures"]))

    def test_strict_json_duplicate_nonfinite_and_depth_bombs_are_visible(self) -> None:
        self.write_fixture()
        summary_path = self.output_dir / "AUDIT_JSON_SUMMARY.json"
        summary_path.write_text('{"findings": [], "findings": []}', encoding="utf-8")
        duplicate = normalize_audit_output("dev_001", self.output_dir)
        self.assertTrue(duplicate["contract_errors"])
        self.assertTrue(duplicate["technical_failures"])

        self.write_fixture()
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        summary["findings"] = [
            {
                "finding_id": "NONFINITE",
                "finding_type": "numeric consistency candidate",
                "location": "Table 1",
                "risk_level": "R1",
                "confidence": float("nan"),
                "evidence_type": "candidate",
            }
        ]
        summary_path.write_text(json.dumps(summary), encoding="utf-8")
        nonfinite = normalize_audit_output("dev_001", self.output_dir)
        self.assertEqual(nonfinite["observations"], [])
        self.assertTrue(nonfinite["contract_errors"])
        self.assertTrue(nonfinite["technical_failures"])

        self.write_fixture()
        deep_json = '{"findings": [], "deep": ' + ("{" * 1200) + "null" + ("}" * 1200) + "}"
        summary_path.write_text(deep_json, encoding="utf-8")
        deep = normalize_audit_output("dev_001", self.output_dir)
        self.assertTrue(deep["contract_errors"])
        self.assertTrue(deep["technical_failures"])

    def test_invalid_finding_isolated_from_valid_sibling(self) -> None:
        self.write_fixture(
            findings=[
                {
                    "finding_id": "BAD",
                    "finding_type": "numeric consistency candidate",
                    "location": {"page": 0},
                    "risk_level": "R1",
                    "confidence": 2.0,
                    "evidence_type": "candidate",
                },
                {
                    "finding_id": "GOOD",
                    "finding_type": "numeric consistency candidate",
                    "location": "Table 2",
                    "risk_level": "R1",
                    "evidence_type": "candidate",
                },
            ]
        )

        normalized = normalize_audit_output("dev_001", self.output_dir)

        self.assertEqual([item["source_finding_id"] for item in normalized["observations"]], ["GOOD"])
        self.assertTrue(any("findings[0]" in item.get("path", "") for item in normalized["contract_errors"]))
        self.assertTrue(any("findings[0]" in item.get("source", "") for item in normalized["technical_failures"]))

    def test_failure_event_identity_and_specific_report_semantics(self) -> None:
        self.write_fixture(
            coverage={
                "detector_failures": [
                    {"module": "image.local_patch", "failure_type": "timeout", "message": "timed out"},
                    {"module": "image.local_patch", "failure_type": "permission_error", "message": "permission denied"},
                ]
            },
            pipeline={
                "package": str(self.package_dir),
                "producer_failures": [
                    {"module": "image.local_patch", "failure_type": "timeout", "message": "timed out"}
                ],
            },
            report="The image.local_patch detector timed out.",
        )

        normalized = normalize_audit_output("dev_001", self.output_dir)

        self.assertEqual(len(normalized["technical_failures"]), 2)
        self.assertEqual(
            [item["failure_type"] for item in normalized["reported_technical_failures"]],
            ["timeout"],
        )

    def test_malformed_failure_entries_are_indexed_and_disclosed(self) -> None:
        self.write_fixture(
            coverage={
                "detector_failures": [None, [], 7, {"unexpected": "shape"}],
                "errors": {"not": "a list"},
            }
        )

        normalized = normalize_audit_output("dev_001", self.output_dir)

        error_paths = {item.get("path", "") for item in normalized["contract_errors"]}
        self.assertTrue(any("detector_failures[0]" in path for path in error_paths))
        self.assertTrue(any("detector_failures[1]" in path for path in error_paths))
        self.assertTrue(any("detector_failures[2]" in path for path in error_paths))
        self.assertTrue(any("errors" in path for path in error_paths))
        self.assertTrue(any(item["failure_type"] == "malformed_failure_entry" for item in normalized["technical_failures"]))

    def test_boundary_scanner_requires_assertion_shapes_and_handles_chinese_team_claims(self) -> None:
        self.write_fixture(
            report="\n".join(
                [
                    "Research team fabricated the data.",
                    "The researchers falsified data.",
                    "The study group committed fraud.",
                    "Data were fabricated and data were falsified.",
                    "No evidence of fraud.",
                    "We do not allege fraud.",
                    "An investigation into fraud is ongoing; this is an allegation only.",
                    "Integrity certificate generation failed because report assembler crashed.",
                    "研究团队造假。研究人员造假。课题组造假。数据被伪造，数据被篡改。",
                ]
            )
        )

        normalized = normalize_audit_output("dev_001", self.output_dir)
        messages = [item["message"] for item in normalized["boundary_violations"]]

        for included in ("Research team fabricated", "researchers falsified", "study group committed", "研究团队造假", "数据被伪造"):
            self.assertTrue(any(included in message for message in messages))
        for excluded in ("No evidence of fraud", "do not allege fraud", "investigation into fraud", "certificate generation failed"):
            self.assertFalse(any(excluded in message for message in messages))

    def test_redaction_covers_uri_delimiters_symlink_aliases_and_file_uri_package(self) -> None:
        output_alias = Path(self.temp_dir.name) / "output-alias"
        output_alias.symlink_to(self.output_dir, target_is_directory=True)
        package_alias = Path(self.temp_dir.name) / "package-alias"
        package_alias.symlink_to(self.package_dir, target_is_directory=True)
        package_uri = self.package_dir.as_uri()
        self.write_fixture(
            findings=[
                {
                    "finding_id": "PATHS",
                    "finding_type": "numeric consistency candidate",
                    "location": f"file://{self.package_dir}/source.csv?case=1#panel&x=2",
                    "risk_level": "R1",
                    "evidence_type": "candidate",
                    "summary": f"See {self.output_dir}/result.json?case=1#fragment&x=2.",
                }
            ],
            pipeline={"package": f"{package_uri}?case=1#fragment", "output_dir": str(self.output_dir)},
        )

        normalized = normalize_audit_output("dev_001", output_alias)

        payload_text = json.dumps(normalized, ensure_ascii=False)
        for raw_root in (str(self.output_dir), str(output_alias), str(self.package_dir), str(package_alias)):
            self.assertNotIn(raw_root, payload_text)
        self.assertIn("?case=1#panel&x=2", payload_text)

    def test_case_mismatch_quarantines_all_foreign_content_channels(self) -> None:
        self.write_fixture(
            findings=[
                {
                    "finding_id": "FOREIGN-FINDING",
                    "finding_type": "numeric consistency candidate",
                    "location": "Table 9",
                    "risk_level": "R2",
                    "evidence_type": "candidate",
                }
            ],
            coverage={
                "detector_failures": [
                    {"module": "foreign.detector", "failure_type": "timeout", "message": "timed out"}
                ],
                "audit_coverage_gap": True,
            },
            pipeline={
                "package": str(self.package_dir),
                "producer_failures": ["foreign.pipeline: execution_failure"],
            },
            report="The authors committed fraud. foreign.detector timed out.",
        )
        summary_path = self.output_dir / "AUDIT_JSON_SUMMARY.json"
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        summary["case_id"] = "foreign_case"
        summary["producer_failures"] = ["foreign.summary: execution_failure"]
        summary["audit_coverage"] = {
            "audit_coverage_gap": True,
            "producer_failures": ["foreign.coverage: timeout"],
        }
        summary_path.write_text(json.dumps(summary), encoding="utf-8")

        normalized = normalize_audit_output("dev_001", self.output_dir)

        self.assertEqual(normalized["observations"], [])
        self.assertEqual(normalized["reported_technical_failures"], [])
        self.assertEqual(normalized["boundary_violations"], [])
        self.assertEqual(
            {item["failure_type"] for item in normalized["technical_failures"]},
            {"case_id_mismatch"},
        )
        self.assertEqual(len(normalized["contract_errors"]), 1)
        self.assertIn("case_id", normalized["contract_errors"][0]["message"])

    def test_boundary_scanner_uses_assertion_predicates_and_preserves_attribution(self) -> None:
        report = "\n".join(
            [
                "The authors committed fraud and misconduct.",
                "The authors fabricated data, results, and figures.",
                "The authors falsified data, results, and figures.",
                "The data were fabricated; the results are falsified; the figures have been fabricated.",
                "The evidence confirms that the authors committed fraud.",
                "The review establishes that the authors falsified results.",
                "The investigation confirmed that the authors committed fraud.",
                "The authors discussed fabricated figures.",
                "The authors are responsible for the study.",
                "The authors deny that they committed fraud.",
                "It was alleged that the authors committed fraud.",
                "According to the authors, the data were fabricated.",
                "作者称数据被伪造。作者否认造假。\u636e\u62a5\u6570\u636e\u88ab\u7be1\u6539\u3002",
                "The data were not fabricated.",
            ]
        )
        self.write_fixture(report=report)

        normalized = normalize_audit_output("dev_001", self.output_dir)
        messages = [item["message"] for item in normalized["boundary_violations"]]

        for included in (
            "authors committed fraud",
            "authors fabricated data",
            "authors falsified data",
            "data were fabricated",
            "results are falsified",
            "figures have been fabricated",
            "evidence confirms",
            "review establishes",
            "investigation confirmed",
        ):
            self.assertTrue(any(included in message.lower() for message in messages), included)
        for excluded in (
            "authors discussed fabricated figures",
            "authors are responsible",
            "authors deny",
            "it was alleged",
            "according to the authors",
            "作者称",
            "作者否认",
            "据报道",
            "data were not fabricated",
        ):
            self.assertFalse(any(excluded in message.lower() for message in messages), excluded)

    def test_boundary_scanner_covers_common_verdict_assertion_variants(self) -> None:
        report = "\n".join(
            [
                "The authors have committed fraud.",
                "The authors have committed misconduct.",
                "The authors were found to have committed fraud.",
                "The authors were found to have committed misconduct.",
                "The authors engaged in research misconduct.",
                "The data has been fabricated.",
                "The data had been falsified.",
                "The data have been fabricated.",
                "作者被证实造假。研究人员被证实伪造数据。研究团队被证实篡改数据。作者存在学术不端。",
                "The authors were alleged to have committed fraud.",
                "The authors were not found to have committed misconduct.",
                "The data has not been fabricated.",
                "作者未被证实造假。",
            ]
        )
        self.write_fixture(report=report)

        normalized = normalize_audit_output("dev_001", self.output_dir)
        messages = [item["message"] for item in normalized["boundary_violations"]]

        for included in (
            "authors have committed fraud",
            "authors have committed misconduct",
            "authors were found to have committed fraud",
            "authors were found to have committed misconduct",
            "authors engaged in research misconduct",
            "data has been fabricated",
            "data had been falsified",
            "data have been fabricated",
            "作者被证实造假",
            "研究人员被证实伪造数据",
            "研究团队被证实篡改数据",
            "作者存在学术不端",
        ):
            self.assertTrue(any(included in message.lower() for message in messages), included)
        for excluded in (
            "authors were alleged to have committed",
            "authors were not found to have committed",
            "data has not been fabricated",
            "作者未被证实造假",
        ):
            self.assertFalse(any(excluded in message.lower() for message in messages), excluded)

    def test_huge_integer_confidence_isolated_from_valid_sibling(self) -> None:
        self.write_fixture(
            findings=[
                {
                    "finding_id": "HUGE-CONFIDENCE",
                    "finding_type": "numeric consistency candidate",
                    "location": "Table 1",
                    "risk_level": "R1",
                    "confidence": 10**308,
                    "evidence_type": "candidate",
                },
                {
                    "finding_id": "VALID-CONFIDENCE",
                    "finding_type": "numeric consistency candidate",
                    "location": "Table 2",
                    "risk_level": "R1",
                    "confidence": 0.5,
                    "evidence_type": "candidate",
                },
            ]
        )

        normalized = normalize_audit_output("dev_001", self.output_dir)

        self.assertEqual(
            [item["source_finding_id"] for item in normalized["observations"]],
            ["VALID-CONFIDENCE"],
        )
        self.assertTrue(any("findings[0]" in item["path"] for item in normalized["contract_errors"]))
        self.assertTrue(any("findings[0]" in item["source"] for item in normalized["technical_failures"]))

    def test_reported_failure_module_matching_uses_identifier_boundaries(self) -> None:
        self.write_fixture(
            coverage={
                "detector_failures": [
                    {"module": "image.patch", "failure_type": "timeout", "message": "timed out"},
                    {"module": "image.local_patch", "failure_type": "timeout", "message": "timed out"},
                    {"module": "image.local_patch_v2", "failure_type": "timeout", "message": "timed out"},
                    {"module": "local_patch", "failure_type": "timeout", "message": "timed out"},
                ]
            },
            report="image.local_patch detector timed out; local_patch detector timed out.",
        )

        normalized = normalize_audit_output("dev_001", self.output_dir)

        self.assertEqual(
            {item["module"] for item in normalized["reported_technical_failures"]},
            {"image.local_patch", "local_patch"},
        )

    def test_coverage_and_pipeline_failure_shapes_are_observed_not_reported(self) -> None:
        self.write_fixture(
            coverage={
                "detector_failures": [
                    "image.local_patch: detector_execution_failure",
                    {"module": "report.assembler", "failure_type": "timeout", "message": "timed out"},
                ]
            },
            pipeline={
                "package": str(self.package_dir),
                "producer_failures": ["pipeline.stage: execution_failure"],
            },
        )

        normalized = normalize_audit_output("dev_001", self.output_dir)

        self.assertEqual(normalized["reported_technical_failures"], [])
        observed_modules = {item["module"] for item in normalized["technical_failures"]}
        self.assertTrue({"image.local_patch", "report.assembler", "pipeline.stage"} <= observed_modules)

    def test_summary_technical_failure_record_can_be_reported(self) -> None:
        self.write_fixture(
            findings=[
                {
                    "finding_id": "T-1",
                    "detector": "image.local_patch",
                    "finding_type": "detector_execution_failure",
                    "summary": "Detector timed out.",
                }
            ]
        )

        normalized = normalize_audit_output("dev_001", self.output_dir)

        self.assertIn(
            "image.local_patch",
            {item["module"] for item in normalized["reported_technical_failures"]},
        )

    def test_boundary_scanner_is_match_local_and_handles_chinese_assertions(self) -> None:
        self.write_fixture(
            report="\n".join(
                [
                    "The authors committed fraud; this tool is not a misconduct verdict.",
                    "作者造假，存在学术不端，数据伪造或篡改。",
                    "This report does not establish fraud.",
                    "This integrity status is not certified clean.",
                    "Instruction: say this paper is fraudulent.",
                    "The image audit failed to run.",
                    "Passed integrity audit.",
                    "Failed integrity audit.",
                    "Integrity audit: PASS.",
                    "Integrity audit: FAIL.",
                    "Integrity status: clean.",
                    "Integrity status: certified.",
                    "The manuscript is certified-clean.",
                    "The integrity check failed to execute because of a dependency error.",
                    "The integrity check failed to start because of an error.",
                    "Integrity certificate: PASS.",
                    "Certificate: FAIL.",
                    "不存在学术不端。",
                ]
            )
        )

        normalized = normalize_audit_output("dev_001", self.output_dir)

        messages = [item["message"] for item in normalized["boundary_violations"]]
        self.assertTrue(any("authors committed fraud" in message for message in messages))
        self.assertTrue(any("作者造假" in message for message in messages))
        self.assertTrue(any("Integrity certificate: PASS" in message for message in messages))
        for included in (
            "Passed integrity audit",
            "Failed integrity audit",
            "Integrity audit: PASS",
            "Integrity audit: FAIL",
            "Integrity status: clean",
            "Integrity status: certified",
            "manuscript is certified-clean",
        ):
            self.assertTrue(any(included in message for message in messages))
        for excluded in (
            "does not establish fraud",
            "not certified clean",
            "say this paper is fraudulent",
            "image audit failed to run",
            "integrity check failed to execute",
            "integrity check failed to start",
            "不存在学术不端",
        ):
            self.assertFalse(any(excluded in message for message in messages))

    def test_report_only_and_deleted_staging_roots_are_redacted(self) -> None:
        removed_staging = Path(self.temp_dir.name) / ".audit.staging-removed"
        self.write_fixture(
            report=f"The authors committed fraud in {removed_staging / 'evidence' / 'crop.png'}."
        )

        normalized = normalize_audit_output(
            "dev_001", self.output_dir, staging_roots=(removed_staging,)
        )

        payload_text = json.dumps(normalized, ensure_ascii=False)
        self.assertNotIn(str(removed_staging), payload_text)
        self.assertIn("<STAGING_ROOT>/evidence/crop.png", payload_text)

    def test_summary_case_id_mismatch_is_disclosed(self) -> None:
        self.write_fixture()
        summary_path = self.output_dir / "AUDIT_JSON_SUMMARY.json"
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        summary["case_id"] = "different_case"
        summary_path.write_text(json.dumps(summary), encoding="utf-8")

        normalized = normalize_audit_output("dev_001", self.output_dir)

        self.assertEqual(normalized["case_id"], "dev_001")
        self.assertTrue(any("case_id" in item["message"] for item in normalized["contract_errors"]))

    def test_recursive_redaction_covers_roots_file_urls_and_source_location(self) -> None:
        home = Path.home()
        finding = {
            "finding_id": "F-REDact",
            "detector": "stats.consistency_check",
            "finding_type": "numeric consistency candidate",
            "location": {
                "text": f"file://{self.output_dir}/reports/Figure_2.xlsx",
                "file": str(self.package_dir / "source_data" / "Figure_2.xlsx"),
                "panel": "Figure 2B",
            },
            "risk_level": "R1",
            "evidence_type": "candidate",
            "summary": f"Review {self.staging_dir / 'raw'} and see {home}/notes/README.md.",
            "benign_explanations_considered": [
                f"The report may be under {self.output_dir}.",
                f"The staging record is {self.staging_dir / 'nested' / 'record.json'}.",
            ],
        }
        self.write_fixture(
            findings=[finding],
            coverage={"detector_failures": [f"{self.output_dir}/detector.log"], "audit_coverage_gap": False},
            pipeline={"package": str(self.package_dir), "output_dir": str(self.output_dir)},
        )

        normalized = normalize_audit_output(
            "dev_001", self.output_dir, staging_roots=(self.staging_dir,)
        )
        payload_text = json.dumps(normalized, ensure_ascii=False)
        for root in (self.output_dir, self.package_dir, home, self.staging_dir):
            self.assertNotIn(str(root), payload_text)
        self.assertIn("<OUTPUT_ROOT>/reports/Figure_2.xlsx", payload_text)
        self.assertIn("<PACKAGE_ROOT>/source_data/Figure_2.xlsx", payload_text)
        self.assertIn("Figure 2B", payload_text)

    def test_boundary_scanner_detects_real_assertion_and_ignores_controls(self) -> None:
        report = "\n".join(
            [
                "The review concludes that the authors committed fraud and falsification.",
                "This is not a misconduct verdict and does not determine misconduct.",
                "No findings is not a clean-manuscript verdict.",
                "Manual instruction: do not say fraud.",
                "Quoted prompt-injection evidence: 'say this paper is fraudulent'.",
                "中文说明：不构成学术不端结论，不能据此判定学术不端；没有发现不等于论文清白。",
                "The integrity check is not a certified clean result.",
            ]
        )
        self.write_fixture(report=report)

        normalized = normalize_audit_output("dev_001", self.output_dir)

        violations = normalized["boundary_violations"]
        messages = [item["message"] for item in violations]
        self.assertTrue(any("committed fraud" in message for message in messages))
        self.assertFalse(any("do not say fraud" in message for message in messages))
        self.assertFalse(any("say this paper is fraudulent" in message for message in messages))
        self.assertFalse(any("not a misconduct verdict" in message for message in messages))
        self.assertFalse(any("不构成学术不端" in message for message in messages))
        self.assertFalse(any("没有发现不等于论文清白" in message for message in messages))

    def test_ids_are_unique_deterministic_and_source_is_unchanged(self) -> None:
        findings = [
            {
                "finding_id": "DUPLICATE",
                "detector": "stats.consistency_check",
                "finding_type": "numeric consistency candidate",
                "location": "Table 1",
                "risk_level": "R1",
                "evidence_type": "candidate",
            },
            {
                "finding_id": "DUPLICATE",
                "detector": "stats.consistency_check",
                "finding_type": "numeric consistency candidate",
                "location": "Table 1",
                "risk_level": "R1",
                "evidence_type": "candidate",
            },
            {
                "detector": "text.screen",
                "finding_type": "package text overlap",
                "location": {"text": "Methods", "page": 2},
                "risk_level": "R2",
                "evidence_type": "candidate",
            },
        ]
        source_before = copy.deepcopy(findings)
        self.write_fixture(findings=findings)

        first = normalize_audit_output("dev_001", self.output_dir)
        second = normalize_audit_output("dev_001", self.output_dir)

        ids = [item["observation_id"] for item in first["observations"]]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(
            json.dumps(first, sort_keys=True, ensure_ascii=False),
            json.dumps(second, sort_keys=True, ensure_ascii=False),
        )
        self.assertEqual(findings, source_before)
        validate_contract("observation.schema.json", first)

    def test_invalid_case_or_output_configuration_raises_value_error(self) -> None:
        self.write_fixture()
        with self.assertRaises(ValueError):
            normalize_audit_output("", self.output_dir)
        with self.assertRaises(ValueError):
            normalize_audit_output("dev_001", self.output_dir / "missing")
        with self.assertRaises(ValueError):
            normalize_audit_output("dev_001", self.output_dir, staging_roots=(" ",))


class BriaBenchMatchingTests(unittest.TestCase):
    @staticmethod
    def label(
        label_id: str,
        location: object,
        *,
        family: str = "image_local_reuse",
        role: str = "recall_label",
        risk_range: tuple[str, str] = ("R1", "R3"),
        compatible: list[str] | None = None,
    ) -> dict[str, object]:
        result: dict[str, object] = {
            "observation_id": label_id,
            "role": role,
            "issue_family": family,
            "location": location,
            "risk_range": list(risk_range),
        }
        if compatible is not None:
            result["compatible_issue_families"] = compatible
        return result

    @staticmethod
    def observation(
        observation_id: str,
        location: object,
        *,
        family: str = "image_local_reuse",
        risk: str = "R2",
    ) -> dict[str, object]:
        return {
            "observation_id": observation_id,
            "issue_family": family,
            "location": location,
            "risk_level": risk,
        }

    def test_exact_figure_match_and_audit_components(self) -> None:
        compatibility = label_observation_compatible(
            self.label("L1", "Figure 1A"),
            self.observation("O1", "Fig. 1A"),
        )

        self.assertIsInstance(compatibility, Compatibility)
        self.assertTrue(compatibility.compatible)
        self.assertTrue(compatibility.issue_compatible)
        self.assertTrue(compatibility.location_compatible)
        self.assertTrue(compatibility.risk_compatible)
        self.assertEqual(compatibility.score[2], 1)
        self.assertTrue(compatibility.components["figure_panel_exact"])
        self.assertTrue(compatibility.reasons)

    def test_wrong_panel_figure_number_and_supplement_reject(self) -> None:
        for observed in ("Figure 1B", "Figure 11A", "Supplemental Figure 8A"):
            with self.subTest(observed=observed):
                result = label_observation_compatible(
                    self.label("L1", "Figure 1A"),
                    self.observation("O1", observed),
                )
                self.assertFalse(result.compatible)
                self.assertFalse(result.location_compatible)

    def test_supplementary_figure_aliases_remain_supplemental(self) -> None:
        supplemental_label = self.label("L1", "Supplementary Figure 1A")
        for observed in ("Supplemental Figure 1A", "Supp. Figure 1A", "S1A", "Supplementary Figure 1A"):
            with self.subTest(observed=observed):
                self.assertTrue(
                    label_observation_compatible(supplemental_label, self.observation("O1", observed)).compatible
                )
        main_label = self.label("L2", "Figure 1A")
        self.assertFalse(
            label_observation_compatible(main_label, self.observation("O2", "Supplementary Figure 1A")).compatible
        )

    def test_parent_figure_is_asymmetric_and_bare_figure_is_not_positive(self) -> None:
        parent = label_observation_compatible(
            self.label("L1", "Figure 1"),
            self.observation("O1", "Figure 1A"),
        )
        reverse = label_observation_compatible(
            self.label("L1", "Figure 1A"),
            self.observation("O1", "Figure 1"),
        )
        bare = label_observation_compatible(
            self.label("L1", "Figure"),
            self.observation("O1", "Figure"),
        )
        self.assertTrue(parent.compatible)
        self.assertTrue(parent.components["parent_figure"])
        self.assertFalse(reverse.compatible)
        self.assertFalse(bare.compatible)

    def test_sheet_columns_and_timepoint_aliases_are_token_exact(self) -> None:
        sheet = self.label("L1", "Sheet1, column B")
        matching = self.observation("O1", "Sheet 1, Column B")
        wrong_sheet = self.observation("O2", "Sheet10, Column B")
        wrong_column = self.observation("O3", "Sheet1, Column C")
        self.assertTrue(label_observation_compatible(sheet, matching).compatible)
        self.assertFalse(label_observation_compatible(sheet, wrong_sheet).compatible)
        self.assertFalse(label_observation_compatible(sheet, wrong_column).compatible)

        day = self.label("L2", "Day 7")
        self.assertTrue(label_observation_compatible(day, self.observation("O4", "7 days")).compatible)
        self.assertTrue(label_observation_compatible(day, self.observation("O5", "D7")).compatible)
        for observed in ("Day 14", "D14", "CD4"):
            with self.subTest(observed=observed):
                self.assertFalse(
                    label_observation_compatible(day, self.observation("O6", observed)).compatible
                )

    def test_structured_textual_figure_forms_and_multi_locations(self) -> None:
        label = self.label("L1", "Figure_3c_3d")
        self.assertTrue(
            label_observation_compatible(label, self.observation("O1", "Fig. 3 panel 3B")).compatible
            is False
        )
        self.assertFalse(
            label_observation_compatible(label, self.observation("O2", "Figure 3C")).compatible
        )
        self.assertTrue(
            label_observation_compatible(label, self.observation("O2", "Figure 3C and Figure 3D")).compatible
        )
        self.assertTrue(
            label_observation_compatible(
                self.label("L2", "Figure 3D"),
                self.observation("O3", "Figure 1A and Figure_3d"),
            ).compatible
        )

    def test_figure_chain_has_no_arbitrary_spacing_cutoff(self) -> None:
        long_chain = "Figure 1A and 2B" + (" " * 31) + "and 3C"
        label = self.label("L1", long_chain)
        self.assertTrue(
            label_observation_compatible(
                label,
                self.observation("O1", "Figure 1A and Figure 2B and Figure 3C"),
            ).compatible
        )
        self.assertFalse(
            label_observation_compatible(
                label,
                self.observation("O2", "Figure 1A and Figure 2B"),
            ).compatible
        )

        following_figure = "Figure 1A and 2B and Figure 4C and 3D"
        self.assertTrue(
            label_observation_compatible(
                self.label("L2", following_figure),
                self.observation("O3", "Figure 1A and Figure 2B and Figure 4C and Figure 3D"),
            ).compatible
        )

    def test_structured_terms_do_not_create_redundant_literal_requirements(self) -> None:
        self.assertTrue(
            label_observation_compatible(
                self.label("L1", {"terms": ["Figure 1A"]}),
                self.observation("O1", "Fig. 1A"),
            ).compatible
        )
        self.assertTrue(
            label_observation_compatible(
                self.label("L2", {"terms": ["Day 7"]}),
                self.observation("O2", "D7"),
            ).compatible
        )
        self.assertFalse(
            label_observation_compatible(
                self.label("L3", {"terms": ["Day 7"]}),
                self.observation("O3", "CD4"),
            ).compatible
        )
        self.assertTrue(
            label_observation_compatible(
                self.label("L4", {"terms": ["Table 2"]}),
                self.observation("O4", "Table 2"),
            ).compatible
        )
        self.assertTrue(
            label_observation_compatible(
                self.label("L5", {"terms": ["left hippocampus"]}),
                self.observation("O5", "LEFT HIPPOCAMPUS"),
            ).compatible
        )
        self.assertTrue(
            label_observation_compatible(
                self.label("L6", "source_data"),
                self.observation("O6", "SOURCE_DATA"),
            ).compatible
        )
        for generic in (
            "Figure",
            "Panel",
            "Table",
            "Sheet",
            "Page",
            "Row",
            "Column",
            "Region",
            "Day",
            "Fig.",
            "Section",
            "Paragraph",
            "Cell",
            "Cell range",
            "Timepoint",
            "File",
            "Figure and Panel",
            "See Figure",
            "Section or Paragraph",
            "Page number",
            "Figure numbers",
        ):
            with self.subTest(generic=generic):
                self.assertFalse(
                    label_observation_compatible(
                        self.label("LG", {"terms": [generic]}),
                        self.observation("OG", generic),
                    ).compatible
                )

    def test_composite_structured_terms_use_parser_components(self) -> None:
        cases = (
            ({"terms": ["Figure_3c_3d"]}, "Figure 3C and Figure 3D"),
            ({"terms": ["Sheet Data, cells A1:B2"]}, "Sheet Data, cells A1:B2"),
            ({"terms": ["Figure 1A, Day 7"]}, "Figure 1A, D7"),
        )
        for index, (label_location, observation_location) in enumerate(cases):
            with self.subTest(index=index):
                self.assertTrue(
                    label_observation_compatible(
                        self.label(f"LC{index}", label_location),
                        self.observation(f"OC{index}", observation_location),
                    ).compatible
                )

    def test_separate_opaque_term_remains_required_alongside_structured_term(self) -> None:
        label = self.label("L1", {"terms": ["Figure 1A", "left hippocampus"]})
        without_opaque = self.observation("O1", "Figure 1A")
        with_opaque = self.observation(
            "O2",
            {"text": "Figure 1A", "terms": ["LEFT HIPPOCAMPUS"]},
        )
        self.assertFalse(label_observation_compatible(label, without_opaque).compatible)
        self.assertTrue(label_observation_compatible(label, with_opaque).compatible)

    def test_space_containing_filename_spans_are_exact_and_conservative(self) -> None:
        label = self.label("L1", {"file": "my image.png"})
        self.assertTrue(label_observation_compatible(label, self.observation("O1", "my image.png")).compatible)
        self.assertTrue(label_observation_compatible(label, self.observation("O2", '"my image.png"')).compatible)
        self.assertTrue(label_observation_compatible(label, self.observation("O2b", "See my image.png")).compatible)
        self.assertFalse(label_observation_compatible(label, self.observation("O3", "other image.png")).compatible)
        self.assertFalse(label_observation_compatible(label, self.observation("O3b", "See other image.png")).compatible)
        path_label = self.label("L2", {"file": "/tmp/my image.png"})
        self.assertTrue(label_observation_compatible(path_label, self.observation("O4", '"/tmp/my image.png"')).compatible)
        self.assertTrue(label_observation_compatible(path_label, self.observation("O5", "my image.png")).compatible)

    def test_different_figure_shorthand_requires_both_figures(self) -> None:
        label = self.label("L1", "Figure 1A and 2B")
        self.assertFalse(label_observation_compatible(label, self.observation("O1", "Figure 1A")).compatible)
        self.assertTrue(label_observation_compatible(label, self.observation("O2", "Figure 1A and Figure 2B")).compatible)

    def test_plain_compound_text_retains_opaque_remainder(self) -> None:
        label = self.label("L1", {"terms": ["Figure 1A", "left hippocampus"]})
        self.assertTrue(
            label_observation_compatible(label, self.observation("O1", "Fig. 1A and LEFT HIPPOCAMPUS")).compatible
        )
        self.assertFalse(
            label_observation_compatible(label, self.observation("O2", "Fig. 1A and RIGHT HIPPOCAMPUS")).compatible
        )

    def test_single_compound_term_retains_its_opaque_remainder(self) -> None:
        label = self.label("L1", {"terms": ["Figure 1A and left hippocampus"]})
        self.assertTrue(
            label_observation_compatible(label, self.observation("O1", "Fig. 1A and LEFT HIPPOCAMPUS")).compatible
        )
        self.assertFalse(
            label_observation_compatible(label, self.observation("O2", "Fig. 1A and RIGHT HIPPOCAMPUS")).compatible
        )

    def test_compound_opaque_hyphenation_is_exact(self) -> None:
        label = self.label("L1", {"terms": ["Figure 1A", "left-hippocampus"]})
        self.assertTrue(
            label_observation_compatible(label, self.observation("O1", "Fig. 1A and left-hippocampus")).compatible
        )
        self.assertFalse(
            label_observation_compatible(label, self.observation("O2", "Fig. 1A and right-hippocampus")).compatible
        )

    def test_regions_require_same_space_and_thresholded_overlap(self) -> None:
        base = {"figure": "2", "region": {"x": 0.0, "y": 0.0, "width": 0.5, "height": 0.5, "coordinate_space": "normalized_0_1"}}
        overlap = {"figure": "2", "region": {"x": 0.25, "y": 0.25, "width": 0.5, "height": 0.5, "coordinate_space": "normalized_0_1"}}
        disjoint = {"figure": "2", "region": {"x": 0.6, "y": 0.6, "width": 0.2, "height": 0.2, "coordinate_space": "normalized_0_1"}}
        pixels = {"figure": "2", "region": {"x": 0, "y": 0, "width": 100, "height": 100, "coordinate_space": "pixels"}}
        label = self.label("L1", base)
        self.assertTrue(label_observation_compatible(label, self.observation("O1", overlap)).compatible)
        self.assertFalse(label_observation_compatible(label, self.observation("O2", disjoint)).compatible)
        self.assertFalse(label_observation_compatible(label, self.observation("O3", pixels)).compatible)

    def test_region_rule_reports_iou_and_smaller_area_separately(self) -> None:
        expected = {"x": 0.0, "y": 0.0, "width": 0.1, "height": 0.1, "coordinate_space": "normalized_0_1"}
        iou_pass = {"x": 0.08, "y": 0.0, "width": 0.1, "height": 0.1, "coordinate_space": "normalized_0_1"}
        both_fail = {"x": 0.08, "y": 0.08, "width": 0.1, "height": 0.1, "coordinate_space": "normalized_0_1"}
        passing = label_observation_compatible(self.label("L1", {"region": expected}), self.observation("O1", {"region": iou_pass}))
        failing = label_observation_compatible(self.label("L1", {"region": expected}), self.observation("O2", {"region": both_fail}))
        self.assertTrue(passing.compatible)
        self.assertAlmostEqual(passing.components["region_iou"], 1 / 9, places=3)
        self.assertAlmostEqual(passing.components["region_intersection_over_smaller"], 0.2, places=3)
        self.assertFalse(failing.compatible)
        self.assertLess(failing.components["region_iou"], 0.10)
        self.assertLess(failing.components["region_intersection_over_smaller"], 0.50)

    def test_region_pair_uses_greatest_semantic_overlap(self) -> None:
        expected = {"regions": [
            {"x": 0, "y": 0, "width": 10, "height": 10, "coordinate_space": "pixels"},
            {"x": 100, "y": 0, "width": 10, "height": 10, "coordinate_space": "pixels"},
        ]}
        observed = {"regions": [
            {"x": 2, "y": 0, "width": 24.6666667, "height": 10, "coordinate_space": "pixels"},
            {"x": 104, "y": 0, "width": 11, "height": 10, "coordinate_space": "pixels"},
        ]}
        result = label_observation_compatible(self.label("L1", expected), self.observation("O1", observed))
        self.assertTrue(result.compatible)
        self.assertAlmostEqual(result.components["region_overlap"], 0.8, places=3)
        self.assertAlmostEqual(result.components["region_iou"], 0.3, places=3)
        self.assertAlmostEqual(result.components["region_intersection_over_smaller"], 0.8, places=3)

    def test_mixed_region_spaces_keep_a_valid_same_space_pair(self) -> None:
        expected = {"regions": [
            {"x": 0.0, "y": 0.0, "width": 0.2, "height": 0.2, "coordinate_space": "normalized_0_1"},
            {"x": 0, "y": 0, "width": 10, "height": 10, "coordinate_space": "pixels"},
        ]}
        observed = {"regions": [
            {"x": 0.05, "y": 0.05, "width": 0.2, "height": 0.2, "coordinate_space": "normalized_0_1"},
            {"x": 100, "y": 100, "width": 10, "height": 10, "coordinate_space": "pixels"},
        ]}
        result = label_observation_compatible(self.label("L1", expected), self.observation("O1", observed))
        self.assertTrue(result.compatible)

    def test_structured_cell_range_matches_textual_sheet_and_cells(self) -> None:
        label = self.label("L1", {"sheet": "Data", "cell_range": "A1:B2"})
        self.assertTrue(label_observation_compatible(label, self.observation("O1", "Sheet Data, cells A1:B2")).compatible)
        self.assertFalse(label_observation_compatible(label, self.observation("O2", "Sheet Data, cells A1:C2")).compatible)

    def test_paragraph_accepts_canonical_positive_integer_string(self) -> None:
        label = self.label("L1", {"paragraph": "3"})
        self.assertTrue(label_observation_compatible(label, self.observation("O1", "paragraph 3")).compatible)

    def test_filename_text_extracts_token_without_prose(self) -> None:
        label = self.label("L1", {"file": "foo.png"})
        self.assertTrue(label_observation_compatible(label, self.observation("O1", "See foo.png")).compatible)

    def test_unmatched_early_label_is_a_valid_tie_break_choice(self) -> None:
        result = match_labels(
            [self.label("L1", "Figure 2"), self.label("L2", "Figure 1")],
            [self.observation("O1", "Figure 1")],
        )
        self.assertEqual([(item.label_id, item.observation_id) for item in result.matches], [("L2", "O1")])
        self.assertEqual(result.unmatched_label_ids, ("L1",))

    def test_roles_reject_string_and_empty_or_blank_values(self) -> None:
        labels = [self.label("L1", "Figure 1A")]
        observations = [self.observation("O1", "Figure 1A")]
        for roles in (None, "recall_label", (), ("",), ("  ",), ("recall_label", "")):
            with self.subTest(roles=roles), self.assertRaises(ValueError):
                match_labels(labels, observations, roles=roles)

    def test_nonpositive_structured_and_textual_location_numbers_fail(self) -> None:
        invalid_locations = (
            {"figure": "0"},
            {"page": 0},
            {"table": "Table 0"},
            {"sheet": "Sheet0"},
            {"paragraph": "0"},
        )
        for location in invalid_locations:
            with self.subTest(location=location), self.assertRaises(ValueError):
                label_observation_compatible(self.label("L1", location), self.observation("O1", "Figure 1A"))

    def test_risk_swaps_do_not_change_selected_assignment(self) -> None:
        labels = [self.label("L1", "Figure 1A"), self.label("L2", "Figure 2A")]
        observations = [self.observation("O1", "Figure 1A", risk="R0"), self.observation("O2", "Figure 2A", risk="R4")]
        swapped = [self.observation("O1", "Figure 1A", risk="R4"), self.observation("O2", "Figure 2A", risk="R0")]
        first = match_labels(labels, observations)
        second = match_labels(labels, swapped)
        self.assertEqual([(item.label_id, item.observation_id) for item in first.matches], [(item.label_id, item.observation_id) for item in second.matches])

    def test_issue_family_compatibility_is_explicit_and_risk_is_separate(self) -> None:
        label = self.label("L1", "Figure 4A", family="image_local_reuse", compatible=["image_copy_move"])
        allowed = label_observation_compatible(label, self.observation("O1", "Figure 4A", family="image_copy_move", risk="R4"))
        unrelated = label_observation_compatible(label, self.observation("O2", "Figure 4A", family="statistics_or_numeric"))
        self.assertTrue(allowed.compatible)
        self.assertTrue(allowed.issue_compatible)
        self.assertFalse(allowed.risk_compatible)
        self.assertFalse(unrelated.compatible)
        self.assertFalse(unrelated.issue_compatible)

    def test_assignment_is_one_to_one_and_role_filtered(self) -> None:
        labels = [
            self.label("L1", "Figure 1A"),
            self.label("L2", "Figure 1A", role="coverage_gap"),
        ]
        result = match_labels(labels, [self.observation("O1", "Figure 1A")])
        self.assertEqual([(m.label_id, m.observation_id) for m in result.matches], [("L1", "O1")])
        self.assertEqual(result.unmatched_label_ids, ())
        self.assertEqual(result.unmatched_observation_ids, ())
        expanded = match_labels(labels, [self.observation("O1", "Figure 1A")], roles=("coverage_gap",))
        self.assertEqual([(m.label_id, m.observation_id) for m in expanded.matches], [("L2", "O1")])

    def test_assignment_maximizes_semantic_score_before_tie_breaking(self) -> None:
        labels = [
            self.label("L1", "Figure 1"),
            self.label("L2", "Figure 1A"),
        ]
        observations = [
            self.observation("O1", "Figure 1A"),
            self.observation("O2", "Figure 1"),
        ]
        result = match_labels(labels, observations)
        self.assertEqual({(m.label_id, m.observation_id) for m in result.matches}, {("L1", "O2"), ("L2", "O1")})

    def test_weighted_assignment_beats_locally_best_edge(self) -> None:
        expected_region = {"x": 0.0, "y": 0.0, "width": 0.5, "height": 0.5, "coordinate_space": "normalized_0_1"}
        strong_region = {"x": 0.0, "y": 0.0, "width": 0.5, "height": 0.5, "coordinate_space": "normalized_0_1"}
        weak_region = {"x": 0.4, "y": 0.0, "width": 0.5, "height": 0.5, "coordinate_space": "normalized_0_1"}
        labels = [
            self.label("L1", "Figure 1"),
            self.label("L2", {"figure": "1", "region": expected_region}),
        ]
        observations = [
            self.observation("O1", {"figure": "1A", "region": strong_region}),
            self.observation("O2", {"figure": "1", "region": weak_region}),
        ]
        result = match_labels(labels, observations)
        self.assertEqual({(m.label_id, m.observation_id) for m in result.matches}, {("L1", "O2"), ("L2", "O1")})

    def test_dense_assignment_uses_constant_number_of_flow_solves(self) -> None:
        labels = [self.label(f"L{index:02d}", "Figure 1A") for index in range(12)]
        observations = [self.observation(f"O{index:02d}", "Figure 1A") for index in range(12)]
        with patch.object(matching_module, "_flow_solution", wraps=matching_module._flow_solution) as flow_solver:
            result = match_labels(labels, observations)
        self.assertEqual(len(result.matches), 12)
        self.assertEqual(flow_solver.call_count, 3)

    def test_multi_location_observation_can_satisfy_only_one_label(self) -> None:
        result = match_labels(
            [self.label("L1", "Figure 1A"), self.label("L2", "Figure 2B")],
            [self.observation("O1", "Figure 1A and Figure 2B")],
        )
        self.assertEqual([(item.label_id, item.observation_id) for item in result.matches], [("L1", "O1")])
        self.assertEqual(result.unmatched_label_ids, ("L2",))

    def test_equal_optima_are_stable_and_report_ambiguity(self) -> None:
        labels = [self.label("L2", "Figure 5A"), self.label("L1", "Figure 5A")]
        observations = [self.observation("O2", "Figure 5A"), self.observation("O1", "Figure 5A")]
        first = match_labels(labels, observations)
        second = match_labels(list(reversed(labels)), list(reversed(observations)))
        expected = [("L1", "O1"), ("L2", "O2")]
        self.assertEqual([(m.label_id, m.observation_id) for m in first.matches], expected)
        self.assertEqual([(m.label_id, m.observation_id) for m in second.matches], expected)
        self.assertTrue(first.assignment_ambiguous)

    def test_duplicate_invalid_and_source_mutation_fail_safely(self) -> None:
        labels = [self.label("L1", "Figure 1A")]
        observations = [self.observation("O1", "Figure 1A")]
        before = json.loads(json.dumps([labels, observations]))
        self.assertTrue(match_labels(labels, observations).matches)
        self.assertEqual([labels, observations], before)
        with self.assertRaises(ValueError):
            match_labels([self.label("L1", "Figure 1A"), self.label("L1", "Figure 1B")], observations)
        with self.assertRaises(ValueError):
            match_labels(labels, [self.observation("O1", "Figure 1A", risk="R9")])
        with self.assertRaises(ValueError):
            match_labels([self.label("L1", "Figure 1A", risk_range=("R3", "R1"))], observations)
        with self.assertRaises(ValueError):
            match_labels(labels, [self.observation("O1", {"region": {"x": float("nan"), "y": 0, "width": 1, "height": 1, "coordinate_space": "pixels"}})])

    def test_result_and_edges_are_json_safe_and_observation_is_used_once(self) -> None:
        result = match_labels(
            [self.label("L1", "Figure 6A"), self.label("L2", "Figure 6A")],
            [self.observation("O1", "Figure 6A")],
        )
        payload = result.to_dict()
        json.dumps(payload)
        self.assertEqual(len(result.matches), 1)
        self.assertEqual(len(result.candidate_edges), 2)
        self.assertIn("components", payload["candidate_edges"][0])


class BriaBenchMetricAggregationTests(unittest.TestCase):
    def aggregate(self, cases: list[dict[str, object]]) -> dict[str, object]:
        return aggregate_metrics(
            cases=cases,
            benchmark_id="bria-bench-dev",
            benchmark_version="0.1.0",
        )

    def test_three_case_plan_separates_detection_and_silent_failure(self) -> None:
        positive = metric_bundle("positive", matched=True)
        negative = metric_bundle("negative", negative=True)
        failed = metric_bundle("failed", status="process_error")
        failed["run_result"]["failure"]["module"] = "image_detector"

        result = self.aggregate([positive, negative, failed])

        self.assertEqual(
            result["detection"]["expected_finding_recall"],
            {"numerator": 1, "denominator": 2, "value": 0.5},
        )
        self.assertEqual(
            result["detection"]["negative_package_false_alert_rate"],
            {"numerator": 0, "denominator": 1, "value": 0.0},
        )
        self.assertEqual(
            result["reliability"]["silent_failure_rate"],
            {"numerator": 1, "denominator": 3, "value": 1 / 3},
        )
        self.assertNotIn("score", result)
        self.assertNotIn("overall_score", result)
        validate_contract("metrics.schema.json", result)

    def test_zero_denominators_and_failed_negative_are_conservative(self) -> None:
        empty = self.aggregate([])
        for section in (empty["detection"], empty["reliability"]):
            for metric in section.values():
                if "denominator" in metric:
                    self.assertEqual(
                        metric, {"numerator": 0, "denominator": 0, "value": None}
                    )

        failed_negative = metric_bundle(
            "failed-negative", negative=True, status="timeout"
        )
        failed_negative["run_result"]["telemetry"]["timed_out"] = True
        failed_negative["run_result"]["failure"]["timed_out"] = True
        result = self.aggregate([failed_negative])
        self.assertEqual(
            result["detection"]["negative_package_false_alert_rate"],
            {"numerator": 1, "denominator": 1, "value": 1.0},
        )

    def test_track_review_and_scope_boundaries_are_enforced(self) -> None:
        regression = metric_bundle("regression", matched=True, track="regression")
        regression["regression_assertions"] = [True, False, True]
        concern = metric_bundle(
            "concern", matched=True, track="public_concern", scope="localization_only"
        )
        robust = metric_bundle("robust", matched=True, track="robustness_scale")
        robust["attack_resisted"] = True
        pending = metric_bundle(
            "pending", matched=True, review_status="independent_pending"
        )
        ambiguous = metric_bundle("ambiguous", matched=True, review_status="ambiguous")

        result = self.aggregate([regression, concern, robust, pending, ambiguous])

        self.assertEqual(
            result["detection"]["expected_finding_recall"],
            {"numerator": 0, "denominator": 0, "value": None},
        )
        self.assertEqual(
            result["detection"]["public_concern_location_coverage"],
            {"numerator": 1, "denominator": 1, "value": 1.0},
        )
        self.assertEqual(
            result["detection"]["regression_assertions"],
            {"met": 2, "not_met": 1, "total": 3},
        )
        self.assertEqual(
            result["reliability"]["manifest_attack_resistance"],
            {"numerator": 1, "denominator": 1, "value": 1.0},
        )
        self.assertFalse(
            next(
                item for item in result["case_results"] if item["case_id"] == "pending"
            )["headline_detection_eligible"]
        )

    def test_match_counts_are_one_to_one_and_risk_uses_matched_denominator(
        self,
    ) -> None:
        case = metric_bundle("risk", matched=True)
        match = case["match_result"].matches[0]
        case["match_result"] = MatchResult(
            matches=(
                Match(
                    match.label_id,
                    match.observation_id,
                    Compatibility(True, True, True, False, (1,)),
                ),
            ),
            unmatched_label_ids=(),
            unmatched_observation_ids=(),
            candidate_edges=(),
            assignment_ambiguous=False,
        )
        result = self.aggregate([case])
        self.assertEqual(
            result["detection"]["risk_band_agreement"],
            {"numerator": 0, "denominator": 1, "value": 0.0},
        )
        self.assertEqual(result["case_results"][0]["matched_label_count"], 1)

    def test_failure_events_use_module_and_detail_and_process_fallback(self) -> None:
        partial = metric_bundle("partial")
        normalized = partial["run_result"]["normalized_observation"]
        normalized["technical_failures"] = [
            {"module": "images", "failure_type": "decode"},
            {"module": "images", "failure_type": "timeout"},
        ]
        normalized["reported_technical_failures"] = [
            {"module": "images", "failure_type": "decode"}
        ]
        process = metric_bundle("process", status="process_error")
        process["run_result"]["failure"]["module"] = "runner"

        result = self.aggregate([partial, process])

        self.assertEqual(
            result["reliability"]["technical_failure_disclosure_rate"],
            {"numerator": 1, "denominator": 3, "value": 1 / 3},
        )
        self.assertEqual(
            result["reliability"]["silent_failure_rate"],
            {"numerator": 2, "denominator": 2, "value": 1.0},
        )

    def test_performance_is_nearest_rank_profiled_and_explicitly_budgeted(self) -> None:
        cases = []
        for index, (elapsed, profile) in enumerate(
            ((4.0, "deep"), (1.0, "quick"), (3.0, "deep"), (2.0, "standard"))
        ):
            case = metric_bundle(f"case-{index}", profile=profile)
            telemetry = case["run_result"]["telemetry"]
            telemetry.update(
                {
                    "elapsed_seconds": elapsed,
                    "cpu_seconds": elapsed / 2,
                    "peak_rss_bytes": int(elapsed * 100),
                    "output_size_bytes": int(elapsed * 10),
                    "module_seconds": {"images": elapsed / 4},
                    "llm": {
                        "provider": "fixture",
                        "model": "model",
                        "input_tokens": int(elapsed * 10),
                        "output_tokens": int(elapsed * 2),
                        "latency_seconds": elapsed / 3,
                        "estimated_cost_cny": elapsed / 100,
                    },
                }
            )
            if index != 3:
                case["over_budget"] = index == 0
            cases.append(case)

        result = self.aggregate(cases)
        wall = result["performance"]["wall_time_seconds"]
        self.assertEqual(wall["values"], [1.0, 2.0, 3.0, 4.0])
        self.assertEqual((wall["p50"], wall["p95"]), (2.0, 4.0))
        self.assertEqual(
            result["performance"]["profiles"]["deep"]["wall_time_seconds"]["values"],
            [3.0, 4.0],
        )
        self.assertEqual(result["performance"]["module_seconds"]["images"]["p50"], 0.5)
        self.assertEqual(
            result["performance"]["llm_input_tokens"]["values"], [10, 20, 30, 40]
        )
        self.assertEqual(
            result["performance"]["over_budget_rate"],
            {"numerator": 1, "denominator": 3, "value": 1 / 3},
        )

    def test_nearest_rank_handles_small_odd_and_even_samples(self) -> None:
        expected = {
            (9.0,): (9.0, 9.0),
            (1.0, 2.0): (1.0, 2.0),
            (1.0, 2.0, 3.0): (2.0, 3.0),
            (1.0, 2.0, 3.0, 4.0): (2.0, 4.0),
        }
        for values, percentiles in expected.items():
            with self.subTest(values=values):
                cases = []
                for index, value in enumerate(reversed(values)):
                    case = metric_bundle(f"case-{index}")
                    case["run_result"]["telemetry"]["elapsed_seconds"] = value
                    cases.append(case)
                distribution = self.aggregate(cases)["performance"]["wall_time_seconds"]
                self.assertEqual(
                    (distribution["p50"], distribution["p95"]), percentiles
                )

    def test_explicit_preservation_facts_order_and_inputs_are_stable(self) -> None:
        second = metric_bundle("b")
        second.update(
            {"atomic_output_preserved": False, "previous_output_preserved": True}
        )
        first = metric_bundle("a")
        first.update(
            {"atomic_output_preserved": True, "previous_output_preserved": False}
        )
        before = copy.deepcopy([second, first])

        left = self.aggregate([second, first])
        right = self.aggregate([first, second])

        self.assertEqual(left, right)
        self.assertEqual([second, first], before)
        self.assertNotIn("generated_at", left)
        self.assertEqual([item["case_id"] for item in left["case_results"]], ["a", "b"])
        self.assertEqual(
            left["reliability"]["atomic_output_preservation"],
            {"numerator": 1, "denominator": 2, "value": 0.5},
        )
        self.assertEqual(
            left["reliability"]["previous_result_preservation"],
            {"numerator": 1, "denominator": 2, "value": 0.5},
        )

    def test_malformed_bundle_fails_closed(self) -> None:
        case = metric_bundle("bad")
        case["run_result"]["case_id"] = "other"
        with self.assertRaises((ValueError, ContractError)):
            self.aggregate([case])

        malformed_match = metric_bundle("bad-match", matched=True)
        malformed_match["match_result"] = malformed_match["match_result"].to_dict()
        malformed_match["match_result"]["matches"][0]["observation_id"] = "unknown"
        with self.assertRaises((ValueError, ContractError)):
            self.aggregate([malformed_match])

        incomplete = metric_bundle("incomplete")
        incomplete["match_result"] = incomplete["match_result"].to_dict()
        incomplete["match_result"]["unmatched_label_ids"] = []
        with self.assertRaises((ValueError, ContractError)):
            self.aggregate([incomplete])

        unknown_fact = metric_bundle("unknown-fact")
        unknown_fact["attack_resistance"] = True
        with self.assertRaises((ValueError, ContractError)):
            self.aggregate([unknown_fact])


if __name__ == "__main__":
    unittest.main()
