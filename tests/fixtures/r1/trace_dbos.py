"""Real DBOS trace transport with export constructors denied and destinations empty."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import sqlalchemy as sa
from dbos import DBOS, DBOSClient
from opentelemetry.context import Context
from opentelemetry.exporter.otlp.proto.http import _log_exporter, trace_exporter

from panestria.execution.admission import DurableAdmission, SqlUnitOfWork
from panestria.execution.dbos_runtime import QUEUE_NAME, WORKFLOW_NAME, sqlalchemy_url
from panestria.kernel.goals import Actor
from panestria.telemetry.tracing import Telemetry, current_trace_id, metadata_span


def deny_exporter(*args: object, **kwargs: object) -> None:
    raise RuntimeError("network_exporter_initialization_denied")


# Fail closed if DBOS ever tries to construct an exporter. Span creation and
# PostgreSQL transport remain real; exporter creation would fail the test.
trace_exporter.OTLPSpanExporter = deny_exporter
_log_exporter.OTLPLogExporter = deny_exporter


ids = json.loads(os.environ["PANESTRIA_SYNTHETIC_TRACE_IDS"])
DATABASE_ENDPOINT = ("127.0.0.1", int(ids["dsn"].rsplit(":", 1)[1].split("/", 1)[0]))


def restrict_python_connections(event: str, arguments: tuple[object, ...]) -> None:
    if event == "socket.connect" and arguments[1] != DATABASE_ENDPOINT:
        raise RuntimeError("non_database_network_connection_denied")


sys.addaudithook(restrict_python_connections)
telemetry = Telemetry()
telemetry.install_global()
assert telemetry.processor.sink is None
url = sqlalchemy_url(ids["dsn"])
DBOS(
    config={
        "name": "panestria",
        "system_database_url": url,
        "enable_otlp": True,
        "otlp_traces_endpoints": [],
        "otlp_logs_endpoints": [],
        "log_level": "ERROR",
        "otel_attribute_format": "semconv",
    }
)


@DBOS.step(name="trace_adapter")
def adapter(task_id: str) -> str | None:
    with metadata_span("worker.adapter", **{"panestria.task_id": task_id, "panestria.privacy_label": "RESTRICTED"}):
        return current_trace_id()


@DBOS.step(name="trace_verifier")
def verifier(task_id: str) -> str | None:
    with metadata_span("verifier.run", **{"panestria.task_id": task_id, "panestria.privacy_label": "RESTRICTED"}):
        return current_trace_id()


@DBOS.workflow(name=WORKFLOW_NAME)
def workflow(task_id: str, contract_sha256: str, attempt_number: int) -> tuple[str | None, str | None]:
    return adapter(task_id), verifier(task_id)


DBOS.launch()
engine = sa.create_engine(url)
client = DBOSClient(system_database_url=url, application_name="panestria", use_listen_notify=False)
client.register_queue(QUEUE_NAME, application_name="panestria")
try:
    with telemetry.tracer.start_as_current_span("api.request", context=Context()) as parent:
        parent_id = format(parent.get_span_context().trace_id, "032x")
        with engine.begin() as connection:
            DurableAdmission(client).submit(
                SqlUnitOfWork(connection),
                Actor(ids["owner"], ids["project"]),
                ids["task"],
                ids["workflow"],
                attempt_id=ids["attempt"],
                idempotency_key="synthetic-trace-enqueue",
                contract_sha256="ab" * 32,
            )
    joined = client.retrieve_workflow(ids["workflow"]).get_result()
    assert joined == (parent_id, parent_id)
    records = telemetry.processor.snapshot()
    assert {r["trace_id"] for r in records} == {parent_id}
    assert {"api.request", "worker.adapter", "verifier.run", "dbos.operation"} <= {r["name"] for r in records}
    Path(os.environ["PANESTRIA_SYNTHETIC_TRACE_REPORT"]).write_text(
        json.dumps({"trace_id": parent_id, "spans": records})
    )
finally:
    client.destroy()
    engine.dispose()
    DBOS.destroy(destroy_registry=True, workflow_completion_timeout_sec=0)
    telemetry.shutdown()
