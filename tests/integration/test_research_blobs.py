"""Actual protected files/process crashes; no fetched-source/citation qualification."""

import fcntl
import hashlib
import os
import subprocess
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest

from panestria.contracts.research import MAX_SOURCE_BYTES
from panestria.kernel import research_blobs
from panestria.kernel.goals import Actor
from panestria.kernel.research_blobs import ResearchBlobStore, ResearchBlobUnavailable


@pytest.fixture
def blobs(tmp_path):
    root = tmp_path / "protected"
    root.mkdir(mode=0o700)
    actor = Actor(str(uuid4()), str(uuid4()))
    with ResearchBlobStore(root, actor) as store:
        yield root, actor, store, root / actor.owner_id / actor.project_id


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def test_bounded_bytes_are_private_immutable_and_idempotent(blobs):
    root, actor, store, scope = blobs
    for raw in (b"", b"public source", b"x" * MAX_SOURCE_BYTES):
        receipt = store.put(raw)
        inode = (scope / receipt.sha256).stat().st_ino
        assert receipt.sha256 == sha(raw) and receipt.size_bytes == len(raw)
        assert store.read(receipt.sha256, expected_size=len(raw)) == raw
        assert store.put(raw) == receipt
        assert (scope / receipt.sha256).stat().st_ino == inode
        assert (scope / receipt.sha256).stat().st_mode & 0o777 == 0o400
        assert (scope / receipt.sha256).stat().st_nlink == 1
    assert all(path.stat().st_mode & 0o777 == 0o700 for path in (root, root / actor.owner_id, scope))
    assert not list(scope.glob(".pending-*"))
    assert not os.get_inheritable(store._fd)


@pytest.mark.parametrize("raw", [b"a" * (MAX_SOURCE_BYTES + 1), bytearray(b"public"), "private sentinel"])
def test_invalid_payload_never_creates_a_file_or_leaks_body(blobs, raw):
    _, _, store, scope = blobs
    with pytest.raises(ResearchBlobUnavailable) as caught:
        store.put(raw)
    assert "private sentinel" not in str(caught.value)
    assert not list(scope.iterdir())


@pytest.mark.parametrize("digest", ["../outside", "a" * 63, "A" * 64, "a" * 64 + "\n", None])
def test_only_canonical_hash_names_are_read(blobs, digest):
    _, _, store, _ = blobs
    with pytest.raises(ResearchBlobUnavailable, match="invalid_research_blob_hash"):
        store.read(digest, expected_size=1)


@pytest.mark.parametrize("size", [True, -1, MAX_SOURCE_BYTES + 1, 1.0])
def test_expected_length_is_exact_and_bounded(blobs, size):
    _, _, store, _ = blobs
    with pytest.raises(ResearchBlobUnavailable, match="byte_limit"):
        store.read(sha(b"public"), expected_size=size)


def test_existing_wrong_hash_or_size_is_never_replaced(blobs):
    _, _, store, scope = blobs
    receipt = store.put(b"public")
    with pytest.raises(ResearchBlobUnavailable, match="hash_or_size"):
        store.read(receipt.sha256, expected_size=1)
    target = scope / receipt.sha256
    target.chmod(0o600)
    target.write_bytes(b"broken")
    target.chmod(0o400)
    for operation in (lambda: store.read(receipt.sha256, expected_size=6), lambda: store.put(b"public")):
        with pytest.raises(ResearchBlobUnavailable, match="hash_or_size"):
            operation()
        assert target.read_bytes() == b"broken"


@pytest.mark.parametrize("kind", ["symlink", "hardlink", "directory", "public_mode"])
def test_unsafe_finalized_nodes_are_not_followed_or_repaired(blobs, tmp_path, kind):
    _, _, store, scope = blobs
    outside = tmp_path / "private-sentinel"
    outside.write_bytes(b"public")
    outside.chmod(0o400)
    target = scope / sha(b"public")
    if kind == "symlink":
        target.symlink_to(outside)
    elif kind == "hardlink":
        os.link(outside, target)
    elif kind == "directory":
        target.mkdir(mode=0o700)
    else:
        target.write_bytes(b"public")
        target.chmod(0o444)
    for operation in (lambda: store.read(target.name, expected_size=6), lambda: store.put(b"public")):
        with pytest.raises(ResearchBlobUnavailable):
            operation()
    assert outside.read_bytes() == b"public"
    assert target.exists()


