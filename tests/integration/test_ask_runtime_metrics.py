"""Real scoped PG/HTTP/CLI capture, synthetic keys/model/capacity fixtures."""

import json
from uuid import uuid4

import psycopg
from test_profile_ask_terminal import profile_terminal as profile_terminal  # noqa: F401
from test_profile_style_terminal import style_server as style_server  # noqa: F401
from test_profile_vault import profile as profile  # noqa: F401
from typer.testing import CliRunner

from panestria.cli.main import app
from panestria.cli.profile_ask import ProfileAskClient
from panestria.telemetry.performance import latest_snapshot


def test_capture_reads_one_protected_receipt_without_more_model_calls_or_plaintext(profile_terminal, tmp_path):  # noqa: F811
    f, selection, state = profile_terminal
    request_id = str(uuid4())
    client = ProfileAskClient(f.path, selection)
    original = client.ask(request_id, "METRICS_PRIVATE_QUESTION_SENTINEL")
    receipt = client.receipt(request_id)
    assert original["state"] == "COMPLETED" and len(state.calls) == 1
    directory = tmp_path / "metrics"
    args = [
        "metrics",
        "capture-ask",
        "--config",
        str(f.path),
        "--request-id",
        request_id,
        "--directory",
        str(directory),
    ]
    result = CliRunner().invoke(app, args)
    assert result.exit_code == 0, result.output
    snapshot = latest_snapshot(directory)
    assert {m.scope for m in snapshot.observations} == {"runtime_profile_ask"}
    measured = {m.metric: m.value for m in snapshot.observations}
    assert measured["latency.ask_generation"] == receipt["usage"]["elapsed_seconds"]
    assert measured["usage.ask_output_tokens"] == receipt["usage"]["output_tokens"]
    assert measured["quality.correct_fraction"] is None and len(state.calls) == 1
    forbidden = ("METRICS_PRIVATE_QUESTION_SENTINEL", "SYNTHETIC_PROFILE_ONLY_ANSWER", f.token, f.dsn)
    for path in directory.rglob("*"):
        if path.is_file():
            assert all(v not in path.read_text() for v in forbidden)
    assert client.receipt(request_id) == receipt
    with psycopg.connect(f.dsn) as c:
        assert c.execute("SELECT state FROM panestria.ask_request WHERE id=%s", (request_id,)).fetchone() == (
            "COMPLETED",
        )
    # Wrong project scope refuses before any new history/model/canonical mutation.
    f.path.write_text(f.config.model_copy(update={"project_id": uuid4()}).model_dump_json())
    denied = tmp_path / "denied"
    result = CliRunner().invoke(app, [*args[:-1], str(denied)])
    assert result.exit_code == 1 and "UNAVAILABLE" in result.output
    assert not denied.exists() and len(state.calls) == 1
    f.path.write_text(f.config.model_dump_json())
    # A full private history cannot affect the already completed Ask or start a retry.
    full = tmp_path / "full"
    full.mkdir(mode=0o700)
    with (full / "existing.bin").open("wb") as stream:
        stream.truncate(16 * 1024 * 1024)
    result = CliRunner().invoke(app, [*args[:-1], str(full)])
    assert result.exit_code == 1 and list((full / "sources").iterdir()) == []
    assert len(state.calls) == 1 and client.receipt(request_id) == receipt
    assert json.loads(result.output)["reason"] == "ask_receipt_or_private_metrics_invalid"
