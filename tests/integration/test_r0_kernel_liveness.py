"""Known kernel liveness defects, pinned as strict xfails until plan 2.1/2.2 fix them.

Production-readiness plan item 1.16. Each test asserts the intended outcome and
fails today for the reason in its marker. ``strict=True`` turns an accidental fix
into a failure, so the item that fixes a defect must remove that marker:

- plan 2.2 (effect ledger): a cleanly refused protected merge is definitive, reconcile
  honours a NoEffect verdict, and the Build CLI can reconcile;
- plan 2.1 (task state machine): goal cancel covers every task and closes a PREPARED,
  never-dispatched effect; the receipt reports the stored goal status; an expired lease
  on the final attempt, or a release on it, ends the task instead of stranding it.

The ``test_r0_`` prefix routes this file to the kernel CI lane. The entry points
are today's kernel services. If a fix adds a dedicated one (for example a lease
reaper), it updates the call and keeps the asserted end state.
"""

from __future__ import annotations

import subprocess
from typing import Any
from uuid import uuid4

import psycopg
import pytest
from build_support import BuildFixture, _git, _publish
from build_support import build as build
from test_aos_027a import _approve, _target

from panestria.execution.outbox import Confirmed, EffectExecutor, NoEffect, Unknown
from panestria.kernel.cancellation import CancellationService
from panestria.kernel.effects import DispatchClaim, SideEffectService
from panestria.kernel.errors import KernelDenied
from panestria.kernel.goals import Actor
from panestria.kernel.leases import AttemptLease, LeaseService
from panestria.kernel.uow import UnitOfWork

_AMBIGUOUS = frozenset({"EXECUTING", "UNKNOWN", "RECONCILING"})


def _effect(dsn: str, effect_id: str) -> tuple[str, str | None, str, str]:
    """Return (effect state, reconciliation note, task state, goal status)."""
    with psycopg.connect(dsn) as c:
        row = c.execute(
            "SELECT e.state, e.reconciliation_note, t.state, g.status FROM panestria.side_effect e"
            " JOIN panestria.task t ON t.id = e.task_id JOIN panestria.goal g ON g.id = t.goal_id"
            " WHERE e.id = %s",
            (effect_id,),
        ).fetchone()
    assert row is not None
    return str(row[0]), None if row[1] is None else str(row[1]), str(row[2]), str(row[3])


def _executor(build: BuildFixture, target: Any) -> EffectExecutor:
    return EffectExecutor(lambda: psycopg.connect(build.task["dsn"]), target)


def _task_version(dsn: str, task_id: str) -> int:
    with psycopg.connect(dsn) as c:
        row = c.execute("SELECT row_version FROM panestria.task WHERE id = %s", (task_id,)).fetchone()
    assert row is not None
    return int(row[0])


def _cancel(dsn: str, actor: Actor, goal_id: str, version: int) -> Any:
    # Callers commit a receipt and roll back a denial (connection context manager).
    with psycopg.connect(dsn) as c:
        return CancellationService().cancel(
            UnitOfWork(c), actor, goal_id, version, "owner_requested_cancel", correlation_id=str(uuid4())
        )


# K1: a cleanly refused protected merge must not strand the task in RECONCILING.


