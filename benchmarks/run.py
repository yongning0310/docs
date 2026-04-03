#!/usr/bin/env python3
"""
Performance benchmarks for Redline Service APIs.

Measures latency across workload scales using FastAPI TestClient (in-process,
no network overhead). Results written to benchmarks/results/results.json.

Usage:
    python benchmarks/run.py
"""
from __future__ import annotations

import json
import os
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import psycopg
from fastapi.testclient import TestClient
from pgvector.psycopg import register_vector
from psycopg.rows import dict_row

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.database import init_db, get_db
from app.main import app

DB_URL = os.environ.get(
    "REDLINE_PERF_DATABASE_URL",
    "postgresql://postgres:postgres@localhost:5433/redline_perf",
)
RESULTS_DIR = Path(__file__).parent / "results"
ITERATIONS = 3


# ── helpers ──────────────────────────────────────────────────────────────


def _setup_db():
    admin_url = DB_URL.rsplit("/", 1)[0] + "/postgres"
    with psycopg.connect(admin_url, autocommit=True) as conn:
        conn.execute(
            "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
            "WHERE datname = 'redline_perf' AND pid <> pg_backend_pid()"
        )
        conn.execute("DROP DATABASE IF EXISTS redline_perf")
        conn.execute("CREATE DATABASE redline_perf")
    with psycopg.connect(DB_URL) as conn:
        init_db(conn)


def _teardown_db():
    admin_url = DB_URL.rsplit("/", 1)[0] + "/postgres"
    with psycopg.connect(admin_url, autocommit=True) as conn:
        conn.execute(
            "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
            "WHERE datname = 'redline_perf' AND pid <> pg_backend_pid()"
        )
        conn.execute("DROP DATABASE IF EXISTS redline_perf")


def _truncate():
    with psycopg.connect(DB_URL) as conn:
        conn.execute(
            "TRUNCATE documents, change_history, suggestions, "
            "suggestion_comments, chunk_embeddings CASCADE"
        )
        conn.commit()


def _client():
    def override():
        conn = psycopg.connect(DB_URL, row_factory=dict_row)
        register_vector(conn)
        try:
            yield conn
        finally:
            conn.close()

    app.dependency_overrides[get_db] = override
    return TestClient(app, raise_server_exceptions=False)


def _content(size_kb: int) -> str:
    block = (
        "This Agreement shall be governed by and construed in accordance with the laws "
        "of the State of Delaware without regard to conflict of law principles. "
        "Party A shall indemnify and hold harmless Party B against any claims arising. "
        "Confidential information shall not be disclosed to any third party whatsoever. "
    )
    n = (size_kb * 1024) // len(block) + 1
    return (block * n)[: size_kb * 1024]


def _bulk_insert_docs(n: int):
    with psycopg.connect(DB_URL) as conn:
        with conn.cursor() as cur:
            cur.executemany(
                "INSERT INTO documents (id, title, content) VALUES (%s, %s, %s)",
                [
                    (
                        str(uuid.uuid4()),
                        f"Agreement {i}",
                        f"This is legal agreement number {i}. "
                        f"Party A and Party B agree to the terms of this contract. "
                        f"Confidential information shall be protected under Delaware law.",
                    )
                    for i in range(n)
                ],
            )
        conn.commit()


def _bulk_insert_history(doc_id: str, n: int):
    with psycopg.connect(DB_URL) as conn:
        with conn.cursor() as cur:
            cur.executemany(
                "INSERT INTO change_history (id, document_id, version, changes_json, summary) "
                "VALUES (%s, %s, %s, %s, %s)",
                [
                    (
                        str(uuid.uuid4()),
                        doc_id,
                        i + 1,
                        json.dumps([{"old": "x", "new": "y"}]),
                        f"Change {i}",
                    )
                    for i in range(n)
                ],
            )
        conn.commit()


def _bulk_insert_suggestions(doc_id: str, n: int):
    with psycopg.connect(DB_URL) as conn:
        with conn.cursor() as cur:
            cur.executemany(
                "INSERT INTO suggestions "
                "(id, document_id, original_text, replacement_text, position, author) "
                "VALUES (%s, %s, %s, %s, %s, %s)",
                [
                    (str(uuid.uuid4()), doc_id, "Party A", f"Company {i}", 0, f"user{i}")
                    for i in range(n)
                ],
            )
        conn.commit()


