"""Actual PG authority rejects an injected input-channel widening before create."""

from dataclasses import replace

from test_registered_check_authority import configured as configured
from test_registered_check_authority import run

from panestria.execution import registered_checks as checks
from panestria.sandbox.runner import DockerSandbox


def test_closed_permit_cannot_journal_a_framed_launch_even_with_matching_new_hash(configured, monkeypatch):
    task, args = configured
    controller = checks.RegisteredCheckController(*args)
    original = checks._ReadAuthority.record_launch
    actual_docker = DockerSandbox._docker
    calls = []
    attacked = []

    def trace(self, argv, **kwargs):
        calls.append(argv[0])
        return actual_docker(self, argv, **kwargs)

    def widen(self, permit, reference, profile):
        assert permit.profile.stdin_mode == profile.stdin_mode == "closed"
        changed = replace(profile, stdin_mode="native-frame-v1")
        attacked.append(self.identity)
        # Injection is explicit; a matching new reference hash cannot widen
        # the independently bound original permit or its one-use claim.
        return original(self, permit, replace(reference, profile_sha256=changed.sha256()), changed)

    monkeypatch.setattr(DockerSandbox, "_docker", trace)
    monkeypatch.setattr(checks._ReadAuthority, "record_launch", widen)
    assert run(controller).outcome == "UNKNOWN"
    assert len(attacked) == 1 and "create" not in calls
    with controller.connect() as connection:
        assert connection.execute(
            "SELECT state,receipt_sha256 FROM panestria.worker_invocation WHERE id=%s", (attacked[0],)
        ).fetchone() == ("UNKNOWN", None)
        assert connection.execute(
            "SELECT count(*) FROM panestria.worker_invocation_launch WHERE invocation_id=%s", (attacked[0],)
        ).fetchone() == (0,)
