from __future__ import annotations

import copy
import hashlib
import hmac
import json
import os
import stat
import subprocess
import sys
import tempfile
import unicodedata
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from PIL import Image, PngImagePlugin

from benchmarks.bria_bench.contracts import ContractError, validate_contract
from benchmarks.bria_bench.hashing import hash_tree
from benchmarks.bria_bench.registry import freeze_manifest


REPOSITORY_ROOT = Path(__file__).parents[1]
BRIA_BENCH_ROOT = REPOSITORY_ROOT / "benchmarks" / "bria_bench"
FORM_KEYS = {
    "reviewer_case_id",
    "presence",
    "comment_class",
    "locations",
    "observation",
    "scientific_relevance",
    "benign_explanations",
    "required_materials",
    "recommended_action",
}
ALGORITHM_CONTEXT = b"BRIA-BENCH/REVIEWER-PACKET/1\0"


def _json_bytes(payload: object) -> bytes:
    return (
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")


def _length_prefixed(value: str) -> bytes:
    encoded = unicodedata.normalize("NFC", value).encode("utf-8")
    return len(encoded).to_bytes(4, "big") + encoded


def _packet_bytes(root: Path) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(root.rglob("*"), key=lambda item: item.as_posix())
        if path.is_file()
    }


class ReviewerPacketFixture(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name).resolve()
        self.cases_root = self.root / "cases"
        self.annotations_root = self.root / "annotations"
        self.cases_root.mkdir()
        self.annotations_root.mkdir()
        self.case_ids = ["source_alpha", "source_beta", "source_gamma"]
        for index, case_id in enumerate(self.case_ids, start=1):
            package = self.cases_root / case_id
            (package / "nested").mkdir(parents=True)
            (package / "paper.txt").write_text(
                f"Neutral scientific material number {index}.\n", encoding="utf-8"
            )
            (package / "nested" / "data.csv").write_text(
                f"sample,value\nS{index},0.{index}\n", encoding="utf-8"
            )
            annotation = {
                "schema_version": "1.0.0",
                "case_id": case_id,
                "negative_control": False,
                "review_status": "controlled_ground_truth",
                "expected_observations": [],
            }
            (self.annotations_root / f"{case_id}.json").write_bytes(
                _json_bytes(annotation)
            )
        self.source_manifest = self.root / "benchmark_manifest.source.json"
        self.manifest = self.root / "benchmark_manifest.json"
        self.source_manifest.write_bytes(
            _json_bytes(
                {
                    "schema_version": "1.0.0",
                    "benchmark_id": "reviewer-packet-tests",
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
                        }
                        for case_id in self.case_ids
                    ],
                }
            )
        )
        self.refreeze()
        self.seed = self.root / "seed.txt"
        self.seed.write_text("01" * 32, encoding="ascii")
        self.output = self.root / "packet"
        self.mapping = self.root / "mapping.json"

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def refreeze(self) -> None:
        freeze_manifest(
            self.source_manifest,
            self.manifest,
            "2026-07-12T00:00:00Z",
        )

    def export(
        self,
        *,
        case_ids: list[str] | None = None,
        output: Path | None = None,
        mapping: Path | None = None,
        seed: Path | None = None,
    ) -> dict[str, object]:
        from benchmarks.bria_bench.reviewer_packet import export_reviewer_packet

        return export_reviewer_packet(
            self.manifest,
            case_ids if case_ids is not None else self.case_ids[:2],
            output if output is not None else self.output,
            mapping if mapping is not None else self.mapping,
            seed if seed is not None else self.seed,
        )

    def rewrite_frozen_manifest(self, transform: object) -> None:
        payload = json.loads(self.manifest.read_text(encoding="utf-8"))
        transform(payload)
        self.manifest.write_bytes(_json_bytes(payload))


