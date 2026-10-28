"""Actual PG/Git/Docker/archive/recall; native and local model transports are fixtures."""

import json
import os
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from uuid import uuid4

import pytest
from test_local_provider import transport, valid_frames
from test_native_plan_execution import native_plan as native_plan  # noqa: F401
from test_native_plan_execution import prepared_plan as prepared_plan  # noqa: F401
from test_offline_build_reference import approve, enable_capture
from test_owner_build_cli import invoke
from test_owner_build_cli import owner_cli as owner_cli  # noqa: F401

from panestria.config_build import BuildSettings
from panestria.contracts.ask import AskSubmission
from panestria.execution.offline_build_recall import OfflineBuildRecall
from panestria.inference.local import LocalProvider
from panestria.kernel.ask import AskService
from panestria.kernel.errors import KernelDenied
from panestria.kernel.uow import UnitOfWork
from panestria.memory.service import MemoryService


def confirmed(prepared_plan, native_plan):
    f, owner, _, plan = prepared_plan
    _, runner, _, state = native_plan
    enable_capture(owner, f)
    assert runner.run(plan.plan_id, public_subscription_run=True)["status"] == "WAITING_APPROVAL"
    outcome = approve(owner, plan.goal_id)
    assert outcome["task_state"] == "COMPLETED"
    return f, owner, state, outcome["offline_reference"]["reference_sha256"]


def test_confirmed_archive_exact_review_concurrent_import_and_offline_ask_without_runtime_auth(
    prepared_plan, native_plan, monkeypatch
):
    f, owner, state, digest = confirmed(prepared_plan, native_plan)
    # Recall needs the historical archive and scoped memory DB, not current
    # Build runtime/certificates/auth/Git. Do not initialize those components.
    cfg = json.loads(f.config.read_text())
    cfg.update(certificates="/ABSENT_CERTIFICATES", native_config="/ABSENT_AUTH", native_binary="/ABSENT_NATIVE")
    f.config.write_text(json.dumps(cfg))
    service = OfflineBuildRecall(BuildSettings.model_validate_json(f.config.read_bytes()), owner.dsn)
    with owner.connect() as c:
        assert c.execute("SELECT count(*) FROM panestria.memory_item").fetchone() == (0,)
    review = invoke(f, "prepare-recall", digest)
    preview = review["preview"]
    assert review["status"] == "REVIEW_ONLY" and preview["training_export"] == "DENIED"
    document = preview["document"]
    assert len(document["body"].encode()) <= 1536 and document["pinned"] is False
    note = json.loads(document["body"])
    assert note["reference_sha256"] == digest and "+value = 43" in note["diff"]["text"]
    assert note["authority"] == "UNTRUSTED_REFERENCE_ONLY"
    invoke(f, "remember-reference", digest, review["review_sha256"], expected=1)
    invoke(f, "remember-reference", digest, "ff" * 32, "--accept-local-recall", expected=1)
    invoke(
        f,
        "remember-reference",
        digest,
        review["review_sha256"],
        "--retain-days",
        "60",
        "--accept-local-recall",
        expected=1,
    )
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(
            pool.map(lambda _: service.remember(digest, review["review_sha256"], accept_local_recall=True), range(2))
        )
    assert sorted(v["replayed"] for v in results) == [False, True]
    assert {k: v for k, v in results[0].items() if k != "replayed"} == {
        k: v for k, v in results[1].items() if k != "replayed"
    }
    item = results[0]["item_id"]
    assert results[1]["item_id"] == item and state["launches"] == 2
    assert invoke(f, "remember-reference", digest, review["review_sha256"], "--accept-local-recall")["replayed"]
    with owner.connect() as c:
        uow = UnitOfWork(c)
        assert c.execute("SELECT count(*) FROM panestria.memory_item").fetchone() == (1,)
        ask = AskService()
        prepared = ask.prepare(
            uow,
            owner.actor,
            AskSubmission(
                request_id=str(uuid4()),
                project_id=owner.actor.project_id,
                question="What did the calculator Build change?",
                context_tokens=4096,
            ),
        )
        c.commit()
        assert len(prepared.context.sources) == 1 and prepared.context.sources[0].item_id == item
        assert document["body"] == json.loads(prepared.context.prompt)["untrusted_reference_data"][0]["body"]
        inference = ask.claim(uow, owner.actor, prepared)
        c.commit()
        mocked, calls = transport(valid_frames())
        result = LocalProvider(Path("/EXPLICIT_SYNTHETIC_LOCAL_SOCKET"), transport=mocked).generate(inference)
        ask.finish(uow, owner.actor, prepared.submission.request_id, result)
        c.commit()
        assert inference.offline and inference.label == "RESTRICTED" and result.text == "READY"
        sent = json.loads(next(r.content for r in calls if r.method == "POST"))
        assert digest in sent["prompt"] and all(r.url.host == "local-model" for r in calls)
        assert ask.receipt(uow, owner.actor, prepared.submission.request_id)["sources"]
        assert c.execute(
            "SELECT stage FROM panestria.memory_use_event WHERE item_id=%s ORDER BY created_at", (item,)
        ).fetchall() == [("retrieved",), ("included",)]
    # A fresh reviewed policy version changes the exact import review; an old
    # digest cannot serve as fresh consent, even for a no-op existing item.
    policy = owner.prepare_policy()
    owner.confirm_policy(policy["review_id"], policy["effect_digest"])
    with pytest.raises(KernelDenied, match="exact_review"):
        service.remember(digest, review["review_sha256"], accept_local_recall=True)


