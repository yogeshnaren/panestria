"""Skip only a main push whose exact merge parents/tree have passing PR evidence.

Missing API access, stale artifacts, direct pushes or any uncertainty run CI.
This is source-equivalence reuse, never a new test or release-gate result.
"""

from __future__ import annotations

import json
import os
import re
import signal
import subprocess
import urllib.request
from pathlib import Path

REQUIRED = {
    "quality",
    "behavioral (fast)",
    "behavioral (kernel)",
    "behavioral (platform)",
    "behavioral (research)",
    "test",
}


def git(*args: str) -> str:
    return subprocess.check_output(["git", *args], text=True, stderr=subprocess.DEVNULL, timeout=5).strip()


def prove() -> dict[str, object]:
    if os.environ.get("GITHUB_EVENT_NAME") != "push" or os.environ.get("GITHUB_REF") != "refs/heads/main":
        return {"already_tested": False, "reason": "not_main_push"}
    repository, token = os.environ.get("GITHUB_REPOSITORY", ""), os.environ.get("GH_TOKEN", "")
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository) or not token:
        return {"already_tested": False, "reason": "metadata_access_unavailable"}
    commit = git("rev-parse", "HEAD")
    if commit != os.environ.get("GITHUB_SHA"):
        return {"already_tested": False, "reason": "checkout_mismatch"}
    parents = git("rev-list", "--parents", "-n", "1", commit).split()[1:]
    if len(parents) != 2:
        return {"already_tested": False, "reason": "not_two_parent_merge"}
    tree = git("rev-parse", "HEAD^{tree}")

    def api(path: str):
        request = urllib.request.Request(
            f"https://api.github.com/repos/{repository}/{path}",
            headers={
                "Authorization": "Bearer " + token,
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
        )
        with urllib.request.urlopen(request, timeout=5) as response:
            raw = response.read(2 * 1024 * 1024 + 1)
        if len(raw) > 2 * 1024 * 1024:
            raise ValueError("metadata_size_limit")
        return json.loads(raw)

    runs = api(f"actions/workflows/ci.yml/runs?head_sha={parents[1]}&per_page=100")
    entries = runs["workflow_runs"]
    # Never search past a failed/pending/manual full run for an older green.
    # Reruns update their existing run; incomplete/truncated history is unknown.
    if (
        not entries
        or runs["total_count"] != len(entries)
        or any(
            r.get("head_sha") != parents[1]
            or r.get("path") != ".github/workflows/ci.yml"
            or r.get("status") != "completed"
            or r.get("conclusion") != "success"
            for r in entries
        )
    ):
        return {"already_tested": False, "reason": "head_has_failed_pending_or_incomplete_ci_history"}
    for run in entries:
        if (run.get("head_sha"), run.get("event"), run.get("status"), run.get("conclusion"), run.get("path")) != (
            parents[1],
            "pull_request",
            "completed",
            "success",
            ".github/workflows/ci.yml",
        ):
            continue
        run_id = run["id"]
        if type(run_id) is not int or run_id < 1:
            continue
        jobs = api(f"actions/runs/{run_id}/jobs?filter=latest&per_page=100")["jobs"]
        if (
            len(jobs) != 6
            or {j["name"] for j in jobs} != REQUIRED
            or any(j.get("status") != "completed" or j.get("conclusion") != "success" for j in jobs)
        ):
            continue
        artifacts = api(f"actions/runs/{run_id}/artifacts?per_page=100")["artifacts"]
        previews, suites = set(), set()
        for artifact in artifacts:
            match = re.fullmatch(r"ci-(fast|kernel|platform|research)-([0-9a-f]{40})", artifact["name"])
            if match and not artifact.get("expired", True):
                suites.add(match[1])
                previews.add(match[2])
        if len(previews) != 1 or suites != {"fast", "kernel", "platform", "research"}:
            continue
        preview = previews.pop()
        tested = api("git/commits/" + preview)
        if (
            tested.get("sha") != preview
            or tested["tree"]["sha"] != tree
            or [p["sha"] for p in tested["parents"]] != parents
        ):
            continue
        return {
            "already_tested": True,
            "reason": "same_tested_merge_parents_and_tree",
            "merge_commit": commit,
            "parents": parents,
            "tree": tree,
            "upstream_run": run_id,
            "tested_preview": preview,
            "required_checks": sorted(REQUIRED),
            "release_gate": "NOT_EVALUATED",
        }
    return {"already_tested": False, "reason": "no_exact_passing_pr_evidence"}


def main() -> None:
    def deadline(_signum: int, _frame: object) -> None:
        raise TimeoutError("metadata_proof_deadline")

    signal.signal(signal.SIGALRM, deadline)
    signal.alarm(20)  # Optional metadata lookup must not turn into a long wait.
    try:
        result = prove()
    except Exception:
        # Fail open to *more verification*, never skip on a network/parser error.
        result = {"already_tested": False, "reason": "proof_unavailable_run_checks"}
    finally:
        signal.alarm(0)
    out = Path("evidence/ci-merge-proof.json")
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result))
    if path := os.environ.get("GITHUB_OUTPUT"):
        with Path(path).open("a") as stream:
            stream.write("already_tested=" + str(result["already_tested"]).lower() + "\n")


if __name__ == "__main__":
    main()