class ReviewerPacketExportTests(ReviewerPacketFixture):
    def test_export_is_deterministic_strict_and_matches_hmac_contract(self) -> None:
        selected = ["source_beta", "source_alpha"]
        returned = self.export(case_ids=selected)
        packet_manifest_path = self.output / "packet_manifest.json"
        packet_manifest = json.loads(packet_manifest_path.read_text(encoding="utf-8"))
        mapping = json.loads(self.mapping.read_text(encoding="utf-8"))

        self.assertEqual(returned, packet_manifest)
        validate_contract("reviewer_packet_manifest.schema.json", packet_manifest)
        validate_contract("reviewer_mapping.schema.json", mapping)
        self.assertEqual(packet_manifest["schema_version"], "1.0.0")
        self.assertEqual(packet_manifest["packet_scope"], "workflow_demo_only")
        self.assertEqual(
            set(packet_manifest), {"schema_version", "packet_scope", "cases"}
        )
        self.assertEqual(
            [item["reviewer_case_id"] for item in packet_manifest["cases"]],
            ["BRIA-R001", "BRIA-R002"],
        )

        manifest_bytes = self.manifest.read_bytes()
        manifest_digest = hashlib.sha256(manifest_bytes).digest()
        normalized = sorted(unicodedata.normalize("NFC", item) for item in selected)
        selection_bytes = b"".join(_length_prefixed(item) for item in normalized)
        selection_digest = hashlib.sha256(selection_bytes).digest()
        seed_bytes = bytes.fromhex(self.seed.read_text(encoding="ascii"))
        ranked = sorted(
            (
                hmac.new(
                    seed_bytes,
                    ALGORITHM_CONTEXT
                    + manifest_digest
                    + selection_digest
                    + _length_prefixed(case_id),
                    hashlib.sha256,
                ).digest(),
                case_id,
            )
            for case_id in normalized
        )
        expected_mapping = [item[1] for item in ranked]
        self.assertEqual(
            [item["source_case_id"] for item in mapping["cases"]], expected_mapping
        )
        self.assertEqual(mapping["source_manifest_sha256"], manifest_digest.hex())
        self.assertEqual(mapping["selection_sha256"], selection_digest.hex())
        self.assertEqual(
            mapping["packet_manifest_sha256"],
            hashlib.sha256(packet_manifest_path.read_bytes()).hexdigest(),
        )
        self.assertEqual(
            mapping["anonymization"],
            {
                "algorithm": "hmac-sha256-ranked-permutation-v1",
                "seed_commitment_sha256": hashlib.sha256(seed_bytes).hexdigest(),
            },
        )
        self.assertEqual(stat.S_IMODE(self.mapping.stat().st_mode), 0o600)

        frozen = json.loads(self.manifest.read_text(encoding="utf-8"))
        frozen_by_id = {item["case_id"]: item for item in frozen["cases"]}
        mapped_by_reviewer = {
            item["reviewer_case_id"]: item for item in mapping["cases"]
        }
        for item in packet_manifest["cases"]:
            reviewer_id = item["reviewer_case_id"]
            source_id = mapped_by_reviewer[reviewer_id]["source_case_id"]
            source_package = self.cases_root / source_id
            materials = self.output / "cases" / reviewer_id / "materials"
            self.assertEqual(
                hash_tree(materials), frozen_by_id[source_id]["expected_sha256"]
            )
            self.assertEqual(
                item,
                {
                    "reviewer_case_id": reviewer_id,
                    "source_package_sha256": frozen_by_id[source_id]["expected_sha256"],
                    "annotation_schema_version": "1.0.0",
                },
            )
            self.assertEqual(
                {
                    path.relative_to(source_package).as_posix()
                    for path in source_package.rglob("*")
                },
                {
                    path.relative_to(materials).as_posix()
                    for path in materials.rglob("*")
                },
            )
            for source_file in source_package.rglob("*"):
                if source_file.is_file():
                    copied = materials / source_file.relative_to(source_package)
                    self.assertEqual(copied.read_bytes(), source_file.read_bytes())

            form = json.loads(
                (self.output / "forms" / f"{reviewer_id}.json").read_text(
                    encoding="utf-8"
                )
            )
            validate_contract("reviewer_form_template.schema.json", form)
            self.assertEqual(len(form), 1)
            self.assertEqual(set(form[0]), FORM_KEYS)
            self.assertEqual(
                form[0],
                {
                    "reviewer_case_id": reviewer_id,
                    "presence": None,
                    "comment_class": None,
                    "locations": [],
                    "observation": "",
                    "scientific_relevance": "",
                    "benign_explanations": [],
                    "required_materials": [],
                    "recommended_action": "",
                },
            )

        second_output = self.root / "packet-second"
        second_mapping = self.root / "mapping-second.json"
        self.export(
            case_ids=list(reversed(selected)),
            output=second_output,
            mapping=second_mapping,
        )
        self.assertEqual(_packet_bytes(self.output), _packet_bytes(second_output))
        self.assertEqual(self.mapping.read_bytes(), second_mapping.read_bytes())

    def test_seed_and_selection_change_external_mapping_without_exposing_seed(
        self,
    ) -> None:
        self.export(case_ids=self.case_ids[:2])
        first_mapping = self.mapping.read_bytes()
        first_packet = _packet_bytes(self.output)
        raw_seed = bytes.fromhex(self.seed.read_text(encoding="ascii"))

        second_seed = self.root / "seed-two.txt"
        second_seed.write_text("02" * 32, encoding="ascii")
        second_output = self.root / "packet-two"
        second_mapping = self.root / "mapping-two.json"
        self.export(
            case_ids=self.case_ids[:2],
            output=second_output,
            mapping=second_mapping,
            seed=second_seed,
        )
        self.assertNotEqual(first_mapping, second_mapping.read_bytes())

        third_output = self.root / "packet-three"
        third_mapping = self.root / "mapping-three.json"
        self.export(
            case_ids=self.case_ids,
            output=third_output,
            mapping=third_mapping,
        )
        self.assertNotEqual(first_mapping, third_mapping.read_bytes())

        all_first_bytes = b"\0".join(first_packet.values()) + first_mapping
        self.assertNotIn(self.seed.read_bytes(), all_first_bytes)
        self.assertNotIn(raw_seed, all_first_bytes)
        generated_json = [
            json.loads(
                (self.output / "packet_manifest.json").read_text(encoding="utf-8")
            ),
            json.loads(self.mapping.read_text(encoding="utf-8")),
        ]
        self.assertNotIn("timestamp", json.dumps(generated_json).lower())
        self.assertNotIn("reviewer_identity", json.dumps(generated_json).lower())

    def test_packet_contains_no_source_ids_paths_labels_or_external_mapping(
        self,
    ) -> None:
        self.export()
        packet_bytes = b"\0".join(_packet_bytes(self.output).values())
        packet_text = packet_bytes.decode("utf-8", errors="ignore")
        for source_id in self.case_ids:
            self.assertNotIn(source_id, packet_text)
        self.assertNotIn(str(self.root), packet_text)
        for forbidden in (
            "expected_observations",
            "issue_family",
            "risk_range",
            "normalized_observation",
            "detector_registry",
            "source_case_id",
            "seed_commitment_sha256",
        ):
            self.assertNotIn(forbidden, packet_text)
        self.assertFalse((self.output / self.mapping.name).exists())
        self.assertFalse(
            any(path.name == self.mapping.name for path in self.output.rglob("*"))
        )

    def test_rejects_empty_duplicate_unknown_and_non_sequence_selection(self) -> None:
        from benchmarks.bria_bench.reviewer_packet import ReviewerPacketError

        for selected in ([], ["source_alpha", "source_alpha"], ["unknown"]):
            with self.subTest(selected=selected):
                with self.assertRaises(ReviewerPacketError):
                    self.export(case_ids=selected)
        with self.assertRaises(ReviewerPacketError):
            self.export(case_ids="source_alpha")  # type: ignore[arg-type]

    def test_seed_file_is_exact_lowercase_hex_without_newline(self) -> None:
        from benchmarks.bria_bench.reviewer_packet import ReviewerPacketError

        invalid_values = [
            b"0" * 63,
            b"0" * 65,
            b"A" * 64,
            b"01" * 32 + b"\n",
            b"g" * 64,
            bytes(range(64)),
        ]
        for index, value in enumerate(invalid_values):
            with self.subTest(value=value[:10]):
                seed = self.root / f"invalid-seed-{index}"
                seed.write_bytes(value)
                with self.assertRaises(ReviewerPacketError):
                    self.export(
                        output=self.root / f"packet-{index}",
                        mapping=self.root / f"mapping-{index}.json",
                        seed=seed,
                    )

    def test_rejects_nonredistributable_license_and_frozen_hash_mismatch(self) -> None:
        from benchmarks.bria_bench.reviewer_packet import ReviewerPacketError

        def set_redistributable(payload: dict[str, object]) -> None:
            payload["cases"][0]["redistributable"] = False  # type: ignore[index]

        self.rewrite_frozen_manifest(set_redistributable)
        with self.assertRaisesRegex(ReviewerPacketError, "redistributable"):
            self.export(case_ids=["source_alpha"])

        self.refreeze()

        def set_license(payload: dict[str, object]) -> None:
            payload["cases"][0]["license"] = "Proprietary"  # type: ignore[index]

        self.rewrite_frozen_manifest(set_license)
        with self.assertRaisesRegex(ReviewerPacketError, "license"):
            self.export(case_ids=["source_alpha"])

        self.refreeze()

        def set_hash(payload: dict[str, object]) -> None:
            payload["cases"][0]["expected_sha256"] = "0" * 64  # type: ignore[index]

        self.rewrite_frozen_manifest(set_hash)
        with self.assertRaisesRegex(ReviewerPacketError, "hash mismatch"):
            self.export(case_ids=["source_alpha"])
        self.assertFalse(self.output.exists())
        self.assertFalse(self.mapping.exists())

    def test_source_xattrs_permissions_and_timestamps_are_not_copied(self) -> None:
        source = self.cases_root / "source_alpha" / "paper.txt"
        source.chmod(0o777)
        os.utime(source, (946684800, 946684800))
        xattr_set = False
        if hasattr(os, "setxattr"):
            try:
                os.setxattr(source, "com.example.reviewer-test", b"private metadata")
                xattr_set = True
            except OSError:
                pass
        self.refreeze()
        self.export(case_ids=["source_alpha"])
        copied = self.output / "cases" / "BRIA-R001" / "materials" / "paper.txt"
        self.assertNotEqual(stat.S_IMODE(copied.stat().st_mode), 0o777)
        self.assertNotEqual(int(copied.stat().st_mtime), 946684800)
        if xattr_set and hasattr(os, "listxattr"):
            self.assertEqual(os.listxattr(copied), [])


