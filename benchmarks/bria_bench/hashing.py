"""Descriptor-relative deterministic hashing for BRIA-Bench frozen identity.

Package filenames must be NFC-normalized and casefold-unique within each
directory so frozen packages have one portable filename interpretation.
"""

from __future__ import annotations

import hashlib
import os
import stat
import unicodedata
from dataclasses import dataclass
from pathlib import Path


CHUNK_SIZE = 1024 * 1024
_ORIGINAL_OPEN = os.open
_ORIGINAL_STAT = os.stat
_ORIGINAL_LISTDIR = os.listdir
_SECURE_HASHING_SUPPORTED = bool(
    os.name == "posix"
    and hasattr(os, "O_DIRECTORY")
    and hasattr(os, "O_NOFOLLOW")
    and _ORIGINAL_OPEN in os.supports_dir_fd
    and _ORIGINAL_STAT in os.supports_dir_fd
    and _ORIGINAL_STAT in os.supports_follow_symlinks
    and _ORIGINAL_LISTDIR in os.supports_fd
)


class HashingError(ValueError):
    """Raised when a package cannot be safely and completely hashed."""


@dataclass
class _OpenDirectory:
    fd: int
    name: str | None
    parent_fd: int | None
    relative: str
    initial_stat: os.stat_result
    initial_names: tuple[str, ...]


@dataclass
class _OpenFile:
    fd: int
    name: str
    parent_fd: int
    relative: str
    initial_stat: os.stat_result


def secure_hashing_supported() -> bool:
    """Return whether this platform exposes the primitives secure hashing needs."""

    return _SECURE_HASHING_SUPPORTED


def _require_secure_hashing() -> None:
    if not secure_hashing_supported():
        raise HashingError(
            "Secure frozen hashing requires POSIX descriptor-relative openat, "
            "lstat, O_DIRECTORY, O_NOFOLLOW, and fd directory enumeration support"
        )


def _path(value: Path | str) -> Path:
    try:
        return Path(value)
    except (TypeError, ValueError, OSError) as exc:
        raise HashingError(f"Invalid hashing path: {value!r}") from exc


def _lstat(path: Path) -> os.stat_result:
    try:
        return path.lstat()
    except (OSError, ValueError) as exc:
        raise HashingError(f"Could not inspect package path: {path}") from exc


def _fstat(descriptor: int, path: str, stage: str) -> os.stat_result:
    try:
        return os.fstat(descriptor)
    except (OSError, ValueError) as exc:
        raise HashingError(f"Could not inspect package file {stage}: {path}") from exc


def _stat_at(parent_fd: int, name: str, relative: str) -> os.stat_result:
    try:
        return os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
    except (OSError, ValueError) as exc:
        raise HashingError(f"Could not inspect package entry: {relative}") from exc


def _stable_metadata(value: os.stat_result) -> tuple[object, ...]:
    return (
        value.st_dev,
        value.st_ino,
        value.st_size,
        getattr(value, "st_mtime_ns", None),
        getattr(value, "st_ctime_ns", None),
    )


def _same_identity(left: os.stat_result, right: os.stat_result) -> bool:
    return left.st_dev == right.st_dev and left.st_ino == right.st_ino


def _ensure_regular(value: os.stat_result, relative: str, stage: str) -> None:
    if stat.S_ISLNK(value.st_mode) or not stat.S_ISREG(value.st_mode):
        raise HashingError(f"Package file changed {stage}: {relative}")


def _ensure_directory(value: os.stat_result, relative: str, stage: str) -> None:
    if stat.S_ISLNK(value.st_mode) or not stat.S_ISDIR(value.st_mode):
        raise HashingError(f"Package directory changed {stage}: {relative}")


def _ensure_stable(
    before: os.stat_result,
    after: os.stat_result,
    relative: str,
    stage: str,
) -> None:
    if _stable_metadata(before) != _stable_metadata(after):
        raise HashingError(f"Package entry changed {stage}: {relative}")


def _list_names(directory: _OpenDirectory) -> tuple[str, ...]:
    try:
        names = os.listdir(directory.fd)
    except (OSError, ValueError) as exc:
        raise HashingError(
            f"Could not enumerate directory {directory.relative or '.'} from its open fd"
        ) from exc
    if any(not isinstance(name, str) for name in names):
        raise HashingError(f"Package filenames must be text: {directory.relative or '.'}")

    folded: dict[str, str] = {}
    for name in names:
        normalized = unicodedata.normalize("NFC", name)
        if normalized != name:
            raise HashingError(
                f"Package filename is not NFC-normalized: "
                f"{directory.relative + '/' if directory.relative else ''}{name}"
            )
        previous = folded.get(name.casefold())
        if previous is not None and previous != name:
            raise HashingError(
                f"Package filenames casefold-collide in {directory.relative or '.'}: "
                f"{previous!r} and {name!r}"
            )
        folded[name.casefold()] = name
    return tuple(sorted(names))


