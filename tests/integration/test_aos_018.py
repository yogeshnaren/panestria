"""No-network failures and physical resource pressure preserve durable request/task state."""

from __future__ import annotations

import asyncio
import ctypes
import json
from pathlib import Path

import psycopg
import pytest
from test_ask_kernel import initialize
from test_local_provider import request, transport, valid_frames

from panestria.contracts.inference import InferenceResult, InferenceUnavailable
from panestria.inference.local import LocalProvider
from panestria.inference.runtime import ModelRuntime
from panestria.resources.admission import RuntimeGovernor, admit
from panestria.resources.hardware import HardwareProbe

ARCHIVE = Path(__file__).resolve().parents[2] / "docs/specification/attachments/agentos-skills-v0.1.0.zip"


def test_offline_dns_no_provider(record_property: pytest.RecordProperty) -> None:
    record_property("gate_case_id", "AOS-018-TC01")
    record_property("source_clauses", "AOS-018-F01,AOS-018-AC01")
    # This adapter never creates a network transport when the pinned model is absent.
    # The actual OS denial is independently asserted by test_model_os_boundary.
    mocked, calls = transport(valid_frames(), pin="00" * 32)
    with pytest.raises(InferenceUnavailable, match="model_missing_or_digest_mismatch"):
        LocalProvider(Path("/synthetic"), transport=mocked).generate(request())
    assert len(calls) == 1 and calls[0].url.path == "/api/tags" and calls[0].url.host == "local-model"


@pytest.mark.live
def test_oom_disk_model_restart(
    offline_model: ModelRuntime, r1_task: dict[str, str], record_property: pytest.RecordProperty
) -> None:
    record_property("gate_case_id", "AOS-018-TC02")
    record_property("source_clauses", "AOS-018-F01,AOS-018-F03")
    record_property("execution_mode", "LIVE")
    provider = LocalProvider(offline_model.socket_path, gpu=True)

    async def kill_during_stream() -> None:
        seen_delta = False
        try:
            async for event in provider.stream(
                request(
                    prompt="List the integers from 1 to 1000 on separate lines.",
                    max_output_tokens=512,
                    deadline_seconds=30.0,
                )
            ):
                assert not isinstance(event, InferenceResult), "Model completed before the injected failure"
                if not seen_delta:
                    seen_delta = True
                    await asyncio.to_thread(offline_model._docker, ["kill", offline_model.id or ""])
        except InferenceUnavailable as exc:
            assert exc.code in {"model_timeout_or_response_unknown", "model_output_incomplete"}
        else:
            raise AssertionError("Interrupted model returned a success")
        assert seen_delta

    try:
        asyncio.run(kill_during_stream())
    finally:
        offline_model.stop()
        offline_model.start()
    recovered = provider.generate(request(prompt="Reply with exactly READY.", deadline_seconds=60.0))
    assert recovered.text.strip() == "READY"
    with psycopg.connect(r1_task["dsn"]) as c:
        assert c.execute("SELECT state FROM panestria.task WHERE id=%s", (r1_task["task"],)).fetchone() == ("READY",)
    manifest = HardwareProbe(ARCHIVE).collect()
    assert admit(manifest.model_copy(update={"disk_free_gib": 0.0}), gpu=True).decision == "WAIT"
    assert admit(manifest.model_copy(update={"ram_available_gib": 0.0}), gpu=True).decision == "WAIT"
    record_property("injected_failure", "real_model_container_killed_after_first_delta")
    record_property("oom_boundary_reference", "tests/integration/test_aos_008.py")


def test_capacity_queue_and_cancel(record_property: pytest.RecordProperty) -> None:
    record_property("gate_case_id", "AOS-018-TC03")
    record_property("source_clauses", "AOS-018-F02,AOS-018-F03,AOS-018-AC02")

    async def scenario() -> None:
        governor = RuntimeGovernor(max_queue=1)
        active = await governor.acquire()
        queued = asyncio.create_task(governor.acquire())
        await asyncio.sleep(0.03)
        queued.cancel()
        with pytest.raises(asyncio.CancelledError):
            await queued
        assert governor.status() == {"active": True, "queued": 0, "admissions_stopped": False}
        governor.release(active)
        governor.stop_admissions()
        with pytest.raises(InferenceUnavailable, match="admissions_stopped"):
            await governor.acquire()

    asyncio.run(scenario())


@pytest.mark.live
def test_foreground_pressure_profile(
    offline_model: ModelRuntime, r1_task: dict[str, str], tmp_path: Path, record_property: pytest.RecordProperty
) -> None:
    record_property("gate_case_id", "AOS-018-TC04")
    record_property("source_clauses", "AOS-018-F02,AOS-018-AC02,AOS-018-AC03")
    record_property("execution_mode", "LIVE")
    initialize(r1_task, tmp_path)
    provider = LocalProvider(offline_model.socket_path, gpu=True)
    provider.generate(request(prompt="Reply with exactly READY.", deadline_seconds=60.0))
    probe = HardwareProbe(ARCHIVE)
    before = probe.collect()
    assert admit(before, gpu=True).decision == "PERMIT", "Foreground headroom must be available before a pressure test"
    assert before.accelerators[0].free_gib is not None and before.accelerators[0].free_gib >= 4.5
    cuda = ctypes.CDLL("/usr/local/lib/ollama/cuda_v12/libcudart.so.12")
    cuda.cudaMalloc.argtypes, cuda.cudaMalloc.restype = [ctypes.POINTER(ctypes.c_void_p), ctypes.c_size_t], ctypes.c_int
    cuda.cudaFree.argtypes, cuda.cudaFree.restype = [ctypes.c_void_p], ctypes.c_int
    allocation = ctypes.c_void_p()
    # At most 3 GiB, with >=1.5 GiB of physical GPU headroom retained, held only
    # through one readonly sample. This is coarse pressure, not GPU partitioning.
    assert cuda.cudaMalloc(ctypes.byref(allocation), 3 * 1024**3) == 0
    try:
        during = probe.collect()
        decision = admit(during, gpu=True)
        assert decision.decision == "WAIT" and decision.reasons == ("gpu_pressure_or_unknown",)
        assert during.accelerators[0].free_gib is not None and during.accelerators[0].free_gib < 3.5
        with psycopg.connect(r1_task["dsn"]) as c:
            assert c.execute("SELECT state FROM panestria.task WHERE id=%s", (r1_task["task"],)).fetchone() == (
                "READY",
            )
    finally:
        assert cuda.cudaFree(allocation) == 0
    after = probe.collect()
    assert admit(after, gpu=True).decision == "PERMIT"
    assert provider.generate(request(prompt="Reply with exactly READY.", deadline_seconds=30.0)).text.strip() == "READY"
    record_property(
        "resource_pressure",
        json.dumps(
            {
                "allocated_bytes": 3 * 1024**3,
                "before_free_gib": before.accelerators[0].free_gib,
                "during_free_gib": during.accelerators[0].free_gib,
                "after_free_gib": after.accelerators[0].free_gib,
                "decision_during": decision.decision,
                "gpu_partition_guaranteed": decision.gpu_partition_guaranteed,
                "model_cpu_limit": 2,
                "gpu_model_budget_gib": decision.gpu_model_budget_gib,
                "gpu_foreground_reserve_gib": decision.gpu_foreground_reserve_gib,
                "model_ram_limit_bytes": 2560 * 1024 * 1024,
            }
        ),
    )