class ReviewerFormContractTests(unittest.TestCase):
    def row(self, **updates: object) -> dict[str, object]:
        row: dict[str, object] = {
            "reviewer_case_id": "BRIA-R001",
            "presence": "present",
            "comment_class": "major",
            "locations": ["figures/Figure_1A.png: upper-left region"],
            "observation": "The displayed regions have matching visual structure.",
            "scientific_relevance": "The comparison affects interpretation of the result.",
            "benign_explanations": [
                "A shared acquisition field could explain the match."
            ],
            "required_materials": ["Original acquisition files"],
            "recommended_action": "Compare the original files and document the relationship.",
        }
        row.update(updates)
        return row

    def test_completed_form_accepts_multiple_present_observations(self) -> None:
        payload = [self.row(), self.row(comment_class="minor", locations=["Table 2"])]
        validate_contract("reviewer_form_completed.schema.json", payload)

    def test_completed_form_accepts_materials_request_and_absent(self) -> None:
        validate_contract(
            "reviewer_form_completed.schema.json",
            [
                self.row(
                    presence="insufficient_materials",
                    comment_class="materials_request",
                    locations=[],
                    observation="The summary cannot be checked from the supplied files.",
                    scientific_relevance="The underlying values are needed for review.",
                    required_materials=["Underlying sample-level values"],
                )
            ],
        )
        validate_contract(
            "reviewer_form_completed.schema.json",
            [
                self.row(
                    presence="absent",
                    comment_class=None,
                    locations=[],
                    observation="",
                    scientific_relevance="",
                    benign_explanations=[],
                    required_materials=[],
                    recommended_action="",
                )
            ],
        )

    def test_completed_form_enforces_cross_field_semantics(self) -> None:
        invalid = [
            [self.row(locations=[])],
            [self.row(observation="")],
            [self.row(comment_class="materials_request")],
            [
                self.row(
                    presence="insufficient_materials",
                    comment_class="minor",
                    locations=[],
                )
            ],
            [
                self.row(
                    presence="insufficient_materials",
                    comment_class="materials_request",
                    locations=[],
                    required_materials=[],
                )
            ],
            [
                self.row(
                    presence="absent",
                    comment_class=None,
                    locations=[],
                    observation="",
                    scientific_relevance="",
                    benign_explanations=[],
                    required_materials=[],
                    recommended_action="",
                ),
                self.row(),
            ],
            [self.row(), self.row(reviewer_case_id="BRIA-R002")],
        ]
        for payload in invalid:
            with self.subTest(payload=payload):
                with self.assertRaises(ContractError):
                    validate_contract("reviewer_form_completed.schema.json", payload)

    def test_template_and_completed_contracts_are_separate_and_strict(self) -> None:
        blank = [
            {
                "reviewer_case_id": "BRIA-R001",
                "presence": None,
                "comment_class": None,
                "locations": [],
                "observation": "",
                "scientific_relevance": "",
                "benign_explanations": [],
                "required_materials": [],
                "recommended_action": "",
            }
        ]
        validate_contract("reviewer_form_template.schema.json", blank)
        with self.assertRaises(ContractError):
            validate_contract("reviewer_form_completed.schema.json", blank)
        with self.assertRaises(ContractError):
            validate_contract("reviewer_form_template.schema.json", [self.row()])
        blank[0]["unexpected"] = "not allowed"
        with self.assertRaises(ContractError):
            validate_contract("reviewer_form_template.schema.json", blank)

    def test_packet_and_mapping_require_unique_reviewer_and_source_ids(self) -> None:
        packet_case = {
            "reviewer_case_id": "BRIA-R001",
            "source_package_sha256": "1" * 64,
            "annotation_schema_version": "1.0.0",
        }
        with self.assertRaises(ContractError):
            validate_contract(
                "reviewer_packet_manifest.schema.json",
                {
                    "schema_version": "1.0.0",
                    "packet_scope": "workflow_demo_only",
                    "cases": [packet_case, dict(packet_case)],
                },
            )
        mapping_case = {
            "reviewer_case_id": "BRIA-R001",
            "source_case_id": "source_alpha",
            "source_package_sha256": "1" * 64,
            "source_annotation_sha256": "2" * 64,
        }
        base = {
            "schema_version": "1.0.0",
            "packet_manifest_sha256": "3" * 64,
            "source_manifest_sha256": "4" * 64,
            "selection_sha256": "5" * 64,
            "anonymization": {
                "algorithm": "hmac-sha256-ranked-permutation-v1",
                "seed_commitment_sha256": "6" * 64,
            },
            "cases": [mapping_case, dict(mapping_case, reviewer_case_id="BRIA-R002")],
        }
        with self.assertRaises(ContractError):
            validate_contract("reviewer_mapping.schema.json", base)

        invalid_packet = {
            "schema_version": "1.0.0",
            "packet_scope": "workflow_demo_only",
            "cases": [dict(packet_case, reviewer_case_id="BRIA-R001\n")],
        }
        with self.assertRaises(ContractError):
            validate_contract("reviewer_packet_manifest.schema.json", invalid_packet)

        invalid_mapping = copy.deepcopy(base)
        invalid_mapping["cases"] = [dict(mapping_case, source_case_id="source_alpha\n")]
        with self.assertRaises(ContractError):
            validate_contract("reviewer_mapping.schema.json", invalid_mapping)


