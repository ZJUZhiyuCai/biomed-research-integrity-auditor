from __future__ import annotations

import json
import os
import stat
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from benchmarks.bria_bench.cli import (
    CliError,
    _optional_llm_telemetry,
    _validate_llm_adapter_identity,
    default_adapters,
    run_benchmark,
)
from benchmarks.bria_bench.hashing import hash_tree
from benchmarks.bria_bench.llm_baseline import (
    LLMBaselineError,
    LLMConfig,
    _live_response,
    _request_payload,
    _response_parts,
    build_prompts,
    collect_package_materials,
    obtain_response,
    response_cache_key,
    run,
    snapshot_package,
    system_prompt,
    validate_model_output,
)


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
BENCHMARK_ROOT = REPOSITORY_ROOT / "benchmarks" / "bria_bench"
MANIFEST = BENCHMARK_ROOT / "benchmark_manifest.json"
FIXTURES = BENCHMARK_ROOT / "fixtures" / "deepseek-v4-flash"


def config(
    *,
    transport: str = "fixture",
    repeat_index: int = 1,
    fixture_dir: Path | None = FIXTURES,
    cache_dir: Path | None = None,
) -> LLMConfig:
    return LLMConfig(
        provider="deepseek",
        base_url="https://api.deepseek.com",
        model="deepseek-v4-flash",
        api_key_env="DEEPSEEK_API_KEY",
        transport=transport,
        repeat_index=repeat_index,
        temperature=0.0,
        top_p=1.0,
        max_output_tokens=8192,
        thinking="disabled",
        input_cache_hit_usd_per_million=0.0028,
        input_cache_miss_usd_per_million=0.14,
        output_usd_per_million=0.28,
        usd_to_cny=7.2,
        fixture_dir=fixture_dir,
        cache_dir=cache_dir,
    )


def model_payload(
    *, observations: list[dict[str, object]] | None = None
) -> dict[str, object]:
    return {
        "observations": observations or [],
        "coverage_gaps": [],
        "scope_note": "Limited direct text review; source records and human review remain required.",
    }


def api_response(payload: dict[str, object] | None = None) -> dict[str, object]:
    return {
        "id": "test-response",
        "object": "chat.completion",
        "created": 0,
        "model": "deepseek-v4-flash",
        "system_fingerprint": "test-fingerprint",
        "choices": [
            {
                "index": 0,
                "finish_reason": "stop",
                "message": {
                    "role": "assistant",
                    "content": json.dumps(
                        payload or model_payload(), ensure_ascii=False
                    ),
                },
            }
        ],
        "usage": {
            "prompt_tokens": 100,
            "completion_tokens": 20,
            "total_tokens": 120,
            "prompt_cache_hit_tokens": 0,
            "prompt_cache_miss_tokens": 100,
        },
    }


