"""Private path names are compared as a permissive filesystem would resolve them."""

import pytest

from panestria.contracts.private_paths import folded_name
from panestria.sandbox.egress import _public_unicast
from panestria.sandbox.profiles import SandboxProfile, SandboxRejected
from panestria.sandbox.runner import DockerSandbox
from panestria.verification.git_snapshot import SnapshotRejected, _safe_path

FULLWIDTH_SECRETS = "\uff53\uff45\uff43\uff52\uff45\uff54\uff53"


@pytest.mark.parametrize(
    ("name", "folded"),
    [(".ENV.", ".env"), (".Git", ".git"), (FULLWIDTH_SECRETS, "secrets"), (".ssh. ", ".ssh"), ("src", "src")],
)
def test_folded_name(name, folded):
    assert folded_name(name) == folded


@pytest.mark.parametrize(
    "path",
    [
        ".Git/config",
        "a/.GIT/hooks/pre-commit",
        ".ENV",
        ".Env.local",
        "SECRETS/token.txt",
        f"{FULLWIDTH_SECRETS}/token.txt",
        ".ssh./id_ed25519",
        ".AWS/credentials",
        ".Claude/settings.json",
        "docs/.Mcp.JSON",
        ".mcp.json.",
    ],
)
def test_snapshot_rejects_private_names_in_any_spelling(path):
    with pytest.raises(SnapshotRejected, match="unsafe_candidate_path"):
        _safe_path(path.encode())


@pytest.mark.parametrize(
    "path", ["src/secrets_util.py", "docs/Secretsauce.md", "docs/environment.md", "src/git_tools.py", "a/.github/x"]
)
def test_snapshot_still_accepts_ordinary_names(path):
    assert _safe_path(path.encode()) == path


@pytest.mark.parametrize("name", [".ENV", ".Env.production", "SECRETS", ".SSH", ".aws.", ".Credentials.JSON"])
def test_sandbox_workspace_scan_rejects_private_names_in_any_spelling(tmp_path, name):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / name).write_text("synthetic")
    with pytest.raises(SandboxRejected, match="private_workspace_path"):
        DockerSandbox(tmp_path).run(workspace, ("/usr/local/bin/python", "-c", "pass"), SandboxProfile())


@pytest.mark.parametrize("address", ["192.88.99.1", "192.88.99.255"])
def test_deprecated_6to4_relay_anycast_is_not_a_public_destination(address):
    assert _public_unicast(address) is None