@pytest.mark.xfail(
    strict=True,
    reason="plan 2.2: K1 a base-moved CAS refusal is recorded as UNKNOWN and the task is stuck in RECONCILING",
)
def test_base_moved_merge_refusal_is_definitive(build: BuildFixture) -> None:
    effect = _approve(build, _publish(build))
    # Another merge lands first, so the approved base is no longer the destination head.
    _git(build.source, "checkout", "-q", "-b", "concurrent", build.base)
    (build.source / "concurrent.txt").write_text("concurrent")
    _git(build.source, "add", "concurrent.txt")
    _git(build.source, "commit", "-qm", "synthetic concurrent merge")
    moved = _git(build.source, "rev-parse", "HEAD")
    subprocess.run(["git", "--git-dir", str(build.bare), "fetch", "-q", str(build.source), moved], check=True)
    subprocess.run(["git", "--git-dir", str(build.bare), "update-ref", "refs/heads/main", moved], check=True)

    _executor(build, _target(build)).dispatch(build.actor, effect)

    # Git refused the compare-and-swap: nothing moved and no witness exists.
    assert _git(build.bare, "rev-parse", "refs/heads/main") == moved
    assert not _git(build.bare, "for-each-ref", "refs/panestria/effects")
    state, _note, task, _goal = _effect(build.task["dsn"], effect)
    assert state not in _AMBIGUOUS, f"refused CAS recorded as {state}"
    assert task == "FAILED", f"task left in {task}"


@pytest.mark.xfail(
    strict=True,
    reason="plan 2.2: K1 a revalidation denial before any I/O is recorded as UNKNOWN and the task enters RECONCILING",
)
def test_pre_io_revalidation_denial_is_definitive(build: BuildFixture) -> None:
    effect = _approve(build, _publish(build))
    # The required check changes after approval: revalidation denies before any Git I/O.
    with psycopg.connect(build.task["dsn"]) as c:
        c.execute(
            "UPDATE panestria.acceptance_check"
            " SET verifier_spec = jsonb_set(verifier_spec, '{timeout_seconds}', '1') WHERE id = %s",
            (build.ids["AC-001"],),
        )
    target = _target(build)
    denials: list[str] = []

    class Recording:
        def dispatch(self, claim: DispatchClaim) -> str:
            try:
                return target.dispatch(claim)
            except KernelDenied as exc:
                denials.append(exc.code)
                raise

        def query(self, claim: DispatchClaim) -> Confirmed | NoEffect | Unknown:
            return target.query(claim)

    _executor(build, Recording()).dispatch(build.actor, effect)

    assert denials == ["build_check_set_mismatch"]
    assert _git(build.bare, "rev-parse", "refs/heads/main") == build.base
    state, _note, task, _goal = _effect(build.task["dsn"], effect)
    assert state not in _AMBIGUOUS, f"pre-I/O denial recorded as {state}"
    assert task != "RECONCILING", "pre-I/O denial stranded the task in RECONCILING"


@pytest.mark.xfail(
    strict=True,
    reason="plan 2.2: K1 reconcile discards a NoEffect verdict and leaves the effect and task RECONCILING",
)
def test_reconcile_honours_no_effect(build: BuildFixture) -> None:
    effect = _approve(build, _publish(build))
    target = _target(build)
    sent: list[str] = []
    verdicts: list[Confirmed | NoEffect | Unknown] = []

    class LostBeforeSend:
        """The transport fails before the request leaves: ambiguous to the caller."""

        def dispatch(self, claim: DispatchClaim) -> str:
            sent.append(claim.effect_id)
            raise ConnectionError("synthetic transport failure before the Git CAS")

        def query(self, claim: DispatchClaim) -> Confirmed | NoEffect | Unknown:
            verdicts.append(target.query(claim))
            return verdicts[-1]

    executor = _executor(build, LostBeforeSend())
    executor.dispatch(build.actor, effect)
    # A transport exception is not proof of no effect: UNKNOWN is correct here.
    assert _effect(build.task["dsn"], effect)[0] == "UNKNOWN"

    executor.reconcile(build.actor, effect)

    # The protected target answered definitively: destination at base, no witness.
    assert sent == [effect] and verdicts == [NoEffect()]
    assert _git(build.bare, "rev-parse", "refs/heads/main") == build.base
    state, note, task, _goal = _effect(build.task["dsn"], effect)
    assert state not in _AMBIGUOUS, f"NoEffect verdict left the effect {state}"
    assert note != "owner_resolution_required"
    assert task != "RECONCILING", "NoEffect verdict left the task in RECONCILING"