class ReviewerPacketLeakageTests(ReviewerPacketFixture):
    def assert_leak_rejected(
        self,
        expected: str | None = None,
        *,
        hidden_values: tuple[str, ...] = (),
    ) -> None:
        from benchmarks.bria_bench.reviewer_packet import ReviewerPacketError

        context = (
            self.assertRaisesRegex(ReviewerPacketError, expected)
            if expected is not None
            else self.assertRaises(ReviewerPacketError)
        )
        with context as caught:
            self.export(case_ids=["source_alpha"])
        message = str(caught.exception)
        for value in hidden_values:
            self.assertNotIn(value, message)
        self.assertFalse(self.output.exists())
        self.assertFalse(self.mapping.exists())
        self.assertEqual(list(self.root.glob(".packet.stage-*")), [])

    def test_sniffs_utf8_text_even_when_named_pdf_or_binary(self) -> None:
        (self.cases_root / "source_alpha" / "opaque.pdf").write_bytes(
            b"expected_observations: do not disclose\n"
        )
        self.refreeze()
        self.assert_leak_rejected("sensitive")

    def test_rejects_exact_source_id_and_local_absolute_path_in_binary(self) -> None:
        (self.cases_root / "source_alpha" / "opaque.bin").write_bytes(
            b"prefix\x00source_beta\x00/Users/private/review.txt\x00suffix"
        )
        self.refreeze()
        self.assert_leak_rejected()

    def test_rejects_bomless_utf16_leakage_without_echoing_values(self) -> None:
        sensitive = (
            "source_alpha",
            "expected_observations",
            "/Users/private/review.txt",
        )
        text = " | ".join(sensitive)
        (self.cases_root / "source_alpha" / "encoded.bin").write_bytes(
            text.encode("utf-16-le")
        )
        self.refreeze()
        self.assert_leak_rejected(hidden_values=sensitive)

    def test_rejects_bom_tagged_utf16_and_utf32_leakage(self) -> None:
        from benchmarks.bria_bench.reviewer_packet import ReviewerPacketError

        sensitive = "expected_observations"
        encodings = ("utf-16", "utf-16-be", "utf-32", "utf-32-be")
        for index, encoding in enumerate(encodings):
            with self.subTest(encoding=encoding):
                output = self.root / f"packet-{index}"
                mapping = self.root / f"mapping-{index}.json"
                data = sensitive.encode(encoding)
                if encoding.endswith("-be"):
                    data = (
                        b"\xfe\xff" if encoding == "utf-16-be" else b"\x00\x00\xfe\xff"
                    ) + data
                (self.cases_root / "source_alpha" / "encoded.bin").write_bytes(data)
                self.refreeze()

                with self.assertRaises(ReviewerPacketError) as caught:
                    self.export(
                        case_ids=["source_alpha"],
                        output=output,
                        mapping=mapping,
                    )
                self.assertNotIn(sensitive, str(caught.exception))
                self.assertFalse(output.exists())
                self.assertFalse(mapping.exists())

    def test_rejects_utf16_in_deflated_docx_member_without_echoing_values(
        self,
    ) -> None:
        sensitive = (
            "source_alpha",
            "expected_observations",
            "/Users/private/review.txt",
        )
        archive_path = self.cases_root / "source_alpha" / "document.docx"
        with zipfile.ZipFile(
            archive_path,
            "w",
            compression=zipfile.ZIP_DEFLATED,
        ) as archive:
            archive.writestr(
                "word/document.xml",
                " | ".join(sensitive).encode("utf-16-be"),
            )
        self.refreeze()
        self.assert_leak_rejected(hidden_values=sensitive)

    def test_rejects_zip_traversal_and_office_creator_metadata(self) -> None:
        archive_path = self.cases_root / "source_alpha" / "document.dat"
        with zipfile.ZipFile(archive_path, "w") as archive:
            archive.writestr("../outside.txt", "neutral")
        self.refreeze()
        self.assert_leak_rejected("traversal")

    def test_rejects_zip_member_content_without_trusting_outer_suffix(self) -> None:
        archive_path = self.cases_root / "source_alpha" / "document.dat"
        with zipfile.ZipFile(archive_path, "w") as archive:
            archive.writestr(
                "docProps/core.xml",
                "<cp:coreProperties><dc:creator>private-user</dc:creator>"
                "</cp:coreProperties>",
            )
        self.refreeze()
        self.assert_leak_rejected("identity")

    def test_rejects_png_text_metadata_without_trusting_suffix(self) -> None:
        image = Image.new("RGB", (4, 4), color="white")
        metadata = PngImagePlugin.PngInfo()
        metadata.add_text("Author", "private.user@example.org")
        path = self.cases_root / "source_alpha" / "image.dat"
        image.save(path, format="PNG", pnginfo=metadata)
        self.refreeze()
        self.assert_leak_rejected()

    def test_allows_neutral_png_international_text_metadata(self) -> None:
        image = Image.new("RGB", (4, 4), color="white")
        metadata = PngImagePlugin.PngInfo()
        metadata.add_itxt("Description", "Neutral microscopy overview")
        path = self.cases_root / "source_alpha" / "image.dat"
        image.save(path, format="PNG", pnginfo=metadata)
        self.refreeze()
        self.export(case_ids=["source_alpha"])
        self.assertTrue(
            (self.output / "cases" / "BRIA-R001" / "materials" / "image.dat").is_file()
        )

    def test_rejects_jpeg_exif_identity_without_trusting_suffix(self) -> None:
        image = Image.new("RGB", (4, 4), color="white")
        exif = Image.Exif()
        exif[315] = "private-user"
        path = self.cases_root / "source_alpha" / "image.dat"
        image.save(path, format="JPEG", exif=exif)
        self.refreeze()
        self.assert_leak_rejected("identity")

    def test_rejects_utf16_jpeg_user_comment_without_echoing_values(self) -> None:
        sensitive = (
            "source_alpha",
            "expected_observations",
            "/Users/private/review.txt",
        )
        image = Image.new("RGB", (4, 4), color="white")
        exif = Image.Exif()
        exif[37510] = b"UNICODE\x00" + " | ".join(sensitive).encode("utf-16-le")
        path = self.cases_root / "source_alpha" / "image.dat"
        image.save(path, format="JPEG", exif=exif)
        self.refreeze()
        self.assert_leak_rejected(hidden_values=sensitive)

    def test_rejects_real_pdf_metadata_and_text_without_trusting_suffix(self) -> None:
        import fitz

        document = fitz.open()
        page = document.new_page()
        page.insert_text((72, 72), "Neutral manuscript text")
        document.set_metadata({"author": "private-user"})
        path = self.cases_root / "source_alpha" / "document.dat"
        document.save(path)
        document.close()
        self.refreeze()
        self.assert_leak_rejected("identity")

    def test_rejects_credentials_and_administrative_artifacts(self) -> None:
        package = self.cases_root / "source_alpha"
        (package / "notes.txt").write_text(
            "-----BEGIN PRIVATE KEY-----\nsecret\n", encoding="utf-8"
        )
        self.refreeze()
        self.assert_leak_rejected("credential")

    def test_rejects_analysis_identifiers_and_binary_credentials(self) -> None:
        package = self.cases_root / "source_alpha"
        (package / "opaque.bin").write_bytes(
            b"\xff\x00channel_metadata_consistency\x00password=private-value"
        )
        self.refreeze()
        self.assert_leak_rejected()

    def test_rejects_administrative_mapping_material(self) -> None:
        (self.cases_root / "source_alpha" / "mapping.json").write_text(
            '{"BRIA-R001":"private"}\n', encoding="utf-8"
        )
        self.refreeze()
        self.assert_leak_rejected("Administrative")

    def test_scanner_does_not_ban_ordinary_scientific_reuse_word(self) -> None:
        (self.cases_root / "source_alpha" / "paper.txt").write_text(
            "The protocol permits sample reuse for an orthogonal assay.\n",
            encoding="utf-8",
        )
        self.refreeze()
        self.export(case_ids=["source_alpha"])
        copied = self.output / "cases" / "BRIA-R001" / "materials" / "paper.txt"
        self.assertIn("reuse", copied.read_text(encoding="utf-8"))