class BriaBenchLlmBaselineTests(unittest.TestCase):
    def test_default_registry_exposes_fixture_and_three_deepseek_repeats(self) -> None:
        adapters = default_adapters()

        self.assertEqual(
            set(adapters),
            {
                "full",
                "deepseek-fixture",
                "deepseek-v4-flash-r1",
                "deepseek-v4-flash-r2",
                "deepseek-v4-flash-r3",
            },
        )
        for repeat in range(1, 4):
            command = adapters[f"deepseek-v4-flash-r{repeat}"].build_command(
                package="package",
                case={
                    "case_id": "case",
                    "mode": "mode",
                    "scan_profile": "quick",
                    "expected_sha256": "a" * 64,
                },
                output="output",
            )
            self.assertIn(str(repeat), command)
            self.assertNotIn("deepseek-chat", command)

    def test_prompt_treats_package_text_as_untrusted_and_discloses_text_only_scope(
        self,
    ) -> None:
        prompt = system_prompt()

        self.assertIn("untrusted study material", prompt)
        self.assertIn("text-only", prompt)
        self.assertIn("Do not infer image duplication", prompt)
        self.assertIn("Return exactly one JSON object", prompt)

    def test_material_collection_reads_text_but_not_image_pixels(self) -> None:
        package = BENCHMARK_ROOT / "cases" / "dev" / "dev_001_global_flip"

        materials = collect_package_materials(package)

        self.assertIn("manuscript/manuscript.txt", materials.text)
        self.assertIn("figures/Figure_1A.png", materials.text)
        self.assertNotIn("PNG image data", materials.text)
        self.assertTrue(
            any(
                gap["module"] == "llm_baseline.image_input"
                for gap in materials.coverage_gaps
            )
        )

    def test_dev_prompts_do_not_disclose_case_labels_or_expected_outcomes(self) -> None:
        forbidden = (
            "negative control",
            "deliberately incomplete",
            "image-similarity",
            "numerical-consistency",
            "material-intake",
            "provenance-context",
            "truncated",
            "corrupt",
            "incomplete",
            "_valid",
        )
        for package in sorted((BENCHMARK_ROOT / "cases" / "dev").iterdir()):
            with self.subTest(case_id=package.name):
                _, user, _ = build_prompts(
                    package.name, collect_package_materials(package)
                )
                lowered = user.lower()
                for phrase in forbidden:
                    self.assertNotIn(phrase, lowered)

    def test_secure_snapshot_rejects_root_symlink_and_hash_drift(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            package = root / "package"
            package.mkdir()
            (package / "input.txt").write_text("stable\n", encoding="utf-8")
            alias = root / "package-link"
            try:
                alias.symlink_to(package, target_is_directory=True)
            except OSError as exc:
                self.skipTest(f"directory symlinks unavailable: {exc}")

            with self.assertRaisesRegex(LLMBaselineError, "symlink"):
                snapshot_package(alias, root / "snapshot-link", hash_tree(package))
            with self.assertRaisesRegex(LLMBaselineError, "hash mismatch"):
                snapshot_package(package, root / "snapshot-drift", "0" * 64)

            destination = root / "snapshot"
            snapshot_package(package, destination, hash_tree(package))
            self.assertEqual(hash_tree(destination), hash_tree(package))

    def test_container_visual_layers_and_image_only_pdf_are_disclosed(self) -> None:
        from openpyxl import Workbook
        from pypdf import PdfWriter

        with tempfile.TemporaryDirectory() as temporary:
            package = Path(temporary) / "package"
            package.mkdir()
            writer = PdfWriter()
            writer.add_blank_page(width=200, height=200)
            with (package / "scan.pdf").open("wb") as stream:
                writer.write(stream)
            workbook = Workbook()
            workbook.active["A1"] = "value"
            workbook.save(package / "table.xlsx")
            workbook.close()

            materials = collect_package_materials(package)

            modules = {gap["module"] for gap in materials.coverage_gaps}
            self.assertIn("llm_baseline.embedded_visual_input", modules)
            self.assertIn("llm_baseline.material_reader", modules)
            scan = next(item for item in materials.inventory if item["path"] == "scan.pdf")
            self.assertNotIn("machine_readable_text", scan)

    def test_model_output_schema_rejects_unknown_keys_and_truncation(self) -> None:
        invalid = model_payload()
        invalid["verdict"] = "clean"
        with self.assertRaises(LLMBaselineError):
            validate_model_output(invalid)

        response = api_response()
        response["choices"][0]["finish_reason"] = "length"  # type: ignore[index]
        with self.assertRaisesRegex(LLMBaselineError, "truncated"):
            _response_parts(response)

        response = api_response()
        response["model"] = "unexpected-model"
        with self.assertRaisesRegex(LLMBaselineError, "does not match requested"):
            _response_parts(response, expected_model="deepseek-v4-flash")

    def test_fixture_is_locked_to_the_current_prompt_hash(self) -> None:
        package = BENCHMARK_ROOT / "cases" / "dev" / "dev_003_stats_shift"
        materials = collect_package_materials(package)
        system, user, hashes = build_prompts("dev_003_stats_shift", materials)

        self.assertNotIn("dev_003_stats_shift", user)
        self.assertNotIn("stats_shift", user)

        response, _, status, _ = obtain_response(
            config(),
            "dev_003_stats_shift",
            hashes["prompt_sha256"],
            _request_payload(config(), system, user),
        )
        self.assertEqual(status, "fixture")
        self.assertEqual(
            len(_response_parts(response, expected_model="deepseek-v4-flash")[0]["observations"]),
            1,
        )
        with self.assertRaisesRegex(LLMBaselineError, "does not match"):
            obtain_response(
                config(),
                "dev_003_stats_shift",
                "0" * 64,
                _request_payload(config(), system, user),
            )

        with tempfile.TemporaryDirectory() as temporary:
            fixture_dir = Path(temporary)
            fixture = json.loads(
                (FIXTURES / "dev_003_stats_shift.json").read_text(encoding="utf-8")
            )
            fixture["request_sha256"] = "0" * 64
            (fixture_dir / "dev_003_stats_shift.json").write_text(
                json.dumps(fixture), encoding="utf-8"
            )
            with self.assertRaisesRegex(LLMBaselineError, "does not match"):
                obtain_response(
                    config(fixture_dir=fixture_dir),
                    "dev_003_stats_shift",
                    hashes["prompt_sha256"],
                    _request_payload(config(), system, user),
                )
            fixture = json.loads(
                (FIXTURES / "dev_003_stats_shift.json").read_text(encoding="utf-8")
            )
            fixture["base_url"] = "https://example.invalid"
            (fixture_dir / "dev_003_stats_shift.json").write_text(
                json.dumps(fixture), encoding="utf-8"
            )
            with self.assertRaisesRegex(LLMBaselineError, "does not match"):
                obtain_response(
                    config(fixture_dir=fixture_dir),
                    "dev_003_stats_shift",
                    hashes["prompt_sha256"],
                    _request_payload(config(), system, user),
                )

    def test_live_transport_requires_explicit_consent_before_network_or_key_use(
        self,
    ) -> None:
        called = False

        def forbidden_post(*args: object, **kwargs: object) -> object:
            nonlocal called
            called = True
            raise AssertionError("network must not be called")

        with patch.dict(os.environ, {"DEEPSEEK_API_KEY": "secret-value"}, clear=False):
            os.environ.pop("BRIA_BENCH_ALLOW_REMOTE_LLM", None)
            with self.assertRaisesRegex(LLMBaselineError, "disabled"):
                _live_response(
                    config(transport="live", fixture_dir=None), {}, post=forbidden_post
                )
        self.assertFalse(called)

    def test_live_transport_requires_environment_key_without_exposing_it(self) -> None:
        with patch.dict(os.environ, {"BRIA_BENCH_ALLOW_REMOTE_LLM": "1"}, clear=True):
            with self.assertRaisesRegex(LLMBaselineError, "DEEPSEEK_API_KEY") as raised:
                _live_response(
                    config(transport="live", fixture_dir=None), {}, post=lambda: None
                )
        self.assertNotIn("Bearer", str(raised.exception))

    def test_live_transport_retries_retryable_http_status_without_logging_body(
        self,
    ) -> None:
        responses = [
            SimpleNamespace(
                status_code=429, text="sensitive upstream detail", headers={}
            ),
            SimpleNamespace(
                status_code=200, text=json.dumps(api_response()), headers={}
            ),
        ]
        sleeps: list[float] = []

        def fake_post(*args: object, **kwargs: object) -> object:
            self.assertIs(kwargs["allow_redirects"], False)
            return responses.pop(0)

        with patch.dict(
            os.environ,
            {"BRIA_BENCH_ALLOW_REMOTE_LLM": "1", "DEEPSEEK_API_KEY": "private-key"},
            clear=False,
        ):
            response, latency = _live_response(
                config(transport="live", fixture_dir=None),
                {},
                post=fake_post,
                sleep=sleeps.append,
            )

        self.assertEqual(response["model"], "deepseek-v4-flash")
        self.assertGreaterEqual(latency, 0)
        self.assertEqual(sleeps, [1.0])

    def test_live_response_cache_is_private_and_repeat_specific(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            package = root / "package"
            package.mkdir()
            (package / "input.txt").write_text("study material\n", encoding="utf-8")
            cache = root / "private-cache"
            live = config(transport="live", fixture_dir=None, cache_dir=cache)
            materials = collect_package_materials(package)
            system, user, hashes = build_prompts("case_001", materials)
            request = _request_payload(live, system, user)
            calls: list[dict[str, object]] = []

            def fake_post(*args: object, **kwargs: object) -> object:
                calls.append(dict(kwargs))
                return SimpleNamespace(
                    status_code=200,
                    text=json.dumps(api_response()),
                    headers={},
                )

            environment = {
                "BRIA_BENCH_ALLOW_REMOTE_LLM": "1",
                "DEEPSEEK_API_KEY": "do-not-persist-this-secret",
            }
            with patch.dict(os.environ, environment, clear=False):
                first = obtain_response(
                    live,
                    "case_001",
                    hashes["prompt_sha256"],
                    request,
                    post=fake_post,
                    sleep=lambda _: None,
                )
                second = obtain_response(
                    live,
                    "case_001",
                    hashes["prompt_sha256"],
                    request,
                    post=fake_post,
                    sleep=lambda _: None,
                )

            self.assertEqual((first[2], second[2]), ("miss", "hit"))
            self.assertEqual(len(calls), 1)
            cache_files = list(cache.glob("*.json"))
            self.assertEqual(len(cache_files), 1)
            self.assertEqual(stat.S_IMODE(cache_files[0].stat().st_mode), 0o600)
            self.assertNotIn(
                "do-not-persist-this-secret", cache_files[0].read_text(encoding="utf-8")
            )
            repeat_two = config(
                transport="live", repeat_index=2, fixture_dir=None, cache_dir=cache
            )
            self.assertNotEqual(
                response_cache_key(
                    live, "case_001", hashes["prompt_sha256"], request
                ),
                response_cache_key(
                    repeat_two, "case_001", hashes["prompt_sha256"], request
                ),
            )

            changed_request = dict(request, stream=True)
            self.assertNotEqual(
                response_cache_key(
                    live, "case_001", hashes["prompt_sha256"], request
                ),
                response_cache_key(
                    live,
                    "case_001",
                    hashes["prompt_sha256"],
                    changed_request,
                ),
            )

    def test_live_cache_cannot_overlap_inputs_outputs_or_repository(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            package = root / "package"
            package.mkdir()
            request = {"model": "deepseek-v4-flash"}
            overlapping = config(
                transport="live",
                fixture_dir=None,
                cache_dir=package / "cache",
            )
            with self.assertRaisesRegex(LLMBaselineError, "must not overlap"):
                obtain_response(
                    overlapping,
                    "case_001",
                    "a" * 64,
                    request,
                    forbidden_cache_roots=(package, root / "output"),
                )
            output = root / "output"
            output_cache = config(
                transport="live",
                fixture_dir=None,
                cache_dir=output / "cache",
            )
            with self.assertRaisesRegex(LLMBaselineError, "must not overlap"):
                obtain_response(
                    output_cache,
                    "case_001",
                    "a" * 64,
                    request,
                    forbidden_cache_roots=(package, output),
                )

        repository_cache = config(
            transport="live",
            fixture_dir=None,
            cache_dir=REPOSITORY_ROOT / ".forbidden-llm-cache",
        )
        with self.assertRaisesRegex(LLMBaselineError, "outside the repository"):
            obtain_response(
                repository_cache,
                "case_001",
                "a" * 64,
                {"model": "deepseek-v4-flash"},
            )

    def test_live_producer_artifacts_never_persist_api_key_value(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            package = root / "package"
            output = root / "output"
            cache = root / "cache"
            package.mkdir()
            (package / "input.txt").write_text(
                "A neutral source-data note.\n", encoding="utf-8"
            )
            secret = "deepseek-test-secret-must-not-appear"
            live = config(transport="live", fixture_dir=None, cache_dir=cache)

            def fake_post(*args: object, **kwargs: object) -> object:
                self.assertEqual(kwargs["headers"]["Authorization"], f"Bearer {secret}")  # type: ignore[index]
                return SimpleNamespace(
                    status_code=200, text=json.dumps(api_response()), headers={}
                )

            with (
                patch.dict(
                    os.environ,
                    {"BRIA_BENCH_ALLOW_REMOTE_LLM": "1", "DEEPSEEK_API_KEY": secret},
                    clear=False,
                ),
                patch("requests.post", side_effect=fake_post),
            ):
                run(live, package, hash_tree(package), "case_001", output)

            persisted = "\n".join(
                path.read_text(encoding="utf-8", errors="replace")
                for path in list(output.rglob("*")) + list(cache.rglob("*"))
                if path.is_file()
            )
            self.assertNotIn(secret, persisted)
            self.assertIn("deepseek", persisted)

    def test_runner_ingests_fixture_telemetry_and_uses_common_normalizer(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            runs = Path(temporary) / "runs"

            summary = run_benchmark(
                MANIFEST,
                runs,
                case_ids=["dev_003_stats_shift"],
                adapter_name="deepseek-fixture",
                timeout_seconds=60,
            )

            self.assertEqual(summary["cases"][0]["status"], "success")
            result = json.loads(
                (runs / summary["cases"][0]["run_result"]).read_text(encoding="utf-8")
            )
            self.assertEqual(result["telemetry"]["llm"]["provider"], "deepseek-fixture")
            self.assertEqual(result["telemetry"]["llm"]["repeat_index"], 1)
            self.assertEqual(
                result["normalized_observation"]["observations"][0]["issue_family"],
                "statistics_or_numeric",
            )
            self.assertEqual(
                result["normalized_observation"]["boundary_violations"], []
            )
            self.assertEqual(result["normalized_observation"]["contract_errors"], [])

    def test_model_reported_gap_is_normalized_and_fixture_identity_is_visible(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            runs = Path(temporary) / "runs"
            summary = run_benchmark(
                MANIFEST,
                runs,
                case_ids=["dev_005_corrupt_image"],
                adapter_name="deepseek-fixture",
                timeout_seconds=60,
            )
            result = json.loads(
                (runs / summary["cases"][0]["run_result"]).read_text(encoding="utf-8")
            )
            observations = result["normalized_observation"]["observations"]
            self.assertTrue(
                any(
                    item["issue_family"] == "material_or_coverage_gap"
                    and "Figure_5B.png" in json.dumps(item["location"])
                    for item in observations
                )
            )
            output = runs / result["output_paths"]["case_output"]
            report = (output / "audit-report.md").read_text(encoding="utf-8")
            summary_payload = json.loads(
                (output / "AUDIT_JSON_SUMMARY.json").read_text(encoding="utf-8")
            )
            self.assertIn("Provider / 提供方: `deepseek-fixture`", report)
            self.assertIn("Transport / 传输方式: `fixture`", report)
            self.assertTrue(
                all(
                    item["detector"] == "llm_baseline.deepseek-fixture"
                    for item in summary_payload["findings"]
                )
            )

    def test_deepseek_adapter_identity_rejects_repeat_and_transport_mismatch(self) -> None:
        complete = {
            "provider": "deepseek",
            "model": "deepseek-v4-flash",
            "response_model": "deepseek-v4-flash",
            "repeat_index": 1,
            "response_cache_status": "miss",
        }
        _validate_llm_adapter_identity("deepseek-v4-flash-r1", complete)
        with self.assertRaisesRegex(CliError, "mismatch"):
            _validate_llm_adapter_identity("deepseek-v4-flash-r2", complete)
        with self.assertRaisesRegex(CliError, "mismatch"):
            _validate_llm_adapter_identity(
                "deepseek-fixture", dict(complete, response_cache_status="fixture")
            )

    def test_llm_telemetry_rejects_unknown_or_malformed_fields(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary)
            (output / "llm_telemetry.json").write_text(
                json.dumps(
                    {"provider": "deepseek", "model": "model", "api_key": "secret"}
                ),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(Exception, "invalid structure"):
                _optional_llm_telemetry(output)

            (output / "llm_telemetry.json").write_text(
                json.dumps({"provider": "deepseek", "model": "deepseek-v4-flash"}),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(CliError, "missing required fields"):
                _optional_llm_telemetry(output)


if __name__ == "__main__":
    unittest.main()