def test_cross_project_and_cross_owner_lookups_are_separate(blobs):
    root, actor, store, _ = blobs
    receipt = store.put(b"public")
    for other in (Actor(actor.owner_id, str(uuid4())), Actor(str(uuid4()), actor.project_id)):
        with ResearchBlobStore(root, other) as separate:
            with pytest.raises(ResearchBlobUnavailable):
                separate.read(receipt.sha256, expected_size=receipt.size_bytes)


def test_renamed_root_descriptor_does_not_follow_replacement_path(blobs, tmp_path):
    root, actor, store, _ = blobs
    moved = tmp_path / "original-protected"
    root.rename(moved)
    outside = tmp_path / "outside"
    outside.mkdir(mode=0o700)
    root.symlink_to(outside, target_is_directory=True)
    receipt = store.put(b"public")
    assert (moved / actor.owner_id / actor.project_id / receipt.sha256).read_bytes() == b"public"
    assert not list(outside.iterdir())
    with pytest.raises(ResearchBlobUnavailable):
        ResearchBlobStore(root, actor)


@pytest.mark.parametrize("fault", ["root_mode", "owner_symlink", "project_mode", "bad_id"])
def test_unsafe_scope_setup_fails_before_blob_access(blobs, tmp_path, fault):
    root, actor, _, scope = blobs
    if fault == "root_mode":
        root.chmod(0o750)
    elif fault == "owner_symlink":
        actor = Actor(str(uuid4()), str(uuid4()))
        (root / actor.owner_id).symlink_to(tmp_path, target_is_directory=True)
    elif fault == "project_mode":
        scope.chmod(0o770)
    else:
        actor = Actor("../private", actor.project_id)
    with pytest.raises(ResearchBlobUnavailable):
        ResearchBlobStore(root, actor)


def test_concurrent_instances_publish_one_final_inode(blobs):
    root, actor, store, scope = blobs

    def write(_):
        with ResearchBlobStore(root, actor) as separate:
            return separate.put(b"public" * 1024)

    with ThreadPoolExecutor(max_workers=8) as pool:
        receipts = list(pool.map(write, range(32)))
    assert len(set(receipts)) == 1
    assert len(list(scope.iterdir())) == 1
    assert store.read(receipts[0].sha256, expected_size=receipts[0].size_bytes) == b"public" * 1024


CHILD = """
import os, sys
from pathlib import Path
from panestria.kernel.goals import Actor
from panestria.kernel.research_blobs import ResearchBlobStore, ResearchBlobUnavailable
root, owner, project, mode = sys.argv[1:]
with ResearchBlobStore(Path(root), Actor(owner, project)) as store:
    if mode in ('link', 'unlink'):
        def crash(*args, **kwargs): os._exit(17)
        setattr(os, mode, crash)
        store.put(b'public')
    elif mode == 'read_fifo':
        import hashlib
        try: store.read(hashlib.sha256(b'public').hexdigest(), expected_size=6)
        except ResearchBlobUnavailable: sys.exit(0)
        sys.exit(19)
    else:
        for _ in range(8): store.put(b'public')
"""


def child_args(root, actor, mode):
    return [sys.executable, "-c", CHILD, str(root), actor.owner_id, actor.project_id, mode]


def child_env():
    return {"PATH": os.defpath, "HOME": "/nonexistent", "PYTHONNOUSERSITE": "1"}


