"""Document CRUD and redline endpoints."""

from __future__ import annotations

import difflib
import json
import uuid

import psycopg
from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import Response

from app.config import settings
from app.database import DOC_COLUMNS, get_db, serialize_row
from app.errors import DocumentFrozen, DocumentNotFound, VersionConflict
from app.models import (
    ContentUpdate,
    DocumentCreate,
    DocumentListResponse,
    DocumentResponse,
    HistoryEntry,
    HistoryResponse,
    RedlineRequest,
    RedlineResponse,
)
from app.services.embeddings import compute_chunk_embeddings, get_embedding
from app.services.llm import summarize_changes
from app.services.redline import apply_changes

router = APIRouter(prefix="/documents", tags=["documents"])


def _row_to_doc(row: dict) -> DocumentResponse:
    return DocumentResponse(**serialize_row(row))


@router.post("", status_code=201, response_model=DocumentResponse)
def create_document(
    body: DocumentCreate,
    db: psycopg.Connection = Depends(get_db),
) -> DocumentResponse:
    """Create a new document."""
    doc_id = str(uuid.uuid4())
    db.execute(
        "INSERT INTO documents (id, title, content) VALUES (%s, %s, %s)",
        (doc_id, body.title, body.content),
    )
    db.commit()

    _update_embedding(db, doc_id, body.content)

    row = db.execute(
        f"SELECT {DOC_COLUMNS} FROM documents WHERE id = %s", (doc_id,)
    ).fetchone()
    return _row_to_doc(row)


