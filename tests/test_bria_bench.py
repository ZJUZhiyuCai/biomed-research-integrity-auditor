from __future__ import annotations

import copy
import json
import re
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

from jsonschema import Draft202012Validator

from benchmarks.bria_bench import ContractError, __version__, validate_contract
from benchmarks.bria_bench.contracts import SCHEMA_ROOT, load_schema
from benchmarks.bria_bench.hashing import HashingError, hash_tree
from benchmarks.bria_bench.registry import (
    RegistryError,
    freeze_manifest,
    load_manifest,
    resolve_case_paths,
    resolve_inside,
    verify_frozen_case,
)


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
        self.root = Path(self._temporary.name)
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

    def test_tree_hash_is_stable_content_sensitive_and_root_name_independent(self) -> None:
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
                (package / "link").symlink_to(target)
                with self.assertRaises(HashingError):
                    hash_tree(package)

        root_link = self.root / "root-link"
        root_link.symlink_to(self.root / "cases" / "dev_001", target_is_directory=True)
        with self.assertRaises(HashingError):
            hash_tree(root_link)

    def test_resolver_rejects_empty_absolute_traversal_and_symlink_paths(self) -> None:
        outside = self.root / "outside"
        outside.mkdir()
        (outside / "package").mkdir()
        (self.root / "link").symlink_to(outside, target_is_directory=True)
        for value in ("", "/tmp/absolute", "../private", "link/package"):
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
        incomplete["cases"][0]["expected_sha256"] = "a" * 64
        incomplete_path = self.write_manifest("incomplete.json", incomplete)
        with self.assertRaisesRegex(RegistryError, "expected_sha256"):
            load_manifest(incomplete_path, require_frozen=True)

        invalid_hash = self.manifest(cases=[first])
        invalid_hash["cases"][0]["expected_sha256"] = "A" * 64
        invalid_hash_path = self.write_manifest("invalid-hash.json", invalid_hash)
        with self.assertRaises(RegistryError):
            load_manifest(invalid_hash_path)

    def test_freeze_preserves_case_order_and_verifies_frozen_case(self) -> None:
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

        mismatch = dict(frozen["cases"][0], expected_sha256="0" * 64)
        with self.assertRaisesRegex(RegistryError, "Case ID first.*expected.*actual"):
            verify_frozen_case(self.root, mismatch)

    def test_failed_freeze_serialization_and_replace_preserve_previous_output(self) -> None:
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


if __name__ == "__main__":
    unittest.main()
