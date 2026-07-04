"""Portable parallel workstream execution for the audit pipeline."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
import time
from pathlib import Path
from typing import Any, Callable

from scripts.pipeline.common import write_json


@dataclass(frozen=True)
class WorkstreamTask:
    phase: str
    name: str
    runner: Callable[[], Any]


def result_count(value: Any) -> int:
    if value is None:
        return 0
    if isinstance(value, (list, tuple, set)):
        return len(value)
    return 1


def run_many(*builders: Callable[[], Any]) -> list[Any]:
    outputs = []
    for builder in builders:
        result = builder()
        if result is None:
            continue
        if isinstance(result, list):
            outputs.extend(item for item in result if item is not None)
        else:
            outputs.append(result)
    return outputs


def _run_one(task: WorkstreamTask) -> tuple[Any, dict[str, Any]]:
    started = time.time()
    try:
        result = task.runner()
    except Exception as exc:
        elapsed = round(time.time() - started, 3)
        return None, {
            "phase": task.phase,
            "name": task.name,
            "status": "failed",
            "elapsed_seconds": elapsed,
            "output_count": 0,
            "error": f"{type(exc).__name__}: {exc}",
        }
    elapsed = round(time.time() - started, 3)
    return result, {
        "phase": task.phase,
        "name": task.name,
        "status": "completed",
        "elapsed_seconds": elapsed,
        "output_count": result_count(result),
    }


def run_workstream_tasks(
    tasks: list[WorkstreamTask],
    *,
    execution_mode: str,
    max_workers: int = 4,
) -> tuple[list[Any], list[dict[str, Any]]]:
    if not tasks:
        return [], []
    if execution_mode == "sequential" or len(tasks) == 1:
        results = []
        records = []
        for task in tasks:
            result, record = _run_one(task)
            records.append(record)
            if record["status"] != "completed":
                raise RuntimeError(f"Workstream {task.phase}/{task.name} failed: {record.get('error')}")
            results.append(result)
        return results, records

    results_by_index: dict[int, Any] = {}
    records_by_index: dict[int, dict[str, Any]] = {}
    with ThreadPoolExecutor(max_workers=max(1, min(max_workers, len(tasks)))) as executor:
        future_to_index = {executor.submit(_run_one, task): idx for idx, task in enumerate(tasks)}
        for future in as_completed(future_to_index):
            idx = future_to_index[future]
            result, record = future.result()
            results_by_index[idx] = result
            records_by_index[idx] = record

    records = [records_by_index[idx] for idx in range(len(tasks))]
    failed = [record for record in records if record["status"] != "completed"]
    if failed:
        first = failed[0]
        raise RuntimeError(f"Workstream {first['phase']}/{first['name']} failed: {first.get('error')}")
    return [results_by_index[idx] for idx in range(len(tasks))], records


def write_workstream_report(
    output_dir: Path,
    *,
    execution_mode: str,
    max_workers: int,
    records: list[dict[str, Any]],
) -> Path:
    path = output_dir / "workstreams.json"
    payload = {
        "schema_version": "0.1.0",
        "execution_mode": execution_mode,
        "parallel_enabled": execution_mode == "parallel",
        "max_workers": max_workers if execution_mode == "parallel" else 1,
        "workstreams": records,
        "scope_note": (
            "Parallel workstreams are portable local pipeline stages, not misconduct verdict agents. "
            "They only change execution scheduling; calibration and report assembly remain serialized."
        ),
    }
    write_json(path, payload)
    return path
