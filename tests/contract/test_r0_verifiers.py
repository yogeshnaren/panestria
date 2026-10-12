"""R0-01 and R0-07. Each acceptance node uses its own specification."""

from __future__ import annotations

import base64
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

from panestria.brokers.harness.mock import MockWorkerAdapter
from panestria.contracts.goal import GoalContract, contract_sha256, load_contract
from panestria.sandbox.gitcmd import allow_git
from panestria.sandbox.worktree import WorktreeManager
from panestria.verification.diff import inspect_diff
from panestria.verification.nodes import (
    ArtifactFact,
    ReviewFact,
    evaluate_checks,
    report_output_consistent,
    required_passed,
)
from panestria.verification.registry import CommandRegistry, RegisteredCommand
from panestria.verification.runner import OUTPUT_LIMIT, TrustedCheckRunner

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "docs" / "fixtures" / "synthetic-goal-contract.json"
ALLOWLIST = frozenset({"allowed.txt"})


def _contract(acceptance: list[dict[str, object]]) -> GoalContract:
    document = json.loads(FIXTURE.read_text(encoding="utf-8"))
    document["acceptance"] = acceptance
    loaded = load_contract(document)
    assert isinstance(loaded, GoalContract)
    return loaded


def _check(check_id: str, required: bool, verifier: dict[str, object]) -> dict[str, object]:
    return {
        "id": check_id,
        "description": check_id,
        "required": required,
        "verifier": verifier,
        "evidence": {"required": True, "kind": f"{verifier['type']}-report"},
    }


def _bundle(root: Path) -> tuple[CommandRegistry, TrustedCheckRunner, Path]:
    bundle = root / "protected" / "bundle"
    bundle.mkdir(parents=True)
    passing = bundle / "pass.py"
    failing = bundle / "fail.py"
    sleeping = bundle / "sleep.py"
    flooding = bundle / "flood.py"
    passing.write_text("raise SystemExit(0)\n", encoding="utf-8")
    failing.write_text("raise SystemExit(1)\n", encoding="utf-8")
    sleeping.write_text("import time\ntime.sleep(30)\n", encoding="utf-8")
    flooding.write_text("import sys\nsys.stdout.buffer.write(b'x' * 10000)\n", encoding="utf-8")
    commands: list[RegisteredCommand] = []
    for ref, script in (
        ("synthetic-test-suite", passing),
        ("exits-one", failing),
        ("sleeps", sleeping),
        ("floods", flooding),
    ):
        digest = hashlib.sha256(script.read_bytes()).hexdigest()
        commands.append(RegisteredCommand(ref, (sys.executable, str(script.resolve())), False, digest))
    registry = CommandRegistry(bundle, sys.executable, tuple(commands))
    return registry, TrustedCheckRunner(registry), root / "candidate.txt"


def _tree(tmp_path: Path, name: str) -> tuple[Path, Path, str]:
    manifest = WorktreeManager().create(tmp_path / name, "attempt-1", "seed")
    return Path(manifest.root), Path(manifest.worktree), manifest.base_sha


def test_distinct_command_specs_do_not_share_one_result(tmp_path: Path, record_property: pytest.RecordProperty) -> None:
    record_property("gate_case_id", "AOS-004-TC02")
    registry, runner, candidate = _bundle(tmp_path)
    candidate.write_text("edit:seed\n", encoding="utf-8")
    root, worktree, base = _tree(tmp_path, "commands")
    contract = _contract(
        [
            _check(
                "pass-zero",
                True,
                {
                    "type": "trusted-command-ref",
                    "command_ref": "synthetic-test-suite",
                    "expected_exit_code": 0,
                    "timeout_seconds": 5,
                },
            ),
            _check(
                "want-one",
                True,
                {
                    "type": "trusted-command-ref",
                    "command_ref": "synthetic-test-suite",
                    "expected_exit_code": 1,
                    "timeout_seconds": 5,
                },
            ),
            _check(
                "unknown",
                True,
                {
                    "type": "trusted-command-ref",
                    "command_ref": "not-in-the-command-registry",
                    "expected_exit_code": 1,
                    "timeout_seconds": 5,
                },
            ),
        ]
    )
    reports = evaluate_checks(
        contract,
        root=root,
        worktree=worktree,
        base_sha=base,
        registry=registry,
        runner=runner,
        attempt_id="attempt-1",
        candidate_sha256=hashlib.sha256(candidate.read_bytes()).hexdigest(),
        candidate_path=candidate,
    )
    by_id = {item.check_id: item for item in reports}
    assert by_id["pass-zero"].verdict == "PASS"
    retained = json.loads(by_id["pass-zero"].canonical_bytes())
    assert base64.b64decode(retained["output_b64"]) == b""
    assert retained["output_sha256"] == hashlib.sha256(b"").hexdigest()
    assert report_output_consistent(by_id["pass-zero"].canonical_bytes()) is True
    mutated = json.loads(by_id["pass-zero"].canonical_bytes())
    mutated["output_sha256"] = "ab" * 32
    assert report_output_consistent(json.dumps(mutated).encode()) is False
    assert by_id["want-one"].verdict == "FAIL"
    assert by_id["want-one"].reason == "exit_0"
    assert by_id["unknown"].verdict == "FAIL"
    assert by_id["unknown"].reason == "unknown_command"
    assert required_passed(reports) is False
    assert {item.contract_sha256 for item in reports} == {contract_sha256(contract)}


