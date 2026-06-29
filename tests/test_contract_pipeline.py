from __future__ import annotations

import importlib.util
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
PYTHON = sys.executable
RISK_ORDER = {"R0": 0, "R1": 1, "R2": 2, "R3": 3, "R4": 4}

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from calibrators.contract_validation import ContractError, validate_instance  # noqa: E402
from calibrators.risk_cap_engine import calibrate_payload  # noqa: E402


def run(cmd: list[str]) -> None:
    subprocess.run(cmd, cwd=ROOT, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)


def load_report_assembler():
    path = ROOT / "skill" / "biomed-research-integrity-auditor" / "scripts" / "report_assembler.py"
    spec = importlib.util.spec_from_file_location("report_assembler", path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def risk_value(risk: str) -> int:
    return RISK_ORDER.get(risk, -1)


class ContractPipelineTests(unittest.TestCase):
    def test_image_detector_clusters_case004_and_keeps_flip_edge(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "case004_image.json"
            run([
                PYTHON,
                "detectors/image/global_near_duplicate.py",
                "evals/cases/case_004",
                "--output",
                str(output),
            ])
            payload = json.loads(output.read_text(encoding="utf-8"))
            validate_instance(payload, ROOT / "schemas" / "detector_output.schema.json", "case004 image detector")
            self.assertEqual(len(payload["candidates"]), 1)
            candidate = payload["candidates"][0]
            self.assertNotIn("risk_level", candidate)
            self.assertNotIn("calibrated_risk_level", candidate)
            self.assertEqual(candidate["candidate_type"], "image_reuse_cluster")
            transforms = {edge["best_transform"] for edge in candidate["evidence"]["edges"]}
            self.assertIn("flip_h", transforms)

    def test_case008_adaptive_weak_stats_default(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "case008_stats.json"
            run([
                PYTHON,
                "skill/biomed-research-integrity-auditor/scripts/stats_consistency_check.py",
                "evals/cases/case_008/source_data",
                "--output",
                str(output),
            ])
            payload = json.loads(output.read_text(encoding="utf-8"))
            validate_instance(payload, ROOT / "schemas" / "detector_output.schema.json", "case008 stats detector")
            self.assertGreater(len(payload["candidates"]), 0)
            weak = [item for item in payload["candidates"] if item["candidate_type"] == "weak_statistical_signal"]
            self.assertGreater(len(weak), 0)
            self.assertTrue(all(item["evidence_strength"] == "weak_signal" for item in weak))
            self.assertTrue(all(item["risk_suggestion"] == "R2_max" for item in weak))
            self.assertTrue(any(item["evidence"].get("effective_min_count") == 3 for item in weak))

    def test_reporter_rejects_uncalibrated_candidates(self) -> None:
        report_assembler = load_report_assembler()
        with self.assertRaises(ContractError):
            report_assembler.normalize_findings([{"candidates": [{"candidate_id": "X"}]}])


class RiskCapTests(unittest.TestCase):
    def detector_payload(self, risk_suggestion: str = "R4_possible") -> dict:
        return {
            "detector_name": "unit.test",
            "detector_version": "0.0",
            "input": {},
            "candidates": [
                {
                    "candidate_id": "UNIT-0001",
                    "detector": "unit.test",
                    "candidate_type": "weak_statistical_signal",
                    "locations": ["table.csv:col"],
                    "evidence": {"message": "synthetic weak signal"},
                    "evidence_strength": "weak_signal",
                    "risk_suggestion": risk_suggestion,
                    "risk_cap_tags": ["weak_statistical_signal", "weak_signal"],
                    "benign_explanations": ["rounding or export behavior may explain the pattern"],
                    "required_materials": ["source data", "analysis code"],
                    "recommended_action": "verify against source records",
                    "requires_contextual_calibration": True,
                }
            ],
            "errors": [],
        }

    def test_weak_stats_cannot_exceed_r2_and_yaml_changes_result(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            detector_output = tmp_path / "detector.json"
            detector_output.write_text(json.dumps(self.detector_payload()), encoding="utf-8")

            default_result = calibrate_payload(
                [detector_output],
                "internal_presubmission",
                ROOT / "schemas" / "risk_rules.yaml",
            )
            self.assertEqual(default_result["findings"][0]["calibrated_risk_level"], "R2")

            rules = yaml.safe_load((ROOT / "schemas" / "risk_rules.yaml").read_text(encoding="utf-8"))
            rules["detector_caps"]["weak_statistical_signal"]["max"] = "R1"
            altered_rules = tmp_path / "risk_rules.yaml"
            altered_rules.write_text(yaml.safe_dump(rules), encoding="utf-8")
            altered_result = calibrate_payload([detector_output], "internal_presubmission", altered_rules)
            self.assertEqual(altered_result["findings"][0]["calibrated_risk_level"], "R1")

    def test_r4_requires_direct_contradiction_tag(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            detector_output = Path(tmp) / "detector.json"
            payload = self.detector_payload("R4_possible")
            payload["candidates"][0]["candidate_type"] = "image_reuse_cluster"
            payload["candidates"][0]["evidence_strength"] = "strong_candidate"
            payload["candidates"][0]["risk_cap_tags"] = ["image_reuse_cluster"]
            detector_output.write_text(json.dumps(payload), encoding="utf-8")
            result = calibrate_payload([detector_output], "internal_presubmission", ROOT / "schemas" / "risk_rules.yaml")
            self.assertEqual(result["findings"][0]["calibrated_risk_level"], "R3")


class EndToEndTests(unittest.TestCase):
    def test_case001_clean_expected_traceability_no_r3(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "case001"
            run([
                PYTHON,
                "scripts/audit_package.py",
                "evals/cases/case_001",
                "--output-dir",
                str(out),
                "--case-id",
                "case_001",
            ])
            summary = json.loads((out / "AUDIT_JSON_SUMMARY.json").read_text(encoding="utf-8"))
            self.assertLessEqual(risk_value(summary["overall_risk"]), risk_value("R2"))
            calibrated = json.loads((out / "calibrated_findings.json").read_text(encoding="utf-8"))
            self.assertFalse(any(risk_value(item["calibrated_risk_level"]) >= risk_value("R3") for item in calibrated["findings"]))
            contextual = json.loads((out / "contextual_image_candidates.json").read_text(encoding="utf-8"))
            self.assertEqual(contextual["candidates"], [])
            self.assertGreaterEqual(len(contextual.get("positive_evidence", [])), 3)
            edges = [
                edge
                for item in contextual.get("positive_evidence", [])
                for edge in item.get("edges", [])
            ]
            self.assertTrue(any(
                edge["left"] == "figures/Figure_1A_control.png"
                and edge["right"] == "raw_images/acquisition_A001.png"
                and edge["contextual_tag"] == "expected_traceability"
                for edge in edges
            ))
            report = (out / "audit-report.md").read_text(encoding="utf-8")
            self.assertIn("Verified Traceability Evidence", report)
            self.assertIn("positive provenance evidence", report)

    def test_case012_prompt_injection_no_image_false_positive(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "case012"
            run([
                PYTHON,
                "scripts/audit_package.py",
                "evals/cases/case_012",
                "--output-dir",
                str(out),
                "--case-id",
                "case_012",
            ])
            summary = json.loads((out / "AUDIT_JSON_SUMMARY.json").read_text(encoding="utf-8"))
            self.assertLessEqual(risk_value(summary["overall_risk"]), risk_value("R2"))
            calibrated = json.loads((out / "calibrated_findings.json").read_text(encoding="utf-8"))
            self.assertTrue(calibrated["findings"])
            self.assertTrue(all(risk_value(item["calibrated_risk_level"]) <= risk_value("R1") for item in calibrated["findings"]))
            self.assertTrue(any(item["finding_type"] == "unresolved_fig_raw_similarity" for item in calibrated["findings"]))

    def test_unmapped_fig_raw_similarity_caps_at_r1(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "unmapped"
            run([
                PYTHON,
                "scripts/audit_package.py",
                "evals/cases/case_012",
                "--output-dir",
                str(out),
                "--case-id",
                "unmapped",
            ])
            calibrated = json.loads((out / "calibrated_findings.json").read_text(encoding="utf-8"))
            unresolved = [item for item in calibrated["findings"] if item["finding_type"] == "unresolved_fig_raw_similarity"]
            self.assertTrue(unresolved)
            self.assertTrue(all(item["calibrated_risk_level"] == "R1" for item in unresolved))
            self.assertTrue(all("unresolved_fig_raw_similarity" in item.get("source_candidate_tags", []) for item in unresolved))

    def test_traceability_does_not_hide_cross_context_reuse(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            package = Path(tmp) / "mixed_case"
            (package / "figures").mkdir(parents=True)
            (package / "raw_images").mkdir()
            (package / "figure_assembly").mkdir()
            (package / "source_data").mkdir()
            shutil.copy(ROOT / "evals/cases/case_001/figures/Figure_1A_control.png", package / "figures/Figure_1A.png")
            shutil.copy(ROOT / "evals/cases/case_001/figures/Figure_1A_control.png", package / "figures/Figure_4D.png")
            shutil.copy(ROOT / "evals/cases/case_001/figures/Figure_1A_control.png", package / "raw_images/acquisition_A001.png")
            (package / "figure_assembly/assembly_manifest.txt").write_text(
                "figures/Figure_1A.png derives from raw_images/acquisition_A001.png.\n",
                encoding="utf-8",
            )
            (package / "manuscript.pdf").write_text(
                "Figure 1A is control. Figure 4D is a different treatment condition.\n",
                encoding="utf-8",
            )
            (package / "source_data/Figure_1_source.csv").write_text("group,mean,sd,sem,n\ncontrol,1,0.1,0.05,4\n", encoding="utf-8")
            out = Path(tmp) / "mixed_out"
            run([
                PYTHON,
                "scripts/audit_package.py",
                str(package),
                "--output-dir",
                str(out),
                "--case-id",
                "mixed_case",
            ])
            contextual = json.loads((out / "contextual_image_candidates.json").read_text(encoding="utf-8"))
            positive_edges = [
                edge
                for item in contextual.get("positive_evidence", [])
                for edge in item.get("edges", [])
            ]
            self.assertTrue(any(edge["contextual_tag"] == "expected_traceability" for edge in positive_edges))
            calibrated = json.loads((out / "calibrated_findings.json").read_text(encoding="utf-8"))
            tags = [tag for item in calibrated["findings"] for tag in item.get("source_candidate_tags", [])]
            self.assertIn("cross_context_reuse_candidate", tags)
            self.assertTrue(any(item["calibrated_risk_level"] == "R3" for item in calibrated["findings"]))

    def test_case005_disclosed_legitimate_reuse_caps_at_r2(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "case005"
            run([
                PYTHON,
                "scripts/audit_package.py",
                "evals/cases/case_005",
                "--output-dir",
                str(out),
                "--case-id",
                "case_005",
            ])
            calibrated = json.loads((out / "calibrated_findings.json").read_text(encoding="utf-8"))
            validate_instance(calibrated, ROOT / "schemas" / "calibrated_findings.schema.json", "case005 calibrated")
            levels = [item["calibrated_risk_level"] for item in calibrated["findings"]]
            self.assertTrue(levels)
            self.assertLessEqual(max(levels), "R2")
            caps = [cap for item in calibrated["findings"] for cap in item["risk_caps_applied"]]
            self.assertTrue(any("disclosed_legitimate_reuse" in cap for cap in caps))

    def test_case006_disclosed_but_unjustified_is_not_cleared(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "case006"
            run([
                PYTHON,
                "scripts/audit_package.py",
                "evals/cases/case_006",
                "--output-dir",
                str(out),
                "--case-id",
                "case_006",
            ])
            calibrated = json.loads((out / "calibrated_findings.json").read_text(encoding="utf-8"))
            levels = [item["calibrated_risk_level"] for item in calibrated["findings"]]
            self.assertTrue(levels)
            self.assertGreaterEqual(max(levels), "R2")
            self.assertLessEqual(max(levels), "R3")
            tags = [tag for item in calibrated["findings"] for tag in item.get("source_candidate_tags", [])]
            self.assertIn("disclosed_unjustified_reuse", tags)


if __name__ == "__main__":
    unittest.main()
