"""Process monitoring and atomic output helpers for BRIA-Bench runners."""

from __future__ import annotations

import errno
import json
import math
import os
import signal
import subprocess
import tempfile
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

import psutil


DEFAULT_TAIL_BYTES = 64 * 1024
_READ_CHUNK_BYTES = 64 * 1024
_DIRECTORY_FSYNC_UNSUPPORTED = frozenset(
    {
        errno.EINVAL,
        errno.ENOSYS,
        errno.ENOTSUP,
        getattr(errno, "EOPNOTSUPP", errno.ENOTSUP),
    }
)
Identity = tuple[int, float]


@dataclass(frozen=True, slots=True)
class RuntimeResult:
    """Stable, JSON-safe telemetry for one monitored process invocation."""

    status: str
    returncode: int | None
    elapsed_seconds: float
    cpu_seconds: float
    peak_rss_bytes: int
    timed_out: bool
    stdout_tail: str
    stderr_tail: str

    def to_dict(self) -> dict[str, object]:
        return {
            "status": self.status,
            "returncode": self.returncode,
            "elapsed_seconds": self.elapsed_seconds,
            "cpu_seconds": self.cpu_seconds,
            "peak_rss_bytes": self.peak_rss_bytes,
            "timed_out": self.timed_out,
            "stdout_tail": self.stdout_tail,
            "stderr_tail": self.stderr_tail,
        }


class _ByteTail:
    def __init__(self, limit: int) -> None:
        self._limit = limit
        self._data = bytearray()

    def append(self, chunk: bytes) -> None:
        if len(chunk) >= self._limit:
            self._data[:] = chunk[-self._limit :]
            return
        self._data.extend(chunk)
        if len(self._data) > self._limit:
            del self._data[: len(self._data) - self._limit]

    def decode(self) -> str:
        return bytes(self._data).decode("utf-8", errors="replace")


@dataclass
class _TrackedProcess:
    process: psutil.Process
    max_cpu_seconds: float = 0.0


def _validate_inputs(
    command: Sequence[str],
    cwd: Path | str,
    timeout_seconds: float,
    tail_bytes: int,
    poll_interval_seconds: float,
) -> tuple[tuple[str, ...], Path, float]:
    try:
        normalized_command = tuple(command)
    except (TypeError, ValueError) as exc:
        raise ValueError("command must be a non-empty sequence") from exc
    if not normalized_command or any(not isinstance(arg, str) for arg in normalized_command):
        raise ValueError("command must be a non-empty sequence of strings")

    if isinstance(timeout_seconds, bool):
        raise ValueError("timeout_seconds must be finite and positive")
    try:
        timeout = float(timeout_seconds)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError("timeout_seconds must be finite and positive") from exc
    if not math.isfinite(timeout) or timeout <= 0:
        raise ValueError("timeout_seconds must be finite and positive")

    if isinstance(tail_bytes, bool) or not isinstance(tail_bytes, int) or tail_bytes <= 0:
        raise ValueError("tail_bytes must be a positive integer")

    if isinstance(poll_interval_seconds, bool):
        raise ValueError("poll_interval_seconds must be finite and positive")
    try:
        poll_interval = float(poll_interval_seconds)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError("poll_interval_seconds must be finite and positive") from exc
    if not math.isfinite(poll_interval) or poll_interval <= 0:
        raise ValueError("poll_interval_seconds must be finite and positive")

    try:
        cwd_path = Path(cwd).resolve(strict=True)
    except (OSError, RuntimeError, TypeError, ValueError) as exc:
        raise ValueError(f"cwd is not a valid directory: {cwd!r}") from exc
    if not cwd_path.is_dir():
        raise ValueError(f"cwd is not a valid directory: {cwd!r}")
    return normalized_command, cwd_path, timeout


def _identity(process: psutil.Process) -> Identity | None:
    try:
        return process.pid, float(process.create_time())
    except (psutil.Error, OSError, TypeError, ValueError):
        return None


def _current_process(identity: Identity) -> psutil.Process | None:
    try:
        process = psutil.Process(identity[0])
        if float(process.create_time()) != identity[1]:
            return None
        return process
    except (psutil.Error, OSError, TypeError, ValueError):
        return None


def _is_live(process: psutil.Process, identity: Identity) -> bool:
    try:
        if float(process.create_time()) != identity[1] or not process.is_running():
            return False
        return process.status() != psutil.STATUS_ZOMBIE
    except (psutil.Error, OSError, TypeError, ValueError):
        return False


