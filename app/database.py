from __future__ import annotations

from datetime import datetime
from typing import Generator

import psycopg
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool
from pgvector.psycopg import register_vector

from app.config import settings

_CREATE_EXTENSION = "CREATE EXTENSION IF NOT EXISTS vector"

_CREATE_TABLES = [
    """CREATE TABLE IF NOT EXISTS documents (
        id TEXT PRIMARY KEY,
        title TEXT NOT NULL,
        content TEXT NOT NULL,
        version INTEGER NOT NULL DEFAULT 1,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        frozen_at TIMESTAMPTZ,
        search_vector TSVECTOR,
        embedding vector(768)
    )""",
    "CREATE INDEX IF NOT EXISTS idx_documents_search ON documents USING GIN (search_vector)",
    "CREATE INDEX IF NOT EXISTS idx_documents_embedding ON documents USING hnsw (embedding vector_cosine_ops)",
    """CREATE TABLE IF NOT EXISTS change_history (
        id TEXT PRIMARY KEY,
        document_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
        version INTEGER NOT NULL,
        changes_json TEXT NOT NULL,
        summary TEXT,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )""",
    "CREATE INDEX IF NOT EXISTS idx_change_history_doc ON change_history(document_id)",
    """CREATE TABLE IF NOT EXISTS suggestions (
        id TEXT PRIMARY KEY,
        document_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
        original_text TEXT NOT NULL,
        replacement_text TEXT NOT NULL,
        position INTEGER NOT NULL,
        author TEXT NOT NULL DEFAULT 'anonymous',
        status TEXT NOT NULL DEFAULT 'pending',
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        resolved_at TIMESTAMPTZ,
        resolved_by TEXT
    )""",
    "CREATE INDEX IF NOT EXISTS idx_suggestions_doc ON suggestions(document_id)",
    """CREATE TABLE IF NOT EXISTS suggestion_comments (
        id TEXT PRIMARY KEY,
        suggestion_id TEXT NOT NULL REFERENCES suggestions(id) ON DELETE CASCADE,
        author TEXT NOT NULL DEFAULT 'User',
        content TEXT NOT NULL,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )""",
    "CREATE INDEX IF NOT EXISTS idx_comments_suggestion ON suggestion_comments(suggestion_id)",
    """CREATE TABLE IF NOT EXISTS chunk_embeddings (
        document_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
        chunk_index INTEGER NOT NULL,
        chunk_text TEXT NOT NULL,
        position INTEGER NOT NULL,
        embedding vector(768) NOT NULL,
        model TEXT NOT NULL,
        PRIMARY KEY (document_id, chunk_index)
    )""",
    "CREATE INDEX IF NOT EXISTS idx_chunk_embeddings_vector ON chunk_embeddings USING hnsw (embedding vector_cosine_ops)",
]

_CREATE_TRIGGER_FUNCTION = """
CREATE OR REPLACE FUNCTION update_search_vector() RETURNS trigger AS $$
BEGIN
    NEW.search_vector :=
        setweight(to_tsvector('english', coalesce(NEW.title, '')), 'A') ||
        setweight(to_tsvector('english', coalesce(regexp_replace(NEW.content, '<[^>]+>', ' ', 'g'), '')), 'B');
    RETURN NEW;
END;
$$ LANGUAGE plpgsql
"""

_CREATE_TRIGGER = """
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_trigger WHERE tgname = 'trg_documents_search_vector'
    ) THEN
        CREATE TRIGGER trg_documents_search_vector
            BEFORE INSERT OR UPDATE OF title, content ON documents
            FOR EACH ROW
            EXECUTE FUNCTION update_search_vector();
    END IF;
END;
$$
"""

_pool: ConnectionPool | None = None


def init_db(conn: psycopg.Connection | None = None) -> None:
    """Create extensions, tables, indexes, and triggers."""
    if conn is None:
        with psycopg.connect(settings.database_url) as c:
            c.execute(_CREATE_EXTENSION)
            for stmt in _CREATE_TABLES:
                c.execute(stmt)
            c.execute(_CREATE_TRIGGER_FUNCTION)
            c.execute(_CREATE_TRIGGER)
            c.commit()
    else:
        conn.execute(_CREATE_EXTENSION)
        for stmt in _CREATE_TABLES:
            conn.execute(stmt)
        conn.execute(_CREATE_TRIGGER_FUNCTION)
        conn.execute(_CREATE_TRIGGER)
        conn.commit()


def init_pool(database_url: str | None = None) -> None:
    """Initialize the connection pool."""
    global _pool
    url = database_url or settings.database_url
    _pool = ConnectionPool(
        conninfo=url,
        kwargs={"row_factory": dict_row},
        configure=_configure_connection,
        min_size=2,
        max_size=10,
    )


def _configure_connection(conn: psycopg.Connection) -> None:
    register_vector(conn)


def close_pool() -> None:
    """Close the connection pool."""
    global _pool
    if _pool:
        _pool.close()
        _pool = None


def get_db() -> Generator[psycopg.Connection, None, None]:
    """FastAPI dependency: get a connection from the pool."""
    assert _pool is not None, "Connection pool not initialized"
    with _pool.connection() as conn:
        yield conn


# Column list for document queries (excludes search_vector and embedding)
DOC_COLUMNS = "id, title, content, version, created_at, updated_at, frozen_at"


def serialize_row(row: dict) -> dict:
    """Convert datetime values to ISO strings for Pydantic models."""
    result = dict(row)
    for key, val in result.items():
        if isinstance(val, datetime):
            result[key] = val.isoformat()
    return result
