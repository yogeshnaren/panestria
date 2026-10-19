"""Expected current schema comes from the source migration graph, not an old copied revision."""

from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory


def current_schema_revision() -> str:
    config = Config(str(Path(__file__).resolve().parents[1] / "migrations/alembic.ini"))
    revision = ScriptDirectory.from_config(config).get_current_head()
    if revision is None:
        raise AssertionError("single_current_schema_revision_required")
    return revision
