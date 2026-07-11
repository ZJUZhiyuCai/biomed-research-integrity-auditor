from __future__ import annotations

import copy
import unittest

from jsonschema import Draft202012Validator

from benchmarks.bria_bench import ContractError, __version__, validate_contract
from benchmarks.bria_bench.contracts import SCHEMA_ROOT, load_schema


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
        },
        "output_paths": {"case_output": "results/dev_001"},
        "normalized_observation": minimal_observation(),
        "failure": None,
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

    def test_metrics_rejects_composite_score_fields(self) -> None:
        for key in ("score", "overall_score"):
            with self.subTest(key=key):
                payload = minimal_metrics()
                payload[key] = 1.0
                with self.assertRaises(ContractError):
                    validate_contract("metrics.schema.json", payload)

    def test_schema_filename_resolution_is_safe(self) -> None:
        for name in (
            "../annotation.schema.json",
            "schemas/annotation.schema.json",
            "/tmp/annotation.schema.json",
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


if __name__ == "__main__":
    unittest.main()