def test_timeout_and_output_limit_fail_closed(tmp_path: Path, record_property: pytest.RecordProperty) -> None:
    record_property("gate_case_id", "AOS-004-TC02")
    registry, runner, candidate = _bundle(tmp_path)
    candidate.write_text("x\n", encoding="utf-8")
    timed = runner.run("sleeps", candidate, 1, expected_exit_code=0)
    assert timed.verdict == "FAIL"
    assert timed.reason == "timeout"
    flooded = runner.run("floods", candidate, 5, expected_exit_code=0)
    assert flooded.verdict == "FAIL"
    assert flooded.reason == "output_limit"
    assert flooded.truncated is True
    assert flooded.output == b"x" * OUTPUT_LIMIT
    assert flooded.output_sha256 == hashlib.sha256(flooded.output).hexdigest()
    expected = runner.run("exits-one", candidate, 5, expected_exit_code=1)
    assert expected.verdict == "PASS"
    assert expected.exit_code == 1


def test_narrower_path_check_rejects_an_otherwise_allowed_edit(
    tmp_path: Path, record_property: pytest.RecordProperty
) -> None:
    record_property("gate_case_id", "AOS-004-TC02")
    root, worktree, base = _tree(tmp_path, "paths")
    target = worktree / "tests" / "synthetic.txt"
    target.parent.mkdir()
    target.write_text("edit:seed\n", encoding="utf-8")
    broad = inspect_diff(
        root,
        worktree,
        frozenset({"tests/**"}),
        base_sha=base,
        also_allowed=frozenset({"tests/**"}),
    )
    assert broad.ok is True
    assert broad.changed == ("tests/synthetic.txt",)
    registry, runner, _candidate = _bundle(tmp_path / "diff-report")
    reported = evaluate_checks(
        _contract(
            [
                _check(
                    "paths",
                    True,
                    {
                        "type": "git-diff-path-check",
                        "allowed_paths": ["tests/**"],
                        "forbidden_paths": [".env*"],
                    },
                )
            ]
        ),
        root=root,
        worktree=worktree,
        base_sha=base,
        registry=registry,
        runner=runner,
        attempt_id="attempt-1",
        candidate_sha256="ab" * 32,
        candidate_path=target,
    )
    stored = json.loads(reported[0].canonical_bytes())
    assert stored["changed_paths"] == ["tests/synthetic.txt"]
    assert stored["verdict"] == "PASS"
    narrow = inspect_diff(
        root,
        worktree,
        frozenset({"unrelated/**"}),
        base_sha=base,
        also_allowed=frozenset({"src/**", "tests/**"}),
    )
    assert narrow.ok is False
    assert "tests/synthetic.txt" in narrow.denied


def test_policy_uses_the_action_not_the_requested_expectation(
    tmp_path: Path, record_property: pytest.RecordProperty
) -> None:
    record_property("gate_case_id", "AOS-004-TC02")
    contract = _contract(
        [
            _check(
                "merge-policy",
                True,
                {"type": "policy-decision", "action": "protected-merge", "expected": "allow"},
            ),
            _check(
                "unknown-policy",
                False,
                {"type": "policy-decision", "action": "unrestricted-shell", "expected": "allow"},
            ),
        ]
    )
    registry = CommandRegistry(tmp_path, sys.executable, ())
    reports = evaluate_checks(
        contract,
        root=tmp_path,
        worktree=tmp_path,
        base_sha="a" * 40,
        registry=registry,
        runner=TrustedCheckRunner(registry),
        attempt_id="attempt-1",
        candidate_sha256="ab" * 32,
        candidate_path=tmp_path / "candidate",
    )
    assert reports[0].verdict == "FAIL"
    assert reports[0].reason == "policy_mismatch"
    assert reports[1].verdict == "FAIL"
    assert reports[1].reason == "unknown_action"
    assert reports[1].required is False


