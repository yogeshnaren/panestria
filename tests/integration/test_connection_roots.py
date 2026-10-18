"""Actual owned filesystem boundaries, not connector/runtime permission evidence."""

from __future__ import annotations

import gc
import hashlib
import os
import re
import select
import signal
import socket
import stat
import subprocess
import sys
import threading
from pathlib import Path
from uuid import uuid4

import pytest

from panestria.kernel import connection_roots as roots
from panestria.kernel.errors import KernelDenied
from panestria.kernel.goals import Actor

ACTOR = Actor("22222222-2222-2222-2222-222222222222", "33333333-3333-3333-3333-333333333333")
INSIDE = b"PUBLIC_INSIDE_FIXTURE"
OUTSIDE = b"PUBLIC_OUTSIDE_FIXTURE"


def _write(path: Path, body: bytes) -> None:
    path.write_bytes(body)
    path.chmod(0o600)


@pytest.fixture
def directory(tmp_path: Path) -> Path:
    value = tmp_path / "private"
    value.mkdir(mode=0o700)
    _write(value / "file", INSIDE)
    return value


def test_actual_nested_unicode_and_empty_files_are_bounded_snapshots(directory):
    child = directory / "nested"
    child.mkdir()
    # Linux byte identity is retained; no normalization or URL interpretation.
    for name, body in [("café", INSIDE), ("cafe\u0301", OUTSIDE), ("%2e%2e", b""), ("empty", b"")]:
        _write(child / name, body)
    with roots.ConnectionRootSession(ACTOR) as session:
        reference = session.enroll(ACTOR, str(directory))
        assert re.fullmatch("[0-9a-f]{64}", reference)
        for name, body in [("café", INSIDE), ("cafe\u0301", OUTSIDE), ("%2e%2e", b""), ("empty", b"")]:
            result = session.snapshot(ACTOR, reference, "nested/" + name, max_bytes=64)
            assert result.content == body and result.size_bytes == len(body)
            assert result.sha256 == hashlib.sha256(body).hexdigest()
            assert "PUBLIC_" not in repr(result) and str(directory) not in repr(session)


@pytest.mark.parametrize(
    "path",
    [
        "",
        ".",
        "..",
        "../file",
        "/file",
        "a/../file",
        "a/./file",
        "a//file",
        "file/",
        "a\\file",
        "file\x00x",
        "file\nx",
        "\ud800",
        "a/" * 64 + "x",
        "a" * 256,
        "é" * 128,
        "x" * 4096,
        b"file",
        None,
    ],
)
def test_worker_paths_reject_traversal_ambiguous_and_unbounded_spellings(directory, path):
    with roots.ConnectionRootSession(ACTOR) as session:
        reference = session.enroll(ACTOR, str(directory))
        with pytest.raises(KernelDenied, match="^connection_root_path_invalid$") as error:
            session.snapshot(ACTOR, reference, path, max_bytes=64)
        assert str(directory) not in str(error.value)


@pytest.mark.parametrize(
    "locator",
    ["", "/", "relative", "/tmp/../x", "/tmp//x", "/tmp/x/", "/tmp/./x", "/tmp/\x00x", Path("/tmp/example"), None],
)
def test_enrollment_does_not_normalize_or_discover_paths(locator):
    with roots.ConnectionRootSession(ACTOR) as session:
        with pytest.raises(KernelDenied, match="^connection_root_path_invalid$"):
            session.enroll(ACTOR, locator)


@pytest.mark.parametrize("max_bytes", [0, -1, True, 1.0, None, roots.MAX_SNAPSHOT_BYTES + 1])
def test_read_requires_explicit_bounded_integer(directory, max_bytes):
    with roots.ConnectionRootSession(ACTOR) as session:
        reference = session.enroll(ACTOR, str(directory))
        with pytest.raises(KernelDenied, match="^connection_root_byte_limit$"):
            session.snapshot(ACTOR, reference, "file", max_bytes=max_bytes)