def _open_root(root: Path) -> tuple[int, os.stat_result]:
    root_stat = _lstat(root)
    if stat.S_ISLNK(root_stat.st_mode):
        raise HashingError(f"Hashing root must not be a symlink: {root}")
    if not stat.S_ISDIR(root_stat.st_mode):
        raise HashingError(f"Hashing root must be an actual directory: {root}")

    try:
        secure_root = root.resolve(strict=True)
    except (OSError, RuntimeError, ValueError) as exc:
        raise HashingError(f"Could not resolve hashing root: {root}") from exc
    secure_root_stat = _lstat(secure_root)
    _ensure_directory(secure_root_stat, str(root), "after resolving root")

    directory_flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    descriptor = -1
    try:
        descriptor = os.open(os.sep, directory_flags)
        for component in secure_root.parts[1:]:
            next_descriptor = os.open(
                component,
                directory_flags,
                dir_fd=descriptor,
            )
            os.close(descriptor)
            descriptor = next_descriptor
        opened_stat = _fstat(descriptor, str(root), "after opening root")
        _ensure_directory(opened_stat, str(root), "after opening root")
        if not _same_identity(secure_root_stat, opened_stat):
            raise HashingError(f"Hashing root changed before traversal: {root}")
        return descriptor, opened_stat
    except HashingError:
        if descriptor != -1:
            os.close(descriptor)
        raise
    except (OSError, ValueError) as exc:
        if descriptor != -1:
            os.close(descriptor)
        raise HashingError(f"Could not securely open hashing root: {root}") from exc


def _relative_path(parent: str, name: str) -> str:
    return f"{parent}/{name}" if parent else name


def _walk_directory(
    directory: _OpenDirectory,
    directories: list[_OpenDirectory],
    files: list[_OpenFile],
) -> None:
    initial_names = _list_names(directory)
    directory.initial_names = initial_names
    for name in initial_names:
        relative = _relative_path(directory.relative, name)
        entry_stat = _stat_at(directory.fd, name, relative)
        if stat.S_ISLNK(entry_stat.st_mode):
            raise HashingError(f"Symlink is not allowed in frozen benchmark package: {relative}")
        if stat.S_ISDIR(entry_stat.st_mode):
            directory_flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
            child_fd = -1
            try:
                child_fd = os.open(name, directory_flags, dir_fd=directory.fd)
                opened_stat = _fstat(child_fd, relative, "after opening directory")
                _ensure_directory(opened_stat, relative, "after opening directory")
                _ensure_stable(entry_stat, opened_stat, relative, "between directory inspection and open")
                child = _OpenDirectory(
                    child_fd,
                    name,
                    directory.fd,
                    relative,
                    opened_stat,
                    (),
                )
                child_fd = -1
                directories.append(child)
                _walk_directory(child, directories, files)
            except HashingError:
                if child_fd != -1:
                    os.close(child_fd)
                raise
            except (OSError, ValueError) as exc:
                if child_fd != -1:
                    os.close(child_fd)
                raise HashingError(f"Could not securely open package directory: {relative}") from exc
            continue
        if not stat.S_ISREG(entry_stat.st_mode):
            raise HashingError(f"Unsupported package entry: {relative}")

        file_flags = os.O_RDONLY | os.O_NOFOLLOW
        file_fd = -1
        try:
            file_fd = os.open(name, file_flags, dir_fd=directory.fd)
            opened_stat = _fstat(file_fd, relative, "after opening")
            _ensure_regular(opened_stat, relative, "after opening")
            _ensure_stable(entry_stat, opened_stat, relative, "between inspection and open")
            files.append(_OpenFile(file_fd, name, directory.fd, relative, opened_stat))
            file_fd = -1
        except HashingError:
            if file_fd != -1:
                os.close(file_fd)
            raise
        except (OSError, ValueError) as exc:
            if file_fd != -1:
                os.close(file_fd)
            raise HashingError(f"Could not securely open package file: {relative}") from exc

    final_names = _list_names(directory)
    if final_names != initial_names:
        raise HashingError(f"Package directory entries changed during traversal: {directory.relative or '.'}")


def _verify_directory(directory: _OpenDirectory) -> None:
    final_names = _list_names(directory)
    if final_names != directory.initial_names:
        raise HashingError(f"Package directory entries changed during traversal: {directory.relative or '.'}")
    if directory.parent_fd is not None and directory.name is not None:
        current = _stat_at(directory.parent_fd, directory.name, directory.relative)
        _ensure_directory(current, directory.relative, "after traversal")
        _ensure_stable(directory.initial_stat, current, directory.relative, "after traversal")


def _open_file_path(path: Path) -> int:
    """Open a file through canonical descriptor-relative parents."""

    try:
        secure_path = path.resolve(strict=True)
    except (OSError, RuntimeError, ValueError) as exc:
        raise HashingError(f"Could not resolve file path: {path}") from exc
    directory_flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    descriptor = -1
    try:
        descriptor = os.open(os.sep, directory_flags)
        for component in secure_path.parts[1:-1]:
            next_descriptor = os.open(component, directory_flags, dir_fd=descriptor)
            os.close(descriptor)
            descriptor = next_descriptor
        file_descriptor = os.open(
            secure_path.name,
            os.O_RDONLY | os.O_NOFOLLOW,
            dir_fd=descriptor,
        )
        os.close(descriptor)
        return file_descriptor
    except HashingError:
        if descriptor != -1:
            os.close(descriptor)
        raise
    except (OSError, ValueError) as exc:
        if descriptor != -1:
            os.close(descriptor)
        raise HashingError(f"Could not securely open file path: {path}") from exc