def _stats(workload, times: list[float]) -> dict:
    times.sort()
    return {
        "workload": workload,
        "median_ms": round(times[len(times) // 2], 2),
        "min_ms": round(times[0], 2),
        "max_ms": round(times[-1], 2),
    }


def _log(name: str, workload, unit: str, stats: dict):
    print(f"  {workload:>8} {unit:<14} →  {stats['median_ms']:>10.1f} ms")


# ── benchmarks ───────────────────────────────────────────────────────────


def bench_create_document(c):
    """POST /documents — scale by content size."""
    tiers = [1, 10, 100, 1_000, 10_000, 50_000, 100_000]
    results = []
    for kb in tiers:
        _truncate()
        content = _content(kb)
        times = []
        for _ in range(ITERATIONS):
            s = time.perf_counter()
            r = c.post("/documents", json={"title": "Perf", "content": content})
            times.append((time.perf_counter() - s) * 1000)
            assert r.status_code == 201, f"create failed: {r.text}"
        results.append(_stats(kb, times))
        _log("create_document", kb, "KB", results[-1])
    return results


def bench_get_document(c):
    """GET /documents/{id} — scale by content size."""
    tiers = [1, 10, 100, 1_000, 10_000, 50_000, 100_000]
    results = []
    for kb in tiers:
        _truncate()
        content = _content(kb)
        r = c.post("/documents", json={"title": "Perf", "content": content})
        doc_id = r.json()["id"]
        times = []
        for _ in range(ITERATIONS):
            s = time.perf_counter()
            r = c.get(f"/documents/{doc_id}")
            times.append((time.perf_counter() - s) * 1000)
            assert r.status_code == 200
        results.append(_stats(kb, times))
        _log("get_document", kb, "KB", results[-1])
    return results


def bench_list_documents(c):
    """GET /documents — scale by number of documents."""
    tiers = [10, 100, 1_000, 10_000, 50_000, 100_000]
    results = []
    for n in tiers:
        _truncate()
        _bulk_insert_docs(n)
        # API caps limit at 100, so we test with limit=100 against growing table
        # This isolates the COUNT(*) + ORDER BY cost from serialization
        times = []
        for _ in range(ITERATIONS):
            s = time.perf_counter()
            r = c.get("/documents?limit=100")
            times.append((time.perf_counter() - s) * 1000)
            assert r.status_code == 200
        results.append(_stats(n, times))
        _log("list_documents", n, "docs", results[-1])
    return results


def bench_update_content(c):
    """PUT /documents/{id}/content — scale by content size."""
    tiers = [1, 10, 100, 1_000, 10_000, 50_000, 100_000]
    results = []
    for kb in tiers:
        times = []
        content = _content(kb)
        for _ in range(ITERATIONS):
            _truncate()
            r = c.post("/documents", json={"title": "Perf", "content": "initial"})
            doc = r.json()
            s = time.perf_counter()
            r = c.put(
                f"/documents/{doc['id']}/content",
                json={"content": content, "version": doc["version"]},
            )
            times.append((time.perf_counter() - s) * 1000)
            assert r.status_code == 200, f"update failed: {r.text}"
        results.append(_stats(kb, times))
        _log("update_content", kb, "KB", results[-1])
    return results


def bench_redline(c):
    """PATCH /documents/{id} — scale by number of changes."""
    tiers = [1, 10, 100, 500, 1_000, 5_000, 10_000]
    results = []
    for n_changes in tiers:
        times = []
        for _ in range(ITERATIONS):
            _truncate()
            # Create doc with enough unique targets
            parts = [f"Section {i}: Party A agrees to terms." for i in range(n_changes)]
            content = "\n".join(parts)
            r = c.post("/documents", json={"title": "Perf", "content": content})
            doc = r.json()
            changes = [
                {
                    "target": {"text": f"Section {i}:", "occurrence": 1},
                    "replacement": f"Article {i}:",
                }
                for i in range(n_changes)
            ]
            s = time.perf_counter()
            r = c.patch(
                f"/documents/{doc['id']}",
                json={"version": doc["version"], "changes": changes},
            )
            times.append((time.perf_counter() - s) * 1000)
            assert r.status_code == 200, f"redline failed: {r.text}"
        results.append(_stats(n_changes, times))
        _log("redline", n_changes, "changes", results[-1])
    return results


def bench_search_global(c):
    """GET /search — scale by number of documents."""
    tiers = [10, 100, 1_000, 10_000, 50_000, 100_000]
    results = []
    for n in tiers:
        _truncate()
        _bulk_insert_docs(n)
        times = []
        for _ in range(ITERATIONS):
            s = time.perf_counter()
            r = c.get("/search", params={"q": "agreement"})
            times.append((time.perf_counter() - s) * 1000)
            assert r.status_code == 200
        results.append(_stats(n, times))
        _log("search_global", n, "docs", results[-1])
    return results


def bench_search_in_document(c):
    """GET /documents/{id}/search — scale by content size."""
    tiers = [1, 10, 100, 1_000, 10_000, 50_000, 100_000]
    results = []
    for kb in tiers:
        _truncate()
        content = _content(kb)
        r = c.post("/documents", json={"title": "Perf", "content": content})
        doc_id = r.json()["id"]
        times = []
        for _ in range(ITERATIONS):
            s = time.perf_counter()
            r = c.get(f"/documents/{doc_id}/search", params={"q": "indemnify"})
            times.append((time.perf_counter() - s) * 1000)
            assert r.status_code == 200
        results.append(_stats(kb, times))
        _log("search_in_document", kb, "KB", results[-1])
    return results


def bench_list_suggestions(c):
    """GET /documents/{id}/suggestions — scale by number of suggestions."""
    tiers = [10, 100, 500, 1_000, 5_000, 20_000, 50_000]
    results = []
    for n in tiers:
        _truncate()
        # Create frozen doc directly
        with psycopg.connect(DB_URL) as conn:
            with conn.cursor() as cur:
                doc_id = str(uuid.uuid4())
                cur.execute(
                    "INSERT INTO documents (id, title, content, frozen_at) "
                    "VALUES (%s, %s, %s, NOW())",
                    (doc_id, "Frozen Doc", "Party A and Party B agree to terms."),
                )
            conn.commit()
        _bulk_insert_suggestions(doc_id, n)
        times = []
        for _ in range(ITERATIONS):
            s = time.perf_counter()
            r = c.get(f"/documents/{doc_id}/suggestions")
            times.append((time.perf_counter() - s) * 1000)
            assert r.status_code == 200
        results.append(_stats(n, times))
        _log("list_suggestions", n, "suggestions", results[-1])
    return results


def bench_get_history(c):
    """GET /documents/{id}/history — scale by number of history entries."""
    tiers = [10, 100, 500, 1_000, 5_000, 20_000, 50_000]
    results = []
    for n in tiers:
        _truncate()
        r = c.post("/documents", json={"title": "Perf", "content": "Some content"})
        doc_id = r.json()["id"]
        _bulk_insert_history(doc_id, n)
        times = []
        for _ in range(ITERATIONS):
            s = time.perf_counter()
            r = c.get(f"/documents/{doc_id}/history")
            times.append((time.perf_counter() - s) * 1000)
            assert r.status_code == 200
        results.append(_stats(n, times))
        _log("get_history", n, "entries", results[-1])
    return results


# ── runner ───────────────────────────────────────────────────────────────

BENCHMARKS = [
    ("create_document", "POST /documents", "content_kb", bench_create_document),
    ("get_document", "GET /documents/{id}", "content_kb", bench_get_document),
    ("list_documents", "GET /documents", "num_documents", bench_list_documents),
    ("update_content", "PUT /documents/{id}/content", "content_kb", bench_update_content),
    ("redline", "PATCH /documents/{id}", "num_changes", bench_redline),
    ("search_global", "GET /search", "num_documents", bench_search_global),
    ("search_in_document", "GET /documents/{id}/search", "content_kb", bench_search_in_document),
    ("list_suggestions", "GET /documents/{id}/suggestions", "num_suggestions", bench_list_suggestions),
    ("get_history", "GET /documents/{id}/history", "num_entries", bench_get_history),
]


def main():
    print("Performance Benchmarks — Redline Service")
    print("=" * 50)
    print(f"Iterations per tier: {ITERATIONS}\n")

    print("Setting up perf database...")
    _setup_db()

    output = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "iterations": ITERATIONS,
        "benchmarks": [],
    }

    with patch("app.routers.documents.get_embedding", return_value=None), \
         patch("app.routers.documents.compute_chunk_embeddings", return_value=None), \
         patch("app.routers.search.get_embedding", return_value=None):
        with _client() as c:
            total = len(BENCHMARKS)
            for i, (name, desc, dim, fn) in enumerate(BENCHMARKS, 1):
                print(f"\n[{i}/{total}] {name} ({desc})")
                results = fn(c)
                output["benchmarks"].append(
                    {
                        "name": name,
                        "description": desc,
                        "dimension": dim,
                        "results": results,
                    }
                )

    app.dependency_overrides.clear()

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    out_path = RESULTS_DIR / "results.json"
    with open(out_path, "w") as f:
        json.dump(output, f, indent=2)
    print(f"\nResults written to {out_path}")

    _teardown_db()
    print("Done.")


if __name__ == "__main__":
    main()