def test_missing_artifact_and_human_review_are_not_pass(
    tmp_path: Path, record_property: pytest.RecordProperty
) -> None:
    record_property("gate_case_id", "AOS-004-TC02")
    digest = "cd" * 32
    contract = _contract(
        [
            _check(
                "blob",
                True,
                {"type": "artifact-exists", "artifact_ref": "candidate", "expected_sha256": digest},
            ),
            _check(
                "person",
                True,
                {
                    "type": "human-review",
                    "reviewer_ref": "owner",
                    "evidence_requirements": ["diff"],
                },
            ),
            _check(
                "optional-blob",
                False,
                {"type": "artifact-exists", "artifact_ref": "optional", "expected_sha256": digest},
            ),
        ]
    )
    registry = CommandRegistry(tmp_path, sys.executable, ())
    missing = evaluate_checks(
        contract,
        root=tmp_path,
        worktree=tmp_path,
        base_sha="b" * 40,
        registry=registry,
        runner=TrustedCheckRunner(registry),
        attempt_id="attempt-1",
        candidate_sha256=digest,
        candidate_path=tmp_path / "candidate",
    )
    assert [item.verdict for item in missing] == ["FAIL", "FAIL", "FAIL"]
    assert missing[0].reason == "missing_artifact"
    assert missing[1].reason == "missing_review"
    assert required_passed(missing) is False
    present = evaluate_checks(
        contract,
        root=tmp_path,
        worktree=tmp_path,
        base_sha="b" * 40,
        registry=registry,
        runner=TrustedCheckRunner(registry),
        attempt_id="attempt-9",
        candidate_sha256=digest,
        candidate_path=tmp_path / "candidate",
        artifacts=(ArtifactFact("candidate", digest),),
        reviews=(ReviewFact("owner", ("diff", "notes")),),
    )
    assert present[0].verdict == "PASS"
    assert present[1].verdict == "PASS"
    assert present[2].verdict == "FAIL"
    assert required_passed(present) is True
    assert present[0].attempt_id == "attempt-9"


def test_git_diff_sees_baseline_edits_deletions_renames_and_directory_symlinks(
    tmp_path: Path, record_property: pytest.RecordProperty
) -> None:
    record_property("gate_case_id", "AOS-004-TC02")
    root, worktree, base = _tree(tmp_path, "gitdiff")
    (worktree / "README.txt").write_text("changed baseline\n", encoding="utf-8")
    outside = tmp_path / "outside-tree"
    outside.mkdir()
    (worktree / "escape").symlink_to(outside, target_is_directory=True)
    report = inspect_diff(root, worktree, ALLOWLIST, base_sha=base)
    assert report.ok is False
    assert "README.txt" in report.denied
    assert "escape" in report.denied

    fresh_root, fresh_worktree, fresh_base = _tree(tmp_path, "delete")
    (fresh_worktree / "README.txt").unlink()
    deleted = inspect_diff(fresh_root, fresh_worktree, ALLOWLIST, base_sha=fresh_base)
    assert deleted.ok is False
    assert "README.txt" in deleted.denied

    rename_root, rename_worktree, rename_base = _tree(tmp_path, "rename")
    _git(rename_worktree, ["mv", "README.txt", "other.txt"])
    renamed = inspect_diff(rename_root, rename_worktree, ALLOWLIST, base_sha=rename_base)
    assert renamed.ok is False
    assert "other.txt" in renamed.denied

    stale = inspect_diff(rename_root, rename_worktree, ALLOWLIST, base_sha="f" * 40)
    assert stale.ok is False
    assert "<not-a-git-tree>" in stale.denied

    plain_root, plain_worktree, plain_base = _tree(tmp_path, "plain-mode")
    (plain_worktree / "allowed.txt").write_text("edit:alpha\n", encoding="utf-8")
    plain = inspect_diff(plain_root, plain_worktree, ALLOWLIST, base_sha=plain_base)
    assert plain.ok is True
    assert plain.changed == ("allowed.txt",)
    assert plain.denied == ()

    mode_root, mode_worktree, mode_base = _tree(tmp_path, "exec-mode")
    executable = mode_worktree / "allowed.txt"
    executable.write_text("edit:alpha\n", encoding="utf-8")
    executable.chmod(0o755)
    _git(mode_worktree, ["add", "allowed.txt"])
    _git(mode_worktree, ["update-index", "--chmod=+x", "allowed.txt"])
    executable_report = inspect_diff(mode_root, mode_worktree, ALLOWLIST, base_sha=mode_base)
    assert executable_report.ok is False
    assert "allowed.txt" in executable_report.denied