def test_exact_size_and_oversize_have_no_truncation_fallback(directory):
    with roots.ConnectionRootSession(ACTOR) as session:
        reference = session.enroll(ACTOR, str(directory))
        assert session.snapshot(ACTOR, reference, "file", max_bytes=len(INSIDE)).content == INSIDE
        with pytest.raises(KernelDenied, match="^connection_root_unsafe$"):
            session.snapshot(ACTOR, reference, "file", max_bytes=len(INSIDE) - 1)


@pytest.mark.parametrize(
    "actor",
    [
        Actor(str(uuid4()), ACTOR.project_id),
        Actor(ACTOR.owner_id, str(uuid4())),
        Actor("not-an-owner", ACTOR.project_id),
    ],
)
def test_foreign_actor_cannot_enroll_read_or_remove(directory, actor):
    with roots.ConnectionRootSession(ACTOR) as session:
        reference = session.enroll(ACTOR, str(directory))
        for operation in [
            lambda: session.enroll(actor, str(directory)),
            lambda: session.snapshot(actor, reference, "file", max_bytes=64),
            lambda: session.remove(actor, reference),
        ]:
            with pytest.raises(KernelDenied, match="^connection_root_unavailable$"):
                operation()
        assert session.snapshot(ACTOR, reference, "file", max_bytes=64).content == INSIDE


@pytest.mark.parametrize("reference", ["ab" * 32, "A" * 64, "/tmp/private", None, 3])
def test_unknown_or_malformed_root_never_resolves(directory, reference):
    with roots.ConnectionRootSession(ACTOR) as session:
        session.enroll(ACTOR, str(directory))
        with pytest.raises(KernelDenied, match="^connection_root_unavailable$"):
            session.snapshot(ACTOR, reference, "file", max_bytes=64)


def test_refs_cannot_be_recovered_from_same_locator_or_another_session(directory):
    with roots.ConnectionRootSession(ACTOR) as first, roots.ConnectionRootSession(ACTOR) as second:
        old = first.enroll(ACTOR, str(directory))
        other = second.enroll(ACTOR, str(directory))
        assert old != other
        with pytest.raises(KernelDenied):
            second.snapshot(ACTOR, old, "file", max_bytes=64)
        first.remove(ACTOR, old)
        fresh = first.enroll(ACTOR, str(directory))
        assert fresh not in {old, other}
        with pytest.raises(KernelDenied):
            first.snapshot(ACTOR, old, "file", max_bytes=64)


def test_root_and_parent_replacement_cannot_retarget_held_directory(directory):
    with roots.ConnectionRootSession(ACTOR) as session:
        reference = session.enroll(ACTOR, str(directory))
        moved = directory.with_name("moved")
        directory.rename(moved)
        directory.mkdir(mode=0o700)
        _write(directory / "file", OUTSIDE)
        assert session.snapshot(ACTOR, reference, "file", max_bytes=64).content == INSIDE
        parent = directory.parent
        relocated = parent.with_name(parent.name + "-moved")
        parent.rename(relocated)
        try:
            parent.mkdir(mode=0o700)
            directory.mkdir(mode=0o700)
            _write(directory / "file", OUTSIDE)
            assert session.snapshot(ACTOR, reference, "file", max_bytes=64).content == INSIDE
        finally:
            (directory / "file").unlink()
            directory.rmdir()
            parent.rmdir()
            relocated.rename(parent)


@pytest.mark.parametrize("kind", ["file-alias", "directory-alias", "magic-alias", "inside-alias", "hardlink"])
def test_actual_aliases_and_hardlinks_cannot_expose_outside_or_inside_targets(directory, kind):
    outside = directory.parent / "outside"
    _write(outside, OUTSIDE)
    link = directory / "link"
    held = os.open(outside, os.O_PATH | os.O_CLOEXEC)
    try:
        relative = "link"
        if kind == "hardlink":
            os.link(outside, link)
        elif kind == "directory-alias":
            link.symlink_to(directory.parent, target_is_directory=True)
            relative = "link/outside"
        elif kind == "magic-alias":
            link.symlink_to(f"/proc/self/fd/{held}")
        else:
            link.symlink_to(outside if kind == "file-alias" else "file")
        with roots.ConnectionRootSession(ACTOR) as session:
            reference = session.enroll(ACTOR, str(directory))
            with pytest.raises(KernelDenied):
                session.snapshot(ACTOR, reference, relative, max_bytes=64)
    finally:
        os.close(held)


