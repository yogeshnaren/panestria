"""Keep restricted memory plaintext out of PostgreSQL full-text search (MVP-X07)."""

from alembic import op

revision = "0041_memory_restricted_fts"
down_revision = "0040_phone_devices"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Serialize with old and new writers across the backfill/trigger boundary.
    op.execute("LOCK TABLE panestria.memory_source,panestria.memory_revision IN SHARE ROW EXCLUSIVE MODE")
    op.execute("DROP INDEX panestria.ix_memory_fts")
    op.execute("ALTER TABLE panestria.memory_revision ALTER COLUMN search_document DROP EXPRESSION")
    # Remove existing restricted lexemes. History stays immutable to applications;
    # only this migration's own transaction may clear the derived index column.
    op.execute("ALTER TABLE panestria.memory_revision DISABLE TRIGGER immutable_memory")
    op.execute("""UPDATE panestria.memory_revision r SET search_document=NULL
        FROM panestria.memory_classification c
        WHERE c.source_id=r.source_id AND c.effective_label='RESTRICTED'""")
    op.execute("ALTER TABLE panestria.memory_revision ENABLE TRIGGER immutable_memory")
    op.execute("""CREATE FUNCTION panestria.memory_search_document() RETURNS trigger LANGUAGE plpgsql AS $fn$
        BEGIN
            NEW.search_document := CASE WHEN EXISTS (
                SELECT 1 FROM panestria.memory_classification c
                WHERE c.source_id=NEW.source_id AND c.effective_label<>'RESTRICTED'
            ) THEN to_tsvector('english',NEW.body) ELSE NULL END;
            RETURN NEW;
        END; $fn$""")
    op.execute("""CREATE TRIGGER memory_search_document BEFORE INSERT ON panestria.memory_revision
        FOR EACH ROW EXECUTE FUNCTION panestria.memory_search_document()""")
    op.execute(
        "CREATE INDEX ix_memory_fts ON panestria.memory_revision USING gin(search_document)"
        " WHERE search_document IS NOT NULL"
    )


def downgrade() -> None:
    op.execute("LOCK TABLE panestria.memory_source,panestria.memory_revision IN ACCESS EXCLUSIVE MODE")
    restricted = (
        op.get_bind()
        .exec_driver_sql(
            "SELECT EXISTS(SELECT 1 FROM panestria.memory_classification WHERE effective_label='RESTRICTED')"
        )
        .scalar()
    )
    if restricted:
        raise RuntimeError("restricted memory exists; downgrade would index its plaintext")
    op.execute("DROP INDEX panestria.ix_memory_fts")
    op.execute("DROP TRIGGER memory_search_document ON panestria.memory_revision")
    op.execute("DROP FUNCTION panestria.memory_search_document()")
    op.execute(
        "ALTER TABLE panestria.memory_revision DROP COLUMN search_document,"
        " ADD COLUMN search_document tsvector GENERATED ALWAYS AS (to_tsvector('english',body)) STORED"
    )
    op.execute("CREATE INDEX ix_memory_fts ON panestria.memory_revision USING gin(search_document)")
