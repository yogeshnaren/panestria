"""Actual model container enforces readonly host isolation and disabled networking."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import httpx2 as httpx
import pytest

from panestria.inference.runtime import ModelRuntime


@pytest.mark.live
def test_model_os_boundary(offline_model: ModelRuntime, tmp_path: Path, record_property: pytest.RecordProperty) -> None:
    record_property("execution_mode", "LIVE")
    runtime = offline_model
    code = """
import os,socket,json
secret=bool(os.environ.get('OPENAI_API_KEY') or os.environ.get('ANTHROPIC_API_KEY'))
observations={'uid':os.getuid(),'secret_inherited':secret}
try:
 open('/root-write-test','w').write('forbidden')
 observations['readonly']=False
except OSError: observations['readonly']=True
for name,target in [('internet',('1.1.1.1',443)),('local_host',('127.0.0.1',8765))]:
 s=socket.socket();s.settimeout(1)
 try: s.connect(target);observations[name]=True
 except OSError: observations[name]=False
 finally:s.close()
try:
 socket.getaddrinfo('api.openai.com',443);observations['dns']=True
except OSError:observations['dns']=False
print(json.dumps(observations))
"""
    body = json.loads(runtime._docker(["exec", runtime.id or "", "/usr/local/bin/python", "-I", "-c", code]))
    assert body == {
        "uid": 1000,
        "secret_inherited": False,
        "readonly": True,
        "internet": False,
        "local_host": False,
        "dns": False,
    }
    host = runtime.effective["HostConfig"]
    assert host["NetworkMode"] == "none" and host["NanoCpus"] == 2_000_000_000 and host["PidsLimit"] == 128
    assert host["Memory"] == host["MemorySwap"] == 2560 * 1024 * 1024
    assert host["LogConfig"]["Type"] == "none"

    async def denied() -> None:
        async with httpx.AsyncClient(
            transport=httpx.AsyncHTTPTransport(uds=str(runtime.socket_path)), trust_env=False
        ) as c:
            for endpoint in ["pull", "create", "copy", "delete", "push"]:
                r = await c.post(f"http://local-model/api/{endpoint}", json={"model": "qwen2.5:1.5b-instruct"})
                assert r.status_code == 403
            invalid = await c.post("http://local-model/api/generate", json={"model": "foreign", "prompt": "data"})
            assert invalid.status_code == 400

    asyncio.run(denied())
    record_property("effective_network", "none")
    record_property("model_runtime_identity", runtime.identity)


@pytest.mark.live
def test_dead_owner_model_is_reclaimed(offline_model: ModelRuntime, tmp_path: Path) -> None:
    import subprocess
    import sys

    offline_model.stop()
    code = """
import json,os,sys
from pathlib import Path
from panestria.inference.runtime import ModelRuntime
runtime=ModelRuntime(Path(sys.argv[1]),Path(sys.argv[2]),gpu=True)
runtime.start()
print(json.dumps({'id':runtime.id}),flush=True)
os._exit(0)
"""
    try:
        child = subprocess.run(
            [sys.executable, "-c", code, str(offline_model.models), str(tmp_path / "orphan-socket")],
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert child.returncode == 0, child.stderr
        orphan = json.loads(child.stdout)["id"]
        offline_model.start()
        actual = offline_model._docker(
            ["ps", "-a", "-q", "--no-trunc", "--filter", "label=panestria.purpose=local-model"]
        )
        assert orphan not in actual and offline_model.id in actual
    finally:
        if offline_model.id is None:
            offline_model.start()
