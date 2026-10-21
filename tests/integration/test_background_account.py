"""Scoped metadata collection plus real canonical queue links; no live inference."""

import hashlib
import json
import shutil
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest
from test_background_queue import cli, request_for
from test_native_plan_execution import prepared_plan as prepared_plan  # noqa: F401
from test_native_profile import ARCHIVE, FakeMetadata
from test_native_profile import config as config  # noqa: F401
from test_native_profile import pin as pin  # noqa: F401
from test_owner_build_cli import owner_cli as owner_cli  # noqa: F401

from panestria.brokers.harness.account_profile import NativeAccountProbe
from panestria.brokers.harness.cli_profile import NativeProbeUnavailable
from panestria.execution import background_account as controller
from panestria.kernel.background import BackgroundWorkService
from panestria.kernel.background_account import BackgroundAccountService
from panestria.kernel.errors import KernelDenied
from panestria.kernel.goals import Actor
from panestria.kernel.uow import UnitOfWork

EMAIL = "synthetic-owner@panestria.invalid"
TOKEN = "private-token-not-to-be-retained"


def metadata(**changes):
    transport = FakeMetadata()
    transport.auth = json.dumps(
        {
            "loggedIn": True,
            "authMethod": "claude.ai",
            "apiProvider": "firstParty",
            "subscriptionType": "max",
            "email": EMAIL,
            "token": TOKEN,
            **changes,
        }
    ).encode()
    return transport


def test_pinned_account_collector_redacts_and_scopes_identity_without_legacy_manifest_changes(pin, config):
    account, owner, project = str(uuid4()), str(uuid4()), str(uuid4())
    transport = metadata()
    probe = NativeAccountProbe(ARCHIVE, runner=transport)
    result = probe.inspect(pin, config, owner_id=owner, project_id=project, account_ref=account)
    assert result.identity_basis == "EMAIL" and result.subscription_type == "max"
    assert result.execution_authority == "NONE" and result.billing_verified is result.inference_verified is False
    assert len(transport.calls) == 3 and all("-p" not in args for args, _ in transport.calls)
    assert EMAIL not in result.model_dump_json() and TOKEN not in result.model_dump_json()
    same = probe.inspect(pin, config, owner_id=owner, project_id=project, account_ref=account)
    assert (same.identity_sha256, same.profile_sha256) == (result.identity_sha256, result.profile_sha256)
    scoped = probe.inspect(pin, config, owner_id=owner, project_id=project, account_ref=str(uuid4()))
    assert scoped.identity_sha256 != result.identity_sha256 and scoped.profile_sha256 != result.profile_sha256
    # Unknown/organization/API routes cannot be turned into a personal no-spill
    # observation; generic compatibility manifests remain independently redacted.
    for changes in (
        {"subscriptionType": None},
        {"subscriptionType": "team"},
        {"email": "invalid"},
        {"authMethod": "api_key"},
        {"loggedIn": False},
    ):
        with pytest.raises(NativeProbeUnavailable) as caught:
            NativeAccountProbe(ARCHIVE, runner=metadata(**changes)).inspect(
                pin, config, owner_id=owner, project_id=project, account_ref=account
            )
        assert TOKEN not in str(caught.value) and EMAIL not in str(caught.value)