def _hash_open_file(digest: "hashlib._Hash", entry: _OpenFile) -> None:
    relative = entry.relative
    try:
        before_stream_stat = _fstat(entry.fd, relative, "before streaming")
        _ensure_regular(before_stream_stat, relative, "before streaming")
        _ensure_stable(entry.initial_stat, before_stream_stat, relative, "before streaming")

        encoded_path = relative.encode("utf-8")
        digest.update(encoded_path)
        digest.update(b"\0")
        digest.update(str(entry.initial_stat.st_size).encode("ascii"))
        digest.update(b"\0")
        byte_count = 0
        while True:
            try:
                chunk = os.read(entry.fd, CHUNK_SIZE)
            except (OSError, ValueError) as exc:
                raise HashingError(f"Could not read package file: {relative}") from exc
            if not chunk:
                break
            byte_count += len(chunk)
            digest.update(chunk)

        streamed_stat = _fstat(entry.fd, relative, "after streaming")
        _ensure_regular(streamed_stat, relative, "after streaming")
        _ensure_stable(entry.initial_stat, streamed_stat, relative, "during streaming")
        if byte_count != entry.initial_stat.st_size or byte_count != streamed_stat.st_size:
            raise HashingError(f"Package file byte count changed during streaming: {relative}")
    finally:
        try:
            os.close(entry.fd)
        except OSError as exc:
            entry.fd = -1
            raise HashingError(f"Could not close package file: {relative}") from exc
        entry.fd = -1

    after_stat = _stat_at(entry.parent_fd, entry.name, relative)
    _ensure_regular(after_stat, relative, "after close")
    _ensure_stable(entry.initial_stat, after_stat, relative, "after close")
    digest.update(b"\xff")


def _hash_file_bytes(path: Path) -> str:
    before_stat = _lstat(path)
    _ensure_regular(before_stat, str(path), "before open")
    descriptor = -1
    try:
        descriptor = _open_file_path(path)
        opened_stat = _fstat(descriptor, str(path), "after open")
        _ensure_regular(opened_stat, str(path), "after open")
        _ensure_stable(before_stat, opened_stat, str(path), "between inspection and open")
        digest = hashlib.sha256()
        byte_count = 0
        while True:
            try:
                chunk = os.read(descriptor, CHUNK_SIZE)
            except (OSError, ValueError) as exc:
                raise HashingError(f"Could not read annotation file: {path}") from exc
            if not chunk:
                break
            byte_count += len(chunk)
            digest.update(chunk)
        streamed_stat = _fstat(descriptor, str(path), "after streaming")
        _ensure_regular(streamed_stat, str(path), "after streaming")
        _ensure_stable(opened_stat, streamed_stat, str(path), "during streaming")
        if byte_count != opened_stat.st_size:
            raise HashingError(f"Annotation file byte count changed during streaming: {path}")
    finally:
        if descriptor != -1:
            try:
                os.close(descriptor)
            except OSError as exc:
                raise HashingError(f"Could not close annotation file: {path}") from exc
    after_stat = _lstat(path)
    _ensure_regular(after_stat, str(path), "after close")
    _ensure_stable(before_stat, after_stat, str(path), "after close")
    return digest.hexdigest()


def hash_file(path: Path | str) -> str:
    """Stream a regular file's raw bytes into SHA-256 without parsing it."""

    _require_secure_hashing()
    return _hash_file_bytes(_path(path))


def hash_tree(root: Path | str) -> str:
    """Return a deterministic SHA-256 digest for a secure regular-file tree."""

    _require_secure_hashing()
    package_root = _path(root)
    absolute_root = Path(os.path.abspath(package_root))
    root_fd = -1
    directories: list[_OpenDirectory] = []
    files: list[_OpenFile] = []
    try:
        root_fd, root_stat = _open_root(absolute_root)
        root_directory = _OpenDirectory(root_fd, None, None, "", root_stat, ())
        directories.append(root_directory)
        root_fd = -1
        _walk_directory(root_directory, directories, files)

        files.sort(key=lambda entry: entry.relative)
        digest = hashlib.sha256()
        for entry in files:
            _hash_open_file(digest, entry)
        for directory in directories:
            _verify_directory(directory)

        final_root_stat = _lstat(absolute_root)
        _ensure_directory(final_root_stat, str(absolute_root), "after traversal")
        if not _same_identity(root_stat, final_root_stat):
            raise HashingError(f"Hashing root pathname changed during traversal: {absolute_root}")
        return digest.hexdigest()
    finally:
        if root_fd != -1:
            try:
                os.close(root_fd)
            except OSError:
                pass
        for entry in files:
            if entry.fd != -1:
                try:
                    os.close(entry.fd)
                except OSError:
                    pass
                entry.fd = -1
        for directory in directories:
            try:
                os.close(directory.fd)
            except OSError:
                pass
