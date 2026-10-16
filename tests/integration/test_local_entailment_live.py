"""Actual constrained offline model outcomes, not a claimed semantic quality/release pass."""

import asyncio
import json
import os
from dataclasses import asdict
from pathlib import Path

import pytest

from panestria.execution.entailment_probe import LocalEntailmentProbe
from panestria.inference.local import LocalProvider
from panestria.inference.runtime import ModelRuntime


@pytest.fixture(scope="module")
def actual_entailment_model(tmp_path_factory):
    cache = os.environ.get("PANESTRIA_ENTAILMENT_MODEL_CACHE")
    if not cache:
        pytest.skip("explicit read-only existing model cache absent; actual observation not run")
    runtime = ModelRuntime(
        Path(cache), tmp_path_factory.mktemp("entailment-model-socket"), gpu=False, preserve_existing=True
    )
    try:
        runtime.start()
        actual = runtime.effective
        assert actual["HostConfig"]["NetworkMode"] == "none" and not actual["HostConfig"]["PortBindings"]
        assert actual["HostConfig"]["ReadonlyRootfs"] and actual["HostConfig"]["LogConfig"]["Type"] == "none"
        assert (
            actual["HostConfig"]["NanoCpus"] == 2_000_000_000 and actual["HostConfig"]["Memory"] == 2560 * 1024 * 1024
        )
        assert actual["Config"]["User"] == f"{os.getuid()}:{os.getgid()}"
        assert all(not mount["RW"] for mount in actual["Mounts"] if mount["Destination"] != "/bridge")
        assert {mount["Destination"] for mount in actual["Mounts"]} == {
            "/usr/local/bin/ollama",
            "/usr/local/lib/ollama",
            "/models",
            "/bridge",
            "/runtime/bridge.py",
        }
        assert not actual["Config"].get("Env") or all(
            not value.startswith(("ANTHROPIC_", "OPENAI_", "CLAUDE_", "PANESTRIA_DATABASE_URL=", "DBUS_"))
            for value in actual["Config"]["Env"]
        )
        yield LocalProvider(runtime.socket_path, gpu=False)
    finally:
        runtime.stop()  # Exact owned container/lease only, including failure cleanup.


@pytest.mark.live
@pytest.mark.parametrize("fold", ["calibration", "qualification"])
def test_actual_offline_entailment_outcomes_are_recorded_without_inventing_quality(
    actual_entailment_model, fold, record_property
):
    corpus = Path(__file__).resolve().parents[1] / "fixtures/research/snli-v1/corpus.json"
    result = asyncio.run(LocalEntailmentProbe(actual_entailment_model).run(corpus, fold, wall_seconds=180.0))
    record_property("actual_entailment_observation", json.dumps(asdict(result), sort_keys=True))
    assert result.status == "COMPLETE" and len(result.cases) == 36, result.reason
    assert result.score is not None and result.score.authority == "PREDICTION_METRICS_ONLY"
    record_property(
        "scope",
        "actual pinned offline model/runtime and observed metrics only; not quality, policy or release certification",
    )
    record_property("network", "none")
    record_property("limits", "CPU2 / RAM2.5GiB configured; no measured peak claim")
