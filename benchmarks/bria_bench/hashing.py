"""Deterministic, symlink-free hashing for BRIA-Bench packages."""

from __future__ import annotations

import hashlib
import os
import stat
from pathlib import Path


CHUNK_SIZE = 1024 * 1024


class HashingError(ValueError):
    """Raised when a package cannot be safely and completely hashed."""


def _path(value: Path | str) -> Path:
    try:
        return Path(value)
    except (TypeError, ValueError, OSError) as exc:
        raise HashingError(f"Invalid hashing root: {value!r}") from exc


def _lstat(path: Path) -> os.stat_result:
    try:
        return path.lstat()
    except (OSError, ValueError) as exc:
        raise HashingError(f"Could not inspect package path: {path}") from exc


def _collect_files(root: Path, directory: Path, files: list[tuple[str, Path]]) -> None:
    _directory_stat = _lstat(directory)
    if stat.S_ISLNK(_directory_stat.st_mode) or not stat.S_ISDIR(_directory_stat.st_mode):
        raise HashingError(f"Package directory changed during hashing: {directory}")

    try:
        with os.scandir(directory) as entries:
            children = sorted(entries, key=lambda entry: entry.name)
    except (OSError, ValueError) as exc:
        raise HashingError(f"Could not enumerate package directory: {directory}") from exc

    for entry in children:
        child = Path(entry.path)
        try:
            child_stat = entry.stat(follow_symlinks=False)
        except (OSError, ValueError) as exc:
            raise HashingError(f"Could not inspect package entry: {child}") from exc

        if stat.S_ISLNK(child_stat.st_mode):
            raise HashingError(f"Symlink is not allowed in frozen benchmark package: {child}")
        if stat.S_ISDIR(child_stat.st_mode):
            _collect_files(root, child, files)
            continue
        if not stat.S_ISREG(child_stat.st_mode):
            raise HashingError(f"Unsupported package entry: {child}")

        try:
            relative = child.relative_to(root).as_posix()
        except (ValueError, OSError) as exc:
            raise HashingError(f"Could not derive package-relative path: {child}") from exc
        files.append((relative, child))


def _hash_file(digest: "hashlib._Hash", relative: str, path: Path) -> None:
    try:
        encoded_path = relative.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise HashingError(f"Package path is not valid UTF-8: {path}") from exc

    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except (OSError, ValueError) as exc:
        raise HashingError(f"Could not open package file: {path}") from exc

    try:
        with os.fdopen(descriptor, "rb") as stream:
            descriptor = -1
            opened_stat = os.fstat(stream.fileno())
            if not stat.S_ISREG(opened_stat.st_mode):
                raise HashingError(f"Package file changed during hashing: {path}")

            digest.update(encoded_path)
            digest.update(b"\0")
            digest.update(str(opened_stat.st_size).encode("ascii"))
            digest.update(b"\0")
            byte_count = 0
            while True:
                try:
                    chunk = stream.read(CHUNK_SIZE)
                except (OSError, ValueError) as exc:
                    raise HashingError(f"Could not read package file: {path}") from exc
                if not chunk:
                    break
                byte_count += len(chunk)
                digest.update(chunk)

            final_stat = os.fstat(stream.fileno())
            if byte_count != opened_stat.st_size or byte_count != final_stat.st_size:
                raise HashingError(f"Package file changed during hashing: {path}")
            digest.update(b"\xff")
    except HashingError:
        raise
    except (OSError, ValueError) as exc:
        raise HashingError(f"Could not close package file: {path}") from exc
    finally:
        if descriptor != -1:
            try:
                os.close(descriptor)
            except OSError:
                pass


def hash_tree(root: Path | str) -> str:
    """Return the deterministic SHA-256 digest for a regular-file package tree.

    Directory names and metadata are excluded. Every package entry is inspected;
    symlinks and special files are errors rather than entries to skip.
    """

    package_root = _path(root)
    root_stat = _lstat(package_root)
    if stat.S_ISLNK(root_stat.st_mode):
        raise HashingError(f"Hashing root must not be a symlink: {package_root}")
    if not stat.S_ISDIR(root_stat.st_mode):
        raise HashingError(f"Hashing root must be an actual directory: {package_root}")

    files: list[tuple[str, Path]] = []
    _collect_files(package_root, package_root, files)
    files.sort(key=lambda item: item[0])

    digest = hashlib.sha256()
    for relative, path in files:
        _hash_file(digest, relative, path)
    return digest.hexdigest()