@pytest.mark.xfail(strict=True, reason="plan 2.2: K1 the Build CLI has no reconcile command")
def test_build_cli_offers_reconcile() -> None:
    import typer

    from panestria.cli.main import app

    build_commands = typer.main.get_command(app).commands["build"].commands  # type: ignore[attr-defined]
    assert "reconcile" in build_commands


# K2: goal cancellation must cover every task and must not wait on an undispatched effect.


def _second_task(task: dict[str, str], state: str, *, first: bool) -> str:
    """Add a task to the seeded goal, ordered before or after the seeded one by id."""
    while True:
        task_id = str(uuid4())
        if (task_id < task["task"]) is first:
            break
    with psycopg.connect(task["dsn"]) as c:
        c.execute(
            "INSERT INTO panestria.task(id, goal_id, contract_id, name, state) VALUES (%s, %s, %s, 'second', %s)",
            (task_id, task["goal"], task["contract"], state),
        )
    return task_id


@pytest.mark.xfail(
    strict=True,
    reason="plan 2.1: K2 goal cancel handles only the first task of a goal (ORDER BY id)",
)
@pytest.mark.parametrize("first_state", ["READY", "COMPLETED"])
def test_cancel_covers_every_task_of_the_goal(r1_task: dict[str, str], first_state: str) -> None:
    actor = Actor(r1_task["owner"], r1_task["project"])
    # The seeded READY task sorts last; another task of the same goal sorts first.
    other = _second_task(r1_task, first_state, first=True)

    receipt = _cancel(r1_task["dsn"], actor, r1_task["goal"], 0)

    assert receipt.goal_status == "CANCELLED"
    with psycopg.connect(r1_task["dsn"]) as c:
        states = dict(
            c.execute("SELECT id::text, state FROM panestria.task WHERE goal_id = %s", (r1_task["goal"],)).fetchall()
        )
        goal = c.execute("SELECT status FROM panestria.goal WHERE id = %s", (r1_task["goal"],)).fetchone()
    assert goal == ("CANCELLED",)
    assert states[other] == ("CANCELLED" if first_state == "READY" else "COMPLETED")
    assert states[r1_task["task"]] == "CANCELLED", f"later task of the cancelled goal left {states[r1_task['task']]}"


@pytest.mark.xfail(
    strict=True,
    reason="plan 2.1: K2 a PREPARED, never-dispatched effect blocks goal cancel indefinitely",
)
def test_prepared_effect_does_not_block_cancel(build: BuildFixture) -> None:
    effect = _approve(build, _publish(build))
    dsn = build.task["dsn"]

    receipt = _cancel(dsn, build.actor, build.task["goal"], _task_version(dsn, build.task["task"]))
    # Repeating cancel cannot help today: the task is CANCELLING, so the effect can never be claimed.
    for _ in range(2):
        if receipt.goal_status == "CANCELLED":
            break
        receipt = _cancel(dsn, build.actor, build.task["goal"], receipt.task_version)
    with pytest.raises(KernelDenied), psycopg.connect(dsn) as c:
        SideEffectService().claim(UnitOfWork(c), build.actor, effect)

    assert _git(build.bare, "rev-parse", "refs/heads/main") == build.base
    state, _note, task, goal = _effect(dsn, effect)
    assert (receipt.goal_status, receipt.task_state) == ("CANCELLED", "CANCELLED")
    assert (task, goal) == ("CANCELLED", "CANCELLED")
    assert state != "PREPARED", "the undispatched effect is still dispatchable intent"


