from __future__ import annotations

import copy
import json
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest

from benchmarks.bria_bench.registry import (
    RegistryError,
    freeze_manifest,
    load_manifest,
    resolve_case_paths,
    verify_frozen_case,
    verify_independent_review_proof,
)
from benchmarks.bria_bench.reviewer_packet import (
    ReviewerPacketError,
    export_reviewer_packet,
)
from benchmarks.bria_bench.reviewer_workflow import (
    ReviewerWorkflowError,
    compare_reviewer_submissions,
    finalize_reviewer_labels,
    lock_reviewer_submission,
)


def _json_bytes(payload: object) -> bytes:
    return (
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")


class IndependentReviewerWorkflowFixture(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name).resolve()
        (self.root / "cases").mkdir()
        (self.root / "annotations").mkdir()
        self.case_ids = ("sealed_alpha", "sealed_beta")
        for index, case_id in enumerate(self.case_ids, start=1):
            package = self.root / "cases" / case_id
            package.mkdir()
            (package / "manuscript.txt").write_text(
                f"Controlled study record number {index}.\n",
                encoding="utf-8",
            )
            (package / "figure.png").write_bytes(
                b"not-a-real-image-but-neutral-review-material"
            )
            annotation = {
                "schema_version": "1.0.0",
                "case_id": case_id,
                "negative_control": False,
                "review_status": "independent_pending",
                "expected_observations": [],
            }
            (self.root / "annotations" / f"{case_id}.json").write_bytes(
                _json_bytes(annotation)
            )
        self.source_manifest = self.root / "benchmark_manifest.source.json"
        self.manifest = self.root / "benchmark_manifest.json"
        self.source_manifest.write_bytes(
            _json_bytes(
                {
                    "schema_version": "1.0.0",
                    "benchmark_id": "sealed-review-tests",
                    "benchmark_version": "1.0.0",
                    "cases": [
                        {
                            "case_id": case_id,
                            "track": "blinded_challenge",
                            "split": "test",
                            "package_path": f"cases/{case_id}",
                            "annotation_path": f"annotations/{case_id}.json",
                            "mode": "internal_presubmission",
                            "scan_profile": "standard",
                            "redistributable": True,
                            "license": "MIT",
                            "headline_eligible": False,
                        }
                        for case_id in self.case_ids
                    ],
                }
            )
        )
        self.refreeze()
        self.seed_a = self.root / "seed-a"
        self.seed_b = self.root / "seed-b"
        self.seed_a.write_text("11" * 32, encoding="ascii")
        self.seed_b.write_text("22" * 32, encoding="ascii")
        self.seed_a.chmod(0o600)
        self.seed_b.chmod(0o600)
        self.packet_a = self.root / "packet-a"
        self.packet_b = self.root / "packet-b"
        self.mapping_a = self.root / "mapping-a.json"
        self.mapping_b = self.root / "mapping-b.json"

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def refreeze(self) -> None:
        freeze_manifest(
            self.source_manifest,
            self.manifest,
            "2026-07-12T00:00:00Z",
        )

    def export_packets(self) -> None:
        for packet, mapping, seed in (
            (self.packet_a, self.mapping_a, self.seed_a),
            (self.packet_b, self.mapping_b, self.seed_b),
        ):
            export_reviewer_packet(
                self.manifest,
                self.case_ids,
                packet,
                mapping,
                seed,
                packet_scope="independent_blinded",
            )

    def reviewer_case_id(self, mapping_path: Path, source_case_id: str) -> str:
        mapping = json.loads(mapping_path.read_text(encoding="utf-8"))
        return next(
            item["reviewer_case_id"]
            for item in mapping["cases"]
            if item["source_case_id"] == source_case_id
        )

    def present_row(self, reviewer_case_id: str, *, wording: str) -> dict[str, object]:
        return {
            "reviewer_case_id": reviewer_case_id,
            "reviewer_observation_id": f"{reviewer_case_id}-O001",
            "presence": "present",
            "issue_family": "image_similarity",
            "comment_class": "major",
            "risk_range": ["R2", "R3"],
            "locations": ["Figure 1, panel A"],
            "observation": f"A reproducible panel similarity is visible {wording}.",
            "minimum_review_comment": "Please verify the panel against the original acquisition files.",
            "scientific_relevance": "The panel supports a central experimental comparison.",
            "benign_explanations": ["The panels may intentionally show the same field."],
            "required_materials": ["Original acquisition files and assembly history."],
            "recommended_action": "Compare the originals and document the assembly relationship.",
        }

    def absent_row(self, reviewer_case_id: str) -> dict[str, object]:
        return {
            "reviewer_case_id": reviewer_case_id,
            "reviewer_observation_id": f"{reviewer_case_id}-O001",
            "presence": "absent",
            "issue_family": None,
            "comment_class": None,
            "risk_range": None,
            "locations": [],
            "observation": "",
            "minimum_review_comment": "",
            "scientific_relevance": "",
            "benign_explanations": [],
            "required_materials": [],
            "recommended_action": "",
        }

    def fill_packet(
        self,
        packet: Path,
        mapping: Path,
        *,
        alpha_present: bool,
        wording: str,
    ) -> None:
        alpha = self.reviewer_case_id(mapping, "sealed_alpha")
        beta = self.reviewer_case_id(mapping, "sealed_beta")
        alpha_payload = (
            [self.present_row(alpha, wording=wording)]
            if alpha_present
            else [self.absent_row(alpha)]
        )
        (packet / "forms" / f"{alpha}.json").write_bytes(_json_bytes(alpha_payload))
        (packet / "forms" / f"{beta}.json").write_bytes(
            _json_bytes([self.absent_row(beta)])
        )

    def private_id(self, filename: str, value: str) -> Path:
        path = self.root / filename
        path.write_text(value + "\n", encoding="ascii")
        path.chmod(0o600)
        return path

    def lock_pair(self) -> tuple[Path, Path]:
        locked_a = self.root / "locked-a"
        locked_b = self.root / "locked-b"
        lock_reviewer_submission(
            self.packet_a,
            self.private_id("reviewer-a.id", "BRIA-REV-A0000001"),
            locked_a,
            locked_at="2026-07-12T01:00:00Z",
        )
        lock_reviewer_submission(
            self.packet_b,
            self.private_id("reviewer-b.id", "BRIA-REV-B0000002"),
            locked_b,
            locked_at="2026-07-12T01:05:00Z",
        )
        return locked_a, locked_b


class IndependentReviewerWorkflowTests(IndependentReviewerWorkflowFixture):
    def test_full_consensus_flow_locks_compares_and_finalizes(self) -> None:
        self.export_packets()
        self.fill_packet(
            self.packet_a,
            self.mapping_a,
            alpha_present=True,
            wording="in the supplied figure",
        )
        self.fill_packet(
            self.packet_b,
            self.mapping_b,
            alpha_present=True,
            wording="at the indicated location",
        )
        locked_a, locked_b = self.lock_pair()
        comparison_dir = self.root / "comparison"
        comparison = compare_reviewer_submissions(
            locked_a,
            locked_b,
            comparison_dir,
            compared_at="2026-07-12T02:00:00Z",
        )
        self.assertEqual(comparison["agreement"]["presence"]["value"], 1.0)
        self.assertEqual(comparison["agreement"]["presence_kappa"]["value"], 1.0)
        self.assertEqual(comparison["agreement"]["comment_class"]["value"], 1.0)
        self.assertEqual(comparison["agreement"]["location"]["value"], 1.0)
        self.assertTrue(all(case["status"] == "consensus" for case in comparison["cases"]))
        template = json.loads(
            (comparison_dir / "adjudication_template.json").read_text(encoding="utf-8")
        )
        self.assertEqual(template["cases"], [])

        final_dir = self.root / "final"
        finalization = finalize_reviewer_labels(
            comparison_dir / "comparison.json",
            locked_a,
            self.mapping_a,
            locked_b,
            self.mapping_b,
            self.manifest,
            final_dir,
            frozen_at="2026-07-12T03:00:00Z",
            benchmark_version="1.0.0",
        )
        self.assertEqual(
            {item["review_status"] for item in finalization["cases"]},
            {"independent_adjudicated"},
        )
        annotations = [
            json.loads(path.read_text(encoding="utf-8"))
            for path in (final_dir / "annotations").glob("*.json")
        ]
        by_id = {item["case_id"]: item for item in annotations}
        self.assertFalse(by_id["sealed_alpha"]["negative_control"])
        self.assertEqual(len(by_id["sealed_alpha"]["expected_observations"]), 1)
        self.assertTrue(by_id["sealed_beta"]["negative_control"])
        self.assertEqual(by_id["sealed_beta"]["expected_observations"], [])
        for path in final_dir.rglob("*"):
            expected = 0o700 if path.is_dir() else 0o600
            self.assertEqual(stat.S_IMODE(path.lstat().st_mode), expected)

        proof_dir = self.root / "review_proofs"
        annotation_dir = self.root / "release_annotations"
        proof_dir.mkdir()
        annotation_dir.mkdir()
        proof_path = proof_dir / "review_proof_v1.json"
        shutil.copy2(final_dir / "finalization.json", proof_path)
        release_source = json.loads(self.source_manifest.read_text(encoding="utf-8"))
        records = {item["source_case_id"]: item for item in finalization["cases"]}
        for case in release_source["cases"]:
            source_id = case["case_id"]
            finalized_annotation = final_dir / records[source_id]["annotation_path"]
            target_annotation = annotation_dir / f"{source_id}.json"
            shutil.copy2(finalized_annotation, target_annotation)
            case.update(
                {
                    "annotation_path": target_annotation.relative_to(self.root).as_posix(),
                    "headline_eligible": True,
                    "review_proof_path": proof_path.relative_to(self.root).as_posix(),
                }
            )
        release_source_path = self.root / "release_manifest.source.json"
        release_manifest_path = self.root / "release_manifest.json"
        release_source_path.write_bytes(_json_bytes(release_source))
        freeze_manifest(
            release_source_path,
            release_manifest_path,
            "2026-07-12T03:30:00Z",
        )
        release_manifest = load_manifest(
            release_manifest_path, require_frozen=True, resolve_paths=False
        )
        for case in release_manifest["cases"]:
            verify_frozen_case(self.root, case)
            _, annotation_path = resolve_case_paths(self.root, case)
            annotation = json.loads(annotation_path.read_text(encoding="utf-8"))
            self.assertTrue(
                verify_independent_review_proof(self.root, case, annotation)
            )
        proof = json.loads(proof_path.read_text(encoding="utf-8"))
        proof["benchmark_version"] = "9.9.9"
        proof_path.write_bytes(_json_bytes(proof))
        with self.assertRaisesRegex(RegistryError, "review proof hash mismatch"):
            verify_frozen_case(self.root, release_manifest["cases"][0])

    def test_cli_executes_lock_compare_and_consensus_finalize(self) -> None:
        self.export_packets()
        self.fill_packet(
            self.packet_a,
            self.mapping_a,
            alpha_present=True,
            wording="in the supplied figure",
        )
        self.fill_packet(
            self.packet_b,
            self.mapping_b,
            alpha_present=True,
            wording="at the indicated location",
        )
        reviewer_a = self.private_id("reviewer-a.id", "BRIA-REV-A0000001")
        reviewer_b = self.private_id("reviewer-b.id", "BRIA-REV-B0000002")
        locked_a = self.root / "locked-a"
        locked_b = self.root / "locked-b"
        repository = Path(__file__).resolve().parents[1]

        commands = [
            [
                "reviewer-lock",
                "--packet-dir",
                str(self.packet_a),
                "--reviewer-id-file",
                str(reviewer_a),
                "--output-dir",
                str(locked_a),
                "--locked-at",
                "2026-07-12T01:00:00Z",
            ],
            [
                "reviewer-lock",
                "--packet-dir",
                str(self.packet_b),
                "--reviewer-id-file",
                str(reviewer_b),
                "--output-dir",
                str(locked_b),
                "--locked-at",
                "2026-07-12T01:05:00Z",
            ],
        ]
        for arguments in commands:
            result = subprocess.run(
                [sys.executable, "-m", "benchmarks.bria_bench.cli", *arguments],
                cwd=repository,
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)

        comparison = self.root / "comparison"
        compare = subprocess.run(
            [
                sys.executable,
                "-m",
                "benchmarks.bria_bench.cli",
                "reviewer-compare",
                "--submission-a",
                str(locked_a),
                "--submission-b",
                str(locked_b),
                "--output-dir",
                str(comparison),
                "--compared-at",
                "2026-07-12T02:00:00Z",
            ],
            cwd=repository,
            capture_output=True,
            text=True,
        )
        self.assertEqual(compare.returncode, 0, compare.stderr)
        finalized = self.root / "finalized"
        finalize = subprocess.run(
            [
                sys.executable,
                "-m",
                "benchmarks.bria_bench.cli",
                "reviewer-finalize",
                "--comparison",
                str(comparison / "comparison.json"),
                "--submission-a",
                str(locked_a),
                "--mapping-a",
                str(self.mapping_a),
                "--submission-b",
                str(locked_b),
                "--mapping-b",
                str(self.mapping_b),
                "--manifest",
                str(self.manifest),
                "--output-dir",
                str(finalized),
                "--frozen-at",
                "2026-07-12T03:00:00Z",
                "--benchmark-version",
                "1.0.0",
            ],
            cwd=repository,
            capture_output=True,
            text=True,
        )
        self.assertEqual(finalize.returncode, 0, finalize.stderr)
        self.assertTrue((finalized / "finalization.json").is_file())

    def test_disagreement_requires_distinct_completed_adjudication(self) -> None:
        self.export_packets()
        self.fill_packet(
            self.packet_a,
            self.mapping_a,
            alpha_present=True,
            wording="in the supplied figure",
        )
        self.fill_packet(
            self.packet_b,
            self.mapping_b,
            alpha_present=False,
            wording="unused",
        )
        locked_a, locked_b = self.lock_pair()
        comparison_dir = self.root / "comparison"
        comparison = compare_reviewer_submissions(
            locked_a,
            locked_b,
            comparison_dir,
            compared_at="2026-07-12T02:00:00Z",
        )
        disagreement = next(case for case in comparison["cases"] if case["status"] == "disagreement")
        self.assertEqual(
            comparison["agreement"]["location"],
            {"numerator": 0, "denominator": 1, "value": 0.0},
        )
        self.assertEqual(
            comparison["agreement"]["risk_range"],
            {"numerator": 0, "denominator": 1, "value": 0.0},
        )
        with self.assertRaisesRegex(ReviewerWorkflowError, "require completed adjudication"):
            finalize_reviewer_labels(
                comparison_dir / "comparison.json",
                locked_a,
                self.mapping_a,
                locked_b,
                self.mapping_b,
                self.manifest,
                self.root / "missing-adjudication-final",
                frozen_at="2026-07-12T03:00:00Z",
                benchmark_version="1.0.0",
            )

        adjudication = json.loads(
            (comparison_dir / "adjudication_template.json").read_text(encoding="utf-8")
        )
        adjudication["status"] = "completed"
        adjudication["adjudicator_id"] = "BRIA-ADJ-C0000003"
        adjudication["adjudicated_at"] = "2026-07-12T02:30:00Z"
        item = next(
            row
            for row in adjudication["cases"]
            if row["comparison_case_id"] == disagreement["comparison_case_id"]
        )
        item["resolution"] = "ambiguous"
        item["rationale"] = "The supplied record does not resolve the independent disagreement."
        completed = self.root / "completed-adjudication.json"
        completed.write_bytes(_json_bytes(adjudication))
        completed.chmod(0o600)
        final_dir = self.root / "ambiguous-final"
        finalization = finalize_reviewer_labels(
            comparison_dir / "comparison.json",
            locked_a,
            self.mapping_a,
            locked_b,
            self.mapping_b,
            self.manifest,
            final_dir,
            frozen_at="2026-07-12T03:00:00Z",
            benchmark_version="1.0.0",
            adjudication_path=completed,
        )
        ambiguous = next(
            row for row in finalization["cases"] if row["review_status"] == "ambiguous"
        )
        self.assertFalse(ambiguous["eligible_for_manifest_promotion"])

    def test_resolved_adjudication_generates_promotable_annotation(self) -> None:
        self.export_packets()
        self.fill_packet(
            self.packet_a,
            self.mapping_a,
            alpha_present=True,
            wording="in the supplied figure",
        )
        self.fill_packet(
            self.packet_b,
            self.mapping_b,
            alpha_present=False,
            wording="unused",
        )
        locked_a, locked_b = self.lock_pair()
        comparison_dir = self.root / "comparison"
        comparison = compare_reviewer_submissions(
            locked_a,
            locked_b,
            comparison_dir,
            compared_at="2026-07-12T02:00:00Z",
        )
        disagreement = next(case for case in comparison["cases"] if case["status"] == "disagreement")
        source_row = next(
            row for row in disagreement["reviewer_a_rows"] if row["presence"] == "present"
        )
        final_row = {
            "final_observation_id": "FINAL-O001",
            "source_reviewer_observation_ids": [
                source_row["reviewer_observation_id"]
            ],
            "presence": source_row["presence"],
            "issue_family": source_row["issue_family"],
            "comment_class": source_row["comment_class"],
            "risk_range": source_row["risk_range"],
            "locations": source_row["locations"],
            "expected_fact": source_row["observation"],
            "minimum_review_comment": source_row["minimum_review_comment"],
            "scientific_relevance": source_row["scientific_relevance"],
            "benign_explanations": source_row["benign_explanations"],
            "required_materials": source_row["required_materials"],
            "recommended_action": source_row["recommended_action"],
        }
        adjudication = json.loads(
            (comparison_dir / "adjudication_template.json").read_text(encoding="utf-8")
        )
        adjudication.update(
            {
                "status": "completed",
                "adjudicator_id": "BRIA-ADJ-C0000003",
                "adjudicated_at": "2026-07-12T02:30:00Z",
            }
        )
        item = next(
            row
            for row in adjudication["cases"]
            if row["comparison_case_id"] == disagreement["comparison_case_id"]
        )
        item.update(
            {
                "resolution": "resolved",
                "final_presence": "present",
                "final_rows": [final_row],
                "rationale": "The original materials support the reproducible observation.",
            }
        )
        invented = copy.deepcopy(adjudication)
        invented["cases"][0]["final_rows"][0][
            "source_reviewer_observation_ids"
        ] = ["BRIA-R999-O999"]
        invented_path = self.root / "invented-adjudication.json"
        invented_path.write_bytes(_json_bytes(invented))
        invented_path.chmod(0o600)
        with self.assertRaisesRegex(ReviewerWorkflowError, "outside the locked"):
            finalize_reviewer_labels(
                comparison_dir / "comparison.json",
                locked_a,
                self.mapping_a,
                locked_b,
                self.mapping_b,
                self.manifest,
                self.root / "invented-final",
                frozen_at="2026-07-12T03:00:00Z",
                benchmark_version="1.0.0",
                adjudication_path=invented_path,
            )
        no_location = copy.deepcopy(adjudication)
        no_location["cases"][0]["final_rows"][0]["locations"] = []
        no_location_path = self.root / "no-location-adjudication.json"
        no_location_path.write_bytes(_json_bytes(no_location))
        no_location_path.chmod(0o600)
        with self.assertRaisesRegex(ReviewerWorkflowError, "final locations"):
            finalize_reviewer_labels(
                comparison_dir / "comparison.json",
                locked_a,
                self.mapping_a,
                locked_b,
                self.mapping_b,
                self.manifest,
                self.root / "no-location-final",
                frozen_at="2026-07-12T03:00:00Z",
                benchmark_version="1.0.0",
                adjudication_path=no_location_path,
            )
        completed = self.root / "completed-adjudication.json"
        completed.write_bytes(_json_bytes(adjudication))
        completed.chmod(0o600)
        finalization = finalize_reviewer_labels(
            comparison_dir / "comparison.json",
            locked_a,
            self.mapping_a,
            locked_b,
            self.mapping_b,
            self.manifest,
            self.root / "resolved-final",
            frozen_at="2026-07-12T03:00:00Z",
            benchmark_version="1.0.0",
            adjudication_path=completed,
        )
        resolved = next(
            row
            for row in finalization["cases"]
            if row["source_case_id"] == "sealed_alpha"
        )
        self.assertEqual(resolved["review_status"], "independent_adjudicated")
        self.assertTrue(resolved["eligible_for_manifest_promotion"])

    def test_all_absent_comparison_keeps_undefined_metrics_explicit(self) -> None:
        self.export_packets()
        self.fill_packet(self.packet_a, self.mapping_a, alpha_present=False, wording="unused")
        self.fill_packet(self.packet_b, self.mapping_b, alpha_present=False, wording="unused")
        locked_a, locked_b = self.lock_pair()
        comparison = compare_reviewer_submissions(
            locked_a,
            locked_b,
            self.root / "comparison",
            compared_at="2026-07-12T02:00:00Z",
        )
        self.assertEqual(comparison["agreement"]["presence"]["value"], 1.0)
        self.assertEqual(
            comparison["agreement"]["presence_kappa"]["status"],
            "undefined_constant_marginals",
        )
        self.assertIsNone(comparison["agreement"]["comment_class"]["value"])
        self.assertEqual(
            comparison["agreement"]["comment_class_kappa"]["status"],
            "undefined_no_units",
        )

    def test_finalize_recomputes_and_rejects_modified_consensus(self) -> None:
        self.export_packets()
        self.fill_packet(
            self.packet_a,
            self.mapping_a,
            alpha_present=True,
            wording="in the supplied figure",
        )
        self.fill_packet(
            self.packet_b,
            self.mapping_b,
            alpha_present=True,
            wording="at the indicated location",
        )
        locked_a, locked_b = self.lock_pair()
        comparison_dir = self.root / "comparison"
        compare_reviewer_submissions(
            locked_a,
            locked_b,
            comparison_dir,
            compared_at="2026-07-12T02:00:00Z",
        )
        comparison_path = comparison_dir / "comparison.json"
        comparison = json.loads(comparison_path.read_text(encoding="utf-8"))
        positive = next(case for case in comparison["cases"] if case["consensus_rows"])
        positive["consensus_rows"][0]["expected_fact"] = "Modified after comparison."
        comparison_path.write_bytes(_json_bytes(comparison))
        comparison_path.chmod(0o600)
        final_dir = self.root / "tampered-final"
        with self.assertRaisesRegex(ReviewerWorkflowError, "does not match the two locked"):
            finalize_reviewer_labels(
                comparison_path,
                locked_a,
                self.mapping_a,
                locked_b,
                self.mapping_b,
                self.manifest,
                final_dir,
                frozen_at="2026-07-12T03:00:00Z",
                benchmark_version="1.0.0",
            )
        self.assertFalse(final_dir.exists())

    def test_same_reviewer_cannot_supply_both_locked_submissions(self) -> None:
        self.export_packets()
        self.fill_packet(self.packet_a, self.mapping_a, alpha_present=False, wording="unused")
        self.fill_packet(self.packet_b, self.mapping_b, alpha_present=False, wording="unused")
        reviewer = self.private_id("reviewer.id", "BRIA-REV-A0000001")
        locked_a = self.root / "locked-a"
        locked_b = self.root / "locked-b"
        lock_reviewer_submission(
            self.packet_a,
            reviewer,
            locked_a,
            locked_at="2026-07-12T01:00:00Z",
        )
        lock_reviewer_submission(
            self.packet_b,
            reviewer,
            locked_b,
            locked_at="2026-07-12T01:05:00Z",
        )
        with self.assertRaisesRegex(ReviewerWorkflowError, "distinct reviewer IDs"):
            compare_reviewer_submissions(
                locked_a,
                locked_b,
                self.root / "comparison",
                compared_at="2026-07-12T02:00:00Z",
            )

    def test_demo_packet_cannot_enter_independent_lock(self) -> None:
        export_reviewer_packet(
            self.manifest,
            self.case_ids,
            self.packet_a,
            self.mapping_a,
            self.seed_a,
        )
        reviewer = self.private_id("reviewer.id", "BRIA-REV-A0000001")
        with self.assertRaisesRegex(ReviewerWorkflowError, "Only independent_blinded"):
            lock_reviewer_submission(
                self.packet_a,
                reviewer,
                self.root / "locked",
                locked_at="2026-07-12T01:00:00Z",
            )

    def test_independent_export_rejects_answer_labels_and_package_notes(self) -> None:
        annotation_path = self.root / "annotations" / "sealed_alpha.json"
        annotation = json.loads(annotation_path.read_text(encoding="utf-8"))
        annotation["expected_observations"] = [
            {
                "observation_id": "leaked",
                "role": "recall_label",
                "issue_family": "image_similarity",
                "location": "Figure 1",
                "risk_range": ["R2", "R3"],
                "benign_explanations": ["A benign explanation."],
                "required_materials": ["Original files."],
            }
        ]
        annotation_path.write_bytes(_json_bytes(annotation))
        self.refreeze()
        with self.assertRaisesRegex(ReviewerPacketError, "must not contain answer labels"):
            export_reviewer_packet(
                self.manifest,
                self.case_ids,
                self.packet_a,
                self.mapping_a,
                self.seed_a,
                packet_scope="independent_blinded",
            )

        annotation["expected_observations"] = []
        annotation_path.write_bytes(_json_bytes(annotation))
        (self.root / "cases" / "sealed_alpha" / "PACKAGE_NOTE.txt").write_text(
            "Administrative cue.\n", encoding="utf-8"
        )
        self.refreeze()
        with self.assertRaisesRegex(ReviewerPacketError, "administrative cue"):
            export_reviewer_packet(
                self.manifest,
                self.case_ids,
                self.packet_a,
                self.mapping_a,
                self.seed_a,
                packet_scope="independent_blinded",
            )

    def test_lock_rejects_private_paths_and_unsafe_identity_permissions(self) -> None:
        self.export_packets()
        self.fill_packet(
            self.packet_a,
            self.mapping_a,
            alpha_present=True,
            wording="in the supplied figure",
        )
        reviewer = self.root / "reviewer.id"
        reviewer.write_text("BRIA-REV-A0000001\n", encoding="ascii")
        reviewer.chmod(0o644)
        with self.assertRaisesRegex(ReviewerWorkflowError, "mode 0600"):
            lock_reviewer_submission(
                self.packet_a,
                reviewer,
                self.root / "unsafe-id-lock",
                locked_at="2026-07-12T01:00:00Z",
            )

        reviewer.chmod(0o600)
        reviewer_case_id = self.reviewer_case_id(self.mapping_a, "sealed_alpha")
        path = self.packet_a / "forms" / f"{reviewer_case_id}.json"
        form = json.loads(path.read_text(encoding="utf-8"))
        form[0]["recommended_action"] = "Open /Users/private/reviewer-notes.txt."
        path.write_bytes(_json_bytes(form))
        with self.assertRaisesRegex(ReviewerWorkflowError, "absolute local path"):
            lock_reviewer_submission(
                self.packet_a,
                reviewer,
                self.root / "private-path-lock",
                locked_at="2026-07-12T01:00:00Z",
            )

    def test_lock_rejects_reformatted_manifest_and_duplicate_json_keys(self) -> None:
        self.export_packets()
        self.fill_packet(
            self.packet_a,
            self.mapping_a,
            alpha_present=False,
            wording="unused",
        )
        reviewer = self.private_id("reviewer.id", "BRIA-REV-A0000001")
        manifest_path = self.packet_a / "packet_manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        with self.assertRaisesRegex(ReviewerWorkflowError, "formatting changed"):
            lock_reviewer_submission(
                self.packet_a,
                reviewer,
                self.root / "reformatted-lock",
                locked_at="2026-07-12T01:00:00Z",
            )

        manifest_path.write_bytes(_json_bytes(manifest))
        reviewer_case_id = self.reviewer_case_id(self.mapping_a, "sealed_alpha")
        form_path = self.packet_a / "forms" / f"{reviewer_case_id}.json"
        duplicate = form_path.read_text(encoding="utf-8").replace(
            '"presence": "absent",',
            '"presence": "present",\n    "presence": "absent",',
            1,
        )
        form_path.write_text(duplicate, encoding="utf-8")
        with self.assertRaisesRegex(ReviewerWorkflowError, "duplicate JSON key"):
            lock_reviewer_submission(
                self.packet_a,
                reviewer,
                self.root / "duplicate-key-lock",
                locked_at="2026-07-12T01:00:00Z",
            )

if __name__ == "__main__":
    unittest.main()