def _discover_and_sample(tracked: dict[Identity, _TrackedProcess], peak_rss: int) -> int:
    """Discover descendants and sample each identity at most once per pass."""

    pending = list(tracked)
    visited: set[Identity] = set()
    live_rss = 0
    while pending:
        process_identity = pending.pop()
        if process_identity in visited:
            continue
        visited.add(process_identity)
        process = _current_process(process_identity)
        if process is None or not _is_live(process, process_identity):
            continue

        record = tracked[process_identity]
        try:
            memory = max(0, int(process.memory_info().rss))
            times = process.cpu_times()
            cpu_seconds = max(0.0, float(times.user) + float(times.system))
        except (psutil.Error, OSError, TypeError, ValueError):
            continue
        live_rss += memory
        record.max_cpu_seconds = max(record.max_cpu_seconds, cpu_seconds)

        try:
            children = process.children(recursive=False)
        except (psutil.Error, OSError, TypeError, ValueError):
            children = []
        for child in children:
            child_identity = _identity(child)
            if child_identity is None:
                continue
            if child_identity not in tracked:
                tracked[child_identity] = _TrackedProcess(child)
            pending.append(child_identity)

    return max(peak_rss, live_rss)


def _live_identities(tracked: dict[Identity, _TrackedProcess]) -> list[Identity]:
    live: list[Identity] = []
    for process_identity in tracked:
        process = _current_process(process_identity)
        if process is not None and _is_live(process, process_identity):
            live.append(process_identity)
    return live


def _signal_identity(process_identity: Identity, signum: int) -> None:
    process = _current_process(process_identity)
    if process is None or not _is_live(process, process_identity):
        return
    try:
        os.kill(process_identity[0], signum)
    except (OSError, psutil.Error):
        pass


def _signal_process_group(root_identity: Identity, signum: int) -> None:
    process = _current_process(root_identity)
    if process is None or not _is_live(process, root_identity):
        return
    try:
        if hasattr(os, "killpg") and os.getpgid(root_identity[0]) == root_identity[0]:
            os.killpg(root_identity[0], signum)
        else:
            os.kill(root_identity[0], signum)
    except (OSError, psutil.Error):
        pass


def _terminate_process_tree(
    process: subprocess.Popen[bytes],
    root_identity: Identity | None,
    tracked: dict[Identity, _TrackedProcess],
    poll_interval: float,
) -> int:
    if root_identity is not None:
        _signal_process_group(root_identity, signal.SIGTERM)
    else:
        try:
            process.terminate()
        except OSError:
            pass

    term_sent: set[Identity] = set()
    peak_rss = 0
    deadline = time.monotonic() + 1.0
    while True:
        peak_rss = _discover_and_sample(tracked, peak_rss)
        for process_identity in _live_identities(tracked):
            if process_identity not in term_sent:
                _signal_identity(process_identity, signal.SIGTERM)
                term_sent.add(process_identity)
        if not _live_identities(tracked) or time.monotonic() >= deadline:
            break
        time.sleep(min(poll_interval, max(0.0, deadline - time.monotonic())))

    kill_sent: set[Identity] = set()
    kill_deadline = time.monotonic() + 1.0
    while True:
        peak_rss = _discover_and_sample(tracked, peak_rss)
        for process_identity in _live_identities(tracked):
            if process_identity not in kill_sent:
                _signal_identity(process_identity, signal.SIGKILL)
                kill_sent.add(process_identity)
        if not _live_identities(tracked) or time.monotonic() >= kill_deadline:
            break
        time.sleep(min(poll_interval, max(0.0, kill_deadline - time.monotonic())))

    try:
        process.wait(timeout=1.0)
    except subprocess.TimeoutExpired:
        if root_identity is not None:
            _signal_identity(root_identity, signal.SIGKILL)
        else:
            try:
                process.kill()
            except OSError:
                pass
        try:
            process.wait(timeout=1.0)
        except subprocess.TimeoutExpired:
            pass
    return peak_rss


def _drain_pipe(stream: Any, tail: _ByteTail) -> None:
    try:
        while True:
            chunk = stream.read(_READ_CHUNK_BYTES)
            if not chunk:
                return
            tail.append(chunk)
    except (OSError, ValueError):
        return