@pytest.mark.xfail(
    strict=True,
    reason='plan 2.1: K2 a cancel waiting on an in-flight effect hard-codes goal_status "CREATED" in its receipt',
)
def test_waiting_cancel_receipt_reports_stored_goal_status(build: BuildFixture) -> None:
    effect = _approve(build, _publish(build))
    dsn = build.task["dsn"]
    with psycopg.connect(dsn) as c:
        SideEffectService().claim(UnitOfWork(c), build.actor, effect)  # EXECUTING: genuinely in flight

    receipt = _cancel(dsn, build.actor, build.task["goal"], _task_version(dsn, build.task["task"]))

    state, _note, task, goal = _effect(dsn, effect)
    assert (state, task) == ("EXECUTING", "CANCELLING")
    assert receipt.task_state == "CANCELLING"
    assert receipt.goal_status == goal, f"receipt says {receipt.goal_status}, goal is {goal}"


# K4: an expired or released final attempt must end the task, not strand it.


def _acquire(task: dict[str, str], version: int) -> AttemptLease:
    actor = Actor(task["owner"], task["project"])
    with psycopg.connect(task["dsn"]) as c:
        return LeaseService().acquire(UnitOfWork(c), actor, task["task"], "synthetic-worker", version)


def _expire_lease(task: dict[str, str], lease: AttemptLease) -> None:
    """The worker died: its lease runs out without a heartbeat, release or retry."""
    with psycopg.connect(task["dsn"]) as c:
        c.execute(
            "UPDATE panestria.task_attempt SET lease_expires_at = clock_timestamp() - interval '1 second'"
            " WHERE id = %s",
            (lease.attempt_id,),
        )


def _attempts(task: dict[str, str]) -> tuple[str, list[tuple[int, str]]]:
    with psycopg.connect(task["dsn"]) as c:
        state = c.execute("SELECT state FROM panestria.task WHERE id = %s", (task["task"],)).fetchone()
        rows = c.execute(
            "SELECT attempt_number, status FROM panestria.task_attempt WHERE task_id = %s ORDER BY attempt_number",
            (task["task"],),
        ).fetchall()
    assert state is not None
    return str(state[0]), [(int(n), str(s)) for n, s in rows]


@pytest.mark.xfail(
    strict=True,
    reason="plan 2.1: K4 attempts_exhausted is checked before reclaim, so a dead final lease stays RUNNING forever",
)
def test_dead_lease_on_final_attempt_fails_the_task(r1_task: dict[str, str]) -> None:
    # The contract allows three attempts; each worker dies holding its lease.
    lease = _acquire(r1_task, 0)
    for _ in range(2):
        _expire_lease(r1_task, lease)
        lease = _acquire(r1_task, lease.row_version)  # reclaim: the previous attempt becomes LOST
    assert lease.attempt_number == 3
    _expire_lease(r1_task, lease)

    # Reclaiming the dead final attempt is the only recovery path; no reaper exists.
    # A denial must still leave a durable outcome under the usual rollback-on-denial caller.
    try:
        _acquire(r1_task, lease.row_version)
    except KernelDenied as exc:
        assert exc.code == "attempts_exhausted"

    state, attempts = _attempts(r1_task)
    assert attempts[-1] == (3, "LOST"), f"dead final attempt still {attempts[-1][1]}"
    assert state == "FAILED", f"task left in {state} with no attempts left"


@pytest.mark.xfail(
    strict=True,
    reason="plan 2.1: K4 releasing the final attempt parks the task in RETRY_WAIT with no attempts left",
)
def test_release_of_final_attempt_does_not_park_in_retry_wait(r1_task: dict[str, str]) -> None:
    actor = Actor(r1_task["owner"], r1_task["project"])
    version = 0
    for _ in range(3):
        lease = _acquire(r1_task, version)
        with psycopg.connect(r1_task["dsn"]) as c:
            LeaseService().release(UnitOfWork(c), actor, lease.attempt_id, lease.epoch)
        version = lease.row_version + 1
    with pytest.raises(KernelDenied, match="attempts_exhausted"):
        _acquire(r1_task, version)

    state, attempts = _attempts(r1_task)
    assert [status for _n, status in attempts] == ["LOST", "LOST", "LOST"]
    assert state == "FAILED", f"task left in {state} with no attempts left"