class ReviewerPacketPlacementAndAtomicityTests(ReviewerPacketFixture):
    def assert_no_stage_artifacts(self) -> None:
        stages = [path for path in self.root.rglob("*") if ".stage-" in path.name]
        self.assertEqual(stages, [])

    def test_rejects_mapping_equal_beneath_or_ancestor_of_packet(self) -> None:
        from benchmarks.bria_bench.reviewer_packet import ReviewerPacketError

        placements = [
            self.output,
            self.output / "mapping.json",
            self.root,
        ]
        for index, mapping in enumerate(placements):
            with self.subTest(mapping=mapping):
                with self.assertRaises(ReviewerPacketError):
                    self.export(
                        output=self.root / f"packet-{index}",
                        mapping=(self.root / f"packet-{index}")
                        if index == 0
                        else (
                            self.root / f"packet-{index}" / "mapping.json"
                            if index == 1
                            else mapping
                        ),
                    )

    def test_rejects_symlink_aliases_and_symlinked_packet_components(self) -> None:
        from benchmarks.bria_bench.reviewer_packet import ReviewerPacketError

        alias = self.root / "alias"
        try:
            alias.symlink_to(self.root, target_is_directory=True)
        except OSError as exc:
            self.skipTest(f"symlinks unavailable: {exc}")
        with self.assertRaises(ReviewerPacketError):
            self.export(
                output=alias / "packet",
                mapping=self.root / "mapping-alias.json",
            )
        self.assertFalse((self.root / "packet").exists())

    def test_existing_targets_are_never_overwritten(self) -> None:
        from benchmarks.bria_bench.reviewer_packet import ReviewerPacketError

        self.output.mkdir()
        marker = self.output / "keep.txt"
        marker.write_text("keep packet\n", encoding="utf-8")
        self.mapping.write_text("keep mapping\n", encoding="utf-8")
        with self.assertRaises(ReviewerPacketError):
            self.export()
        self.assertEqual(marker.read_text(encoding="utf-8"), "keep packet\n")
        self.assertEqual(self.mapping.read_text(encoding="utf-8"), "keep mapping\n")

    def test_copy_scan_and_mapping_faults_leave_no_partial_packet(self) -> None:
        from benchmarks.bria_bench import reviewer_packet

        faults = ["_copy_materials", "_scan_staged_packet", "_write_mapping_stage"]
        for index, name in enumerate(faults):
            output = self.root / f"packet-fault-{index}"
            mapping = self.root / f"mapping-fault-{index}.json"
            with self.subTest(name=name):
                with patch.object(
                    reviewer_packet, name, side_effect=OSError(f"fault in {name}")
                ):
                    with self.assertRaises(Exception):
                        self.export(output=output, mapping=mapping)
                self.assertFalse(output.exists())
                self.assertFalse(mapping.exists())
                self.assertEqual(list(self.root.glob(f".{output.name}.stage-*")), [])
                self.assertEqual(list(self.root.glob(f".{mapping.name}.stage-*")), [])

    def test_mapping_publish_failure_never_publishes_packet(self) -> None:
        from benchmarks.bria_bench import reviewer_packet

        with patch.object(
            reviewer_packet,
            "_publish_no_replace",
            side_effect=OSError("mapping publish fault"),
        ):
            with self.assertRaises(Exception):
                self.export()
        self.assertFalse(self.output.exists())
        self.assertFalse(self.mapping.exists())

    def test_packet_publish_failure_may_leave_mapping_only_never_packet_only(
        self,
    ) -> None:
        from benchmarks.bria_bench import reviewer_packet

        real_publish = reviewer_packet._publish_no_replace
        calls = 0

        def fail_second(source: Path, target: Path) -> None:
            nonlocal calls
            calls += 1
            if calls == 2:
                raise OSError("packet publish fault")
            real_publish(source, target)

        with patch.object(
            reviewer_packet, "_publish_no_replace", side_effect=fail_second
        ):
            with self.assertRaises(Exception):
                self.export()
        self.assertEqual(calls, 2)
        self.assertTrue(self.mapping.is_file())
        self.assertEqual(stat.S_IMODE(self.mapping.stat().st_mode), 0o600)
        self.assertFalse(self.output.exists())
        self.assertEqual(list(self.root.glob(".packet.stage-*")), [])

    def test_revalidates_packet_after_mapping_stage_and_before_packet_commit(
        self,
    ) -> None:
        from benchmarks.bria_bench import reviewer_packet

        real_validate = reviewer_packet._validate_staged_packet
        validation_states: list[tuple[bool, bool]] = []

        def record_validation(*args: object, **kwargs: object) -> None:
            validation_states.append(
                (
                    bool(list(self.root.glob(".mapping.json.stage-*"))),
                    self.mapping.exists(),
                )
            )
            real_validate(*args, **kwargs)

        with patch.object(
            reviewer_packet,
            "_validate_staged_packet",
            side_effect=record_validation,
        ):
            self.export(case_ids=["source_alpha"])
        self.assertEqual(
            validation_states,
            [(False, False), (True, False), (False, True)],
        )

    def test_hard_linked_mapping_in_packet_is_rejected_after_first_recheck(
        self,
    ) -> None:
        from benchmarks.bria_bench import reviewer_packet
        from benchmarks.bria_bench.reviewer_packet import ReviewerPacketError

        real_recheck = reviewer_packet._recheck_before_mapping_publish

        def inject_hard_link(placement: object) -> None:
            real_recheck(placement)
            packet_stage = next(self.root.glob(".packet.stage-*"))
            mapping_stage = next(self.root.glob(".mapping.json.stage-*"))
            os.link(mapping_stage, packet_stage / "forms" / "mapping-alias.bin")

        with patch.object(
            reviewer_packet,
            "_recheck_before_mapping_publish",
            side_effect=inject_hard_link,
        ):
            with self.assertRaises(ReviewerPacketError):
                self.export(case_ids=["source_alpha"])
        self.assertFalse(self.output.exists())
        if self.mapping.exists():
            mapping_stat = self.mapping.lstat()
            self.assertEqual(stat.S_IMODE(mapping_stat.st_mode), 0o600)
            self.assertEqual(mapping_stat.st_nlink, 1)
        self.assert_no_stage_artifacts()

    def test_published_mapping_hard_link_in_packet_leaves_clean_mapping_only(
        self,
    ) -> None:
        from benchmarks.bria_bench import reviewer_packet
        from benchmarks.bria_bench.reviewer_packet import ReviewerPacketError

        real_recheck = reviewer_packet._recheck_before_packet_publish

        def inject_hard_link(
            placement: object,
            mapping_identity: tuple[int, int],
        ) -> None:
            real_recheck(placement, mapping_identity)
            packet_stage = next(self.root.glob(".packet.stage-*"))
            os.link(self.mapping, packet_stage / "forms" / "mapping-alias.bin")

        with patch.object(
            reviewer_packet,
            "_recheck_before_packet_publish",
            side_effect=inject_hard_link,
        ):
            with self.assertRaises(ReviewerPacketError):
                self.export(case_ids=["source_alpha"])
        self.assertFalse(self.output.exists())
        mapping_stat = self.mapping.lstat()
        self.assertEqual(stat.S_IMODE(mapping_stat.st_mode), 0o600)
        self.assertEqual(mapping_stat.st_nlink, 1)
        self.assert_no_stage_artifacts()

    def test_mapping_stage_cleanup_includes_xattr_verification_failures(self) -> None:
        from benchmarks.bria_bench import reviewer_packet
        from benchmarks.bria_bench.reviewer_packet import ReviewerPacketError

        real_clear_xattrs = reviewer_packet._clear_xattrs

        def fail_mapping_xattrs(path: Path) -> None:
            if path.name.startswith(".mapping.json.stage-"):
                raise OSError("mapping xattr fault")
            real_clear_xattrs(path)

        with patch.object(
            reviewer_packet,
            "_clear_xattrs",
            side_effect=fail_mapping_xattrs,
        ):
            with self.assertRaises(ReviewerPacketError):
                self.export(case_ids=["source_alpha"])
        self.assertFalse(self.output.exists())
        self.assertFalse(self.mapping.exists())
        self.assert_no_stage_artifacts()

    def test_keyboard_interrupt_during_recheck_cleans_unpublished_stages(self) -> None:
        from benchmarks.bria_bench import reviewer_packet

        with patch.object(
            reviewer_packet,
            "_recheck_before_mapping_publish",
            side_effect=KeyboardInterrupt,
        ):
            with self.assertRaises(KeyboardInterrupt):
                self.export(case_ids=["source_alpha"])
        self.assertFalse(self.output.exists())
        self.assertFalse(self.mapping.exists())
        self.assert_no_stage_artifacts()

    def test_keyboard_interrupt_before_packet_publish_leaves_clean_mapping_only(
        self,
    ) -> None:
        from benchmarks.bria_bench import reviewer_packet

        real_publish = reviewer_packet._publish_no_replace
        calls = 0

        def interrupt_second_publish(source: Path, target: Path) -> None:
            nonlocal calls
            calls += 1
            if calls == 2:
                raise KeyboardInterrupt
            real_publish(source, target)

        with patch.object(
            reviewer_packet,
            "_publish_no_replace",
            side_effect=interrupt_second_publish,
        ):
            with self.assertRaises(KeyboardInterrupt):
                self.export(case_ids=["source_alpha"])
        self.assertEqual(calls, 2)
        self.assertFalse(self.output.exists())
        mapping_stat = self.mapping.lstat()
        self.assertEqual(stat.S_IMODE(mapping_stat.st_mode), 0o600)
        self.assertEqual(mapping_stat.st_nlink, 1)
        self.assert_no_stage_artifacts()