def test_suppression_and_correction_fence_prepared_ask_and_cannot_be_bypassed_by_reimport(prepared_plan, native_plan):
    f, owner, state, digest = confirmed(prepared_plan, native_plan)
    service = OfflineBuildRecall(owner.settings, owner.dsn)
    review = service.prepare(digest)
    saved = service.remember(digest, review["review_sha256"], accept_local_recall=True)
    ask = AskService()
    submission = AskSubmission(
        request_id=str(uuid4()), project_id=owner.actor.project_id, question="calculator Build", context_tokens=4096
    )
    with owner.connect() as c:
        prepared = ask.prepare(UnitOfWork(c), owner.actor, submission)
        assert len(prepared.context.sources) == 1
    files = {p.name: p.read_bytes() for p in (f.root / "offline-results/blobs").iterdir()}
    stopped = invoke(f, "suppress-recall", digest, saved["item_id"], "0", "--confirm-local-suppression")
    assert stopped["row_version"] == 1 and stopped["history_deleted"] is False
    with owner.connect() as c:
        with pytest.raises(KernelDenied, match="memory_stale"), c.transaction():
            ask.claim(UnitOfWork(c), owner.actor, prepared)
        new = ask.prepare(UnitOfWork(c), owner.actor, submission.model_copy(update={"request_id": str(uuid4())}))
        assert new.context.sources == ()
    with pytest.raises(KernelDenied, match="suppressed_or_expired"):
        service.remember(digest, review["review_sha256"], accept_local_recall=True)
    # Only explicit owner actions reactivate and correct; the archive importer
    # cannot overwrite that correction with its earlier excerpt.
    document = service._document(digest, 30).model_copy(update={"body": "Owner correction: calculator changed later"})
    with owner.connect() as c:
        with pytest.raises(KernelDenied, match="memory_suppressed"), c.transaction():
            MemoryService().correct(UnitOfWork(c), owner.actor, saved["item_id"], 1, document)
        assert MemoryService().unsuppress(UnitOfWork(c), owner.actor, saved["item_id"], 1) == 2
        MemoryService().correct(UnitOfWork(c), owner.actor, saved["item_id"], 2, document)
    with pytest.raises(KernelDenied, match="memory_changed"):
        service.remember(digest, review["review_sha256"], accept_local_recall=True)
    assert files == {p.name: p.read_bytes() for p in (f.root / "offline-results/blobs").iterdir()}
    assert state["launches"] == 2


@pytest.mark.live
@pytest.mark.parametrize("owner_cli", [{"live_native": False}], indirect=True)
def test_actual_cached_cpu_retrieves_the_reviewed_build_excerpt(prepared_plan, native_plan, tmp_path, record_property):
    from panestria.inference.runtime import ModelRuntime
    from panestria.resources.admission import admit
    from panestria.resources.hardware import HardwareProbe

    cache = os.environ.get("PANESTRIA_RECALL_TEST_MODEL_CACHE")
    if not cache:
        pytest.skip("Explicit existing cache required; no model download")
    assert not subprocess.check_output(
        ["docker", "ps", "-a", "-q", "--filter", "label=panestria.purpose=local-model"], text=True
    ).strip(), "Existing owner model preserved; probe not run"
    archive = Path(__file__).resolve().parents[2] / "docs/specification/attachments/agentos-skills-v0.1.0.zip"
    assert admit(HardwareProbe(archive).collect_cpu(), gpu=False).decision == "PERMIT"
    _, owner, state, digest = confirmed(prepared_plan, native_plan)
    recall = OfflineBuildRecall(owner.settings, owner.dsn)
    preview = recall.prepare(digest)
    saved = recall.remember(digest, preview["review_sha256"], accept_local_recall=True)
    ask = AskService()
    question = AskSubmission(
        request_id=str(uuid4()),
        project_id=owner.actor.project_id,
        context_tokens=4096,
        max_output_tokens=16,
        deadline_seconds=60.0,
        question="What number did the calculator Build change to? Reply with only the number.",
    )
    with owner.connect() as c:
        ready = ask.prepare(UnitOfWork(c), owner.actor, question)
        assert len(ready.context.sources) == 1 and ready.context.sources[0].item_id == saved["item_id"]
    runtime = ModelRuntime(Path(cache), tmp_path / "owned-cpu", preserve_existing=True)
    try:
        runtime.start()
        with owner.connect() as c:
            inference = ask.claim(UnitOfWork(c), owner.actor, ready)
        result = LocalProvider(runtime.socket_path).generate(inference)
        with owner.connect() as c:
            ask.finish(UnitOfWork(c), owner.actor, question.request_id, result)
        record_property("mode", "ACTUAL_CACHED_CPU_PG_ARCHIVE_RECALL__NATIVE_BUILD_GENERATION_FIXTURE")
        record_property("source_commit", subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip())
        record_property("runtime_identity", runtime.identity)
        record_property("input_tokens", result.usage.input_tokens)
        record_property("output_tokens", result.usage.output_tokens)
        record_property("generation_seconds", result.elapsed_seconds)
        record_property("first_token_seconds", result.first_token_seconds)
        record_property("expected_answer", "43")
        record_property("observed_answer", result.text.strip())
        record_property("quality_scope", "ONE_SYNTHETIC_RECALL_SAMPLE_NOT_MODEL_OR_RELEASE_QUALIFICATION")
        assert result.text.strip() == "43" and result.finish_reason == "stop"
        assert state["launches"] == 2  # No additional cloud/native call for capture/recall.
    finally:
        runtime.stop()