@router.get("", response_model=DocumentListResponse)
def list_documents(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: psycopg.Connection = Depends(get_db),
) -> DocumentListResponse:
    """List all documents with pagination."""
    total = db.execute("SELECT COUNT(*) AS cnt FROM documents").fetchone()["cnt"]
    rows = db.execute(
        f"SELECT {DOC_COLUMNS} FROM documents ORDER BY updated_at DESC LIMIT %s OFFSET %s",
        (limit, offset),
    ).fetchall()
    return DocumentListResponse(
        documents=[_row_to_doc(r) for r in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{doc_id}", response_model=DocumentResponse)
def get_document(
    doc_id: str, db: psycopg.Connection = Depends(get_db)
) -> DocumentResponse:
    """Retrieve a single document by ID."""
    row = db.execute(
        f"SELECT {DOC_COLUMNS} FROM documents WHERE id = %s", (doc_id,)
    ).fetchone()
    if row is None:
        raise DocumentNotFound(f"No document with id '{doc_id}'")
    return _row_to_doc(row)


@router.delete("/{doc_id}", status_code=204, response_model=None)
def delete_document(
    doc_id: str,
    db: psycopg.Connection = Depends(get_db),
) -> Response:
    """Delete a document and its change history."""
    row = db.execute("SELECT id FROM documents WHERE id = %s", (doc_id,)).fetchone()
    if row is None:
        raise DocumentNotFound(f"No document with id '{doc_id}'")
    db.execute("DELETE FROM documents WHERE id = %s", (doc_id,))
    db.commit()
    return Response(status_code=204)


@router.post("/{doc_id}/freeze", response_model=DocumentResponse)
def freeze_document(
    doc_id: str,
    db: psycopg.Connection = Depends(get_db),
) -> DocumentResponse:
    """Freeze a document to enter the redlining phase. This action is irreversible."""
    row = db.execute(
        f"SELECT {DOC_COLUMNS} FROM documents WHERE id = %s", (doc_id,)
    ).fetchone()
    if row is None:
        raise DocumentNotFound(f"No document with id '{doc_id}'")

    if row["frozen_at"] is not None:
        raise VersionConflict("Document is already frozen")

    db.execute(
        "UPDATE documents SET frozen_at = NOW() WHERE id = %s",
        (doc_id,),
    )
    db.commit()

    updated_row = db.execute(
        f"SELECT {DOC_COLUMNS} FROM documents WHERE id = %s", (doc_id,)
    ).fetchone()
    return _row_to_doc(updated_row)


@router.patch("/{doc_id}", response_model=RedlineResponse)
def redline_document(
    doc_id: str,
    body: RedlineRequest,
    db: psycopg.Connection = Depends(get_db),
) -> RedlineResponse:
    """Apply redline changes to a document."""
    row = db.execute(
        f"SELECT {DOC_COLUMNS} FROM documents WHERE id = %s", (doc_id,)
    ).fetchone()
    if row is None:
        raise DocumentNotFound(f"No document with id '{doc_id}'")

    if row["version"] != body.version:
        raise VersionConflict(
            f"Document is at version {row['version']}, but request sent version {body.version}"
        )

    new_content, results = apply_changes(row["content"], body.changes)
    changes_applied = sum(1 for r in results if r.success)

    if changes_applied == 0:
        return RedlineResponse(
            id=doc_id,
            content=row["content"],
            version=row["version"],
            changes_applied=0,
            results=results,
            summary="No changes were applied.",
        )

    new_version = row["version"] + 1
    updated = db.execute(
        """UPDATE documents
           SET content = %s, version = %s, updated_at = NOW()
           WHERE id = %s AND version = %s""",
        (new_content, new_version, doc_id, body.version),
    ).rowcount

    if updated == 0:
        raise VersionConflict("Concurrent modification detected")

    summary = summarize_changes(row["title"], results)

    history_id = str(uuid.uuid4())
    db.execute(
        "INSERT INTO change_history (id, document_id, version, changes_json, summary) "
        "VALUES (%s, %s, %s, %s, %s)",
        (
            history_id,
            doc_id,
            new_version,
            json.dumps([c.model_dump() for c in body.changes]),
            summary,
        ),
    )
    db.commit()

    _update_embedding(db, doc_id, new_content)

    return RedlineResponse(
        id=doc_id,
        content=new_content,
        version=new_version,
        changes_applied=changes_applied,
        results=results,
        summary=summary,
    )


def _truncate(text: str, max_len: int = 60) -> str:
    if len(text) <= max_len:
        return text
    return text[:max_len] + "..."


def _generate_edit_summary(
    old_content: str,
    new_content: str,
    opcodes: list[tuple[str, int, int, int, int]],
    old_lines: list[str] | None = None,
    new_lines: list[str] | None = None,
) -> str:
    parts: list[str] = []
    for tag, i1, i2, j1, j2 in opcodes:
        if tag == "equal":
            continue
        if old_lines is not None and new_lines is not None:
            old_text = _truncate("".join(old_lines[i1:i2]))
            new_text = _truncate("".join(new_lines[j1:j2]))
        else:
            old_text = _truncate(old_content[i1:i2])
            new_text = _truncate(new_content[j1:j2])
        if tag == "replace":
            parts.append(f"Replaced '{old_text}' with '{new_text}'")
        elif tag == "delete":
            parts.append(f"Deleted '{old_text}'")
        elif tag == "insert":
            parts.append(f"Added '{new_text}'")

    if not parts:
        return "No changes detected."
    if len(parts) > 5:
        return f"Made {len(parts)} edits across the document"
    return f"Edited {len(parts)} section(s): " + "; ".join(parts)


@router.put("/{doc_id}/content", response_model=DocumentResponse)
def update_document_content(
    doc_id: str,
    body: ContentUpdate,
    db: psycopg.Connection = Depends(get_db),
) -> DocumentResponse:
    """Save full document content from inline editing with auto-save."""
    row = db.execute(
        f"SELECT {DOC_COLUMNS} FROM documents WHERE id = %s", (doc_id,)
    ).fetchone()
    if row is None:
        raise DocumentNotFound(f"No document with id '{doc_id}'")

    if row["frozen_at"] is not None:
        raise DocumentFrozen()

    if row["version"] != body.version:
        raise VersionConflict(
            f"Document is at version {row['version']}, but request sent version {body.version}"
        )

    if row["content"] == body.content:
        return _row_to_doc(row)

    old_content = row["content"]
    new_content = body.content

    # Line-level diff: O(n) on lines instead of O(n²) on characters
    old_lines = old_content.splitlines(keepends=True)
    new_lines = new_content.splitlines(keepends=True)
    matcher = difflib.SequenceMatcher(None, old_lines, new_lines)
    opcodes = matcher.get_opcodes()

    changes: list[dict] = []
    for tag, i1, i2, j1, j2 in opcodes:
        if tag == "equal":
            continue
        old_start = sum(len(old_lines[k]) for k in range(i1))
        old_end = sum(len(old_lines[k]) for k in range(i2))
        new_text = "".join(new_lines[j1:j2])
        if tag == "replace":
            changes.append({
                "operation": "replace",
                "range": {"start": old_start, "end": old_end},
                "replacement": new_text,
            })
        elif tag == "delete":
            changes.append({
                "operation": "replace",
                "range": {"start": old_start, "end": old_end},
                "replacement": "",
            })
        elif tag == "insert":
            changes.append({
                "operation": "replace",
                "range": {"start": old_start, "end": old_start},
                "replacement": new_text,
            })

    summary = _generate_edit_summary(old_content, new_content, opcodes, old_lines, new_lines)

    new_version = row["version"] + 1
    updated = db.execute(
        """UPDATE documents
           SET content = %s, version = %s, updated_at = NOW()
           WHERE id = %s AND version = %s""",
        (new_content, new_version, doc_id, body.version),
    ).rowcount

    if updated == 0:
        raise VersionConflict("Concurrent modification detected")

    history_id = str(uuid.uuid4())
    db.execute(
        "INSERT INTO change_history (id, document_id, version, changes_json, summary) "
        "VALUES (%s, %s, %s, %s, %s)",
        (history_id, doc_id, new_version, json.dumps(changes), summary),
    )
    db.commit()

    _update_embedding(db, doc_id, new_content)

    updated_row = db.execute(
        f"SELECT {DOC_COLUMNS} FROM documents WHERE id = %s", (doc_id,)
    ).fetchone()
    return _row_to_doc(updated_row)


@router.get("/{doc_id}/history", response_model=HistoryResponse)
def get_document_history(
    doc_id: str, db: psycopg.Connection = Depends(get_db)
) -> HistoryResponse:
    """Retrieve the change audit trail for a document."""
    row = db.execute(
        f"SELECT {DOC_COLUMNS} FROM documents WHERE id = %s", (doc_id,)
    ).fetchone()
    if row is None:
        raise DocumentNotFound(f"No document with id '{doc_id}'")

    frozen_at = row.get("frozen_at")

    rows = db.execute(
        "SELECT * FROM change_history WHERE document_id = %s ORDER BY version DESC",
        (doc_id,),
    ).fetchall()

    history: list[HistoryEntry] = []
    for r in rows:
        entry_data = serialize_row(r)
        created_at = r["created_at"]
        if frozen_at is not None and created_at >= frozen_at:
            phase = "redlining"
        else:
            phase = "drafting"
        history.append(HistoryEntry(**entry_data, phase=phase))

    return HistoryResponse(document_id=doc_id, history=history)


def _update_embedding(db: psycopg.Connection, doc_id: str, content: str) -> None:
    """Compute and store document + chunk embeddings via pgvector."""
    embedding = get_embedding(content)
    if embedding is not None:
        db.execute(
            "UPDATE documents SET embedding = %s::vector WHERE id = %s",
            (embedding, doc_id),
        )
        db.commit()

    chunks = compute_chunk_embeddings(content)
    if chunks is not None:
        db.execute("DELETE FROM chunk_embeddings WHERE document_id = %s", (doc_id,))
        for idx, (text, position, emb) in enumerate(chunks):
            db.execute(
                "INSERT INTO chunk_embeddings (document_id, chunk_index, chunk_text, position, embedding, model) "
                "VALUES (%s, %s, %s, %s, %s::vector, %s)",
                (doc_id, idx, text, position, emb, settings.embedding_model),
            )
        db.commit()
