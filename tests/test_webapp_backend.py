from __future__ import annotations

import io
import json
from pathlib import Path
import time
import unittest
import zipfile

from fastapi.testclient import TestClient

from webapp.backend.app import create_app


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
                self.assertEqual(payload["audit_summary"]["misconduct_verdict_present"], False)
                self.assertIn("audit_coverage", payload["audit_summary"])
                self.assertIn("modules_executed", payload["coverage"])
                self.assertEqual(payload["pipeline_summary"]["overall_risk"], artifact_summary["overall_risk"])

                report_response = client.get(f"/api/audits/{audit_id}/report.md")
                report_response.raise_for_status()
                self.assertIn("AUDIT_JSON_SUMMARY", report_response.text)

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


if __name__ == "__main__":
    unittest.main()