def _git(worktree: Path, args: list[str]) -> None:
    completed = subprocess.run(
        ["git", "-C", str(worktree), *args],
        text=True,
        capture_output=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr


@pytest.mark.contract
def test_loaded_registry_keeps_the_required_command_separate(
    tmp_path: Path, record_property: pytest.RecordProperty
) -> None:
    record_property("gate_case_id", "AOS-004-TC02")
    bundle = tmp_path / "bundle"
    bundle.mkdir()
    script = bundle / "required_check.py"
    script.write_text("raise SystemExit(0)\n", encoding="utf-8")
    registry = CommandRegistry.load(bundle, sys.executable)
    assert tuple(item.ref for item in registry.required()) == ("synthetic-required",)
    suite = registry.resolve("synthetic-test-suite")
    required = registry.resolve("synthetic-required")
    assert suite.script_sha256 == required.script_sha256


def test_git_commands_reject_push_and_hook_changes(record_property: pytest.RecordProperty) -> None:
    record_property("gate_case_id", "AOS-004-TC02")
    sha = "a" * 40
    allow_git(["git", "-C", "/tmp/repo", "-c", "core.hooksPath=/dev/null", "commit", "-m", "synthetic-base"])
    allow_git(["git", "-C", "/tmp/repo", "config", "core.hooksPath", "/dev/null"])
    allow_git(["git", "--git-dir", "/tmp/dest.git", "update-ref", "refs/heads/main", sha, sha])
    refused = (
        ["git", "push", "origin", "main"],
        ["git", "config", "--global", "core.hooksPath", "/tmp/hooks"],
        ["git", "-C", "/tmp/repo", "config", "core.hooksPath", "/tmp/hooks"],
        ["git", "-c", "core.hooksPath=/tmp/hooks", "commit", "-m", "synthetic-base"],
        ["git", "commit", "-m", "synthetic-base"],
        ["git", "-C", "/tmp/../outside", "rev-parse", "HEAD"],
    )
    for command in refused:
        with pytest.raises(ValueError, match="git command"):
            allow_git(command)


def test_false_pass_records_readme_path_and_exit_code(tmp_path: Path, record_property: pytest.RecordProperty) -> None:
    record_property("gate_case_id", "AOS-004-TC02")
    registry, runner, _candidate = _bundle(tmp_path)
    manifest = WorktreeManager().create(tmp_path / "readme", "attempt-readme", "alpha")
    adapter = MockWorkerAdapter(manifest, "false_readme", "alpha")
    adapter.start()
    claimed = adapter.collect()
    assert claimed.accepted is False
    assert claimed.stdout_sha256 == hashlib.sha256(b"tests pass\n").hexdigest()
    readme = Path(manifest.worktree) / "README.md"
    assert readme.read_text(encoding="utf-8") == "tests pass\n"
    contract = _contract(
        [
            _check(
                "AC-CMD",
                True,
                {
                    "type": "trusted-command-ref",
                    "command_ref": "exits-one",
                    "expected_exit_code": 0,
                    "timeout_seconds": 5,
                },
            ),
            _check(
                "AC-PATH",
                True,
                {
                    "type": "git-diff-path-check",
                    "allowed_paths": ["tests/**"],
                    "forbidden_paths": [".env*"],
                },
            ),
        ]
    )
    reports = evaluate_checks(
        contract,
        root=Path(manifest.root),
        worktree=Path(manifest.worktree),
        base_sha=manifest.base_sha,
        registry=registry,
        runner=runner,
        attempt_id="attempt-readme",
        candidate_sha256=hashlib.sha256(readme.read_bytes()).hexdigest(),
        candidate_path=readme,
    )
    path_report = next(item for item in reports if item.check_id == "AC-PATH")
    assert path_report.verdict == "FAIL"
    assert "README.md" in path_report.denied_paths
    assert path_report.exit_code == 1
    stored = json.loads(path_report.canonical_bytes())
    assert "README.md" in stored["denied_paths"]
    assert stored["exit_code"] == 1
    assert required_passed(reports) is False
