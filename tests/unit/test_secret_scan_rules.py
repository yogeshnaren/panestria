"""Every secret rule detects a generated sentinel; placeholders and test tokens pass.

Sentinels are generated at runtime from split prefixes so this file never
contains secret-shaped text itself.
"""

from __future__ import annotations

import importlib.util
import random
import string
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
_SPEC = importlib.util.spec_from_file_location("secret_scan", ROOT / "tools/secret_scan.py")
assert _SPEC and _SPEC.loader
secret_scan = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(secret_scan)

_RANDOM = random.Random(20261028)
_ALNUM = string.ascii_letters + string.digits


def _body(length: int, alphabet: str = _ALNUM) -> str:
    return "".join(_RANDOM.choice(alphabet) for _ in range(length))


SENTINELS = {
    "private-key": "-----BEGIN " + "OPENSSH PRIVATE KEY-----\n" + _body(64),
    "aws-access-key-id": "AK" + "IA" + _body(16, string.ascii_uppercase + string.digits),
    "anthropic-api-key": "sk-" + "ant-api03-" + _body(40),
    "openai-api-key": "sk-" + "proj-" + _body(40),
    "github-token": "gh" + "p_" + _body(36),
    "slack-token": "xo" + "xb-" + _body(24),
    "google-api-key": "AI" + "za" + _body(35),
    "jwt": "ey" + "J" + _body(20) + ".ey" + "J" + _body(20) + "." + _body(20),
    "high-entropy-assignment": "SERVICE_API_KEY = '" + _body(40) + "'",
}


@pytest.mark.parametrize("rule", sorted(SENTINELS))
def test_each_rule_detects_its_sentinel_without_printing_it(rule: str, tmp_path: Path) -> None:
    target = tmp_path / "leak.txt"
    target.write_text(f"prefix {SENTINELS[rule]} suffix\n", encoding="utf-8")
    assert rule in secret_scan.rules_matching(target.read_text())
    completed = subprocess.run(
        [sys.executable, str(ROOT / "tools/secret_scan.py"), str(target)], capture_output=True, text=True
    )
    assert completed.returncode == 1 and f": {rule}" in completed.stdout
    assert SENTINELS[rule].splitlines()[-1] not in completed.stdout + completed.stderr


@pytest.mark.parametrize(
    "text",
    [
        "postgresql://panestria_synthetic:placeholder-not-a-secret@127.0.0.1:55432/db",
        "PANESTRIA_TOKEN=test-only-cli-token-at-least-16",
        "token = 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa'",
        "sha256 = 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855'",
        "sk-" + "short",
    ],
)
def test_placeholders_low_entropy_values_and_digests_are_not_findings(text: str) -> None:
    assert secret_scan.rules_matching(text) == []


def test_allowlist_entries_are_exact_with_reasons() -> None:
    rules = {name for name, _ in secret_scan.RULES} | {"high-entropy-assignment"}
    for entry in secret_scan._entries():
        assert entry["reason"] and "*" not in entry["path"] and entry["rule"] in rules
        if "commit" in entry:
            assert len(entry["commit"]) == 40
        else:
            assert (ROOT / entry["path"]).is_file()


def test_commit_scoped_entries_never_excuse_the_current_tree() -> None:
    history_only = {(e["path"], e["rule"]) for e in secret_scan._entries() if "commit" in e}
    assert history_only and not history_only & secret_scan.allowed()
