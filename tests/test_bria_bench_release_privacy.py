from __future__ import annotations

import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import unittest
from unittest.mock import patch
import zipfile

import scripts.build_release_artifacts as release_module


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
BRIA_BENCH_ROOT = REPOSITORY_ROOT / "benchmarks" / "bria_bench"
PRIVATE_DIRECTORY_MARKERS = (
    "runs",
    "results",
    "reviewer_packets",
    "reviewer-packets",
    "reviewer_packet",
    "reviewer-packet",
    "mappings",
    "reviewer_mappings",
    "reviewer-mappings",
    "api_cache",
    "api-cache",
    ".api_cache",
    ".api-cache",
    "cache",
    ".cache",
    "metrics",
    "local_metrics",
    "local-metrics",
    "seeds",
    "identity",
    "identities",
)


class BriaBenchReleasePrivacyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.output_root = Path(self.temporary.name)
        self.token = re.sub(r"[^A-Za-z0-9_-]", "_", self.output_root.name)
        self.created_files: list[Path] = []
        self.created_directories: set[Path] = set()
        committed_schemas = subprocess.run(
            [
                "git",
                "ls-files",
                "benchmarks/bria_bench/schemas/*.schema.json",
            ],
            cwd=REPOSITORY_ROOT,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.splitlines()
        self.public_schema_paths = tuple(
            Path(path).relative_to("benchmarks/bria_bench")
            for path in committed_schemas
        )
        self.reviewer_schema_paths = tuple(
            path for path in self.public_schema_paths if "reviewer" in path.name
        )
        self.assertEqual(
            {path.as_posix() for path in self.public_schema_paths},
            set(release_module.BRIA_BENCH_PUBLIC_SCHEMAS),
        )
        self.assertTrue(self.reviewer_schema_paths)
        self._create_file(
            BRIA_BENCH_ROOT
            / "schemas"
            / f"task12_private_{self.token}.schema.json"
        )

        marker_parent = (
            BRIA_BENCH_ROOT
            / "cases"
            / "dev"
            / "dev_001_global_flip"
            / f"task12_privacy_{self.token}"
        )
        self.private_marker_directories: list[Path] = []
        for marker in PRIVATE_DIRECTORY_MARKERS:
            directory = marker_parent / marker
            self.private_marker_directories.append(directory)
            self._create_file(directory / "token.json")
        self._create_file(
            marker_parent / "results" / f"public_summary_{self.token}.json"
        )

        filename_parent = (
            BRIA_BENCH_ROOT
            / "cases"
            / "dev"
            / "dev_002_independent_images"
            / f"task12_private_files_{self.token}"
        )
        private_filenames = (
            "run_summary.json",
            f"metrics-{self.token}.json",
            f"metrics_{self.token}.json",
            f"local_metrics_{self.token}.json",
            "reviewer_mapping.json",
            f"reviewer_mapping_{self.token}.json",
            f"{self.token}_mapping.json",
            "reviewer_packet_manifest.json",
            f"reviewer_packet_{self.token}.json",
            f"reviewer-packet_{self.token}.zip",
            f"seed_{self.token}.txt",
            f"{self.token}_identity.json",
            f"{self.token}_api_cache.json",
            f"{self.token}_api-cache.json",
        )
        for filename in private_filenames:
            self._create_file(filename_parent / filename)

        annotation_parent = (
            BRIA_BENCH_ROOT / "annotations" / "dev" / f"task12_privacy_{self.token}"
        )
        self._create_file(annotation_parent / "api_cache" / "token.json")
        self._create_file(
            annotation_parent / "reviewer_packets" / "packet_manifest.json"
        )
        self._create_file(annotation_parent / f"metrics-{self.token}.json")
        self._create_file(annotation_parent / "reviewer_mapping.json")
        self._create_file(annotation_parent / "reviewer_packet_manifest.json")

        self._create_file(BRIA_BENCH_ROOT / "results" / "reviewer_mapping.json")
        self._create_file(
            BRIA_BENCH_ROOT / "results" / "reviewer_packet_manifest.json"
        )

        self.allowed_paths = (
            Path("results") / f"release_summary_{self.token}.json",
            Path("results") / f"public_summary_{self.token}.json",
        )
        for relative in self.allowed_paths:
            self._create_file(BRIA_BENCH_ROOT / relative)

        self.private_paths = tuple(
            path.relative_to(BRIA_BENCH_ROOT) for path in self.created_files
            if path.relative_to(BRIA_BENCH_ROOT) not in self.allowed_paths
        )

    def tearDown(self) -> None:
        for path in reversed(self.created_files):
            path.unlink(missing_ok=True)
        for directory in sorted(
            self.created_directories, key=lambda item: len(item.parts), reverse=True
        ):
            try:
                directory.rmdir()
            except OSError:
                pass
        self.temporary.cleanup()

    def _create_file(self, path: Path) -> None:
        missing: list[Path] = []
        parent = path.parent
        while parent != BRIA_BENCH_ROOT and not parent.exists():
            missing.append(parent)
            parent = parent.parent
        path.parent.mkdir(parents=True, exist_ok=True)
        self.created_directories.update(missing)
        path.write_text('{"task12": "private fixture"}\n', encoding="utf-8")
        self.created_files.append(path)

    def _copy_project_source(self) -> Path:
        source_root = self.output_root / "source"
        shutil.copytree(
            REPOSITORY_ROOT,
            source_root,
            ignore=shutil.ignore_patterns(
                ".git",
                ".venv",
                "*.egg-info",
                "__pycache__",
                "build",
                "dist",
                "node_modules",
                "tmp",
            ),
        )
        return source_root

    @staticmethod
    def _benchmark_members(names: set[str]) -> set[str]:
        marker = "benchmarks/bria_bench/"
        return {name[name.index(marker) :] for name in names if marker in name}

    def _assert_archive_privacy(self, members: set[str]) -> None:
        private = {
            f"benchmarks/bria_bench/{path.as_posix()}" for path in self.private_paths
        }
        allowed = {
            f"benchmarks/bria_bench/{path.as_posix()}" for path in self.allowed_paths
        }
        self.assertTrue(private.isdisjoint(members), private & members)
        self.assertTrue(allowed.issubset(members), allowed - members)
        self.assertIn("benchmarks/bria_bench/README.md", members)
        self.assertIn("benchmarks/bria_bench/results/.gitkeep", members)
        self.assertIn("benchmarks/bria_bench/schemas/metrics.schema.json", members)
        for relative in self.public_schema_paths:
            self.assertIn(f"benchmarks/bria_bench/{relative.as_posix()}", members)
        self.assertIn(
            "benchmarks/bria_bench/cases/dev/dev_001_global_flip/PACKAGE_NOTE.txt",
            members,
        )

    def test_nested_private_artifacts_are_git_ignored(self) -> None:
        for relative in self.private_paths:
            completed = subprocess.run(
                [
                    "git",
                    "check-ignore",
                    "--quiet",
                    "--",
                    f"benchmarks/bria_bench/{relative.as_posix()}",
                ],
                cwd=REPOSITORY_ROOT,
                check=False,
            )
            self.assertEqual(completed.returncode, 0, relative.as_posix())

        for relative in self.allowed_paths:
            completed = subprocess.run(
                [
                    "git",
                    "check-ignore",
                    "--quiet",
                    "--",
                    f"benchmarks/bria_bench/{relative.as_posix()}",
                ],
                cwd=REPOSITORY_ROOT,
                check=False,
            )
            self.assertEqual(completed.returncode, 1, relative.as_posix())

        for relative in self.public_schema_paths:
            completed = subprocess.run(
                [
                    "git",
                    "check-ignore",
                    "--no-index",
                    "--quiet",
                    "--",
                    f"benchmarks/bria_bench/{relative.as_posix()}",
                ],
                cwd=REPOSITORY_ROOT,
                check=False,
            )
            self.assertEqual(completed.returncode, 1, relative.as_posix())

    def test_sdist_wheel_and_release_zip_are_fail_closed(self) -> None:
        source_root = self._copy_project_source()
        sdist_dir = self.output_root / "sdist"
        wheel_dir = self.output_root / "wheel"
        site_dir = self.output_root / "site"
        sdist_dir.mkdir()
        wheel_dir.mkdir()
        subprocess.run(
            [
                sys.executable,
                "-c",
                "import sys; from setuptools.build_meta import build_sdist; "
                "build_sdist(sys.argv[1])",
                str(sdist_dir),
            ],
            cwd=source_root,
            check=True,
            capture_output=True,
            text=True,
        )
        subprocess.run(
            [
                sys.executable,
                "-m",
                "pip",
                "wheel",
                "--no-build-isolation",
                "--no-deps",
                "--wheel-dir",
                str(wheel_dir),
                str(source_root),
            ],
            cwd=source_root,
            check=True,
            capture_output=True,
            text=True,
        )

        sdist = next(sdist_dir.glob("*.tar.gz"))
        with tarfile.open(sdist, "r:gz") as archive:
            sdist_members = self._benchmark_members(set(archive.getnames()))
        self._assert_archive_privacy(sdist_members)

        wheel = next(wheel_dir.glob("*.whl"))
        with zipfile.ZipFile(wheel) as archive:
            wheel_members = self._benchmark_members(set(archive.namelist()))
        self._assert_archive_privacy(wheel_members)
        subprocess.run(
            [
                sys.executable,
                "-m",
                "pip",
                "install",
                "--no-deps",
                "--target",
                str(site_dir),
                str(wheel),
            ],
            cwd=self.output_root,
            check=True,
            capture_output=True,
            text=True,
        )
        schema_names = [path.name for path in self.reviewer_schema_paths]
        load_check = subprocess.run(
            [
                sys.executable,
                "-I",
                "-c",
                "import json,sys; sys.path.insert(0,sys.argv[1]); "
                "from benchmarks.bria_bench.contracts import load_schema; "
                "from jsonschema import Draft202012Validator; "
                "schemas=[load_schema(name) for name in json.loads(sys.argv[2])]; "
                "[Draft202012Validator.check_schema(schema) for schema in schemas]",
                str(site_dir),
                json.dumps(schema_names),
            ],
            cwd=self.output_root,
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(load_check.returncode, 0, load_check.stderr)

        release_zip = self.output_root / "release-source.zip"
        with patch.object(release_module, "ROOT", source_root):
            release_module.write_zip(
                release_zip, release_module.iter_source_files(), "task12-source"
            )
        with zipfile.ZipFile(release_zip) as archive:
            release_members = self._benchmark_members(set(archive.namelist()))
        self._assert_archive_privacy(release_members)

    def test_release_walk_prunes_private_directories_deterministically(self) -> None:
        visited: list[Path] = []
        original_walk = os.walk

        def tracking_walk(*args: object, **kwargs: object):
            for current, directories, filenames in original_walk(*args, **kwargs):
                visited.append(Path(current).resolve())
                yield current, directories, filenames

        with patch.object(release_module.os, "walk", tracking_walk):
            first = release_module.iter_source_files()
        second = release_module.iter_source_files()

        self.assertEqual(first, second)
        for directory in self.private_marker_directories:
            self.assertNotIn(directory.resolve(), visited, directory)
        included = {
            path.relative_to(REPOSITORY_ROOT).as_posix() for path in first
        }
        self._assert_archive_privacy(included)

    def test_release_copy_uses_only_the_current_distribution_version(self) -> None:
        source_root = self._copy_project_source()
        dist_dir = source_root / "dist"
        dist_dir.mkdir()
        version = release_module.project_version()
        expected = {
            f"biomed_research_integrity_auditor-{version}.tar.gz",
            f"biomed_research_integrity_auditor-{version}-py3-none-any.whl",
        }
        for name in expected | {
            "biomed_research_integrity_auditor-0.0.0.tar.gz",
            "biomed_research_integrity_auditor-0.0.0-py3-none-any.whl",
        }:
            (dist_dir / name).write_bytes(name.encode("ascii"))
        output = self.output_root / "copied-dist"
        output.mkdir()

        with patch.object(release_module, "ROOT", source_root):
            copied = release_module.copy_dist_artifacts(output)

        self.assertEqual({path.name for path in copied}, expected)
        self.assertEqual({path.name for path in output.iterdir()}, expected)

    def test_smoke_target_cleans_before_run_and_keeps_manual_resumability(self) -> None:
        makefile = (REPOSITORY_ROOT / "Makefile").read_text(encoding="utf-8")
        readme = (BRIA_BENCH_ROOT / "README.md").read_text(encoding="utf-8")

        def target_lines(name: str) -> list[str]:
            match = re.search(
                rf"^{re.escape(name)}:\n((?:\t.*\n)+)", makefile, re.MULTILINE
            )
            self.assertIsNotNone(match, name)
            return match.group(1).rstrip().splitlines()

        smoke = target_lines("benchmark-smoke")
        self.assertIn(
            "BENCHMARK_FROZEN_AT ?= 2026-07-11T00:00:00Z",
            makefile,
        )
        self.assertIn(
            "--frozen-at $(BENCHMARK_FROZEN_AT)",
            "\n".join(target_lines("benchmark-freeze")),
        )
        self.assertIn("make benchmark-freeze", readme)
        self.assertIn("git diff --exit-code", readme)
        self.assertEqual(smoke[0], "\trm -rf $(BRIA_BENCH_SMOKE_DIR)")
        self.assertEqual(smoke[1], "\tmkdir -p $(BRIA_BENCH_SMOKE_DIR)")
        self.assertIn(
            "rm -rf tmp/bria_bench_smoke\nmkdir -p tmp/bria_bench_smoke", readme
        )
        self.assertIn(" --adapter full --timeout-seconds 60", smoke[2])
        self.assertIn("--split dev", smoke[2])
        self.assertIn("--split dev", smoke[3])
        self.assertEqual(
            smoke[-1],
            "\t$(PYTHON) -m benchmarks.bria_bench.cli report "
            "--metrics $(BRIA_BENCH_SMOKE_DIR)/metrics.json "
            "--output $(BRIA_BENCH_SMOKE_DIR)/REPORT.md",
        )
        self.assertNotIn("rm -rf", "\n".join(target_lines("benchmark")))

        release = target_lines("release-artifacts")
        build_index = release.index("\trm -rf build *.egg-info dist/release")
        self.assertLess(build_index, release.index("\t$(PYTHON) -m build"))
        dist_index = release.index(
            "\trm -f dist/biomed_research_integrity_auditor-*.whl "
            "dist/biomed_research_integrity_auditor-*.tar.gz"
        )
        self.assertLess(dist_index, release.index("\t$(PYTHON) -m build"))


if __name__ == "__main__":
    unittest.main()
