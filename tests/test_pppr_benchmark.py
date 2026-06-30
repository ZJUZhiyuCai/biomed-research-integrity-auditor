from __future__ import annotations

import json
import importlib.util
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator


ROOT = Path(__file__).resolve().parents[1]
PYTHON = sys.executable
BENCH = ROOT / "benchmarks" / "pppr_integrity_benchmark"


def run(cmd: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, cwd=ROOT, check=True, capture_output=True, text=True)


def load_public_smoke_runner():
    path = BENCH / "scripts" / "run_public_smoke_benchmark.py"
    spec = importlib.util.spec_from_file_location("run_public_smoke_benchmark", path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class PPPRBenchmarkTests(unittest.TestCase):
    def test_label_schema_rejects_misconduct_truth_fields(self) -> None:
        schema = json.loads((BENCH / "labels.schema.json").read_text(encoding="utf-8"))
        validator = Draft202012Validator(schema)
        valid = {
            "case_id": "case_000001",
            "label_id": "L0001",
            "source": "pubpeer_manual_annotation",
            "source_url": "https://pubpeer.example/publications/example",
            "paper_location": {"figure": "Fig. 3", "panel": "3B"},
            "issue_type": "image_local_reuse",
            "label_strength": "manually_verified_public_evidence",
            "expected_risk": "R2_or_R3",
            "benign_explanation_possible": True,
            "required_materials_to_resolve": ["raw image", "assembly history"],
        }
        self.assertEqual(list(validator.iter_errors(valid)), [])
        invalid = dict(valid)
        invalid["misconduct"] = True
        self.assertTrue(list(validator.iter_errors(invalid)))

    def test_metadata_scripts_normalize_without_verdict_fields(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            rwdb = tmp_path / "rwdb.csv"
            rwdb.write_text(
                "OriginalPaperDOI,OriginalPaperPubMedID,RetractionNature,Reason,Subject,Journal,Publisher,RetractionDate,OriginalPaperDate\n"
                "10.1000/example,12345,Retraction,Image issue,Biology,Example Journal,Example Publisher,2024-01-02,2021-03-04\n",
                encoding="utf-8",
            )
            rwdb_out = tmp_path / "rwdb_out.csv"
            run([
                PYTHON,
                "benchmarks/pppr_integrity_benchmark/scripts/build_rwdb_index.py",
                "--input",
                str(rwdb),
                "--output",
                str(rwdb_out),
                "--snapshot-date",
                "2026-06-30",
            ])
            text = rwdb_out.read_text(encoding="utf-8")
            self.assertIn("publication_status", text)
            self.assertIn("retracted", text)
            self.assertNotIn("misconduct", text.lower())

            pubpeer = tmp_path / "pubpeer.csv"
            pubpeer.write_text(
                "doi,pmid,pubpeer_url,comment_count,manual_issue_category\n"
                "10.1000/example,12345,https://pubpeer.example/publications/example,2,image_similarity\n",
                encoding="utf-8",
            )
            pubpeer_out = tmp_path / "pubpeer_out.csv"
            run([
                PYTHON,
                "benchmarks/pppr_integrity_benchmark/scripts/normalize_pubpeer_manifest.py",
                "--input",
                str(pubpeer),
                "--output",
                str(pubpeer_out),
                "--snapshot-date",
                "2026-06-30",
            ])
            normalized = pubpeer_out.read_text(encoding="utf-8")
            self.assertIn("weak_pubpeer_signal", normalized)
            self.assertNotIn("comment text", normalized.lower())

    def test_matched_controls_do_not_claim_clean_papers(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            articles = tmp_path / "articles.csv"
            articles.write_text(
                "case_id,doi,pmid,pmcid,license,pmc_oa_url\n"
                "a,10.1/a,1,PMC1,CC-BY,https://example.org/a\n"
                "b,10.1/b,2,PMC2,CC-BY,https://example.org/b\n",
                encoding="utf-8",
            )
            exclude = tmp_path / "exclude.csv"
            exclude.write_text("doi,pmid,pmcid\n10.1/a,1,PMC1\n", encoding="utf-8")
            output = tmp_path / "controls.csv"
            run([
                PYTHON,
                "benchmarks/pppr_integrity_benchmark/scripts/make_matched_controls.py",
                "--articles",
                str(articles),
                "--exclude",
                str(exclude),
                "--output",
                str(output),
                "--snapshot-date",
                "2026-06-30",
            ])
            text = output.read_text(encoding="utf-8")
            self.assertIn("10.1/b", text)
            self.assertNotIn("10.1/a", text)
            self.assertIn("not a clean-paper label", text)

    def test_pmc_package_builder_and_evaluator_are_offline(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            source = tmp_path / "source"
            (source / "figures").mkdir(parents=True)
            (source / "paper.xml").write_text("<article />", encoding="utf-8")
            (source / "figures" / "fig1.png").write_bytes(b"png")
            manifest = tmp_path / "pmc.csv"
            manifest.write_text(
                "case_id,doi,pmid,pmcid,license,redistributable,xml_path,figures_dir\n"
                "case_000001,10.1/a,1,PMC1,CC-BY,true,paper.xml,figures\n",
                encoding="utf-8",
            )
            packages = tmp_path / "packages"
            run([
                PYTHON,
                "benchmarks/pppr_integrity_benchmark/scripts/build_pmc_oa_packages.py",
                "--manifest",
                str(manifest),
                "--source-base",
                str(source),
                "--output-dir",
                str(packages),
            ])
            self.assertTrue((packages / "case_000001" / "manuscript" / "paper.xml").is_file())
            self.assertTrue((packages / "case_000001" / "figures" / "fig1.png").is_file())

            outputs = tmp_path / "outputs" / "case_000001"
            outputs.mkdir(parents=True)
            (outputs / "AUDIT_JSON_SUMMARY.json").write_text(json.dumps({
                "overall_risk": "R2",
                "misconduct_verdict_present": False,
                "findings": [
                    {
                        "risk_level": "R2",
                        "finding_type": "image local reuse candidate",
                        "location": "Fig. 3 panel 3B",
                        "evidence_type": "image",
                        "recommended_action": "request raw image",
                    }
                ],
            }), encoding="utf-8")
            (outputs / "audit-report.md").write_text("Neutral report\n", encoding="utf-8")
            labels = tmp_path / "labels.jsonl"
            labels.write_text(json.dumps({
                "case_id": "case_000001",
                "label_id": "L0001",
                "source": "manual_public_material_annotation",
                "source_url": "https://example.org/article",
                "paper_location": {"figure": "Fig. 3", "panel": "3B"},
                "issue_type": "image_local_reuse",
                "label_strength": "manually_verified_public_evidence",
                "expected_risk": "R2_or_R3",
                "benign_explanation_possible": True,
                "required_materials_to_resolve": ["raw image"],
            }) + "\n" + json.dumps({
                "case_id": "case_000001",
                "label_id": "L0002",
                "source": "ori_unit_sample",
                "source_url": "https://ori.hhs.gov/samples",
                "paper_location": {"figure": "unmatched same-section sample"},
                "issue_type": "same_section_overlap",
                "label_strength": "ori_unit_sample",
                "evaluation_role": "scope_gap",
                "expected_risk": "R1",
                "benign_explanation_possible": True,
                "required_materials_to_resolve": ["raw image"],
            }) + "\n", encoding="utf-8")
            eval_out = tmp_path / "eval.json"
            run([
                PYTHON,
                "benchmarks/pppr_integrity_benchmark/scripts/evaluate_audit_outputs.py",
                "--labels",
                str(labels),
                "--outputs-root",
                str(tmp_path / "outputs"),
                "--output",
                str(eval_out),
            ])
            payload = json.loads(eval_out.read_text(encoding="utf-8"))
            self.assertEqual(payload["labels"], 1)
            self.assertEqual(payload["labels_total"], 2)
            self.assertEqual(payload["scope_gap_labels"], 1)
            self.assertEqual(payload["label_hits"], 1)
            self.assertEqual(payload["risk_cap_violations"], 0)
            self.assertEqual(payload["boundary_violations"], 0)

    def test_public_smoke_runner_helpers_are_schema_safe(self) -> None:
        runner = load_public_smoke_runner()
        self.assertEqual(
            runner.s3_to_https("s3://pmc-oa-opendata/PMC10009402.1/PMC10009402.1.xml?md5=abc"),
            "https://pmc-oa-opendata.s3.amazonaws.com/PMC10009402.1/PMC10009402.1.xml",
        )
        with self.assertRaises(ValueError):
            runner.s3_to_https("s3://other-bucket/path/file.xml")

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            labels_path = runner.write_labels_and_splits(tmp_path, ["ori_samples_public_images"], "2026-06-30")
            schema = json.loads((BENCH / "labels.schema.json").read_text(encoding="utf-8"))
            validator = Draft202012Validator(schema)
            labels = [
                json.loads(line)
                for line in labels_path.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            self.assertGreaterEqual(len(labels), 4)
            self.assertTrue(any(label.get("evaluation_role") == "recall_label" for label in labels))
            self.assertTrue(any(label.get("evaluation_role") == "scope_gap" for label in labels))
            for label in labels:
                self.assertEqual(list(validator.iter_errors(label)), [])
                self.assertEqual(label["label_strength"], "ori_unit_sample")
                self.assertNotIn("misconduct", json.dumps(label).lower())


if __name__ == "__main__":
    unittest.main()
