"""Read-only per-process RSS/PSS snapshots, usable inside the model's PID namespace.

Only numeric memory observations leave the probe; no argv, maps or environment.
RSS sums can count shared pages more than once. This is not a peak or cgroup sum.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

METHOD = "procfs-smaps-rollup-sum-v1"


class MemoryObservationUnavailable(ValueError):
    pass


def _read(directory_fd: int, name: str) -> str:
    fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory_fd)
    with os.fdopen(fd, "rb") as stream:
        raw = stream.read(65537)
    if len(raw) > 65536:
        raise MemoryObservationUnavailable("process_memory_unavailable")
    return raw.decode("ascii")


def observe(proc: Path = Path("/proc")) -> dict[str, Any]:
    """Run in the private model container, excluding only this measurement process.

    Require a stable process set and readable smaps_rollup for every process.
    Missing, denied or changing observations fail; they never become zero RSS.
    """
    try:

        def identities() -> list[int]:
            return sorted(
                int(path.name) for path in proc.iterdir() if path.name.isdigit() and int(path.name) != os.getpid()
            )

        pids = identities()
        if not 1 <= len(pids) <= 128:
            raise ValueError
        rows = []
        for pid in pids:
            directory_fd = os.open(proc / str(pid), os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            try:
                before = _read(directory_fd, "stat")
                body = _read(directory_fd, "smaps_rollup")
                after = _read(directory_fd, "stat")
                ticks = before[before.rfind(")") + 2 :].split()[19]
                if not ticks.isdigit() or after[after.rfind(")") + 2 :].split()[19] != ticks:
                    raise ValueError
                rss = re.findall(r"^Rss:\s+([0-9]+) kB$", body, re.MULTILINE)
                pss = re.findall(r"^Pss:\s+([0-9]+) kB$", body, re.MULTILINE)
                if len(rss) != 1 or len(pss) != 1:
                    raise ValueError
                rows.append({"pid": pid, "rss_bytes": int(rss[0]) * 1024, "pss_bytes": int(pss[0]) * 1024})
            finally:
                os.close(directory_fd)
        if identities() != pids:
            raise ValueError
        return validate(
            json.dumps(
                {
                    "method": METHOD,
                    "process_count": len(rows),
                    "processes": rows,
                    "rss_sum_bytes": sum(row["rss_bytes"] for row in rows),
                    "pss_sum_bytes": sum(row["pss_bytes"] for row in rows),
                }
            )
        )
    except (OSError, ValueError, UnicodeError, IndexError):
        raise MemoryObservationUnavailable("process_memory_unavailable") from None


def validate(raw: str) -> dict[str, Any]:
    try:
        if type(raw) is not str or len(raw.encode()) > 16 * 1024:
            raise ValueError
        body = json.loads(raw)
        if not isinstance(body, dict) or set(body) != {
            "method",
            "process_count",
            "processes",
            "rss_sum_bytes",
            "pss_sum_bytes",
        }:
            raise ValueError
        rows = body["processes"]
        if body["method"] != METHOD or type(rows) is not list or not 1 <= len(rows) <= 128:
            raise ValueError
        for row in rows:
            if (
                type(row) is not dict
                or set(row) != {"pid", "rss_bytes", "pss_bytes"}
                or any(type(value) is not int for value in row.values())
                or not 1 <= row["pid"] <= 2**31 - 1
                or not 0 <= row["pss_bytes"] <= row["rss_bytes"] <= 1024**4
            ):
                raise ValueError
        for key in ("process_count", "rss_sum_bytes", "pss_sum_bytes"):
            if type(body[key]) is not int:
                raise ValueError
        if (
            body["process_count"] != len(rows)
            or len({row["pid"] for row in rows}) != len(rows)
            or not 0 < body["rss_sum_bytes"] == sum(row["rss_bytes"] for row in rows)
            or body["pss_sum_bytes"] != sum(row["pss_bytes"] for row in rows)
        ):
            raise ValueError
        return body
    except (ValueError, TypeError, UnicodeError, RecursionError):
        raise MemoryObservationUnavailable("process_memory_unavailable") from None


if __name__ == "__main__":
    try:
        print(json.dumps(observe(), sort_keys=True, separators=(",", ":")))
    except MemoryObservationUnavailable:
        raise SystemExit("process_memory_unavailable") from None
