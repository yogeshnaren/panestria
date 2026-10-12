"""DBOS system schema in the same PostgreSQL database as the panestria schema."""

from __future__ import annotations

import sqlalchemy as sa
from dbos import DBOS, DBOSClient, DBOSConfig
from sqlalchemy.engine import make_url

DBOS_SCHEMA = "dbos"
APPLICATION_NAME = "panestria"
QUEUE_NAME = "panestria-synthetic"
WORKFLOW_NAME = "run_task_workflow"
ADMISSION_LOCK = (106972, 1)


def sqlalchemy_url(database_url: str) -> str:
    """DBOS and SQLAlchemy need the psycopg v3 driver, not a bare postgresql:// URL."""
    return make_url(database_url).set(drivername="postgresql+psycopg").render_as_string(hide_password=False)


def probe_launch(database_url: str) -> str:
    """Migrate the DBOS schema, launch, and stop. Returns the admission isolation level."""
    url = sqlalchemy_url(database_url)
    DBOS.migrate(url, schema=DBOS_SCHEMA)
    config: DBOSConfig = {
        "name": APPLICATION_NAME,
        "system_database_url": url,
        "dbos_system_schema": DBOS_SCHEMA,
        "enable_otlp": False,
        "log_level": "ERROR",
        "use_listen_notify": True,
    }
    DBOS(config=config)
    DBOS.launch()
    engine = sa.create_engine(url, isolation_level="READ COMMITTED")
    try:
        with engine.connect() as connection:
            isolation = connection.execute(sa.text("SHOW transaction_isolation")).scalar_one()
            present = connection.execute(
                sa.text("SELECT 1 FROM information_schema.schemata WHERE schema_name = :schema"),
                {"schema": DBOS_SCHEMA},
            ).fetchone()
        if present is None:
            raise RuntimeError("dbos schema missing after launch")
        return str(isolation)
    finally:
        engine.dispose()
        DBOS.destroy(destroy_registry=True, workflow_completion_timeout_sec=0)


def open_client(database_url: str) -> tuple[sa.Engine, DBOSClient]:
    """Open a client against an already migrated system schema and register the synthetic queue."""
    url = sqlalchemy_url(database_url)
    DBOS.migrate(url, schema=DBOS_SCHEMA)
    engine = sa.create_engine(url, isolation_level="READ COMMITTED")
    client = DBOSClient(
        system_database_url=url,
        dbos_system_schema=DBOS_SCHEMA,
        application_name=APPLICATION_NAME,
        use_listen_notify=False,
    )
    client.register_queue(QUEUE_NAME, application_name=APPLICATION_NAME)
    return engine, client
