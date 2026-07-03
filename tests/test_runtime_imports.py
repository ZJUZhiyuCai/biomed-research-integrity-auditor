from __future__ import annotations

import importlib
import unittest


class RuntimeImportTests(unittest.TestCase):
    def test_required_runtime_dependencies_and_detectors_import(self) -> None:
        modules = [
            "numpy",
            "cv2",
            "PIL",
            "yaml",
            "jsonschema",
            "openpyxl",
            "pypdf",
            "fitz",
            "requests",
            "fastapi",
            "uvicorn",
            "multipart",
            "detectors.image.global_near_duplicate",
            "detectors.image.channel_metadata_consistency",
            "detectors.image.keypoint_geometric_match",
            "detectors.image.local_patch_reuse",
            "detectors.image.splice_forensics_triage",
            "detectors.stats.pseudoreplication_screen",
            "detectors.text.external_literature_search",
            "detectors.text.text_overlap_screen",
            "scripts.fcs_metadata_intake",
            "scripts.docx_structure_extract",
            "scripts.pptx_structure_extract",
            "scripts.xlsx_structure_extract",
            "scripts.prism_project_intake",
            "scripts.psd_preview_extract",
            "webapp.__main__",
            "webapp.backend.app",
        ]
        for module in modules:
            with self.subTest(module=module):
                importlib.import_module(module)


if __name__ == "__main__":
    unittest.main()
