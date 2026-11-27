"""Tally the production DockerSandbox's classification of real kills.

Diagnostic only; not a test and not part of any CI lane. Each run is one real
DockerSandbox.run with the AOS-008 limits (128 MiB, wall 20 s or 2 s for the
deadline case) in a fresh temporary workspace; the runner removes each
container by its exact ID. Cases:

    memory    allocate 384 MiB            -> expect memory_limit
    deadline  sleep past wall_seconds     -> expect deadline_exceeded
    cancel    cancel after 1.5 s          -> expect cancelled
    selfkill  the worker SIGKILLs itself  -> expect process_failed

Set NO_CGROUP_WATCH=1 to point the runner's cgroup root at a missing path,
which reproduces the classification from Docker's OOMKilled alone.

    python runner_classification.py RUNS memory[,deadline,cancel,selfkill]
"""

import collections
import json
import os
import sys
import tempfile
import threading
from pathlib import Path

import panestria.sandbox.runner as runner
from panestria.sandbox.profiles import SandboxProfile
from panestria.sandbox.runner import DockerSandbox

PROGRAMS = {
    "memory": "x=bytearray(384*1024*1024)",
    "deadline": "import time; time.sleep(60)",
    "cancel": "import time; time.sleep(60)",
    "selfkill": "import os,signal; os.kill(os.getpid(), signal.SIGKILL)",
}


def main():
    if os.environ.get("NO_CGROUP_WATCH"):
        runner.CGROUP_ROOT = Path("/nonexistent-cgroup-root")
    runs = int(sys.argv[1])
    tally = collections.Counter()
    for case in sys.argv[2].split(","):
        for _ in range(runs):
            with tempfile.TemporaryDirectory() as directory:
                worker = Path(directory) / "attempts" / "worker"
                worker.mkdir(parents=True)
                profile = SandboxProfile(
                    uid=os.getuid(),
                    gid=os.getgid(),
                    memory_bytes=128 * 1024**2,
                    wall_seconds=2 if case == "deadline" else 20,
                    output_bytes=2048,
                )
                cancel = threading.Event()
                timer = threading.Timer(1.5, cancel.set) if case == "cancel" else None
                if timer:
                    timer.start()
                try:
                    receipt = DockerSandbox(worker.parent).run(
                        worker, ("/usr/local/bin/python", "-u", "-c", PROGRAMS[case]), profile, cancel=cancel
                    )
                finally:
                    if timer:
                        timer.cancel()
            tally[(case, receipt.reason, receipt.exit_code, receipt.oom_killed, receipt.cgroup_oom_kills)] += 1
    for (case, reason, exit_code, docker, cgroup), count in sorted(tally.items(), key=str):
        print(
            json.dumps(
                {
                    "case": case,
                    "reason": reason,
                    "exit_code": exit_code,
                    "docker_oom_killed": docker,
                    "cgroup_oom_kills": cgroup,
                    "runs": count,
                }
            )
        )


if __name__ == "__main__":
    main()