def run_monitored(
    command: Sequence[str],
    cwd: Path | str,
    timeout_seconds: float,
    *,
    tail_bytes: int = DEFAULT_TAIL_BYTES,
    poll_interval_seconds: float = 0.05,
) -> RuntimeResult:
    """Run a command while collecting bounded output and process-tree telemetry."""

    normalized_command, cwd_path, timeout = _validate_inputs(
        command,
        cwd,
        timeout_seconds,
        tail_bytes,
        poll_interval_seconds,
    )
    poll_interval = float(poll_interval_seconds)
    started = time.monotonic()
    stdout_tail = _ByteTail(tail_bytes)
    stderr_tail = _ByteTail(tail_bytes)
    try:
        process = subprocess.Popen(
            normalized_command,
            cwd=cwd_path,
            shell=False,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            bufsize=0,
            start_new_session=True,
        )
    except OSError as exc:
        stderr_tail.append(f"{type(exc).__name__}: {exc}".encode("utf-8", errors="replace"))
        return RuntimeResult(
            status="process_error",
            returncode=None,
            elapsed_seconds=max(time.monotonic() - started, 1e-9),
            cpu_seconds=0.0,
            peak_rss_bytes=0,
            timed_out=False,
            stdout_tail="",
            stderr_tail=stderr_tail.decode(),
        )

    assert process.stdout is not None
    assert process.stderr is not None
    readers = [
        threading.Thread(
            target=_drain_pipe,
            args=(process.stdout, stdout_tail),
            name="bria-stdout-drain",
            daemon=True,
        ),
        threading.Thread(
            target=_drain_pipe,
            args=(process.stderr, stderr_tail),
            name="bria-stderr-drain",
            daemon=True,
        ),
    ]
    for reader in readers:
        reader.start()

    tracked: dict[Identity, _TrackedProcess] = {}
    try:
        root_process = psutil.Process(process.pid)
    except (psutil.Error, OSError, TypeError, ValueError):
        root_process = None
    root_identity = _identity(root_process) if root_process is not None else None
    if root_identity is not None and root_process is not None:
        tracked[root_identity] = _TrackedProcess(root_process)

    peak_rss = _discover_and_sample(tracked, 0)
    timed_out = False
    deadline = started + timeout
    while True:
        peak_rss = _discover_and_sample(tracked, peak_rss)
        returncode = process.poll()
        now = time.monotonic()
        if returncode is not None:
            break
        if now >= deadline:
            timed_out = True
            peak_rss = _discover_and_sample(tracked, peak_rss)
            peak_rss = max(
                peak_rss,
                _terminate_process_tree(process, root_identity, tracked, poll_interval),
            )
            returncode = process.poll()
            break
        time.sleep(min(poll_interval, max(0.0, deadline - now)))

    if not timed_out:
        try:
            returncode = process.wait()
        except (OSError, subprocess.SubprocessError):
            returncode = process.poll()
    for reader in readers:
        reader.join(timeout=2.0)
    for stream in (process.stdout, process.stderr):
        try:
            stream.close()
        except OSError:
            pass

    elapsed = max(time.monotonic() - started, 1e-9)
    cpu_seconds = max(0.0, sum(record.max_cpu_seconds for record in tracked.values()))
    if timed_out:
        status = "timeout"
    elif returncode == 0:
        status = "success"
    else:
        status = "process_error"
    return RuntimeResult(
        status=status,
        returncode=returncode,
        elapsed_seconds=elapsed,
        cpu_seconds=cpu_seconds,
        peak_rss_bytes=max(0, int(peak_rss)),
        timed_out=timed_out,
        stdout_tail=stdout_tail.decode(),
        stderr_tail=stderr_tail.decode(),
    )


def _fsync_directory(directory: Path) -> None:
    if os.name != "posix" or not hasattr(os, "O_DIRECTORY"):
        return
    descriptor = -1
    try:
        descriptor = os.open(directory, os.O_RDONLY | os.O_DIRECTORY)
        os.fsync(descriptor)
    except OSError as exc:
        if exc.errno in _DIRECTORY_FSYNC_UNSUPPORTED:
            return
        raise
    finally:
        if descriptor != -1:
            try:
                os.close(descriptor)
            except OSError:
                pass


def _make_backup(path: Path) -> Path | None:
    try:
        path.lstat()
    except FileNotFoundError:
        return None
    descriptor, name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".bak", dir=path.parent)
    os.close(descriptor)
    backup = Path(name)
    backup.unlink()
    try:
        os.link(path, backup, follow_symlinks=False)
    except (OSError, ValueError):
        backup.unlink(missing_ok=True)
        raise
    return backup


def write_json_atomic(path: Path | str, payload: Any) -> None:
    """Serialize and publish JSON without exposing a partial output file."""

    output = Path(path)
    serialized = json.dumps(
        payload,
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
        allow_nan=False,
    ) + "\n"

    output.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{output.name}.",
        suffix=".tmp",
        dir=output.parent,
    )
    temporary = Path(temporary_name)
    backup: Path | None = None
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            descriptor = -1
            stream.write(serialized)
            stream.flush()
            os.fsync(stream.fileno())
        backup = _make_backup(output)
        os.replace(temporary, output)
        try:
            _fsync_directory(output.parent)
        except OSError:
            if backup is not None:
                os.replace(backup, output)
                backup = None
            else:
                output.unlink(missing_ok=True)
            raise
    finally:
        if descriptor != -1:
            try:
                os.close(descriptor)
            except OSError:
                pass
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass
        except OSError:
            pass
        if backup is not None:
            try:
                backup.unlink()
            except FileNotFoundError:
                pass
            except OSError:
                pass


__all__ = ["DEFAULT_TAIL_BYTES", "RuntimeResult", "run_monitored", "write_json_atomic"]
