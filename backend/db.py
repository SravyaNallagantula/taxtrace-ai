"""PostgreSQL connection for the original packet and the separate review log."""
from __future__ import annotations

import os
from functools import lru_cache

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

DEFAULT_URL = "postgresql+psycopg://taxtrace:taxtrace@localhost:5434/taxtrace"

IMMUTABLE_TABLES = (
    "packet",
    "packet_sections",
    "documents",
    "document_pages",
    "extracted_values",
    "return_versions",
    "version_documents",
    "return_lines",
    "return_line_sources",
    "return_line_inputs",
    "diagnostics",
    "timeline_events",
    "questionnaire_answers",
    "client_messages",
    "call_notes",
    "household_people",
    "staff",
)


def database_url() -> str:
    return os.environ.get("TAXTRACE_DATABASE_URL", DEFAULT_URL)


@lru_cache(maxsize=1)
def get_engine():
    return create_engine(database_url(), pool_pre_ping=True)


@lru_cache(maxsize=1)
def get_sessionmaker():
    return sessionmaker(bind=get_engine(), expire_on_commit=False)


def session() -> Session:
    return get_sessionmaker()()


def install_immutability_triggers(db: Session) -> None:
    """Reject UPDATE and DELETE on original packet tables.

    The import is allowed to INSERT. After that, a correction belongs in the
    review tables, not in these rows.
    """
    db.execute(text("""
        CREATE OR REPLACE FUNCTION taxtrace_reject_packet_change()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
          RAISE EXCEPTION 'original packet rows are immutable';
        END;
        $$;
    """))
    for table in IMMUTABLE_TABLES:
        db.execute(text(f"DROP TRIGGER IF EXISTS {table}_immutable ON {table}"))
        db.execute(text(f"""
            CREATE TRIGGER {table}_immutable
            BEFORE UPDATE OR DELETE ON {table}
            FOR EACH ROW
            EXECUTE FUNCTION taxtrace_reject_packet_change()
        """))
    db.commit()
