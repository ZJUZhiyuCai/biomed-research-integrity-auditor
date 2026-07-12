"""Secure deterministic hashing for BRIA-Bench frozen identity.

The hash is a point-in-time consistent snapshot attempt, not a filesystem
lock. Traversal and a complete final verification pass detect mutations and
entry changes observed during the attempt. A change after :func:`hash_tree`
returns is outside that snapshot and must be caught by verification before use.

Secure freezing currently requires POSIX ``dir_fd`` support, descriptor-relative
``stat``/``open``, ``O_DIRECTORY``, ``O_NOFOLLOW``, and fd directory listing.
Unsupported platforms fail closed with :class:`HashingError`.

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
    """Raised when secure snapshot hashing cannot complete safely."""


@dataclass
class _DirectoryRecord:
    relative: str
    components: tuple[str, ...]
    name: str | None
    initial_stat: os.stat_result
    initial_names: tuple[str, ...]


@dataclass(frozen=True)
class _FileRecord:
    relative: str
    components: tuple[str, ...]
    name: str
    initial_stat: os.stat_result


def secure_hashing_supported() -> bool:
    """Return whether this platform exposes secure descriptor primitives."""

    return _SECURE_HASHING_SUPPORTED


def _require_secure_hashing() -> None:
    if not secure_hashing_supported():
        raise HashingError(
            "Secure frozen hashing requires POSIX dir_fd/openat, lstat, "
            "O_DIRECTORY, O_NOFOLLOW, and fd directory-enumeration support"
        )


def _path(value: Path | str) -> Path:
    try:
        return Path(value)
    except (TypeError, ValueError, OSError) as exc:
        raise HashingError(f"Invalid hashing path: {value!r}") from exc


def _path_components(path: Path) -> tuple[str, ...]:
    components = path.parts[1:] if path.is_absolute() else path.parts
    if any(component == ".." for component in components):
        raise HashingError(f"Lexical '..' is not allowed in secure hashing path: {path}")
    return tuple(component for component in components if component not in ("", "."))


def _stat_path(path: Path) -> os.stat_result:
    try:
        return os.stat(path, follow_symlinks=False)
    except (OSError, ValueError) as exc:
        raise HashingError(f"Could not inspect hashing path: {path}") from exc


def _stat_at(parent_fd: int, name: str, relative: str) -> os.stat_result:
    try:
        return os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
    except (OSError, ValueError) as exc:
        raise HashingError(f"Could not inspect package entry: {relative}") from exc


def _fstat(descriptor: int, relative: str, stage: str) -> os.stat_result:
    try:
        return os.fstat(descriptor)
    except (OSError, ValueError) as exc:
        raise HashingError(f"Could not inspect package entry {stage}: {relative}") from exc


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


def _ensure_stable(
    before: os.stat_result,
    after: os.stat_result,
    relative: str,
    stage: str,
) -> None:
    if _stable_metadata(before) != _stable_metadata(after):
        raise HashingError(f"Package entry changed {stage}: {relative}")


def _ensure_regular(value: os.stat_result, relative: str, stage: str) -> None:
    if stat.S_ISLNK(value.st_mode) or not stat.S_ISREG(value.st_mode):
        raise HashingError(f"Package file changed {stage}: {relative}")


def _ensure_directory(value: os.stat_result, relative: str, stage: str) -> None:
    if stat.S_ISLNK(value.st_mode) or not stat.S_ISDIR(value.st_mode):
        raise HashingError(f"Package directory changed {stage}: {relative}")


def _directory_flags() -> int:
    return os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW


def _close_fd(descriptor: int, label: str) -> None:
    try:
        os.close(descriptor)
    except OSError as exc:
        raise HashingError(f"Could not close {label}") from exc


def _list_names(fd: int, relative: str) -> tuple[str, ...]:
    try:
        names = os.listdir(fd)
    except (OSError, ValueError) as exc:
        raise HashingError(
            f"Could not enumerate directory {relative or '.'} from its open fd"
        ) from exc
    if any(not isinstance(name, str) for name in names):
        raise HashingError(f"Package filenames must be text: {relative or '.'}")

    folded: dict[str, str] = {}
    for name in names:
        normalized = unicodedata.normalize("NFC", name)
        if normalized != name:
            prefix = f"{relative}/" if relative else ""
            raise HashingError(f"Package filename is not NFC-normalized: {prefix}{name}")
        previous = folded.get(name.casefold())
        if previous is not None and previous != name:
            raise HashingError(
                f"Package filenames casefold-collide in {relative or '.'}: "
                f"{previous!r} and {name!r}"
            )
        folded[name.casefold()] = name
    return tuple(sorted(names))


def _relative_path(parent: str, name: str) -> str:
    return f"{parent}/{name}" if parent else name


def _open_anchor(path: Path) -> int:
    anchor = os.sep if path.is_absolute() else "."
    try:
        return os.open(anchor, _directory_flags())
    except (OSError, ValueError) as exc:
        raise HashingError(f"Could not securely open filesystem anchor for {path}") from exc


def _open_directory_component(
    parent_fd: int,
    name: str,
    relative: str,
    expected: os.stat_result | None = None,
    check_expected_metadata: bool = True,
) -> tuple[int, os.stat_result]:
    before = _stat_at(parent_fd, name, relative)
    _ensure_directory(before, relative, "before open")
    if expected is not None and check_expected_metadata:
        _ensure_stable(expected, before, relative, "before open")
    elif expected is not None and not _same_identity(expected, before):
        raise HashingError(f"Package directory identity changed before open: {relative}")
    descriptor = -1
    try:
        descriptor = os.open(name, _directory_flags(), dir_fd=parent_fd)
        opened = _fstat(descriptor, relative, "after open")
        _ensure_directory(opened, relative, "after open")
        if check_expected_metadata:
            _ensure_stable(before, opened, relative, "between inspection and open")
        elif not _same_identity(before, opened):
            raise HashingError(
                f"Package directory identity changed between inspection and open: {relative}"
            )
        if expected is not None and check_expected_metadata:
            _ensure_stable(expected, opened, relative, "after open")
        elif expected is not None and not _same_identity(expected, opened):
            raise HashingError(f"Package directory identity changed after open: {relative}")
        return descriptor, opened
    except HashingError:
        if descriptor != -1:
            os.close(descriptor)
        raise
    except (OSError, ValueError) as exc:
        if descriptor != -1:
            os.close(descriptor)
        raise HashingError(f"Could not securely open package directory: {relative}") from exc


def _open_directory_chain(
    path: Path,
    expected: os.stat_result | None = None,
    check_expected_metadata: bool = True,
) -> tuple[list[int], int, os.stat_result]:
    path_stat = _stat_path(path)
    _ensure_directory(path_stat, str(path), "before open")
    components = _path_components(path)
    descriptors: list[int] = []
    current_fd = -1
    try:
        current_fd = _open_anchor(path)
        descriptors.append(current_fd)
        opened = _fstat(current_fd, str(path), "after opening anchor")
        if not components:
            _ensure_directory(opened, str(path), "after opening anchor")
            if check_expected_metadata:
                _ensure_stable(
                    path_stat,
                    opened,
                    str(path),
                    "between inspection and open",
                )
            elif not _same_identity(path_stat, opened):
                raise HashingError(
                    f"Package directory identity changed between inspection and open: {path}"
                )
        for index, component in enumerate(components):
            relative = "/".join(components[: index + 1])
            next_fd, opened = _open_directory_component(
                current_fd,
                component,
                relative,
                check_expected_metadata=(
                    check_expected_metadata and index == len(components) - 1
                ),
            )
            descriptors.append(next_fd)
            current_fd = next_fd
        if check_expected_metadata:
            _ensure_stable(path_stat, opened, str(path), "after open")
        elif not _same_identity(path_stat, opened):
            raise HashingError(
                f"Package directory identity changed after open: {path}"
            )
        if expected is not None and check_expected_metadata:
            _ensure_stable(expected, opened, str(path), "against expected snapshot")
        elif expected is not None and not _same_identity(expected, opened):
            raise HashingError(f"Package directory identity changed against expected snapshot: {path}")
        return descriptors, current_fd, opened
    except HashingError:
        for descriptor in reversed(descriptors):
            try:
                os.close(descriptor)
            except OSError:
                pass
        raise


def _walk_directory(
    fd: int,
    relative: str,
    components: tuple[str, ...],
    directories: list[_DirectoryRecord],
    files: list[_FileRecord],
    initial_stat: os.stat_result,
) -> None:
    initial_names = _list_names(fd, relative)
    if directories:
        directories[-1].initial_names = initial_names
    for name in initial_names:
        child_relative = _relative_path(relative, name)
        entry_stat = _stat_at(fd, name, child_relative)
        if stat.S_ISLNK(entry_stat.st_mode):
            raise HashingError(f"Symlink is not allowed in frozen benchmark package: {child_relative}")
        if stat.S_ISDIR(entry_stat.st_mode):
            child_fd, child_stat = _open_directory_component(fd, name, child_relative)
            child = _DirectoryRecord(
                child_relative,
                components + (name,),
                name,
                child_stat,
                (),
            )
            directories.append(child)
            try:
                _walk_directory(
                    child_fd,
                    child_relative,
                    components + (name,),
                    directories,
                    files,
                    child_stat,
                )
                current = _stat_at(fd, name, child_relative)
                _ensure_directory(current, child_relative, "after traversal")
                _ensure_stable(child_stat, current, child_relative, "after traversal")
            finally:
                _close_fd(child_fd, f"directory {child_relative}")
            continue
        if not stat.S_ISREG(entry_stat.st_mode):
            raise HashingError(f"Unsupported package entry: {child_relative}")
        files.append(
            _FileRecord(
                child_relative,
                components + (name,),
                name,
                entry_stat,
            )
        )

    final_names = _list_names(fd, relative)
    if final_names != initial_names:
        raise HashingError(f"Package directory entries changed during traversal: {relative or '.'}")


def _open_directory_record(
    root: Path,
    record: _DirectoryRecord,
    expected_directories: dict[str, _DirectoryRecord],
) -> tuple[list[int], int]:
    root_record = expected_directories[""]
    descriptors, current_fd, _ = _open_directory_chain(root, root_record.initial_stat)
    try:
        for index, component in enumerate(record.components):
            relative = "/".join(record.components[: index + 1])
            expected = expected_directories.get(relative)
            if expected is None:
                raise HashingError(f"Missing directory snapshot record: {relative}")
            next_fd, _ = _open_directory_component(
                current_fd,
                component,
                relative,
                expected.initial_stat,
            )
            descriptors.append(next_fd)
            current_fd = next_fd
        return descriptors, current_fd
    except HashingError:
        for descriptor in reversed(descriptors):
            try:
                os.close(descriptor)
            except OSError:
                pass
        raise


def _open_file_record(
    root: Path,
    record: _FileRecord,
    expected_directories: dict[str, _DirectoryRecord],
    check_directory_metadata: bool = True,
) -> tuple[int, list[int], int]:
    root_record = expected_directories[""]
    descriptors, current_fd, _ = _open_directory_chain(
        root,
        root_record.initial_stat,
        check_directory_metadata,
    )
    try:
        for index, component in enumerate(record.components[:-1]):
            relative = "/".join(record.components[: index + 1])
            expected = expected_directories.get(relative)
            if expected is None:
                raise HashingError(f"Missing directory snapshot record: {relative}")
            next_fd, _ = _open_directory_component(
                current_fd,
                component,
                relative,
                expected.initial_stat,
                check_directory_metadata,
            )
            descriptors.append(next_fd)
            current_fd = next_fd

        before = _stat_at(current_fd, record.name, record.relative)
        _ensure_regular(before, record.relative, "before open")
        _ensure_stable(record.initial_stat, before, record.relative, "against expected snapshot")
        file_fd = -1
        try:
            file_fd = os.open(record.name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=current_fd)
            opened = _fstat(file_fd, record.relative, "after open")
            _ensure_regular(opened, record.relative, "after open")
            _ensure_stable(before, opened, record.relative, "between inspection and open")
            _ensure_stable(record.initial_stat, opened, record.relative, "after open")
            return file_fd, descriptors, current_fd
        except HashingError:
            if file_fd != -1:
                os.close(file_fd)
            raise
        except (OSError, ValueError) as exc:
            if file_fd != -1:
                os.close(file_fd)
            raise HashingError(f"Could not securely open package file: {record.relative}") from exc
    except HashingError:
        for descriptor in reversed(descriptors):
            try:
                os.close(descriptor)
            except OSError:
                pass
        raise


def _stream_fd(descriptor: int, digest: "hashlib._Hash", label: str) -> int:
    count = 0
    while True:
        try:
            chunk = os.read(descriptor, CHUNK_SIZE)
        except (OSError, ValueError) as exc:
            raise HashingError(f"Could not read {label}") from exc
        if not chunk:
            return count
        count += len(chunk)
        digest.update(chunk)


def _hash_file_record(
    digest: "hashlib._Hash",
    record: _FileRecord,
    file_fd: int,
    parent_fd: int,
) -> None:
    try:
        before_stream = _fstat(file_fd, record.relative, "before streaming")
        _ensure_regular(before_stream, record.relative, "before streaming")
        _ensure_stable(record.initial_stat, before_stream, record.relative, "before streaming")
        digest.update(record.relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(str(record.initial_stat.st_size).encode("ascii"))
        digest.update(b"\0")
        byte_count = _stream_fd(file_fd, digest, f"package file {record.relative}")
        streamed = _fstat(file_fd, record.relative, "after streaming")
        _ensure_regular(streamed, record.relative, "after streaming")
        _ensure_stable(record.initial_stat, streamed, record.relative, "during streaming")
        if byte_count != record.initial_stat.st_size or byte_count != streamed.st_size:
            raise HashingError(f"Package file byte count changed during streaming: {record.relative}")
    finally:
        _close_fd(file_fd, f"package file {record.relative}")
    after = _stat_at(parent_fd, record.name, record.relative)
    _ensure_regular(after, record.relative, "after close")
    _ensure_stable(record.initial_stat, after, record.relative, "after close")
    digest.update(b"\xff")


def _close_chain(descriptors: list[int], label: str) -> None:
    first_error: OSError | None = None
    for descriptor in reversed(descriptors):
        try:
            os.close(descriptor)
        except OSError as exc:
            if first_error is None:
                first_error = exc
    if first_error is not None:
        raise HashingError(f"Could not close {label}") from first_error


def _close_file_and_chain(
    file_fd: int,
    descriptors: list[int],
    file_label: str,
    chain_label: str,
) -> None:
    first_error: HashingError | None = None
    try:
        _close_fd(file_fd, file_label)
    except HashingError as exc:
        first_error = exc
    try:
        _close_chain(descriptors, chain_label)
    except HashingError as exc:
        if first_error is None:
            first_error = exc
    if first_error is not None:
        raise first_error


def _open_file_path(path: Path) -> tuple[int, list[int], int, os.stat_result]:
    path_stat = _stat_path(path)
    _ensure_regular(path_stat, str(path), "before open")
    components = _path_components(path)
    if not components:
        raise HashingError(f"File path has no lexical filename: {path}")
    parent_components = components[:-1]
    descriptors: list[int] = []
    current_fd = -1
    try:
        current_fd = _open_anchor(path)
        descriptors.append(current_fd)
        for index, component in enumerate(parent_components):
            relative = "/".join(components[: index + 1])
            next_fd, _ = _open_directory_component(
                current_fd,
                component,
                relative,
                check_expected_metadata=False,
            )
            descriptors.append(next_fd)
            current_fd = next_fd
        before = _stat_at(current_fd, components[-1], str(path))
        _ensure_regular(before, str(path), "before open")
        _ensure_stable(path_stat, before, str(path), "between path inspection and open")
        file_fd = -1
        try:
            file_fd = os.open(components[-1], os.O_RDONLY | os.O_NOFOLLOW, dir_fd=current_fd)
            opened = _fstat(file_fd, str(path), "after open")
            _ensure_regular(opened, str(path), "after open")
            _ensure_stable(before, opened, str(path), "between inspection and open")
            return file_fd, descriptors, current_fd, path_stat
        except HashingError:
            if file_fd != -1:
                os.close(file_fd)
            raise
        except (OSError, ValueError) as exc:
            if file_fd != -1:
                os.close(file_fd)
            raise HashingError(f"Could not securely open file path: {path}") from exc
    except HashingError:
        for descriptor in reversed(descriptors):
            try:
                os.close(descriptor)
            except OSError:
                pass
        raise


def _hash_file_bytes(path: Path) -> str:
    file_fd, descriptors, parent_fd, path_stat = _open_file_path(path)
    try:
        parent_stat = _fstat(parent_fd, str(path.parent), "before streaming")
    except BaseException:
        try:
            _close_file_and_chain(
                file_fd,
                descriptors,
                f"annotation file {path}",
                f"annotation path {path}",
            )
        except HashingError:
            pass
        raise
    try:
        digest = hashlib.sha256()
        before_stream = _fstat(file_fd, str(path), "before streaming")
        _ensure_stable(path_stat, before_stream, str(path), "before streaming")
        byte_count = _stream_fd(file_fd, digest, f"annotation file {path}")
        streamed = _fstat(file_fd, str(path), "after streaming")
        _ensure_stable(path_stat, streamed, str(path), "during streaming")
        if byte_count != path_stat.st_size or byte_count != streamed.st_size:
            raise HashingError(f"Annotation file byte count changed during streaming: {path}")
    except BaseException:
        try:
            _close_file_and_chain(
                file_fd,
                descriptors,
                f"annotation file {path}",
                f"annotation path {path}",
            )
        except HashingError:
            pass
        raise
    try:
        _close_fd(file_fd, f"annotation file {path}")
    except HashingError:
        try:
            _close_chain(descriptors, f"annotation path {path}")
        except HashingError:
            pass
        raise
    try:
        after = _stat_at(parent_fd, path.name, str(path))
        _ensure_regular(after, str(path), "after close")
        _ensure_stable(path_stat, after, str(path), "after close")
        result = digest.hexdigest()
    except BaseException:
        try:
            _close_chain(descriptors, f"annotation path {path}")
        except HashingError:
            pass
        raise
    _close_chain(descriptors, f"annotation path {path}")
    verification_descriptors, _, _ = _open_directory_chain(
        path.parent,
        parent_stat,
        check_expected_metadata=False,
    )
    _close_chain(
        verification_descriptors,
        f"final annotation parent verification {path.parent}",
    )
    return result


def hash_file(path: Path | str) -> str:
    """Stream raw file bytes into SHA-256 without parsing the file."""

    _require_secure_hashing()
    return _hash_file_bytes(_path(path))


def _verify_directory_record(
    root: Path,
    record: _DirectoryRecord,
    expected_directories: dict[str, _DirectoryRecord],
) -> None:
    descriptors, fd = _open_directory_record(root, record, expected_directories)
    try:
        final_names = _list_names(fd, record.relative)
        if final_names != record.initial_names:
            raise HashingError(
                f"Package directory entries changed during final verification: {record.relative or '.'}"
            )
        final_fd_stat = _fstat(fd, record.relative, "after final enumeration")
        _ensure_directory(final_fd_stat, record.relative or str(root), "after final enumeration")
        _ensure_stable(record.initial_stat, final_fd_stat, record.relative or str(root), "after final enumeration")
        if record.components:
            final_path_stat = _stat_at(descriptors[-2], record.name or "", record.relative)
        else:
            final_path_stat = _stat_path(root)
        _ensure_directory(final_path_stat, record.relative or str(root), "after final enumeration")
        _ensure_stable(record.initial_stat, final_path_stat, record.relative or str(root), "after final enumeration")
    finally:
        _close_chain(descriptors, f"directory {record.relative or '.'}")


def _verify_file_record(
    root: Path,
    record: _FileRecord,
    expected_directories: dict[str, _DirectoryRecord],
) -> None:
    file_fd, descriptors, parent_fd = _open_file_record(
        root,
        record,
        expected_directories,
        check_directory_metadata=False,
    )
    file_closed = False
    try:
        reopened = _fstat(file_fd, record.relative, "during final verification")
        _ensure_regular(reopened, record.relative, "during final verification")
        _ensure_stable(record.initial_stat, reopened, record.relative, "during final verification")
        _close_fd(file_fd, f"final file verification {record.relative}")
        file_closed = True
        final_path_stat = _stat_at(parent_fd, record.name, record.relative)
        _ensure_regular(final_path_stat, record.relative, "after final verification")
        _ensure_stable(record.initial_stat, final_path_stat, record.relative, "after final verification")
    finally:
        if not file_closed:
            try:
                _close_fd(file_fd, f"final file verification {record.relative}")
            except HashingError:
                pass
        _close_chain(descriptors, f"final file path {record.relative}")


def hash_tree(root: Path | str) -> str:
    """Hash a point-in-time snapshot attempt using bounded descriptors.

    Relative POSIX paths are globally sorted in the aggregate. The function
    does not lock the filesystem or promise that a later mutation is
    impossible; callers must run :func:`verify_frozen_case` before use.
    """

    _require_secure_hashing()
    package_root = _path(root)
    root_stat = _stat_path(package_root)
    _ensure_directory(root_stat, str(package_root), "before open")
    root_descriptors, root_fd, opened_root = _open_directory_chain(package_root)
    try:
        _ensure_stable(root_stat, opened_root, str(package_root), "after open")
        directories = [_DirectoryRecord("", (), None, opened_root, ())]
        files: list[_FileRecord] = []
        _walk_directory(root_fd, "", (), directories, files, opened_root)
    finally:
        _close_chain(root_descriptors, f"hashing root {package_root}")

    expected_directories = {record.relative: record for record in directories}
    digest = hashlib.sha256()
    for record in sorted(files, key=lambda item: item.relative):
        file_fd, descriptors, parent_fd = _open_file_record(
            package_root,
            record,
            expected_directories,
        )
        try:
            _hash_file_record(digest, record, file_fd, parent_fd)
        finally:
            _close_chain(descriptors, f"file path {record.relative}")

    for record in sorted(files, key=lambda item: item.relative):
        _verify_file_record(package_root, record, expected_directories)

    for record in sorted(directories, key=lambda item: (len(item.components), item.relative)):
        _verify_directory_record(package_root, record, expected_directories)

    final_root = _stat_path(package_root)
    _ensure_directory(final_root, str(package_root), "after final verification")
    if not _same_identity(root_stat, final_root):
        raise HashingError(f"Hashing root pathname changed during final verification: {package_root}")
    return digest.hexdigest()