def test_parent_and_final_enrollment_aliases_refuse_without_changing_permissions(directory):
    alias = directory.parent / "alias"
    alias.symlink_to(directory, target_is_directory=True)
    parent_alias = directory.parent.with_name(directory.parent.name + "-alias")
    parent_alias.symlink_to(directory.parent, target_is_directory=True)
    try:
        with roots.ConnectionRootSession(ACTOR) as session:
            for path in (alias, parent_alias / directory.name):
                with pytest.raises(KernelDenied):
                    session.enroll(ACTOR, str(path))
            directory.chmod(0o755)
            with pytest.raises(KernelDenied, match="^connection_root_unsafe$"):
                session.enroll(ACTOR, str(directory))
            assert directory.stat().st_mode & 0o777 == 0o755
    finally:
        parent_alias.unlink()


@pytest.mark.parametrize("kind", ["fifo", "socket", "directory", "symlink"])
def test_special_objects_never_reach_readable_open(directory, monkeypatch, kind):
    target = directory / "special"
    endpoint = socket.socket(socket.AF_UNIX)
    try:
        if kind == "fifo":
            os.mkfifo(target)
        elif kind == "socket":
            endpoint.bind(str(target))
        elif kind == "directory":
            target.mkdir()
        else:
            target.symlink_to("file")
        with roots.ConnectionRootSession(ACTOR) as session:
            reference = session.enroll(ACTOR, str(directory))

            def forbidden(*args, **kwargs):
                raise AssertionError("special object opened for I/O")

            monkeypatch.setattr(roots.os, "open", forbidden)
            with pytest.raises(KernelDenied, match="^connection_root_unsafe$"):
                session.snapshot(ACTOR, reference, "special", max_bytes=64)
    finally:
        endpoint.close()


@pytest.mark.parametrize(
    "mutation", ["replace", "alias", "remove", "rewrite", "grow", "link", "permissions", "root-mode"]
)
def test_actual_changes_during_read_deny_without_returning_partial_data(directory, monkeypatch, mutation):
    original_read = os.read
    source = directory / "file"
    outside = directory.parent / "outside"
    _write(outside, OUTSIDE)
    changed = False

    def racing_read(fd, count):
        nonlocal changed
        result = original_read(fd, count)
        if not changed:
            changed = True
            if mutation in {"replace", "alias", "remove"}:
                source.unlink()
                if mutation == "replace":
                    _write(source, OUTSIDE)
                elif mutation == "alias":
                    source.symlink_to(outside)
            elif mutation == "rewrite":
                before = source.stat()
                _write(source, b"X" * len(INSIDE))
                os.utime(source, ns=(before.st_atime_ns, before.st_mtime_ns))
            elif mutation == "grow":
                with source.open("ab") as stream:
                    stream.write(OUTSIDE)
            elif mutation == "link":
                os.link(source, directory.parent / "new-link")
            elif mutation == "permissions":
                source.chmod(0o666)
            else:
                directory.chmod(0o755)
        return result

    with roots.ConnectionRootSession(ACTOR) as session:
        reference = session.enroll(ACTOR, str(directory))
        monkeypatch.setattr(roots.os, "read", racing_read)
        with pytest.raises(KernelDenied):
            session.snapshot(ACTOR, reference, "file", max_bytes=64)
        assert changed


def test_actual_replacement_between_type_check_and_reopen_cannot_open_fifo(directory, monkeypatch):
    actual_open = os.open
    source = directory / "file"
    opened = []

    def racing_open(path, flags, *args, **kwargs):
        assert str(path).startswith("/proc/self/fd/")
        source.unlink()
        os.mkfifo(source)
        fd = actual_open(path, flags, *args, **kwargs)
        opened.append(os.fstat(fd))
        return fd

    with roots.ConnectionRootSession(ACTOR) as session:
        reference = session.enroll(ACTOR, str(directory))
        monkeypatch.setattr(roots.os, "open", racing_open)
        with pytest.raises(KernelDenied):
            session.snapshot(ACTOR, reference, "file", max_bytes=64)
        assert len(opened) == 1 and opened[0].st_nlink == 0


