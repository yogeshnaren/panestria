"""Create a fresh PUBLIC toy Build scope; never contact a provider or database."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
from pathlib import Path
from uuid import uuid4

from panestria.config_build import load_build_settings
from panestria.config_local import read_private


def create(directory: Path, qualification: Path) -> dict[str, str]:
    if not directory.is_absolute() or directory.resolve() != directory or directory.exists():
        raise ValueError("fresh_absolute_example_directory_required")
    result = json.loads(read_private(qualification / "latest.json", 4096))
    if result["status"] != "PASS" or result["scope"] != "PUBLIC_BASH_RUNTIME_ONLY":
        raise ValueError("qualified_public_runtime_required")
    # Deliberately leave partial output intact on failure; never reset a source,
    # replace an existing example directory, or discard diagnostic evidence.
    directory.mkdir(mode=0o700)
    root, source = directory / "runtime", directory / "source"
    root.mkdir(mode=0o700)
    source.mkdir(mode=0o700)
    reviewed = root / "reviewed"
    reviewed.mkdir(mode=0o700)
    script = reviewed / "required.py"
    script.write_text(
        "from pathlib import Path\n"
        "assert Path('/workspace/calculator.py').read_text() == 'value = 43\\n'\n"
        "assert Path('/workspace/notes/build.txt').read_text() == 'bounded Bash build\\n'\n"
    )
    script.chmod(0o600)
    owner, project, goal = (str(uuid4()) for _ in range(3))
    config = {
        "schema_version": 1,
        "owner_id": owner,
        "project_id": project,
        "root": str(root),
        "certificates": str(qualification / "certificates"),
        "certificate_sha256": result["certificate_sha256"],
        "native_binary": str(Path.home() / ".local/share/claude/versions/2.1.273"),
        "native_config": str(Path.home() / ".panestria-native-claude"),
        "skills_archive": str(
            Path(__file__).resolve().parents[1] / "docs/specification/attachments/agentos-skills-v0.1.0.zip"
        ),
        "checks": [
            {"ref": "unit-check", "script": "required.py", "sha256": hashlib.sha256(script.read_bytes()).hexdigest()}
        ],
    }
    cfg = directory / "build.json"
    cfg.write_text(json.dumps(config, indent=2) + "\n")
    cfg.chmod(0o600)
    settings = load_build_settings(cfg)
    environment = {
        "PATH": "/usr/bin:/bin",
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_GLOBAL": "/dev/null",
        "GIT_CONFIG_SYSTEM": "/dev/null",
        "GIT_ALLOW_PROTOCOL": "file",
        "GIT_TERMINAL_PROMPT": "0",
    }

    def git(*args: str) -> str:
        return subprocess.check_output(
            ["git", "-c", "core.hooksPath=/dev/null", "-c", "core.fsmonitor=false", "-C", str(source), *args],
            env=environment,
            text=True,
            timeout=10,
            stderr=subprocess.DEVNULL,
        ).strip()

    git("init", "-b", "main")
    git("config", "user.name", "Panestria PUBLIC example")
    git("config", "user.email", "public-example@panestria.invalid")
    (source / "calculator.py").write_text("value = 42\n")
    git("add", "calculator.py")
    git("commit", "-m", "Public synthetic baseline")
    settings.repository.parent.mkdir(parents=True, mode=0o700)
    git("clone", "--bare", "--no-local", "--no-hardlinks", ".", str(settings.repository))
    document = {
        "schema_version": 1,
        "goal_id": goal,
        "owner_id": owner,
        "project_id": project,
        "contract_version": 1,
        "intent": "Change calculator.py to exactly 'value = 43\\n' and create notes/build.txt with exactly "
        "'bounded Bash build\\n'. Change no other files.",
        "privacy_class": "PUBLIC",
        "trust_profile_id": "PERSONAL_SANDBOX",
        "autonomy_profile_ref": "REPLACE_WITH_CONFIRMED_POLICY_REF",
        "constraints": {
            "allowed_paths": ["calculator.py", "notes/**"],
            "forbidden_paths": [".git/**", ".env*", "secrets/**"],
            "permitted_capabilities": ["scoped-bash"],
            "cloud_egress": "allow",
        },
        "budget": {"max_attempts_per_task": 1, "max_wall_seconds": 90, "max_api_usd": "0"},
        "acceptance": [
            {
                "id": "tests",
                "description": "Independent source and note check",
                "required": True,
                "evidence": {"required": True, "kind": "registered-check-report"},
                "verifier": {
                    "type": "trusted-command-ref",
                    "command_ref": "unit-check",
                    "expected_exit_code": 0,
                    "timeout_seconds": 10,
                },
            },
            {
                "id": "paths",
                "description": "Only scoped paths change",
                "required": True,
                "evidence": {"required": True, "kind": "git-diff-path-check-report"},
                "verifier": {
                    "type": "git-diff-path-check",
                    "allowed_paths": ["calculator.py", "notes/**"],
                    "forbidden_paths": [".git/**"],
                },
            },
            {
                "id": "merge",
                "description": "Exact owner review",
                "required": True,
                "evidence": {"required": True, "kind": "policy-decision-report"},
                "verifier": {"type": "policy-decision", "action": "protected-merge", "expected": "approval-required"},
            },
        ],
        "non_goals": [],
    }
    contract = directory / "contract.json"
    contract.write_text(json.dumps(document, indent=2) + "\n")
    contract.chmod(0o600)
    return {
        "config": str(cfg),
        "contract": str(contract),
        "goal_id": goal,
        "expected_base": git("rev-parse", "HEAD"),
        "scope": "PUBLIC_SYNTHETIC_EXAMPLE_ONLY",
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", required=True, type=Path)
    parser.add_argument("--qualification-directory", required=True, type=Path)
    args = parser.parse_args()
    os.umask(0o077)
    try:
        print(json.dumps(create(args.directory, args.qualification_directory), sort_keys=True))
    except Exception:
        parser.exit(1, "public_example_unavailable_existing_files_preserved\n")