@pytest.mark.parametrize("stage", ["link", "unlink"])
def test_actual_process_exit_before_or_after_publication_can_retry_exact_bytes(blobs, stage):
    root, actor, store, scope = blobs
    killed = subprocess.run(child_args(root, actor, stage), env=child_env(), capture_output=True, timeout=10)
    assert killed.returncode == 17
    target, pending = scope / sha(b"public"), scope / (".pending-" + sha(b"public"))
    assert pending.exists()
    inode = target.stat().st_ino if stage == "unlink" else None
    with pytest.raises(ResearchBlobUnavailable):
        store.read(target.name, expected_size=6)
    receipt = store.put(b"public")
    assert store.read(receipt.sha256, expected_size=6) == b"public"
    assert not pending.exists() and target.stat().st_nlink == 1
    if inode is not None:
        assert target.stat().st_ino == inode


def test_fifo_is_rejected_in_an_isolated_process_with_a_deadline(blobs):
    root, actor, _, scope = blobs
    os.mkfifo(scope / sha(b"public"), mode=0o600)
    result = subprocess.run(child_args(root, actor, "read_fifo"), env=child_env(), capture_output=True, timeout=5)
    assert result.returncode == 0


def test_separate_process_writers_share_the_same_lock(blobs):
    root, actor, store, scope = blobs
    processes = [
        subprocess.Popen(
            child_args(root, actor, "write"), env=child_env(), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
        for _ in range(2)
    ]
    try:
        assert all(process.wait(timeout=10) == 0 for process in processes)
    finally:
        for process in processes:
            if process.poll() is None:
                process.kill()
                process.wait(timeout=5)
    assert store.read(sha(b"public"), expected_size=6) == b"public"
    assert len(list(scope.iterdir())) == 1


def test_ambiguous_pending_hardlink_is_preserved(blobs, tmp_path):
    _, _, store, scope = blobs
    pending = scope / (".pending-" + sha(b"public"))
    outside = tmp_path / "sentinel"
    outside.write_bytes(b"public")
    outside.chmod(0o400)
    os.link(outside, pending)
    with pytest.raises(ResearchBlobUnavailable):
        store.put(b"public")
    assert outside.read_bytes() == b"public" and pending.exists()


def test_only_own_pending_name_is_recovered_and_close_is_explicit(blobs):
    _, _, store, scope = blobs
    unrelated = scope / "unrelated-note"
    unrelated.write_text("private sentinel")
    pending = scope / (".pending-" + sha(b"public"))
    pending.write_bytes(b"pub")
    pending.chmod(0o600)
    assert store.put(b"public").size_bytes == 6
    assert unrelated.read_text() == "private sentinel"
    store.close()
    store.close()
    with pytest.raises(ResearchBlobUnavailable, match="closed"):
        store.put(b"public")


def test_busy_directory_lock_denies_without_creating_partial_files(blobs, monkeypatch):
    root, actor, store, scope = blobs
    monkeypatch.setattr(research_blobs, "_LOCK_SECONDS", 0.05)
    with ResearchBlobStore(root, actor) as holder:
        fcntl.flock(holder._fd, fcntl.LOCK_EX)
        try:
            with pytest.raises(ResearchBlobUnavailable, match="busy"):
                store.put(b"public")
            assert not list(scope.iterdir())
        finally:
            fcntl.flock(holder._fd, fcntl.LOCK_UN)
    assert store.put(b"public").size_bytes == 6


def test_busy_same_instance_thread_lock_is_bounded(blobs, monkeypatch):
    _, _, store, scope = blobs
    monkeypatch.setattr(research_blobs, "_LOCK_SECONDS", 0.05)
    entered, release = threading.Event(), threading.Event()

    def hold():
        with store._mutex:
            entered.set()
            release.wait(5)

    thread = threading.Thread(target=hold)
    thread.start()
    try:
        assert entered.wait(2)
        with pytest.raises(ResearchBlobUnavailable, match="busy"):
            store.put(b"public")
        assert not list(scope.iterdir())
    finally:
        release.set()
        thread.join(timeout=2)
    assert not thread.is_alive()
