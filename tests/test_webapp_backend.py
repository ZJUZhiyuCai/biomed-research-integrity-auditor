from __future__ import annotations

import csv
import io
import json
from pathlib import Path
import stat
import sys
import tempfile
import threading
import time
import unittest
from unittest import mock
import zipfile
from xml.sax.saxutils import escape

from fastapi.testclient import TestClient

from webapp.backend import app as webapp_app


create_app = webapp_app.create_app


ROOT = Path(__file__).resolve().parents[1]


def write_pzfx(
    path: Path,
    headers: list[str],
    rows: list[list[object]],
    table_title: str = "Figure summary",
    table_id: str = "Table1",
    graph_title: str | None = None,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    columns = []
    for col_idx, header in enumerate(headers):
        values = "".join(
            f"<d>{escape(str(row[col_idx]))}</d>"
            for row in rows
            if col_idx < len(row)
        )
        columns.append(
            f"<Column><Title>{escape(header)}</Title><Subcolumn>{values}</Subcolumn></Column>"
        )
    graph = ""
    if graph_title:
        graph = (
            f"  <Graph ID=\"Graph1\" TableID=\"{escape(table_id)}\">"
            f"<Title>{escape(graph_title)}</Title><SourceTable>{escape(table_id)}</SourceTable></Graph>\n"
        )
    path.write_text(
        "<?xml version='1.0' encoding='UTF-8'?>\n"
        "<GraphPadPrismFile>\n"
        f"  <Table ID=\"{escape(table_id)}\"><Title>{escape(table_title)}</Title>{''.join(columns)}</Table>\n"
        f"{graph}"
        "</GraphPadPrismFile>\n",
        encoding="utf-8",
    )


def write_docx(
    path: Path,
    paragraphs: list[tuple[str, str | None]],
    table_rows: list[list[str]] | None = None,
    review_layers: bool = False,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

    def paragraph_xml(text: str, style: str | None = None) -> str:
        style_xml = f'<w:pPr><w:pStyle w:val="{escape(style)}"/></w:pPr>' if style else ""
        return f"<w:p>{style_xml}<w:r><w:t>{escape(text)}</w:t></w:r></w:p>"

    table_xml = ""
    if table_rows:
        rows = []
        for row in table_rows:
            cells = "".join(
                f"<w:tc>{paragraph_xml(str(cell))}</w:tc>"
                for cell in row
            )
            rows.append(f"<w:tr>{cells}</w:tr>")
        table_xml = f"<w:tbl>{''.join(rows)}</w:tbl>"

    review_xml = ""
    if review_layers:
        review_xml = (
            "<w:p><w:ins><w:r><w:t>Inserted review-layer text for intake testing.</w:t></w:r></w:ins></w:p>"
        )
    body = "".join(paragraph_xml(text, style) for text, style in paragraphs) + table_xml + review_xml
    document = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        f"<w:body>{body}</w:body>"
        "</w:document>"
    )
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("[Content_Types].xml", '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"/>')
        archive.writestr("word/document.xml", document)
        if review_layers:
            archive.writestr(
                "word/comments.xml",
                (
                    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                    '<w:comments xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
                    '<w:comment w:id="0"><w:p><w:r><w:t>Private reviewer note</w:t></w:r></w:p></w:comment>'
                    "</w:comments>"
                ),
            )
            archive.writestr("word/media/image1.png", b"placeholder image bytes")
            archive.writestr("word/embeddings/oleObject1.bin", b"placeholder embedded object")


def write_pptx(
    path: Path,
    slide_paragraphs: list[list[str]],
    speaker_notes: list[list[str]] | None = None,
    alt_texts: list[list[str]] | None = None,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

    def paragraph_xml(paragraphs: list[str]) -> str:
        return "".join(
            "<a:p><a:r><a:t>" + escape(paragraph) + "</a:t></a:r></a:p>"
            for paragraph in paragraphs
        )

    def slide_xml(paragraphs: list[str], slide_alt_texts: list[str]) -> str:
        body = "".join(
            "<a:p><a:r><a:t>" + escape(paragraph) + "</a:t></a:r></a:p>"
            for paragraph in paragraphs
        )
        alt_shapes = "".join(
            f'<p:sp><p:nvSpPr><p:cNvPr id="{idx + 10}" name="AltText{idx}" descr="{escape(text)}"/></p:nvSpPr></p:sp>'
            for idx, text in enumerate(slide_alt_texts)
        )
        return (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<p:sld xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" '
            'xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">'
            f"<p:cSld><p:spTree>{body}{alt_shapes}</p:spTree></p:cSld>"
            "</p:sld>"
        )

    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("[Content_Types].xml", '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"/>')
        for index, paragraphs in enumerate(slide_paragraphs, start=1):
            slide_alt_texts = alt_texts[index - 1] if alt_texts and index <= len(alt_texts) else []
            archive.writestr(f"ppt/slides/slide{index}.xml", slide_xml(paragraphs, slide_alt_texts))
            if speaker_notes and index <= len(speaker_notes):
                archive.writestr(
                    f"ppt/slides/_rels/slide{index}.xml.rels",
                    (
                        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                        f'<Relationship Id="rIdNotes{index}" '
                        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/notesSlide" '
                        f'Target="../notesSlides/notesSlide{index}.xml"/>'
                        "</Relationships>"
                    ),
                )
                archive.writestr(
                    f"ppt/notesSlides/notesSlide{index}.xml",
                    (
                        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                        '<p:notes xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" '
                        'xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">'
                        f"<p:cSld><p:spTree>{paragraph_xml(speaker_notes[index - 1])}</p:spTree></p:cSld>"
                        "</p:notes>"
                    ),
                )


def write_xlsx(path: Path, rows: list[list[object]], sheet_name: str = "Summary") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    from openpyxl import Workbook

    workbook = Workbook()
    worksheet = workbook.active
    worksheet.title = sheet_name
    for row in rows:
        worksheet.append(row)
    workbook.save(path)
    workbook.close()


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
    def test_health_exposes_example_packages_for_onboarding(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            app = create_app(output_root=Path(tmp) / "runs")
            with TestClient(app) as client:
                response = client.get("/api/health")
                response.raise_for_status()
                examples = response.json()["example_packages"]
                ids = {item["id"] for item in examples}
                self.assertIn("minimal_package", ids)
                self.assertIn("full_presubmission_package", ids)
                for item in examples:
                    self.assertTrue(Path(item["path"]).is_dir())

    def test_submission_qc_summary_exposes_image_review_handoff(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp) / "out"
            review_dir = output_dir / "submission_qc_packet" / "image_review_packet"
            review_dir.mkdir(parents=True)
            (output_dir / "submission_qc_packet" / "QC_PACKET_README.md").write_text(
                "# QC Packet\n", encoding="utf-8"
            )
            (review_dir / "image_review_manifest.json").write_text(
                json.dumps({"candidate_count": 1}), encoding="utf-8"
            )
            (review_dir / "EXTERNAL_TOOL_HANDOFF.md").write_text(
                "# External Image-Review Handoff\n", encoding="utf-8"
            )
            (review_dir / "image_review_tracker.csv").write_text(
                "review_item_id,source_finding_id\nIMG-REV-0001,BIOMED-PKG-0001\n",
                encoding="utf-8",
            )
            for name in ("resolved_actions.csv", "accepted_with_reason.csv"):
                with (output_dir / name).open("w", newline="", encoding="utf-8") as handle:
                    writer = csv.DictWriter(handle, fieldnames=webapp_app.ACTION_FIELDNAMES)
                    writer.writeheader()
            with (output_dir / "unresolved_actions.csv").open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(handle, fieldnames=webapp_app.ACTION_FIELDNAMES)
                writer.writeheader()
                writer.writerow({
                    "action_id": "ACT-0007",
                    "action_category": "must_resolve",
                    "risk_level": "R3",
                    "action_type": "keypoint_geometric_match",
                    "source_finding_id": "BIOMED-PKG-0001",
                    "location": "Figure 1A / Figure 4C",
                    "required_action": "Record external image review and attach result.",
                    "owner": "figure_preparer",
                    "status": "unresolved",
                    "attachment_reference": "external_reviews/Fig1A_Fig4C.pdf",
                    "source": "AUDIT_JSON_SUMMARY.findings",
                })
            with (review_dir / "external_tool_handoff.csv").open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(handle, fieldnames=webapp_app.IMAGE_TOOL_HANDOFF_FIELDS)
                writer.writeheader()
                writer.writerow({
                    "handoff_item_id": "IMG-HANDOFF-0001",
                    "source_finding_id": "BIOMED-PKG-0001",
                    "priority": "priority_review",
                    "finding_type": "keypoint_geometric_match",
                    "risk_level": "R3",
                    "candidate_files": "figures/Fig1A.png; figures/Fig4C.png",
                    "recommended_tool_route": "ImageTwin/Proofig feature review",
                    "review_question": "Does manual review support an expected explanation?",
                    "data_governance_note": "Check institutional and privacy rules before upload.",
                    "review_status": "unresolved",
                })

            summary = webapp_app.submission_qc_packet_summary(output_dir)
            self.assertTrue(summary["available"])
            image_review = summary["image_review_packet"]
            self.assertTrue(image_review["available"])
            self.assertEqual(image_review["candidate_count"], 1)
            self.assertEqual(image_review["external_handoff_count"], 1)
            self.assertEqual(image_review["handoff_rows"][0]["handoff_item_id"], "IMG-HANDOFF-0001")
            self.assertIn("ImageTwin/Proofig", image_review["handoff_rows"][0]["recommended_tool_route"])
            self.assertEqual(image_review["handoff_rows"][0]["linked_action_id"], "ACT-0007")
            self.assertEqual(image_review["handoff_rows"][0]["linked_action_status"], "unresolved")
            self.assertEqual(
                image_review["handoff_rows"][0]["linked_action_attachment_reference"],
                "external_reviews/Fig1A_Fig4C.pdf",
            )
            self.assertEqual(
                image_review["external_tool_handoff_csv"],
                "image_review_packet/external_tool_handoff.csv",
            )
            self.assertTrue(
                webapp_app.artifact_download_allowed(
                    "submission_qc_packet/image_review_packet/external_tool_handoff.csv"
                )
            )
            self.assertFalse(
                webapp_app.artifact_download_allowed(
                    "submission_qc_packet/image_review_packet/private_notes.txt"
                )
            )

            updated_rows = webapp_app.update_image_review_tracker(
                output_dir,
                "IMG-REV-0001",
                webapp_app.ImageReviewUpdateRequest(
                    review_owner="image_specialist",
                    review_status="reviewed",
                    external_tool_or_method="ImageTwin manual review",
                    review_result_note="review notes saved locally",
                    attachment_reference="external_reviews/Fig1A_Fig4C.pdf",
                ),
            )
            self.assertEqual(updated_rows[0]["review_owner"], "image_specialist")
            self.assertEqual(updated_rows[0]["review_status"], "reviewed")
            tracker_text = (review_dir / "image_review_tracker.csv").read_text(encoding="utf-8")
            self.assertIn("ImageTwin manual review", tracker_text)
            with (review_dir / "external_tool_handoff.csv").open(encoding="utf-8") as handle:
                handoff_rows = list(csv.DictReader(handle))
            self.assertEqual(handoff_rows[0]["review_status"], "reviewed")
            self.assertEqual(handoff_rows[0]["reviewer"], "image_specialist")
            self.assertEqual(handoff_rows[0]["external_result_reference"], "external_reviews/Fig1A_Fig4C.pdf")

    def test_webapp_action_patch_updates_tracker_csvs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            app = create_app(output_root=tmp_path / "runs")
            settings = app.state.settings
            audit_id = "20260702-action-edit"
            output_dir = settings.audits_dir / audit_id
            output_dir.mkdir(parents=True)
            job = webapp_app.AuditJob(
                audit_id=audit_id,
                status="completed",
                package_path=str(ROOT / "examples" / "minimal_package"),
                mode="internal_presubmission",
                scan_profile="quick",
                domains="wetlab,animal,cell",
                external_literature_provider="none",
                reference_check_provider="none",
                output_dir=str(output_dir),
                created_at=time.time(),
                updated_at=time.time(),
                command=[],
            )
            webapp_app.save_job(settings, job)
            header = "action_id,action_category,risk_level,action_type,location,required_action,owner,status,human_note,accepted_with_reason,source\n"
            (output_dir / "unresolved_actions.csv").write_text(
                header + "ACT-0001,provide_materials,R1,missing_source,source_data,Add source table,suggested_owner,open,,,\n",
                encoding="utf-8",
            )
            (output_dir / "resolved_actions.csv").write_text(header, encoding="utf-8")
            (output_dir / "accepted_with_reason.csv").write_text(header, encoding="utf-8")
            packet = output_dir / "submission_qc_packet"
            packet.mkdir()
            for name in ("unresolved_actions.csv", "resolved_actions.csv", "accepted_with_reason.csv"):
                (packet / name).write_text((output_dir / name).read_text(encoding="utf-8"), encoding="utf-8")

            with TestClient(app) as client:
                response = client.patch(f"/api/audits/{audit_id}/actions/ACT-0001", json={
                    "owner": "first_author",
                    "status": "resolved",
                    "human_note": "uploaded corrected table",
                    "attachment_reference": "source_data/corrected_table.xlsx",
                })
                response.raise_for_status()
                payload = response.json()["action_trackers"]
                self.assertEqual(payload["unresolved"], [])
                self.assertEqual(payload["resolved"][0]["owner"], "first_author")
                self.assertEqual(payload["resolved"][0]["status"], "resolved")
                self.assertEqual(payload["resolved"][0]["attachment_reference"], "source_data/corrected_table.xlsx")

            resolved_text = (output_dir / "resolved_actions.csv").read_text(encoding="utf-8")
            self.assertIn("first_author", resolved_text)
            self.assertIn("uploaded corrected table", resolved_text)
            self.assertIn("attachment_reference", resolved_text)
            self.assertIn("source_data/corrected_table.xlsx", resolved_text)
            self.assertEqual(resolved_text, (packet / "resolved_actions.csv").read_text(encoding="utf-8"))
            correction_text = (output_dir / "correction_plan.csv").read_text(encoding="utf-8")
            self.assertIn("attachment_reference", correction_text)
            self.assertIn("source_data/corrected_table.xlsx", correction_text)
            correction_md = (output_dir / "correction_plan.md").read_text(encoding="utf-8")
            self.assertIn("Attachment/reference", correction_md)
            self.assertIn("source_data/corrected_table.xlsx", correction_md)
            self.assertEqual(correction_text, (packet / "correction_plan.csv").read_text(encoding="utf-8"))
            self.assertEqual(correction_md, (packet / "correction_plan.md").read_text(encoding="utf-8"))

    def test_webapp_attachment_upload_updates_action_tracker_and_packet(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            app = create_app(output_root=tmp_path / "runs")
            settings = app.state.settings
            audit_id = "20260702-action-attachment"
            output_dir = settings.audits_dir / audit_id
            output_dir.mkdir(parents=True)
            job = webapp_app.AuditJob(
                audit_id=audit_id,
                status="completed",
                package_path=str(ROOT / "examples" / "minimal_package"),
                mode="internal_presubmission",
                scan_profile="quick",
                domains="wetlab,animal,cell",
                external_literature_provider="none",
                reference_check_provider="none",
                output_dir=str(output_dir),
                created_at=time.time(),
                updated_at=time.time(),
                command=[],
            )
            webapp_app.save_job(settings, job)
            for name in ("unresolved_actions.csv", "resolved_actions.csv", "accepted_with_reason.csv"):
                with (output_dir / name).open("w", newline="", encoding="utf-8") as handle:
                    writer = csv.DictWriter(handle, fieldnames=webapp_app.ACTION_FIELDNAMES)
                    writer.writeheader()
                    if name == "unresolved_actions.csv":
                        writer.writerow({
                            "action_id": "ACT-0042",
                            "action_category": "provide_materials",
                            "risk_level": "R1",
                            "action_type": "missing_source",
                            "location": "source_data",
                            "required_action": "Attach corrected source table",
                            "owner": "data_owner",
                            "status": "unresolved",
                            "source": "test",
                        })
            packet = output_dir / "submission_qc_packet"
            packet.mkdir()
            for name in ("unresolved_actions.csv", "resolved_actions.csv", "accepted_with_reason.csv"):
                (packet / name).write_text((output_dir / name).read_text(encoding="utf-8"), encoding="utf-8")

            with TestClient(app) as client:
                response = client.post(
                    f"/api/audits/{audit_id}/attachments",
                    data={"target_type": "action", "target_id": "ACT-0042"},
                    files={"file": ("corrected source table.pdf", b"local attachment", "application/pdf")},
                )
                response.raise_for_status()
                attachment = response.json()["attachment"]
                reference = attachment["attachment_reference"]
                self.assertTrue(reference.startswith("attachments/action/ACT-0042/"))
                self.assertTrue(reference.endswith("corrected_source_table.pdf"))
                self.assertNotIn(str(tmp_path), reference)
                stored = packet / reference
                self.assertEqual(stored.read_bytes(), b"local attachment")

                with (output_dir / "unresolved_actions.csv").open(newline="", encoding="utf-8") as handle:
                    rows = list(csv.DictReader(handle))
                self.assertEqual(rows[0]["attachment_reference"], reference)
                self.assertEqual(reference, list(csv.DictReader((packet / "unresolved_actions.csv").open(newline="", encoding="utf-8")))[0]["attachment_reference"])

                artifact_path = f"submission_qc_packet/{reference}"
                self.assertTrue(webapp_app.artifact_download_allowed(artifact_path))
                artifact = client.get(f"/api/audits/{audit_id}/artifact/{artifact_path}")
                artifact.raise_for_status()
                self.assertEqual(artifact.content, b"local attachment")

    def test_webapp_action_patch_routes_false_positive_to_accepted_tracker(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            app = create_app(output_root=tmp_path / "runs")
            settings = app.state.settings
            audit_id = "20260702-action-false-positive"
            output_dir = settings.audits_dir / audit_id
            output_dir.mkdir(parents=True)
            job = webapp_app.AuditJob(
                audit_id=audit_id,
                status="completed",
                package_path=str(ROOT / "examples" / "minimal_package"),
                mode="internal_presubmission",
                scan_profile="quick",
                domains="wetlab,animal,cell",
                external_literature_provider="none",
                reference_check_provider="none",
                output_dir=str(output_dir),
                created_at=time.time(),
                updated_at=time.time(),
                command=[],
            )
            webapp_app.save_job(settings, job)
            header = "action_id,action_category,risk_level,action_type,location,required_action,owner,status,human_note,accepted_with_reason,source\n"
            (output_dir / "unresolved_actions.csv").write_text(
                header + "ACT-0002,low_priority_checks,R1,review,Figure 1,Review candidate,suggested_owner,unresolved,,,\n",
                encoding="utf-8",
            )
            (output_dir / "resolved_actions.csv").write_text(header, encoding="utf-8")
            (output_dir / "accepted_with_reason.csv").write_text(header, encoding="utf-8")
            packet = output_dir / "submission_qc_packet"
            packet.mkdir()
            for name in ("unresolved_actions.csv", "resolved_actions.csv", "accepted_with_reason.csv"):
                (packet / name).write_text((output_dir / name).read_text(encoding="utf-8"), encoding="utf-8")

            with TestClient(app) as client:
                response = client.patch(f"/api/audits/{audit_id}/actions/ACT-0002", json={
                    "status": "false_positive",
                    "human_note": "manual review found this non-actionable",
                })
                response.raise_for_status()
                payload = response.json()["action_trackers"]
                self.assertEqual(payload["unresolved"], [])
                self.assertEqual(payload["accepted_with_reason"][0]["status"], "false_positive")

            accepted_text = (output_dir / "accepted_with_reason.csv").read_text(encoding="utf-8")
            self.assertIn("false_positive", accepted_text)
            self.assertIn("manual review found this non-actionable", accepted_text)
            self.assertEqual(accepted_text, (packet / "accepted_with_reason.csv").read_text(encoding="utf-8"))

    def test_webapp_marks_orphaned_running_audits_failed_on_startup(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            runs = tmp_path / "runs"
            audit_id = "20260702-orphan"
            output_dir = runs / "audits" / audit_id
            output_dir.mkdir(parents=True)
            (output_dir / "job.json").write_text(json.dumps({
                "audit_id": audit_id,
                "status": "running",
                "package_path": str(ROOT / "examples" / "minimal_package"),
                "mode": "internal_presubmission",
                "scan_profile": "quick",
                "domains": "wetlab,animal,cell",
                "external_literature_provider": "none",
                "reference_check_provider": "none",
                "output_dir": str(output_dir),
                "created_at": time.time(),
                "updated_at": time.time(),
                "command": [],
                "process_pid": 999999,
            }), encoding="utf-8")

            with TestClient(create_app(output_root=runs)) as client:
                response = client.get(f"/api/audits/{audit_id}")
                response.raise_for_status()
                payload = response.json()
                self.assertEqual(payload["status"], "failed")
                self.assertIn("restarted", payload["error"])
                deleted = client.delete(f"/api/audits/{audit_id}")
                deleted.raise_for_status()
                self.assertFalse(output_dir.exists())

    def test_webapp_streams_stdout_tail_and_cancels_running_audit(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            app = create_app(output_root=tmp_path / "runs")
            settings = app.state.settings
            audit_id = "20260702-stream-cancel"
            output_dir = settings.audits_dir / audit_id
            output_dir.mkdir(parents=True)
            job = webapp_app.AuditJob(
                audit_id=audit_id,
                status="queued",
                package_path=str(ROOT / "examples" / "minimal_package"),
                mode="internal_presubmission",
                scan_profile="quick",
                domains="wetlab,animal,cell",
                external_literature_provider="none",
                reference_check_provider="none",
                output_dir=str(output_dir),
                created_at=time.time(),
                updated_at=time.time(),
                command=[
                    sys.executable,
                    "-c",
                    "import time; print('stage-one', flush=True); time.sleep(20)",
                ],
            )
            webapp_app.save_job(settings, job)

            thread = threading.Thread(target=webapp_app.run_job, args=(settings, audit_id), daemon=True)
            thread.start()
            with TestClient(app) as client:
                deadline = time.time() + 8
                payload = {}
                while time.time() < deadline:
                    response = client.get(f"/api/audits/{audit_id}")
                    response.raise_for_status()
                    payload = response.json()
                    if "stage-one" in payload.get("stdout_tail", ""):
                        break
                    time.sleep(0.2)
                self.assertIn("stage-one", payload.get("stdout_tail", ""))
                cancel = client.post(f"/api/audits/{audit_id}/cancel")
                cancel.raise_for_status()
                thread.join(timeout=8)
                final = client.get(f"/api/audits/{audit_id}")
                final.raise_for_status()
                self.assertEqual(final.json()["status"], "canceled")

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
                with zipfile.ZipFile(io.BytesIO(packet.content)) as archive:
                    names = set(archive.namelist())
                self.assertIn("audience_exports/PI_BRIEF.md", names)
                self.assertIn("audience_exports/COAUTHOR_ACTIONS.md", names)
                self.assertIn("audience_exports/JOURNAL_RESPONSE_DRAFT.md", names)

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
                rerun_payload = rerun_summary.json()
                self.assertIsNotNone(rerun_payload["re_audit_diff"])
                self.assertIn("material_changes", rerun_payload["re_audit_diff"])
                diff_markdown = client.get(f"/api/audits/{rerun_id}/artifact/re_audit_diff.md")
                diff_markdown.raise_for_status()
                self.assertIn("Re-audit Diff", diff_markdown.text)

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
                vendor_raw = package / "raw_images" / "Acq_002.czi"
                source = package / "source_data" / "Figure_1_values.csv"
                analysis = package / "statistics_code" / "analysis.py"
                protocol = package / "protocols" / "sample_map.md"
                figure.write_bytes(b"figure")
                raw.write_bytes(b"raw")
                vendor_raw.write_bytes(b"vendor raw")
                source.write_text("group,value\ncontrol,1.0\n", encoding="utf-8")
                analysis.write_text("print('analysis placeholder')\n", encoding="utf-8")
                protocol.write_text("Sample map placeholder.\n", encoding="utf-8")

                inspect = client.post("/api/packages/inspect", json={"package_path": str(package)})
                inspect.raise_for_status()
                inventory = inspect.json()["inventory"]
                self.assertIn("microscopy", inventory["modality_options"])
                self.assertIn("figures/Figure_1A.png", inventory["files_by_role"]["figures"])
                self.assertIn("raw_images/Acq_001.tif", inventory["files_by_role"]["raw_images"])
                self.assertIn("raw_images/Acq_002.czi", inventory["files_by_role"]["raw_images"])
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

                claim_save = client.post("/api/packages/claim-manifest", json={
                    "package_path": str(package),
                    "rows": [
                        {
                            "claim_id": "C-001",
                            "claim_text": "Treatment increases signal intensity in Figure 1A.",
                            "manuscript_location": "Results p. 4",
                            "figure_or_table": "Figure 1A",
                            "source_data": "source_data/Figure_1_values.csv",
                            "raw_record": "raw_images/Acq_001.tif",
                            "analysis_code": "statistics_code/analysis.py",
                            "protocol": "protocols/sample_map.md",
                            "owner": "=PI",
                            "status": "ready",
                        }
                    ],
                })
                claim_save.raise_for_status()
                claim_payload = claim_save.json()
                self.assertEqual(claim_payload["rows_written"], 1)
                self.assertEqual(claim_payload["inventory"]["claim_manifest"]["row_count"], 1)
                claim_text = (package / "claim_manifest.csv").read_text(encoding="utf-8")
                self.assertIn("claim_id,claim_text,manuscript_location,figure_or_table,source_data,raw_record,analysis_code,protocol,owner,status", claim_text)
                self.assertIn("source_data/Figure_1_values.csv", claim_text)
                self.assertIn("'=PI", claim_text)
                refreshed = client.post("/api/packages/inspect", json={"package_path": str(package)})
                refreshed.raise_for_status()
                self.assertEqual(refreshed.json()["inventory"]["claim_manifest"]["rows"][0]["claim_id"], "C-001")

    def test_package_prep_inspect_returns_conservative_manifest_suggestions(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            package = tmp_path / "package"
            (package / "figures").mkdir(parents=True)
            (package / "raw_images").mkdir()
            (package / "source_data").mkdir()
            (package / "statistics_code").mkdir()
            (package / "protocols").mkdir()
            (package / "figures" / "Figure_2A_DAPI.png").write_bytes(b"figure")
            (package / "raw_images" / "Figure_2A_DAPI_raw.tif").write_bytes(b"raw")
            (package / "source_data" / "Figure_2A_values.csv").write_text("x,y\n1,2\n", encoding="utf-8")
            (package / "statistics_code" / "Figure_2A_analysis.py").write_text("print('x')\n", encoding="utf-8")
            (package / "protocols" / "Figure_2A_protocol.md").write_text("protocol\n", encoding="utf-8")

            with TestClient(create_app(output_root=tmp_path / "runs")) as client:
                response = client.post("/api/packages/inspect", json={"package_path": str(package)})
                response.raise_for_status()
                inventory = response.json()["inventory"]

            suggestions = inventory["material_prep_suggestions"]
            self.assertIn("filename", suggestions["scope_note"].lower())
            self.assertFalse((package / "figure_assembly" / "assembly_manifest.csv").exists())
            assembly_rows = suggestions["assembly_rows"]
            self.assertEqual(len(assembly_rows), 2)
            self.assertEqual({row["source_record"] for row in assembly_rows}, {
                "raw_images/Figure_2A_DAPI_raw.tif",
                "source_data/Figure_2A_values.csv",
            })
            self.assertTrue(all(row["relation_type"] == "declared_derived_from" for row in assembly_rows))
            self.assertTrue(all("not verified provenance" in row["notes"] for row in assembly_rows))
            claim_rows = suggestions["claim_rows"]
            self.assertEqual(len(claim_rows), 1)
            self.assertEqual(claim_rows[0]["claim_text"], "")
            self.assertEqual(claim_rows[0]["figure_or_table"], "figures/Figure_2A_DAPI.png")
            self.assertEqual(claim_rows[0]["source_data"], "source_data/Figure_2A_values.csv")
            self.assertEqual(claim_rows[0]["raw_record"], "raw_images/Figure_2A_DAPI_raw.tif")
            self.assertEqual(claim_rows[0]["analysis_code"], "statistics_code/Figure_2A_analysis.py")
            self.assertEqual(claim_rows[0]["protocol"], "protocols/Figure_2A_protocol.md")

    def test_package_prep_suggestions_normalize_messy_figure_filenames(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            package = tmp_path / "package"
            (package / "figures").mkdir(parents=True)
            (package / "raw_images").mkdir()
            (package / "source_data").mkdir()
            (package / "statistics_code").mkdir()
            (package / "protocols").mkdir()
            (package / "figures" / "Fig 02-A DAPI final.png").write_bytes(b"figure")
            (package / "raw_images" / "mouse2A_dapi_acq.tif").write_bytes(b"raw")
            (package / "source_data" / "F2A values.csv").write_text("x,y\n1,2\n", encoding="utf-8")
            (package / "statistics_code" / "fig2a analysis.py").write_text("print('x')\n", encoding="utf-8")
            (package / "protocols" / "Figure-02A protocol.md").write_text("protocol\n", encoding="utf-8")

            with TestClient(create_app(output_root=tmp_path / "runs")) as client:
                response = client.post("/api/packages/inspect", json={"package_path": str(package)})
                response.raise_for_status()
                inventory = response.json()["inventory"]

            suggestions = inventory["material_prep_suggestions"]
            assembly_rows = suggestions["assembly_rows"]
            self.assertEqual(len(assembly_rows), 2)
            self.assertEqual({row["source_record"] for row in assembly_rows}, {
                "raw_images/mouse2A_dapi_acq.tif",
                "source_data/F2A values.csv",
            })
            self.assertTrue(all("shared token(s): 2" in row["notes"] for row in assembly_rows))
            self.assertTrue(all("not verified provenance" in row["notes"] for row in assembly_rows))
            claim_rows = suggestions["claim_rows"]
            self.assertEqual(len(claim_rows), 1)
            self.assertEqual(claim_rows[0]["figure_or_table"], "figures/Fig 02-A DAPI final.png")
            self.assertEqual(claim_rows[0]["source_data"], "source_data/F2A values.csv")
            self.assertEqual(claim_rows[0]["raw_record"], "raw_images/mouse2A_dapi_acq.tif")
            self.assertEqual(claim_rows[0]["analysis_code"], "statistics_code/fig2a analysis.py")
            self.assertEqual(claim_rows[0]["protocol"], "protocols/Figure-02A protocol.md")

    def test_package_prep_reports_ambiguous_filename_suggestions_without_auto_linking(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            package = tmp_path / "package"
            (package / "figures").mkdir(parents=True)
            (package / "raw_images").mkdir()
            (package / "source_data").mkdir()
            (package / "figures" / "Figure_2A_DAPI.png").write_bytes(b"figure")
            (package / "raw_images" / "Figure_2A_DAPI_raw.tif").write_bytes(b"raw one")
            (package / "raw_images" / "Fig_02_A_DAPI_acq.tif").write_bytes(b"raw two")
            (package / "source_data" / "Figure_2A_values.csv").write_text("x,y\n1,2\n", encoding="utf-8")

            with TestClient(create_app(output_root=tmp_path / "runs")) as client:
                response = client.post("/api/packages/inspect", json={"package_path": str(package)})
                response.raise_for_status()
                inventory = response.json()["inventory"]

            suggestions = inventory["material_prep_suggestions"]
            warnings = suggestions["filename_match_warnings"]
            self.assertEqual(len(warnings), 1)
            self.assertIn("Ambiguous filename starter suggestion", warnings[0])
            self.assertIn("raw_images/Figure_2A_DAPI_raw.tif", warnings[0])
            self.assertIn("raw_images/Fig_02_A_DAPI_acq.tif", warnings[0])
            self.assertIn("No row was suggested", warnings[0])

            assembly_rows = suggestions["assembly_rows"]
            self.assertEqual(len(assembly_rows), 1)
            self.assertEqual(assembly_rows[0]["source_record"], "source_data/Figure_2A_values.csv")
            self.assertFalse(any(row["source_record"].startswith("raw_images/") for row in assembly_rows))

            claim_rows = suggestions["claim_rows"]
            self.assertEqual(len(claim_rows), 1)
            self.assertEqual(claim_rows[0]["source_data"], "source_data/Figure_2A_values.csv")
            self.assertEqual(claim_rows[0]["raw_record"], "")

    def test_package_prep_claim_suggestions_use_existing_assembly_manifest_rows(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            package = tmp_path / "package"
            (package / "figures").mkdir(parents=True)
            (package / "raw_images").mkdir()
            (package / "source_data").mkdir()
            (package / "figure_assembly").mkdir()
            (package / "figures" / "Figure_3B.png").write_bytes(b"figure")
            (package / "raw_images" / "unmatched_acquisition.tif").write_bytes(b"raw")
            (package / "source_data" / "unmatched_table.csv").write_text("x,y\n1,2\n", encoding="utf-8")
            (package / "figure_assembly" / "assembly_manifest.csv").write_text(
                "\n".join([
                    "figure_panel,source_record,relation_type,modality,notes",
                    "figures/Figure_3B.png,raw_images/unmatched_acquisition.tif,declared_derived_from,microscopy,declared by lab",
                    "figures/Figure_3B.png,source_data/unmatched_table.csv,declared_derived_from,chart,declared by lab",
                    "",
                ]),
                encoding="utf-8",
            )

            with TestClient(create_app(output_root=tmp_path / "runs")) as client:
                response = client.post("/api/packages/inspect", json={"package_path": str(package)})
                response.raise_for_status()
                suggestions = response.json()["inventory"]["material_prep_suggestions"]

            self.assertEqual(suggestions["assembly_rows"], [])
            self.assertEqual(len(suggestions["claim_rows"]), 1)
            self.assertEqual(suggestions["claim_rows"][0]["figure_or_table"], "figures/Figure_3B.png")
            self.assertEqual(suggestions["claim_rows"][0]["raw_record"], "raw_images/unmatched_acquisition.tif")
            self.assertEqual(suggestions["claim_rows"][0]["source_data"], "source_data/unmatched_table.csv")

    def test_package_prep_prism_graph_table_hints_seed_draft_suggestions(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            package = tmp_path / "package"
            (package / "figures").mkdir(parents=True)
            (package / "source_data").mkdir()
            (package / "figures" / "Figure_1_graph.png").write_bytes(b"figure")
            write_pzfx(
                package / "source_data" / "Figure_summary.pzfx",
                ["group", "mean", "sd"],
                [["control", 1.0, 0.2], ["treated", 1.5, 0.3]],
                table_title="Figure 1 source values",
                table_id="TableFig1",
                graph_title="Figure 1 graph",
            )

            with TestClient(create_app(output_root=tmp_path / "runs")) as client:
                response = client.post("/api/packages/inspect", json={"package_path": str(package)})
                response.raise_for_status()
                suggestions = response.json()["inventory"]["material_prep_suggestions"]

            prism_links = suggestions["prism_graph_table_links"]
            self.assertEqual(len(prism_links), 1)
            self.assertEqual(prism_links[0]["graph_title"], "Figure 1 graph")
            self.assertEqual(prism_links[0]["table_title"], "Figure 1 source values")
            self.assertIn("not verified provenance", prism_links[0]["interpretation"])
            assembly_rows = suggestions["assembly_rows"]
            self.assertEqual(len(assembly_rows), 1)
            self.assertEqual(assembly_rows[0]["figure_panel"], "figures/Figure_1_graph.png")
            self.assertEqual(assembly_rows[0]["source_record"], "source_data/Figure_summary.pzfx")
            self.assertIn("Prism graph-title starter suggestion", assembly_rows[0]["notes"])
            self.assertFalse((package / "figure_assembly" / "assembly_manifest.csv").exists())
            claim_rows = suggestions["claim_rows"]
            self.assertEqual(len(claim_rows), 1)
            self.assertEqual(claim_rows[0]["figure_or_table"], "figures/Figure_1_graph.png")
            self.assertEqual(claim_rows[0]["source_data"], "source_data/Figure_summary.pzfx")
            self.assertIn("Prism graph", claim_rows[0]["suggestion_reason"])

    def test_package_prep_pdf_captions_seed_claim_drafts_without_source_links(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            package = tmp_path / "package"
            (package / "supplementary").mkdir(parents=True)
            (package / "supplementary" / "manuscript.pdf").write_text(
                "\n".join([
                    "Results",
                    "Figure 2A. Treatment increased marker intensity in representative cells.",
                    "The following paragraph continues the result narrative.",
                    "Table 1. Animal cohort and endpoint summary.",
                    "group  n  mean  sd",
                    "control  6  1.2  0.3",
                    "",
                ]),
                encoding="utf-8",
            )

            with TestClient(create_app(output_root=tmp_path / "runs")) as client:
                response = client.post("/api/packages/inspect", json={"package_path": str(package)})
                response.raise_for_status()
                suggestions = response.json()["inventory"]["material_prep_suggestions"]

            captions = suggestions["pdf_captions"]
            self.assertEqual([item["label"] for item in captions], ["Figure 2A", "Table 1"])
            claim_rows = suggestions["claim_rows"]
            self.assertEqual([row["figure_or_table"] for row in claim_rows], ["Figure 2A", "Table 1"])
            self.assertTrue(all(row["claim_text"] == "" for row in claim_rows))
            self.assertTrue(all(row["source_data"] == "" for row in claim_rows))
            self.assertTrue(all(row["raw_record"] == "" for row in claim_rows))
            self.assertTrue(all(row["manuscript_location"] == "supplementary/manuscript.pdf p. 1" for row in claim_rows))
            self.assertIn("PDF caption detected", claim_rows[0]["suggestion_reason"])

    def test_package_prep_docx_captions_seed_claim_drafts_without_source_links(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            package = tmp_path / "package"
            write_docx(
                package / "manuscript" / "draft.docx",
                [
                    ("Results", None),
                    ("Figure 3B. Treatment changed nuclear marker intensity.", "Caption"),
                    ("Table 2. Cohort summary and endpoint measurements.", "Caption"),
                ],
                table_rows=[
                    ["group", "n", "mean", "sd"],
                    ["control", "6", "1.2", "0.3"],
                ],
            )

            with TestClient(create_app(output_root=tmp_path / "runs")) as client:
                response = client.post("/api/packages/inspect", json={"package_path": str(package)})
                response.raise_for_status()
                suggestions = response.json()["inventory"]["material_prep_suggestions"]

            captions = suggestions["docx_captions"]
            self.assertEqual([item["label"] for item in captions], ["Figure 3B", "Table 2"])
            self.assertGreaterEqual(len(suggestions["docx_table_like_blocks"]), 1)
            claim_rows = suggestions["claim_rows"]
            self.assertEqual([row["figure_or_table"] for row in claim_rows], ["Figure 3B", "Table 2"])
            self.assertTrue(all(row["claim_text"] == "" for row in claim_rows))
            self.assertTrue(all(row["source_data"] == "" for row in claim_rows))
            self.assertTrue(all(row["raw_record"] == "" for row in claim_rows))
            self.assertTrue(all(row["manuscript_location"] == "manuscript/draft.docx" for row in claim_rows))
            self.assertIn("DOCX caption detected", claim_rows[0]["suggestion_reason"])

    def test_package_prep_docx_review_layers_surface_as_warnings(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            package = tmp_path / "package"
            write_docx(
                package / "manuscript" / "draft.docx",
                [
                    ("Results", "Heading1"),
                    ("Figure 3B. Treatment changed nuclear marker intensity.", "Caption"),
                ],
                review_layers=True,
            )

            with TestClient(create_app(output_root=tmp_path / "runs")) as client:
                response = client.post("/api/packages/inspect", json={"package_path": str(package)})
                response.raise_for_status()
                suggestions = response.json()["inventory"]["material_prep_suggestions"]

            warnings = suggestions["docx_warnings"]
            self.assertEqual(len(warnings), 3)
            self.assertTrue(any("Word comments" in warning for warning in warnings))
            self.assertTrue(any("tracked revisions" in warning for warning in warnings))
            self.assertTrue(any("embedded objects or media" in warning for warning in warnings))
            self.assertEqual(suggestions["docx_errors"], [])

    def test_package_prep_pptx_explicit_paths_seed_assembly_and_claim_drafts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            package = tmp_path / "package"
            (package / "figures").mkdir(parents=True)
            (package / "raw_images").mkdir()
            (package / "source_data").mkdir()
            (package / "figure_assembly").mkdir()
            (package / "figures" / "Panel_A.png").write_bytes(b"figure")
            (package / "raw_images" / "acq_mouse_77.tif").write_bytes(b"raw")
            (package / "source_data" / "table_values.csv").write_text("group,value\nA,1\n", encoding="utf-8")
            write_pptx(
                package / "figure_assembly" / "layout.pptx",
                [[
                    "Panel A uses figures/Panel_A.png.",
                    "Raw acquisition: raw_images/acq_mouse_77.tif.",
                    "Quantification table: source_data/table_values.csv.",
                ]],
            )

            with TestClient(create_app(output_root=tmp_path / "runs")) as client:
                response = client.post("/api/packages/inspect", json={"package_path": str(package)})
                response.raise_for_status()
                suggestions = response.json()["inventory"]["material_prep_suggestions"]

            pptx_links = suggestions["pptx_links"]
            self.assertEqual(len(pptx_links), 2)
            self.assertEqual({item["source_record"] for item in pptx_links}, {
                "raw_images/acq_mouse_77.tif",
                "source_data/table_values.csv",
            })
            assembly_rows = suggestions["assembly_rows"]
            self.assertEqual(len(assembly_rows), 2)
            self.assertTrue(all(row["figure_panel"] == "figures/Panel_A.png" for row in assembly_rows))
            self.assertTrue(all("PPTX text/notes/alt-text starter suggestion" in row["notes"] for row in assembly_rows))
            self.assertFalse((package / "figure_assembly" / "assembly_manifest.csv").exists())
            claim_rows = suggestions["claim_rows"]
            self.assertEqual(len(claim_rows), 1)
            self.assertEqual(claim_rows[0]["figure_or_table"], "figures/Panel_A.png")
            self.assertEqual(claim_rows[0]["raw_record"], "raw_images/acq_mouse_77.tif")
            self.assertEqual(claim_rows[0]["source_data"], "source_data/table_values.csv")

    def test_package_prep_pptx_notes_and_alt_text_seed_assembly_drafts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            package = tmp_path / "package"
            (package / "figures").mkdir(parents=True)
            (package / "raw_images").mkdir()
            (package / "source_data").mkdir()
            (package / "figure_assembly").mkdir()
            (package / "figures" / "Panel_A.png").write_bytes(b"figure")
            (package / "raw_images" / "acq_mouse_77.tif").write_bytes(b"raw")
            (package / "source_data" / "table_values.csv").write_text("group,value\nA,1\n", encoding="utf-8")
            write_pptx(
                package / "figure_assembly" / "layout.pptx",
                [["Visible slide only says Panel A."]],
                speaker_notes=[[
                    "Speaker note links figures/Panel_A.png to raw_images/acq_mouse_77.tif.",
                ]],
                alt_texts=[[
                    "Alt text links figures/Panel_A.png to source_data/table_values.csv.",
                ]],
            )

            with TestClient(create_app(output_root=tmp_path / "runs")) as client:
                response = client.post("/api/packages/inspect", json={"package_path": str(package)})
                response.raise_for_status()
                suggestions = response.json()["inventory"]["material_prep_suggestions"]

            pptx_links = suggestions["pptx_links"]
            self.assertEqual(len(pptx_links), 2)
            self.assertEqual({item["source_record"] for item in pptx_links}, {
                "raw_images/acq_mouse_77.tif",
                "source_data/table_values.csv",
            })
            self.assertTrue(any(item["evidence_source"].endswith(":speaker_notes") for item in pptx_links))
            self.assertTrue(any(item["evidence_source"].endswith(":alt_text") for item in pptx_links))
            assembly_rows = suggestions["assembly_rows"]
            self.assertEqual(len(assembly_rows), 2)
            self.assertTrue(all("PPTX text/notes/alt-text starter suggestion" in row["notes"] for row in assembly_rows))
            self.assertFalse((package / "figure_assembly" / "assembly_manifest.csv").exists())

    def test_package_prep_xlsx_sheets_seed_claim_drafts_for_figure_like_sheets(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            package = tmp_path / "package"
            write_xlsx(
                package / "source_data" / "Figure_4_source.xlsx",
                [
                    ["group", "mean", "sd", "n"],
                    ["control", 1.0, 0.2, 4],
                    ["treated", 1.5, 0.3, 4],
                ],
                sheet_name="Figure 4A",
            )

            with TestClient(create_app(output_root=tmp_path / "runs")) as client:
                response = client.post("/api/packages/inspect", json={"package_path": str(package)})
                response.raise_for_status()
                suggestions = response.json()["inventory"]["material_prep_suggestions"]

            sheets = suggestions["xlsx_sheets"]
            self.assertEqual(len(sheets), 1)
            self.assertEqual(sheets[0]["source_xlsx"], "source_data/Figure_4_source.xlsx")
            self.assertEqual(sheets[0]["sheet_name"], "Figure 4A")
            self.assertEqual(sheets[0]["suggested_label"], "Figure 4A")
            self.assertEqual(sheets[0]["header_row"], "1")
            self.assertEqual(sheets[0]["headers"], ["group", "mean", "sd", "n"])
            self.assertEqual(sheets[0]["data_rows_scanned"], "2")
            self.assertIn("not a statistical validation result", sheets[0]["interpretation"])

            claim_rows = suggestions["claim_rows"]
            self.assertEqual(len(claim_rows), 1)
            self.assertEqual(claim_rows[0]["claim_text"], "")
            self.assertEqual(claim_rows[0]["figure_or_table"], "Figure 4A")
            self.assertEqual(claim_rows[0]["source_data"], "source_data/Figure_4_source.xlsx")
            self.assertEqual(claim_rows[0]["raw_record"], "")
            self.assertIn("XLSX sheet/header detected", claim_rows[0]["suggestion_reason"])
            self.assertFalse((package / "figure_assembly" / "assembly_manifest.csv").exists())
            self.assertFalse((package / "claim_manifest.csv").exists())

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

    def test_package_prep_claim_manifest_rejects_unsafe_or_mismatched_rows(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            package = tmp_path / "package"
            (package / "source_data").mkdir(parents=True)
            (package / "raw_images").mkdir()
            (package / "statistics_code").mkdir()
            (package / "protocols").mkdir()
            (package / "source_data" / "Figure_1.csv").write_text("x,y\n1,2\n", encoding="utf-8")
            (package / "raw_images" / "Acq_001.tif").write_bytes(b"raw")
            (package / "statistics_code" / "analysis.py").write_text("print('x')\n", encoding="utf-8")
            (package / "protocols" / "sample_map.md").write_text("sample map\n", encoding="utf-8")

            with TestClient(create_app(output_root=tmp_path / "runs")) as client:
                traversal = client.post("/api/packages/claim-manifest", json={
                    "package_path": str(package),
                    "rows": [
                        {
                            "claim_id": "C-001",
                            "claim_text": "Signal changes.",
                            "source_data": "../outside.csv",
                        }
                    ],
                })
                self.assertEqual(traversal.status_code, 400)
                self.assertIn("Invalid package-relative path", traversal.text)

                mismatch = client.post("/api/packages/claim-manifest", json={
                    "package_path": str(package),
                    "rows": [
                        {
                            "claim_id": "C-001",
                            "claim_text": "Signal changes.",
                            "source_data": "raw_images/Acq_001.tif",
                        }
                    ],
                })
                self.assertEqual(mismatch.status_code, 400)
                self.assertIn("source_data must point to", mismatch.text)

                unsupported_status = client.post("/api/packages/claim-manifest", json={
                    "package_path": str(package),
                    "rows": [
                        {
                            "claim_id": "C-001",
                            "claim_text": "Signal changes.",
                            "source_data": "source_data/Figure_1.csv",
                            "status": "proved",
                        }
                    ],
                })
                self.assertEqual(unsupported_status.status_code, 400)
                self.assertIn("Unsupported claim status", unsupported_status.text)

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