def test_actual_concurrent_symlink_swaps_only_return_inside_bytes_or_deny(directory):
    outside = directory.parent / "outside"
    _write(outside, OUTSIDE)
    source = directory / "file"
    stop, started = threading.Event(), threading.Event()
    errors, swaps = [], []

    def swapper():
        try:
            while not stop.is_set():
                candidate = directory / "candidate"
                candidate.symlink_to(outside)
                candidate.replace(source)
                _write(candidate, INSIDE)
                candidate.replace(source)
                swaps.append(1)
                started.set()
        except BaseException as error:
            errors.append(error)
            started.set()

    with roots.ConnectionRootSession(ACTOR) as session:
        reference = session.enroll(ACTOR, str(directory))
        assert session.snapshot(ACTOR, reference, "file", max_bytes=64).content == INSIDE
        thread = threading.Thread(target=swapper)
        thread.start()
        try:
            assert started.wait(3)
            for _ in range(100):
                try:
                    result = session.snapshot(ACTOR, reference, "file", max_bytes=64)
                except KernelDenied:
                    continue
                assert result.content == INSIDE
        finally:
            stop.set()
            thread.join(timeout=3)
        assert not thread.is_alive() and not errors and swaps


def test_actual_mount_crossing_is_refused_before_content_read():
    # Low-level OS probe only: / is not an enrolled private directory. No /proc
    # content is read and no mount is created or owner filesystem changed.
    fd = os.open("/", os.O_PATH | os.O_DIRECTORY | os.O_CLOEXEC)
    try:
        with pytest.raises(KernelDenied, match="^connection_root_unavailable$"):
            roots._open_path(fd, b"proc/self/status", resolve=roots._DESCENDANT)
    finally:
        os.close(fd)


def test_descriptors_close_on_remove_context_failure_and_gc(directory):
    baseline = set(os.listdir("/proc/self/fd"))
    session = roots.ConnectionRootSession(ACTOR)
    reference = session.enroll(ACTOR, str(directory))
    assert all(not os.get_inheritable(fd) for fd in session._roots.values())
    for _ in range(10):
        session.snapshot(ACTOR, reference, "file", max_bytes=64)
        with pytest.raises(KernelDenied):
            session.snapshot(ACTOR, reference, "missing", max_bytes=64)
    session.remove(ACTOR, reference)
    assert set(os.listdir("/proc/self/fd")) == baseline
    session.enroll(ACTOR, str(directory))
    del session
    gc.collect()
    assert set(os.listdir("/proc/self/fd")) == baseline
    with pytest.raises(RuntimeError), roots.ConnectionRootSession(ACTOR) as session:
        session.enroll(ACTOR, str(directory))
        raise RuntimeError("PUBLIC_TEST_FAILURE")
    session.close()
    assert set(os.listdir("/proc/self/fd")) == baseline
    with pytest.raises(KernelDenied):
        session.enroll(ACTOR, str(directory))


def test_enrollment_capacity_and_failed_enrollment_close_only_owned_fds(directory):
    baseline = set(os.listdir("/proc/self/fd"))
    with roots.ConnectionRootSession(ACTOR) as session:
        for _ in range(roots.MAX_ROOTS):
            session.enroll(ACTOR, str(directory))
        with pytest.raises(KernelDenied, match="^connection_root_limit$"):
            session.enroll(ACTOR, str(directory))
    assert set(os.listdir("/proc/self/fd")) == baseline
    directory.chmod(0o755)
    with roots.ConnectionRootSession(ACTOR) as session, pytest.raises(KernelDenied):
        session.enroll(ACTOR, str(directory))
    assert set(os.listdir("/proc/self/fd")) == baseline


