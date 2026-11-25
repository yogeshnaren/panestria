"""Install a built wheel the way an owner would, then prove it migrates and serves.

    PANESTRIA_DATABASE_URL=postgresql://...disposable... \\
        python3 tools/wheel_smoke.py dist/panestria-*.whl [--umask 0002] [--require-dashboard]

Steps, each of which must pass:

1. Create a fresh virtual environment outside the checkout.
2. Install every runtime dependency from ``constraints/runtime.txt`` with
   ``--require-hashes --no-deps``, then the wheel with ``--no-deps``, then
   ``uv pip check``. A dependency missing from the constraints fails here.
3. From a neutral directory and ``python -I``, the packaged skills archive,
   migrations and (with ``--require-dashboard``) Mission Control resolve inside
   the venv's site-packages, never in a checkout.
4. ``panestria --help``; ``panestria db upgrade`` brings the database to the
   packaged head, and ``panestria db status`` then reports it current.
5. The API server starts on a free loopback port: ``/healthz`` is 200, a
   scoped goal read is 401 without the token and 404 with it.

Use a disposable database only: step 4 migrates it. The script imports nothing
from panestria itself, so it runs under any Python 3.12.
"""

from __future__ import annotations

import argparse
import json
import os
import secrets
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_PROBE = """
import json, sysconfig
from pathlib import Path
import panestria, panestria.assets as a
found = {"package": panestria.__file__, "skills_archive": a.skills_archive(), "migrations": a.migrations()}
if REQUIRE_DASHBOARD:
    found["mission_control"] = a.mission_control()
purelib = Path(sysconfig.get_paths()["purelib"]).resolve()
outside = {k: str(v) for k, v in found.items() if purelib not in Path(v).resolve().parents}
print(json.dumps({"purelib": str(purelib), "outside": outside, "found": {k: str(v) for k, v in found.items()}}))
"""


class SmokeFailed(Exception):
    pass


def _run(argv: list[str], *, env: dict[str, str], cwd: Path, timeout: float = 600) -> str:
    completed = subprocess.run(argv, env=env, cwd=cwd, capture_output=True, text=True, timeout=timeout, check=False)
    if completed.returncode != 0:
        raise SmokeFailed(f"{' '.join(argv[:4])} exited {completed.returncode}:\n{completed.stdout}{completed.stderr}")
    return completed.stdout


def _free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


def _get(url: str, token: str | None = None) -> int:
    request = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"} if token else {})
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            return int(response.status)
    except urllib.error.HTTPError as error:
        return int(error.code)


def smoke(wheel: Path, constraints: Path, dsn: str, *, require_dashboard: bool) -> dict[str, object]:
    uv = os.environ.get("UV") or shutil.which("uv")
    if uv is None:
        raise SmokeFailed("uv is required")
    with tempfile.TemporaryDirectory(prefix="panestria-wheel-smoke-") as folder:
        root = Path(folder)
        # Only what a fresh shell would have: no PANESTRIA_* settings leak in.
        env = {
            "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
            "HOME": os.environ.get("HOME", str(root)),
            "LANG": "C.UTF-8",
        }
        # uv alone also keeps its own settings (cache, managed Python location).
        uv_env = {**env, **{key: value for key, value in os.environ.items() if key.startswith("UV_")}}
        venv = root / "venv"
        python = venv / "bin" / "python"
        _run([uv, "venv", "--quiet", "--python", "3.12", str(venv)], env=uv_env, cwd=root)
        install = [uv, "pip", "install", "--quiet", "--python", str(python), "--no-deps"]
        _run([*install, "--require-hashes", "-r", str(constraints)], env=uv_env, cwd=root)
        _run([*install, str(wheel)], env=uv_env, cwd=root)
        _run([uv, "pip", "check", "--python", str(python)], env=uv_env, cwd=root)

        probe = _PROBE.replace("REQUIRE_DASHBOARD", repr(require_dashboard))
        located = json.loads(_run([str(python), "-I", "-c", probe], env=env, cwd=root))
        if located["outside"]:
            raise SmokeFailed(f"assets resolved outside the installed package: {located['outside']}")

        cli = str(venv / "bin" / "panestria")
        _run([cli, "--help"], env=env, cwd=root)
        db_env = {**env, "PANESTRIA_DATABASE_URL": dsn}
        upgrade = json.loads(_run([cli, "db", "upgrade"], env=db_env, cwd=root))
        status = json.loads(_run([cli, "db", "status"], env=db_env, cwd=root))
        if status.get("current_is_head") is not True:
            raise SmokeFailed(f"database not at the packaged head after upgrade: {status}")

        token, port = secrets.token_hex(16), _free_port()
        server_env = {
            **db_env,
            "PANESTRIA_TOKEN": token,
            "PANESTRIA_BIND_HOST": "127.0.0.1",
            "PANESTRIA_BIND_PORT": str(port),
            "PANESTRIA_SANDBOX": str(root / "sandbox"),
        }
        server = subprocess.Popen(
            [str(python), "-I", "-m", "panestria.api.serve"],
            env=server_env,
            cwd=root,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        base = f"http://127.0.0.1:{port}"
        try:
            deadline = time.monotonic() + 60
            while True:
                if server.poll() is not None:
                    output = server.stdout.read() if server.stdout else ""
                    raise SmokeFailed(f"server exited {server.returncode}:\n{output}")
                try:
                    if _get(base + "/healthz") == 200:
                        break
                except OSError:
                    pass
                if time.monotonic() > deadline:
                    raise SmokeFailed("server did not answer /healthz within 60 s")
                time.sleep(0.25)
            goal = f"{base}/v1/goals/{uuid.uuid4()}"
            served = {"healthz": 200, "goal_without_token": _get(goal), "goal_with_token": _get(goal, token)}
            if (served["goal_without_token"], served["goal_with_token"]) != (401, 404):
                raise SmokeFailed(f"unexpected scoped goal responses: {served}")
        finally:
            server.terminate()
            try:
                server.wait(timeout=10)
            except subprocess.TimeoutExpired:
                server.kill()
                server.wait(timeout=5)
        return {"located": located["found"], "upgrade": upgrade, "status": status, "served": served}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("wheel", type=Path)
    parser.add_argument("--constraints", type=Path, default=ROOT / "constraints" / "runtime.txt")
    parser.add_argument("--umask", help="octal umask for the install and every step, for example 0002")
    parser.add_argument("--require-dashboard", action="store_true", help="the wheel must carry Mission Control")
    args = parser.parse_args()
    dsn = os.environ.get("PANESTRIA_DATABASE_URL", "")
    if not dsn:
        parser.error("set PANESTRIA_DATABASE_URL to a disposable database")
    if args.umask is not None:
        os.umask(int(args.umask, 8))
    try:
        result = smoke(args.wheel.resolve(), args.constraints.resolve(), dsn, require_dashboard=args.require_dashboard)
    except SmokeFailed as failure:
        print(f"wheel_smoke_failed: {failure}", file=sys.stderr)
        return 1
    print(json.dumps({"wheel": args.wheel.name, "umask": args.umask, **result}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
