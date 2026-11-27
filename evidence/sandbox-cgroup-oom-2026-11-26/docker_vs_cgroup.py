"""Compare Docker's OOMKilled with the kernel's cgroup v2 count on real memory kills.

Diagnostic only; not a test and not part of any CI lane. Each run creates one
disposable labelled container with the AOS-008 memory case's limits (128 MiB,
no swap, --init) and the pinned sandbox image, allocating 384 MiB. A host
thread polls the container's own memory.events (systemd driver layout) every
0.5 ms from before `docker start` until the cgroup is removed. Docker's
State.OOMKilled is read when the attach returns and again 1.5 s later, and the
labelled `docker events` stream is checked for an "oom" event. Every container
is removed by its exact ID.

    python docker_vs_cgroup.py [RUNS]
"""

import json
import subprocess
import sys
import threading
import time
import uuid

IMAGE = "python@sha256:2f17fc044b579bab302c2e8054d3a686e2cb9a83de48e70534b94cd8ebbe06a9"
RUNS = int(sys.argv[1]) if len(sys.argv) > 1 else 30
TAG = "oom-diagnostic-" + uuid.uuid4().hex[:8]


def poll_events(path, out, stop):
    seen = False
    last = None
    while not stop.is_set():
        try:
            with open(path) as handle:
                text = handle.read()
        except OSError:
            if seen:
                out["removed_at"] = time.monotonic()
                return
            time.sleep(0.0005)
            continue
        seen = True
        if text != last:
            last = text
            out.setdefault("readings", []).append((time.monotonic(), dict(line.split() for line in text.splitlines())))
        time.sleep(0.0005)


def state(container):
    inspected = subprocess.run(["docker", "inspect", container], capture_output=True, text=True, check=True)
    return json.loads(inspected.stdout)[0]["State"]


def main():
    events = []
    stream = subprocess.Popen(
        ["docker", "events", "--format", "{{json .}}", "--filter", f"label=oom-diagnostic={TAG}"],
        stdout=subprocess.PIPE,
        text=True,
    )
    threading.Thread(target=lambda: events.extend(json.loads(line) for line in stream.stdout), daemon=True).start()
    time.sleep(0.5)
    rows = []
    for index in range(RUNS):
        container = subprocess.run(
            [
                "docker",
                "create",
                "--name",
                f"{TAG}-{index}",
                "--label",
                f"oom-diagnostic={TAG}",
                "--network",
                "none",
                "--user",
                "1000:1000",
                "--read-only",
                "--log-driver",
                "none",
                "--cap-drop",
                "ALL",
                "--security-opt",
                "no-new-privileges=true",
                "--memory",
                str(128 * 1024**2),
                "--memory-swap",
                str(128 * 1024**2),
                "--pids-limit",
                "32",
                "--cpus",
                "0.5",
                "--init",
                "--entrypoint",
                "/usr/local/bin/python",
                IMAGE,
                "-u",
                "-c",
                "x=bytearray(384*1024*1024)",
            ],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        out, stop = {}, threading.Event()
        poller = threading.Thread(
            target=poll_events,
            args=(f"/sys/fs/cgroup/system.slice/docker-{container}.scope/memory.events", out, stop),
            daemon=True,
        )
        poller.start()
        try:
            subprocess.run(["docker", "start", "--attach", container], capture_output=True, timeout=60)
            returned = time.monotonic()
            at_return = state(container)
            time.sleep(1.5)
            later = state(container)
        finally:
            stop.set()
            poller.join(2)
            subprocess.run(["docker", "rm", "--force", container], capture_output=True)
        readings = out.get("readings", [])
        first_kill = next((t for t, values in readings if int(values.get("oom_kill", 0)) > 0), None)
        removed = out.get("removed_at")
        rows.append(
            {
                "container": container,
                "exit_code": at_return["ExitCode"],
                "docker_oom_killed_at_return": at_return["OOMKilled"],
                "docker_oom_killed_1_5s_later": later["OOMKilled"],
                "cgroup_memory_events_last": readings[-1][1] if readings else None,
                "kill_counted_to_cgroup_removed_ms": None
                if first_kill is None or removed is None
                else round((removed - first_kill) * 1000, 1),
                "cgroup_removed_before_attach_returned": None if removed is None else removed < returned,
            }
        )
    time.sleep(1)
    stream.terminate()
    oom_events = {event.get("Actor", {}).get("ID") for event in events if event.get("Action") == "oom"}
    for row in rows:
        row["docker_oom_event"] = row.pop("container") in oom_events
        print(json.dumps(row))
    lost = [row for row in rows if not row["docker_oom_killed_1_5s_later"]]
    counted = [row for row in rows if int((row["cgroup_memory_events_last"] or {}).get("oom_kill", 0)) > 0]
    print(
        json.dumps(
            {
                "runs": len(rows),
                "exit_137": sum(row["exit_code"] == 137 for row in rows),
                "docker_oom_killed": len(rows) - len(lost),
                "docker_oom_event": sum(row["docker_oom_event"] for row in rows),
                "cgroup_oom_kill_counted": len(counted),
                "docker_lost_but_cgroup_counted": sum(row in counted for row in lost),
                "cgroup_removed_before_attach_returned": sum(
                    bool(row["cgroup_removed_before_attach_returned"]) for row in rows
                ),
            }
        )
    )


if __name__ == "__main__":
    main()