def test_fork_cannot_reuse_reference_and_closes_child_copy_without_touching_parent(directory):
    with roots.ConnectionRootSession(ACTOR) as session:
        reference = session.enroll(ACTOR, str(directory))
        fd = session._roots[reference]
        pid = os.fork()
        if pid == 0:
            try:
                try:
                    session.snapshot(ACTOR, reference, "file", max_bytes=64)
                except KernelDenied:
                    pass
                else:
                    os._exit(10)
                try:
                    os.fstat(fd)
                except OSError:
                    os._exit(0)
                os._exit(11)
            except BaseException:
                os._exit(12)
        _pid, status = os.waitpid(pid, 0)
        assert os.waitstatus_to_exitcode(status) == 0
        assert session.snapshot(ACTOR, reference, "file", max_bytes=64).content == INSIDE


def test_unknown_platform_and_actual_syscall_failure_never_fall_back(directory, monkeypatch):
    with roots.ConnectionRootSession(ACTOR) as session:
        monkeypatch.setattr(roots.platform, "machine", lambda: "unknown-abi")
        with pytest.raises(KernelDenied, match="^connection_root_kernel_unsupported$"):
            session.enroll(ACTOR, str(directory))
    monkeypatch.undo()
    fd = os.open(directory, os.O_PATH | os.O_DIRECTORY | os.O_CLOEXEC)
    try:
        # Actual kernel rejection of an unknown resolve flag, not a mocked
        # syscall pass. The helper must not retry without this constraint.
        with pytest.raises(KernelDenied, match="^connection_root_unavailable$"):
            roots._open_path(fd, b"file", resolve=1 << 63)
    finally:
        os.close(fd)


def test_actual_special_device_is_metadata_only_and_cannot_reach_readable_open(directory, monkeypatch):
    # Known system device metadata, never content; not a private-root enrollment.
    root = directory.stat()
    fd = os.open("/dev/null", os.O_PATH | os.O_CLOEXEC | os.O_NOFOLLOW)
    try:
        assert stat.S_ISCHR(os.fstat(fd).st_mode)
        with pytest.raises(KernelDenied, match="^connection_root_unsafe$"):
            roots._regular(fd, root, 64)
    finally:
        os.close(fd)


def test_actual_exec_closes_root_even_without_subprocess_close_fds(directory):
    with roots.ConnectionRootSession(ACTOR) as session:
        reference = session.enroll(ACTOR, str(directory))
        fd = session._roots[reference]
        info = os.fstat(fd)
        program = (
            "import os,sys\n"
            "try: s=os.fstat(int(sys.argv[1]))\n"
            "except OSError: sys.exit(0)\n"
            "sys.exit(1 if (s.st_dev,s.st_ino)==(int(sys.argv[2]),int(sys.argv[3])) else 0)\n"
        )
        result = subprocess.run(
            [sys.executable, "-I", "-c", program, str(fd), str(info.st_dev), str(info.st_ino)],
            close_fds=False,
            env={},
            capture_output=True,
            timeout=5,
        )
        assert result.returncode == 0 and result.stdout == b"" and result.stderr == b""


def test_read_io_failure_is_sanitized_and_closes_transient_descriptors(directory, monkeypatch):
    with roots.ConnectionRootSession(ACTOR) as session:
        reference = session.enroll(ACTOR, str(directory))
        baseline = set(os.listdir("/proc/self/fd"))

        def failed_read(*args):
            raise OSError("PUBLIC_FIXTURE_LOCATOR:" + str(directory))

        monkeypatch.setattr(roots.os, "read", failed_read)
        with pytest.raises(KernelDenied, match="^connection_root_unavailable$") as error:
            session.snapshot(ACTOR, reference, "file", max_bytes=64)
        assert str(directory) not in str(error.value) and error.value.__suppress_context__
        assert set(os.listdir("/proc/self/fd")) == baseline


def test_foreign_uid_metadata_denies_without_chmod_or_chown(directory, monkeypatch):
    actual_uid = os.getuid()
    with roots.ConnectionRootSession(ACTOR) as session:
        reference = session.enroll(ACTOR, str(directory))
        monkeypatch.setattr(roots.os, "getuid", lambda: actual_uid + 1)
        # Injected identity mismatch only; no privilege/owner-file change.
        with pytest.raises(KernelDenied, match="^connection_root_unsafe$"):
            session.snapshot(ACTOR, reference, "file", max_bytes=64)