class ReviewerPacketGuideAndCliTests(unittest.TestCase):
    def test_reviewer_guide_states_workflow_demo_boundary_and_neutral_process(
        self,
    ) -> None:
        guide_path = BRIA_BENCH_ROOT / "REVIEWER_GUIDE.md"
        guide = guide_path.read_text(encoding="utf-8")
        lowered = guide.lower()
        for required in (
            "workflow_demo_only",
            "public fixtures",
            "not independent blinded evidence",
            "joinable",
            "package_note",
            "sealed private corpus",
            "hash index",
            "two independent reviewers",
            "forms are locked",
            "external adjudicator",
            "do not infer intent",
        ):
            self.assertIn(required, lowered)
        for forbidden in (
            "expected_observations",
            "issue_family",
            "risk_range",
            "detector",
            "overall score",
            "r0",
            "r1",
            "r2",
            "r3",
            "r4",
        ):
            self.assertNotIn(forbidden, lowered)

    def test_cli_requires_repeatable_case_and_seed_then_exports(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            seed = root / "seed"
            seed.write_text("03" * 32, encoding="ascii")
            packet = root / "packet"
            mapping = root / "mapping.json"
            command = [
                sys.executable,
                "-m",
                "benchmarks.bria_bench.cli",
                "reviewer-packet",
                "--manifest",
                str(BRIA_BENCH_ROOT / "benchmark_manifest.json"),
                "--case",
                "dev_001_global_flip",
                "--output-dir",
                str(packet),
                "--mapping-output",
                str(mapping),
                "--seed-file",
                str(seed),
            ]
            result = subprocess.run(
                command,
                cwd=REPOSITORY_ROOT,
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue((packet / "packet_manifest.json").is_file())
            self.assertTrue(mapping.is_file())

            missing_case = subprocess.run(
                [
                    item
                    for item in command
                    if item not in ("--case", "dev_001_global_flip")
                ],
                cwd=REPOSITORY_ROOT,
                capture_output=True,
                text=True,
            )
            self.assertEqual(missing_case.returncode, 2)
            self.assertIn("--case", missing_case.stderr)

            missing_seed = subprocess.run(
                command[:-2],
                cwd=REPOSITORY_ROOT,
                capture_output=True,
                text=True,
            )
            self.assertEqual(missing_seed.returncode, 2)
            self.assertIn("--seed-file", missing_seed.stderr)

    def test_current_public_fixture_packet_is_explicitly_demo_only(self) -> None:
        from benchmarks.bria_bench.reviewer_packet import export_reviewer_packet

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            seed = root / "seed"
            seed.write_text("04" * 32, encoding="ascii")
            packet = root / "packet"
            mapping = root / "mapping.json"
            export_reviewer_packet(
                BRIA_BENCH_ROOT / "benchmark_manifest.json",
                ["case_001", "dev_001_global_flip"],
                packet,
                mapping,
                seed,
            )
            manifest = json.loads(
                (packet / "packet_manifest.json").read_text(encoding="utf-8")
            )
            self.assertEqual(manifest["packet_scope"], "workflow_demo_only")
            guide = (packet / "REVIEWER_GUIDE.md").read_text(encoding="utf-8")
            self.assertIn("not independent blinded evidence", guide.lower())
            self.assertTrue(
                any(path.name == "PACKAGE_NOTE.txt" for path in packet.rglob("*"))
            )


if __name__ == "__main__":
    unittest.main()