def test_actual_queue_account_review_race_scope_freshness_change_and_withdrawal(prepared_plan, monkeypatch):
    f, owner, _, plan = prepared_plan
    request = request_for(owner, plan)
    with owner.connect() as c:
        queued = BackgroundWorkService().enqueue(
            UnitOfWork(c), owner.actor, request, request.policy.sha256(), accept_background_policy=True
        )
    assert cli(f, "account", request.item_id)["status"] == "NOT_LINKED"
    binary = Path(f.cfg["native_binary"])
    shutil.copyfile(Path(sys.executable).resolve(), binary)
    binary.chmod(0o700)
    monkeypatch.setattr(controller, "PINNED_BINARY_SHA256", hashlib.sha256(binary.read_bytes()).hexdigest())
    transport = metadata()
    monkeypatch.setattr(controller, "NativeAccountProbe", lambda archive: NativeAccountProbe(archive, runner=transport))
    review = cli(f, "probe-account", request.item_id)
    assert review["status"] == "REVIEW_ONLY" and review["billing_verified"] is False
    assert review["link"]["binding_sha256"] == queued["binding_sha256"]
    assert cli(f, "account", request.item_id)["status"] == "NOT_LINKED"
    digest, link_sha = review["observation_sha256"], review["link_sha256"]
    cli(f, "link-account", request.item_id, digest, "ff" * 32, "--accept-account-link", expected=1)
    reports = controller.account_reports(owner)
    raw = reports.read_blob(digest)
    assert (
        EMAIL.encode() not in raw
        and TOKEN.encode() not in raw
        and str(owner.settings.native_config).encode() not in raw
    )
    assert (reports.root / digest).stat().st_mode & 0o777 == 0o400
    service = BackgroundAccountService(reports)

    def confirm(uow, actor=owner.actor, sha=link_sha, observation=digest):
        return service.confirm(uow, actor, request.item_id, observation, sha, accept_account_link=True)

    # The acknowledged blob precedes the event; rollback cannot leave a link.
    with pytest.raises(RuntimeError):
        with owner.connect() as c:
            confirm(UnitOfWork(c))
            raise RuntimeError("fixture rollback")
    assert cli(f, "account", request.item_id)["status"] == "NOT_LINKED"

    def concurrent():
        with owner.connect() as c:
            return confirm(UnitOfWork(c))

    with ThreadPoolExecutor(max_workers=2) as pool:
        linked = list(pool.map(lambda _: concurrent(), range(2)))
    assert len({r["event_seq"] for r in linked}) == 1
    assert sorted(r["replayed"] for r in linked) == [False, True]
    view = cli(f, "account", request.item_id)
    assert view["freshness"] == "FRESH" and view["runtime_qualification"] == "NOT_ASSESSED"
    assert view["link_sha256"] == link_sha and view["execution_authority"] == "NONE"
    assert cli(f, "show", request.item_id)["scheduling_candidate"] is False
    with owner.connect() as c:
        with pytest.raises(KernelDenied, match="not_found"):
            service.inspect(UnitOfWork(c), Actor(str(uuid4()), owner.actor.project_id), request.item_id)

    observed = service.observation(digest)
    for delta in (timedelta(seconds=-301), timedelta(minutes=1)):
        altered = observed.model_copy(update={"observed_at": datetime.now(UTC) + delta})
        old = reports.write_report(
            json.dumps(altered.model_dump(mode="json"), sort_keys=True, separators=(",", ":")).encode()
        )
        with owner.connect() as c:
            proposed = service.prepare(UnitOfWork(c), owner.actor, request.item_id, old)
            with pytest.raises(KernelDenied, match="stale_or_future"):
                confirm(UnitOfWork(c), sha=proposed.sha256(), observation=old)
    changed = observed.model_copy(update={"identity_sha256": "ab" * 32})
    changed_sha = reports.write_report(
        json.dumps(changed.model_dump(mode="json"), sort_keys=True, separators=(",", ":")).encode()
    )
    with owner.connect() as c:
        proposed = service.prepare(UnitOfWork(c), owner.actor, request.item_id, changed_sha)
        with pytest.raises(KernelDenied, match="account_changed"):
            confirm(UnitOfWork(c), sha=proposed.sha256(), observation=changed_sha)
    cli(f, "withdraw", request.item_id, queued["binding_sha256"])
    fresh = cli(f, "probe-account", request.item_id)
    cli(
        f,
        "link-account",
        request.item_id,
        fresh["observation_sha256"],
        fresh["link_sha256"],
        "--accept-account-link",
        expected=1,
    )
    # A historical exact replay returns its original event, not a fresh grant.
    assert cli(f, "link-account", request.item_id, digest, link_sha, "--accept-account-link")["replayed"]
    with owner.connect() as c:
        assert c.execute(
            "SELECT count(*) FROM panestria.task_attempt a JOIN panestria.task t ON t.id=a.task_id WHERE t.goal_id=%s",
            (plan.goal_id,),
        ).fetchone() == (0,)
        assert c.execute("SELECT DISTINCT state FROM panestria.task WHERE goal_id=%s", (plan.goal_id,)).fetchall() == [
            ("CREATED",)
        ]
    assert f.transport.launches == 0