def test_missing_libc_entrypoint_is_unavailable_without_fallback(directory, monkeypatch):
    with roots.ConnectionRootSession(ACTOR) as session:
        monkeypatch.setattr(roots.ctypes, "CDLL", lambda *args, **kwargs: object())
        with pytest.raises(KernelDenied, match="^connection_root_kernel_unsupported$"):
            session.enroll(ACTOR, str(directory))


def test_actual_controller_sigkill_leaves_no_root_authority_or_persisted_locator(directory):
    program = (
        "import os,signal,sys\n"
        "from panestria.kernel.connection_roots import ConnectionRootSession\n"
        "from panestria.kernel.goals import Actor\n"
        "a=Actor(sys.argv[2],sys.argv[3])\n"
        "s=ConnectionRootSession(a)\n"
        "r=s.enroll(a,sys.argv[1])\n"
        "print(r,s._roots[r],flush=True)\n"
        "signal.pause()\n"
    )
    child = subprocess.Popen(
        [sys.executable, "-I", "-c", program, str(directory), ACTOR.owner_id, ACTOR.project_id],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env={},
    )
    try:
        assert child.stdout is not None
        assert select.select([child.stdout], [], [], 5)[0], "controller enrollment did not finish"
        raw = os.read(child.stdout.fileno(), 256)
        assert re.fullmatch(rb"[0-9a-f]{64} [0-9]+\n", raw)
        reference, fd = raw.decode().strip().split()
        descriptor_path = Path(f"/proc/{child.pid}/fd/{fd}")
        observed = descriptor_path.stat()
        assert (observed.st_dev, observed.st_ino) == (directory.stat().st_dev, directory.stat().st_ino)
        child.kill()
        out, error = child.communicate(timeout=5)
        assert child.returncode == -signal.SIGKILL and out == b"" and error == b""
        assert not descriptor_path.exists() and sorted(p.name for p in directory.iterdir()) == ["file"]
        assert (directory / "file").read_bytes() == INSIDE
        with roots.ConnectionRootSession(ACTOR) as restarted:
            with pytest.raises(KernelDenied, match="^connection_root_unavailable$"):
                restarted.snapshot(ACTOR, reference, "file", max_bytes=64)
            fresh = restarted.enroll(ACTOR, str(directory))
            assert fresh != reference
            assert restarted.snapshot(ACTOR, fresh, "file", max_bytes=64).content == INSIDE
    finally:
        if child.poll() is None:
            child.kill()
        child.communicate(timeout=5)


def test_reference_collision_refuses_without_retarget_or_fd_leak(directory, monkeypatch):
    with roots.ConnectionRootSession(ACTOR) as session:
        reference = session.enroll(ACTOR, str(directory))
        baseline = set(os.listdir("/proc/self/fd"))
        monkeypatch.setattr(roots.secrets, "token_hex", lambda count: reference)
        with pytest.raises(KernelDenied, match="^connection_root_unavailable$"):
            session.enroll(ACTOR, str(directory))
        assert set(os.listdir("/proc/self/fd")) == baseline
        assert session.snapshot(ACTOR, reference, "file", max_bytes=64).content == INSIDE


def test_same_size_rewrite_with_coarse_timestamp_observation_still_denies(directory, monkeypatch):
    actual_read, actual_identity = os.read, roots._identity
    changed = False

    def change_after_first_read(fd, count):
        nonlocal changed
        raw = actual_read(fd, count)
        if not changed:
            changed = True
            (directory / "file").write_bytes(b"X" * len(INSIDE))
        return raw

    with roots.ConnectionRootSession(ACTOR) as session:
        reference = session.enroll(ACTOR, str(directory))
        # Inject a coarse timestamp observation only. The file, FD and same-size
        # content mutation are real; timestamp fields cannot decide this result.
        monkeypatch.setattr(roots, "_identity", lambda info: actual_identity(info)[:7])
        monkeypatch.setattr(roots.os, "read", change_after_first_read)
        with pytest.raises(KernelDenied, match="^connection_root_changed$"):
            session.snapshot(ACTOR, reference, "file", max_bytes=64)
        assert changed
