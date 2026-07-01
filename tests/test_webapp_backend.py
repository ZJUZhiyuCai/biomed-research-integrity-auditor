from __future__ import annotations

import io
import json
from pathlib import Path
import stat
import tempfile
import time
import unittest
from unittest import mock
import zipfile

from fastapi.testclient import TestClient

from webapp.backend import app as webapp_app


create_app = webapp_app.create_app


ROOT = Path(__file__).resolve().parents[1]


def wait_for_audit(client: TestClient, audit_id: str, timeout: float = 90.0) -> dict:
    deadline = time.time() + timeout
    last_payload: dict | None = None
    while time.time() < deadline:
        response = client.get(f"/api/audits/{audit_id}")
        response.raise_for_status()
        last_payload = response.json()
        if last_payload["status"] in {"completed", "failed"}:
            return last_payload
        time.sleep(0.5)
    raise AssertionError(f"audit did not finish before timeout: {last_payload}")


class WebappBackendTests(unittest.TestCase):
    def test_webapp_runs_example_package_and_serves_unmutated_artifacts(self) -> None:
        with self.subTest("minimal package"):
            with TestClient(create_app(output_root=ROOT / "tmp" / "webapp_test_runs")) as client:
                response = client.post("/api/audits", json={
                    "package_path": str(ROOT / "examples" / "minimal_package"),
                    "mode": "internal_presubmission",
                    "scan_profile": "quick",
                    "domains": "wetlab,animal,cell",
                    "external_literature_provider": "none",
                })
                response.raise_for_status()
                audit_id = response.json()["audit_id"]
                job = wait_for_audit(client, audit_id)
                self.assertEqual(job["status"], "completed", job.get("stderr_tail"))

                summary_response = client.get(f"/api/audits/{audit_id}/summary")
                summary_response.raise_for_status()
                payload = summary_response.json()
                artifact_summary = json.loads(
                    Path(job["artifacts"]["summary"]).read_text(encoding="utf-8")
                )

                self.assertEqual(payload["audit_summary"]["overall_risk"], artifact_summary["overall_risk"])
                self.assertEqual(payload["audit_summary"]["scan_profile"], "quick")
                self.assertEqual(payload["audit_summary"]["misconduct_verdict_present"], False)
                self.assertIn("audit_coverage", payload["audit_summary"])
                self.assertIn("modules_executed", payload["coverage"])
                self.assertIn("writing_submission_readiness", payload["coverage"]["modules_executed"])
                self.assertEqual(payload["pipeline_summary"]["overall_risk"], artifact_summary["overall_risk"])
                self.assertEqual(payload["pipeline_summary"]["scan_profile"], "quick")
                self.assertIn("claim_coverage", payload)
                self.assertIn("unresolved", payload["action_trackers"])
                self.assertIn("correction_plan", payload)
                self.assertGreater(len(payload["correction_plan"]), 0)
                self.assertTrue(payload["submission_qc_packet"]["available"])
                self.assertIn("writing_readiness", payload)
                self.assertEqual(payload["writing_readiness"]["scope"], "writing_submission_readiness_only")
                self.assertGreater(len(payload["writing_readiness"].get("checks", [])), 0)
                finding_text = json.dumps(
                    payload.get("calibrated_findings", {}).get("findings", []),
                    sort_keys=True,
                ).lower()
                self.assertNotIn("writing_submission_readiness", finding_text)
                self.assertNotIn("writing_readiness", finding_text)

                actions = client.get(f"/api/audits/{audit_id}/artifact/unresolved_actions.csv")
                actions.raise_for_status()
                self.assertIn("action_id", actions.text)

                correction_plan = client.get(f"/api/audits/{audit_id}/artifact/correction_plan.md")
                correction_plan.raise_for_status()
                self.assertIn("Pre-submission Correction Plan", correction_plan.text)

                packet = client.get(f"/api/audits/{audit_id}/submission-qc-packet.zip")
                packet.raise_for_status()
                self.assertGreater(len(packet.content), 100)

                report_response = client.get(f"/api/audits/{audit_id}/report.md")
                report_response.raise_for_status()
                self.assertIn("AUDIT_JSON_SUMMARY", report_response.text)
                self.assertIn("Writing & Submission Readiness", report_response.text)

                rerun = client.post("/api/audits", json={
                    "package_path": str(ROOT / "examples" / "minimal_package"),
                    "mode": "internal_presubmission",
                    "scan_profile": "quick",
                    "domains": "wetlab,animal,cell",
                    "external_literature_provider": "none",
                    "reference_check_provider": "none",
                    "compare_to_audit_id": audit_id,
                })
                rerun.raise_for_status()
                rerun_id = rerun.json()["audit_id"]
                rerun_job = wait_for_audit(client, rerun_id)
                self.assertEqual(rerun_job["status"], "completed", rerun_job.get("stderr_tail"))
                rerun_summary = client.get(f"/api/audits/{rerun_id}/summary")
                rerun_summary.raise_for_status()
                self.assertIsNotNone(rerun_summary.json()["re_audit_diff"])

    def test_evidence_endpoint_blocks_path_traversal(self) -> None:
        with TestClient(create_app(output_root=ROOT / "tmp" / "webapp_traversal_runs")) as client:
            response = client.post("/api/audits", json={
                "package_path": str(ROOT / "examples" / "minimal_package"),
                "external_literature_provider": "none",
            })
            response.raise_for_status()
            audit_id = response.json()["audit_id"]
            job = wait_for_audit(client, audit_id)
            self.assertEqual(job["status"], "completed", job.get("stderr_tail"))

            traversal = client.get(f"/api/audits/{audit_id}/evidence/%2E%2E/%2E%2E/README.md")
            self.assertEqual(traversal.status_code, 400)

            artifact_traversal = client.get(f"/api/audits/{audit_id}/artifact/%2E%2E/README.md")
            self.assertEqual(artifact_traversal.status_code, 400)

            output_dir = Path(job["output_dir"])
            self.assertTrue(output_dir.is_dir())
            deleted = client.delete(f"/api/audits/{audit_id}")
            deleted.raise_for_status()
            self.assertFalse(output_dir.exists())

    def test_zip_upload_rejects_unsafe_members(self) -> None:
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            archive.writestr("../evil.txt", "not a package")
        buffer.seek(0)

        with TestClient(create_app(output_root=ROOT / "tmp" / "webapp_upload_runs")) as client:
            response = client.post(
                "/api/audits/upload",
                files={"file": ("unsafe.zip", buffer.getvalue(), "application/zip")},
            )
            self.assertEqual(response.status_code, 400)
            self.assertIn("unsafe path", response.text)

    def test_zip_upload_rejects_symlink_members(self) -> None:
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            info = zipfile.ZipInfo("figures/link.png")
            info.create_system = 3
            info.external_attr = (stat.S_IFLNK | 0o777) << 16
            archive.writestr(info, "raw_images/target.png")
        buffer.seek(0)

        with TestClient(create_app(output_root=ROOT / "tmp" / "webapp_upload_symlink_runs")) as client:
            response = client.post(
                "/api/audits/upload",
                files={"file": ("symlink.zip", buffer.getvalue(), "application/zip")},
            )
            self.assertEqual(response.status_code, 400)
            self.assertIn("symlink", response.text)

    def test_package_prep_scaffold_inspect_and_manifest_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            package = tmp_path / "package"
            with TestClient(create_app(output_root=tmp_path / "runs")) as client:
                scaffold = client.post("/api/packages/scaffold", json={"package_path": str(package)})
                scaffold.raise_for_status()
                inventory = scaffold.json()["inventory"]
                self.assertTrue(inventory["folders"]["figures"])
                self.assertTrue(inventory["folders"]["raw_images"])
                self.assertTrue((package / "PACKAGE_NOTE.txt").is_file())

                figure = package / "figures" / "Figure_1A.png"
                raw = package / "raw_images" / "Acq_001.tif"
                source = package / "source_data" / "Figure_1_values.csv"
                figure.write_bytes(b"figure")
                raw.write_bytes(b"raw")
                source.write_text("group,value\ncontrol,1.0\n", encoding="utf-8")

                inspect = client.post("/api/packages/inspect", json={"package_path": str(package)})
                inspect.raise_for_status()
                inventory = inspect.json()["inventory"]
                self.assertIn("microscopy", inventory["modality_options"])
                self.assertIn("figures/Figure_1A.png", inventory["files_by_role"]["figures"])
                self.assertIn("raw_images/Acq_001.tif", inventory["files_by_role"]["raw_images"])
                self.assertIn("source_data/Figure_1_values.csv", inventory["files_by_role"]["source_data"])

                save = client.post("/api/packages/assembly-manifest", json={
                    "package_path": str(package),
                    "rows": [
                        {
                            "figure_panel": "figures/Figure_1A.png",
                            "source_record": "raw_images/Acq_001.tif",
                            "relation_type": "declared_derived_from",
                            "modality": "image",
                            "notes": "exported figure panel traced to acquisition file",
                        },
                        {
                            "figure_panel": "figures/Figure_1A.png",
                            "source_record": "source_data/Figure_1_values.csv",
                            "relation_type": "declared_derived_from",
                            "modality": "table",
                            "notes": "=HYPERLINK(\"https://example.invalid\",\"note\")",
                        },
                    ],
                })
                save.raise_for_status()
                payload = save.json()
                self.assertEqual(payload["rows_written"], 2)
                self.assertEqual(payload["inventory"]["assembly_manifest"]["row_count"], 2)
                manifest_text = (package / "figure_assembly" / "assembly_manifest.csv").read_text(encoding="utf-8")
                self.assertIn("figure_panel,source_record,relation_type,modality,notes", manifest_text)
                self.assertIn("raw_images/Acq_001.tif", manifest_text)
                self.assertIn(",other,", manifest_text)
                self.assertIn(",chart,", manifest_text)
                self.assertIn("'=HYPERLINK", manifest_text)

    def test_package_prep_manifest_rejects_unsafe_or_unsupported_rows(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            package = tmp_path / "package"
            (package / "figures").mkdir(parents=True)
            (package / "raw_images").mkdir()
            (package / "figures" / "Figure_1A.png").write_bytes(b"figure")
            (package / "raw_images" / "Acq_001.tif").write_bytes(b"raw")

            with TestClient(create_app(output_root=tmp_path / "runs")) as client:
                traversal = client.post("/api/packages/assembly-manifest", json={
                    "package_path": str(package),
                    "rows": [
                        {
                            "figure_panel": "../outside.png",
                            "source_record": "raw_images/Acq_001.tif",
                            "relation_type": "declared_derived_from",
                        }
                    ],
                })
                self.assertEqual(traversal.status_code, 400)
                self.assertIn("Invalid package-relative path", traversal.text)

                absolute = client.post("/api/packages/assembly-manifest", json={
                    "package_path": str(package),
                    "rows": [
                        {
                            "figure_panel": str(package / "figures" / "Figure_1A.png"),
                            "source_record": "raw_images/Acq_001.tif",
                            "relation_type": "declared_derived_from",
                        }
                    ],
                })
                self.assertEqual(absolute.status_code, 400)
                self.assertIn("Invalid package-relative path", absolute.text)

                unsupported = client.post("/api/packages/assembly-manifest", json={
                    "package_path": str(package),
                    "rows": [
                        {
                            "figure_panel": "figures/Figure_1A.png",
                            "source_record": "raw_images/Acq_001.tif",
                            "relation_type": "proves_correctness",
                        }
                    ],
                })
                self.assertEqual(unsupported.status_code, 400)
                self.assertIn("Unsupported relation_type", unsupported.text)

    def test_package_prep_inventory_reports_scan_limits(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            package = tmp_path / "package"
            package.mkdir()
            for idx in range(5):
                (package / f"file_{idx}.txt").write_text("x", encoding="utf-8")

            with mock.patch.object(webapp_app, "INVENTORY_MAX_FILES", 3):
                with TestClient(create_app(output_root=tmp_path / "runs")) as client:
                    response = client.post("/api/packages/inspect", json={"package_path": str(package)})
                    response.raise_for_status()
                    inventory = response.json()["inventory"]

            self.assertTrue(inventory["scan_limit_reached"])
            self.assertEqual(inventory["scan_limits"]["max_files"], 3)
            self.assertTrue(any("Inventory stopped after 3 files" in item for item in inventory["inventory_warnings"]))

    def test_package_prep_inventory_skips_symlinks(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            package = tmp_path / "package"
            outside = tmp_path / "outside.png"
            (package / "figures").mkdir(parents=True)
            outside.write_bytes(b"outside")
            (package / "figures" / "linked.png").symlink_to(outside)

            with TestClient(create_app(output_root=tmp_path / "runs")) as client:
                response = client.post("/api/packages/inspect", json={"package_path": str(package)})
                response.raise_for_status()
                inventory = response.json()["inventory"]

            self.assertNotIn("figures/linked.png", inventory["files_by_role"]["figures"])
            self.assertTrue(any("Skipped symlink: figures/linked.png" in item for item in inventory["inventory_warnings"]))

    def test_package_prep_manifest_rejects_relation_source_role_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            package = tmp_path / "package"
            (package / "figures").mkdir(parents=True)
            (package / "source_data").mkdir()
            (package / "raw_images").mkdir()
            (package / "figures" / "Figure_1A.png").write_bytes(b"figure")
            (package / "figures" / "Figure_1B.png").write_bytes(b"figure")
            (package / "source_data" / "Figure_1.csv").write_text("x,y\n1,2\n", encoding="utf-8")

            with TestClient(create_app(output_root=tmp_path / "runs")) as client:
                mismatch = client.post("/api/packages/assembly-manifest", json={
                    "package_path": str(package),
                    "rows": [
                        {
                            "figure_panel": "figures/Figure_1A.png",
                            "source_record": "source_data/Figure_1.csv",
                            "relation_type": "same_membrane_reprobe",
                        }
                    ],
                })
                self.assertEqual(mismatch.status_code, 400)
                self.assertIn("same_membrane_reprobe source_record", mismatch.text)

                valid_figure_relation = client.post("/api/packages/assembly-manifest", json={
                    "package_path": str(package),
                    "rows": [
                        {
                            "figure_panel": "figures/Figure_1A.png",
                            "source_record": "figures/Figure_1B.png",
                            "relation_type": "same_field_different_channel",
                        }
                    ],
                })
                valid_figure_relation.raise_for_status()
                self.assertEqual(valid_figure_relation.json()["rows_written"], 1)

    def test_webapp_serves_frontend_and_package_prep_endpoints(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            with TestClient(create_app(output_root=tmp_path / "runs")) as client:
                index = client.get("/")
                self.assertEqual(index.status_code, 200)
                self.assertIn("root", index.text)

                response = client.post("/api/packages/inspect", json={
                    "package_path": str(ROOT / "examples" / "full_presubmission_package")
                })
                response.raise_for_status()
                inventory = response.json()["inventory"]
                self.assertIn("relation_allowed_source_roles", inventory)
                self.assertIn("declared_derived_from", inventory["relation_allowed_source_roles"])

    def test_webapp_rejects_invalid_audit_ids_before_filesystem_lookup(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            with TestClient(create_app(output_root=tmp_path / "runs")) as client:
                response = client.get("/api/audits/bad$id")
                self.assertEqual(response.status_code, 400)
                self.assertIn("Invalid audit id", response.text)


if __name__ == "__main__":
    unittest.main()
