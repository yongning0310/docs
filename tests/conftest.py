import os
from unittest.mock import patch

import psycopg
import pytest
from fastapi.testclient import TestClient
from pgvector.psycopg import register_vector
from psycopg.rows import dict_row

from app.database import init_db, serialize_row
from app.main import app
from app.database import get_db

TEST_DB_URL = os.environ.get(
    "REDLINE_TEST_DATABASE_URL",
    "postgresql://postgres:postgres@localhost:5433/redline_test",
)

SAMPLE_CONTENT = (
    "This Non-Disclosure Agreement (the 'Agreement') is entered into by and between "
    "Party A ('Disclosing Party') and Party B ('Receiving Party'). "
    "Party A agrees to disclose certain confidential information to Party B. "
    "Party B agrees not to disclose such information to any third party. "
    "This Agreement shall be governed by the laws of the State of Delaware."
)

SAMPLE_TITLE = "NDA Agreement"


@pytest.fixture(scope="session", autouse=True)
def setup_test_db():
    """Create the test database and schema once per session."""
    # Connect to default database to create the test database
    admin_url = TEST_DB_URL.rsplit("/", 1)[0] + "/postgres"
    with psycopg.connect(admin_url, autocommit=True) as conn:
        # Terminate existing connections to allow drop
        conn.execute(
            "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
            "WHERE datname = 'redline_test' AND pid <> pg_backend_pid()"
        )
        conn.execute("DROP DATABASE IF EXISTS redline_test")
        conn.execute("CREATE DATABASE redline_test")

    # Initialize schema
    with psycopg.connect(TEST_DB_URL) as conn:
        init_db(conn)

    yield

    # Cleanup: drop test database
    with psycopg.connect(admin_url, autocommit=True) as conn:
        conn.execute(
            "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
            "WHERE datname = 'redline_test' AND pid <> pg_backend_pid()"
        )
        conn.execute("DROP DATABASE IF EXISTS redline_test")


@pytest.fixture()
def client(setup_test_db):
    """Test client with an isolated database (tables truncated per test)."""
    # Truncate all tables between tests
    with psycopg.connect(TEST_DB_URL) as conn:
        conn.execute(
            "TRUNCATE documents, change_history, suggestions, suggestion_comments, chunk_embeddings CASCADE"
        )
        conn.commit()

    def _override_get_db():
        conn = psycopg.connect(TEST_DB_URL, row_factory=dict_row)
        register_vector(conn)
        try:
            yield conn
        finally:
            conn.close()

    app.dependency_overrides[get_db] = _override_get_db

    with patch("app.routers.documents.get_embedding", return_value=None), \
         patch("app.routers.documents.compute_chunk_embeddings", return_value=None), \
         patch("app.routers.search.get_embedding", return_value=None), \
         TestClient(app, raise_server_exceptions=False) as c:
        yield c

    app.dependency_overrides.clear()


@pytest.fixture()
def sample_doc(client):
    """Create and return a sample document."""
    resp = client.post("/documents", json={"title": SAMPLE_TITLE, "content": SAMPLE_CONTENT})
    assert resp.status_code == 201
    return resp.json()


@pytest.fixture()
def frozen_doc(client):
    """Create a document and freeze it for redlining."""
    resp = client.post("/documents", json={"title": SAMPLE_TITLE, "content": SAMPLE_CONTENT})
    assert resp.status_code == 201
    doc = resp.json()
    resp = client.post(f"/documents/{doc['id']}/freeze")
    assert resp.status_code == 200
    return resp.json()


@pytest.fixture()
def suggestion(client, frozen_doc):
    """Create a suggestion on a frozen document."""
    resp = client.post(
        f"/documents/{frozen_doc['id']}/suggestions",
        json={
            "original_text": "Party A",
            "replacement_text": "Acme Corp",
            "position": SAMPLE_CONTENT.index("Party A"),
            "author": "alice",
        },
    )
    assert resp.status_code == 201
    return resp.json()
