"""First-run owner CLI against disposable Postgres, without launching inference."""

import json
import stat

import psycopg
import pytest
from typer.testing import CliRunner

from panestria.cli.local_init import first_run_files
from panestria.cli.main import app
from panestria.config_local import LocalApplicationRejected, load_local_settings
from panestria.kernel.goals import Actor
from panestria.kernel.local_setup import offline_policy
from panestria.kernel.repositories.policy import current_policy
from panestria.kernel.uow import UnitOfWork


@pytest.fixture
def first_run(tmp_path, r1_database, monkeypatch):
    directory = tmp_path / "new private setup"
    cache = tmp_path / "public-models"
    cache.mkdir()
    (cache / "blobs").mkdir()
    (cache / "manifests").mkdir()
    monkeypatch.setenv("PANESTRIA_DATABASE_URL", r1_database)
    args = ["local", "init", "--directory", str(directory), "--model-cache", str(cache), "--offline-ask"]
    return directory, cache, args


def test_first_run_creates_private_stable_scope_and_prints_start_instructions(first_run, r1_database):
    directory, _, args = first_run
    result = CliRunner().invoke(app, args)
    assert result.exit_code == 0, result.output
    receipt = json.loads(result.output)
    assert receipt["status"] == "CONFIGURED" and receipt["replayed"] is False
    assert receipt["server_started"] is False
    config, token = load_local_settings(directory / "local.json")
    assert str(config.owner_id) == receipt["owner_id"] and str(config.project_id) == receipt["project_id"]
    assert receipt["next_steps"][0] == "panestria local serve --config '" + str(directory / "local.json") + "'"
    assert receipt["next_steps"][1].startswith("panestria tui --config ")
    assert token.get_secret_value() not in result.output and r1_database not in result.output
    assert not config.runtime_directory.exists()  # No model/service or fake qualification.
    assert stat.S_IMODE(directory.stat().st_mode) == 0o700
    files = {name: (directory / name).read_bytes() for name in ("local.json", "local.token")}
    assert all(stat.S_IMODE((directory / name).stat().st_mode) == 0o600 for name in files)
    retried = CliRunner().invoke(app, args)
    assert retried.exit_code == 0 and json.loads(retried.output)["replayed"] is True
    assert all((directory / name).read_bytes() == value for name, value in files.items())
    with psycopg.connect(r1_database) as c:
        actor = Actor(receipt["owner_id"], receipt["project_id"])
        assert current_policy(UnitOfWork(c), actor) == offline_policy(actor)
        assert c.execute("SELECT count(*) FROM panestria.goal WHERE project_id=%s", (actor.project_id,)).fetchone() == (
            0,
        )
        assert c.execute(
            "SELECT count(*) FROM panestria.local_project_setup WHERE project_id=%s", (actor.project_id,)
        ).fetchone() == (1,)


def test_database_failure_preserves_exact_scope_and_retry_uses_it(first_run, r1_database, monkeypatch):
    directory, _, args = first_run
    monkeypatch.setenv("PANESTRIA_DATABASE_URL", "postgresql://private-sentinel:private-sentinel@127.0.0.1:1/test")
    failed = CliRunner().invoke(app, args)
    assert failed.exit_code == 2 and json.loads(failed.output)["code"] == "database_unavailable"
    assert "private-sentinel" not in failed.output
    config = (directory / "local.json").read_bytes()
    token = (directory / "local.token").read_bytes()
    monkeypatch.setenv("PANESTRIA_DATABASE_URL", r1_database)
    resumed = CliRunner().invoke(app, args)
    assert resumed.exit_code == 0 and json.loads(resumed.output)["replayed"] is False
    assert (directory / "local.json").read_bytes() == config and (directory / "local.token").read_bytes() == token
    # A changed port cannot silently rewrite settings or scope.
    conflict = CliRunner().invoke(app, [*args, "--port", "8769"])
    assert conflict.exit_code == 2
    assert json.loads(conflict.output)["code"] == "local_initialization_configuration_conflict"
    assert (directory / "local.json").read_bytes() == config


def test_first_run_explicit_intent_private_directory_and_cache_required(first_run):
    directory, cache, args = first_run
    denied = CliRunner().invoke(app, args[:-1])
    assert denied.exit_code == 2 and not directory.exists()
    (cache / "PRIVATE_SENTINEL").write_text("private data")
    denied = CliRunner().invoke(app, args)
    assert denied.exit_code == 2 and not directory.exists() and "PRIVATE_SENTINEL" not in denied.output
    (cache / "PRIVATE_SENTINEL").unlink()
    directory.mkdir(mode=0o755)
    directory.chmod(0o755)
    denied = CliRunner().invoke(app, args)
    assert denied.exit_code == 2 and list(directory.iterdir()) == []
    directory.chmod(0o700)
    (directory / "PRIVATE_SENTINEL").write_text("keep me")
    denied = CliRunner().invoke(app, args)
    assert denied.exit_code == 2 and "PRIVATE_SENTINEL" not in denied.output
    assert (directory / "PRIVATE_SENTINEL").read_text() == "keep me" and not (directory / "local.json").exists()


def test_first_run_lock_and_missing_or_symlink_token_never_replace_identity(first_run, tmp_path):
    directory, cache, args = first_run
    with first_run_files(directory, cache, 8768):
        with pytest.raises(LocalApplicationRejected, match="^local_initialization_busy$"):
            with first_run_files(directory, cache, 8768):
                pytest.fail("Second initializer acquired a held lock")
    original = (directory / "local.json").read_bytes()
    target = tmp_path / "protected-token"
    (directory / "local.token").rename(target)
    missing = CliRunner().invoke(app, args)
    assert missing.exit_code == 2 and (directory / "local.json").read_bytes() == original
    (directory / "local.token").symlink_to(target)
    denied = CliRunner().invoke(app, args)
    assert denied.exit_code == 2 and (directory / "local.token").is_symlink()
    assert (directory / "local.json").read_bytes() == original and target.exists()
