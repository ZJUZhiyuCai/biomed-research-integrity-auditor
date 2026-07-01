from __future__ import annotations

import importlib
import unittest


class RuntimeImportTests(unittest.TestCase):
    def test_required_runtime_dependencies_and_detectors_import(self) -> None:
        modules = [
            "numpy",
            "PIL",
            "yaml",
            "jsonschema",
            "openpyxl",
            "pypdf",
            "fitz",
            "requests",
            "detectors.image.global_near_duplicate",
            "detectors.image.local_patch_reuse",
            "detectors.stats.pseudoreplication_screen",
            "detectors.text.external_literature_search",
            "detectors.text.text_overlap_screen",
        ]
        for module in modules:
            with self.subTest(module=module):
                importlib.import_module(module)


if __name__ == "__main__":
    unittest.main()
