"""Physical cold/warm local inference benchmark and loss of the real model process."""

from __future__ import annotations

import asyncio
import json
import math

import pytest
from test_local_provider import request

from panestria.inference.local import LocalProvider
from panestria.inference.runtime import ModelRuntime


@pytest.mark.live
def test_physical_cold_warm(offline_model: ModelRuntime, record_property: pytest.RecordProperty) -> None:
    record_property("gate_case_id", "AOS-016-TC03")
    record_property("source_clauses", "AOS-016-F02,AOS-016-AC01,AOS-016-AC02")
    record_property("execution_mode", "LIVE")
    provider = LocalProvider(offline_model.socket_path, gpu=True)
    asyncio.run(provider.unload())
    assert asyncio.run(provider.status())["models"] == []
    cold = provider.generate(
        request(prompt="Reply with exactly the word READY.", deadline_seconds=60.0, max_output_tokens=32)
    )
    warm = [
        provider.generate(
            request(prompt="Reply with exactly the word READY.", deadline_seconds=30.0, max_output_tokens=32)
        )
        for _ in range(5)
    ]
    for result in [cold, *warm]:
        assert result.text.strip() == "READY" and result.completion == "COMPLETED" and result.finish_reason == "stop"
        assert result.first_token_seconds is not None and result.decode_tokens_per_second is not None
    resident = asyncio.run(provider.status())["models"]
    assert len(resident) == 1 and 0 < resident[0]["size_vram"] < 2560 * 1024 * 1024
    p95 = sorted(r.first_token_seconds for r in warm)[math.ceil(0.95 * len(warm)) - 1]
    stats = json.loads(
        offline_model._docker(["stats", "--no-stream", "--format", "{{json .}}", offline_model.id or ""])
    )
    memory = offline_model.process_memory()
    assert memory["rss_sum_bytes"] > 0 and memory["process_count"] >= 3
    record_property(
        "benchmark",
        json.dumps(
            {
                "cold_ttft_seconds": cold.first_token_seconds,
                "warm_ttft_seconds": [r.first_token_seconds for r in warm],
                "warm_p95_ttft_seconds": p95,
                "decode_tps": [r.decode_tokens_per_second for r in warm],
                "size_vram_bytes": resident[0]["size_vram"],
                "cgroup_memory": stats["MemUsage"],
                "process_memory": memory,
                "memory_is_peak": False,
                "rss_may_double_count_shared_pages": True,
                "network": "none",
                "model_digest": resident[0]["digest"],
                "samples": 5,
            }
        ),
    )
    assert p95 is not None and p95 <= 3.0  # Small-model profile on the physical Omen, not all model/hardware claims.
