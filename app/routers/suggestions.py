"""Suggestion and comment endpoints for document review workflows."""

from __future__ import annotations

import json
import uuid
from collections import defaultdict

import psycopg
from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from pydantic import BaseModel, Field

from app.database import DOC_COLUMNS, get_db, serialize_row
from app.errors import (
    DocumentNotFound,
    DocumentNotFrozen,
    SelfApproval,
    SuggestionAlreadyResolved,
    SuggestionConflict,
    SuggestionNotFound,
    VersionConflict,
)
from app.models import (
    Change,
    ChangeRange,
    CommentCreate,
    CommentResponse,
    SuggestionCreate,
    SuggestionListResponse,
    SuggestionResponse,
)
from app.services.redline import apply_single_change

router = APIRouter(prefix="/documents", tags=["suggestions"])


class SuggestionAction(BaseModel):
    """Request body for PATCH (accept/reject) a suggestion."""

    action: str = Field(pattern="^(accept|reject)$")
    author: str = Field(min_length=1, max_length=50)


def _row_to_suggestion(
    row: dict, comments: list[CommentResponse]
) -> SuggestionResponse:
    data = serialize_row(row)
    return SuggestionResponse(
        id=data["id"],
        document_id=data["document_id"],
        original_text=data["original_text"],
        replacement_text=data["replacement_text"],
        position=data["position"],
        author=data["author"],
        status=data["status"],
        created_at=data["created_at"],
        resolved_at=data["resolved_at"],
        resolved_by=data["resolved_by"],
        comments=comments,
    )


def _fetch_comments(db: psycopg.Connection, suggestion_id: str) -> list[CommentResponse]:
    rows = db.execute(
        "SELECT * FROM suggestion_comments WHERE suggestion_id = %s ORDER BY created_at ASC",
        (suggestion_id,),
    ).fetchall()
    return [CommentResponse(**serialize_row(r)) for r in rows]


def _get_document_or_404(db: psycopg.Connection, doc_id: str) -> dict:
    row = db.execute(
        f"SELECT {DOC_COLUMNS} FROM documents WHERE id = %s", (doc_id,)
    ).fetchone()
    if row is None:
        raise DocumentNotFound(f"No document with id '{doc_id}'")
    return row


def _get_suggestion_or_404(
    db: psycopg.Connection, doc_id: str, suggestion_id: str
) -> dict:
    row = db.execute(
        "SELECT * FROM suggestions WHERE id = %s AND document_id = %s",
        (suggestion_id, doc_id),
    ).fetchone()
    if row is None:
        raise SuggestionNotFound(
            f"No suggestion with id '{suggestion_id}' for document '{doc_id}'"
        )
    return row


@router.post(
    "/{doc_id}/suggestions", status_code=201, response_model=SuggestionResponse
)
def create_suggestion(
    doc_id: str,
    body: SuggestionCreate,
    db: psycopg.Connection = Depends(get_db),
) -> SuggestionResponse:
    """Create a new suggestion on a document."""
    doc_row = _get_document_or_404(db, doc_id)

    if doc_row["frozen_at"] is None:
        raise DocumentNotFrozen()

    suggestion_id = str(uuid.uuid4())
    db.execute(
        "INSERT INTO suggestions (id, document_id, original_text, replacement_text, position, author) "
        "VALUES (%s, %s, %s, %s, %s, %s)",
        (suggestion_id, doc_id, body.original_text, body.replacement_text, body.position, body.author),
    )
    db.commit()

    row = db.execute(
        "SELECT * FROM suggestions WHERE id = %s", (suggestion_id,)
    ).fetchone()
    return _row_to_suggestion(row, [])


@router.get(
    "/{doc_id}/suggestions", response_model=SuggestionListResponse
)
def list_suggestions(
    doc_id: str,
    status: str | None = Query(default=None, pattern="^(pending|accepted|rejected)$"),
    db: psycopg.Connection = Depends(get_db),
) -> SuggestionListResponse:
    """List all suggestions for a document, optionally filtered by status."""
    _get_document_or_404(db, doc_id)

    if status is not None:
        rows = db.execute(
            "SELECT * FROM suggestions WHERE document_id = %s AND status = %s "
            "ORDER BY created_at DESC",
            (doc_id, status),
        ).fetchall()
    else:
        rows = db.execute(
            "SELECT * FROM suggestions WHERE document_id = %s ORDER BY created_at DESC",
            (doc_id,),
        ).fetchall()

    # Batch-fetch all comments in one query instead of N+1
    suggestion_ids = [r["id"] for r in rows]
    if suggestion_ids:
        all_comments = db.execute(
            "SELECT * FROM suggestion_comments WHERE suggestion_id = ANY(%s) "
            "ORDER BY created_at ASC",
            (suggestion_ids,),
        ).fetchall()
    else:
        all_comments = []
    comments_by_sid: dict[str, list[CommentResponse]] = defaultdict(list)
    for c in all_comments:
        comments_by_sid[c["suggestion_id"]].append(CommentResponse(**serialize_row(c)))

    suggestions = [
        _row_to_suggestion(r, comments_by_sid.get(r["id"], [])) for r in rows
    ]
    return SuggestionListResponse(
        document_id=doc_id,
        suggestions=suggestions,
        total=len(suggestions),
    )


@router.patch(
    "/{doc_id}/suggestions/{suggestion_id}", response_model=SuggestionResponse
)
def resolve_suggestion(
    doc_id: str,
    suggestion_id: str,
    body: SuggestionAction,
    db: psycopg.Connection = Depends(get_db),
) -> SuggestionResponse:
    """Accept or reject a suggestion."""
    doc_row = _get_document_or_404(db, doc_id)
    suggestion_row = _get_suggestion_or_404(db, doc_id, suggestion_id)

    if suggestion_row["status"] != "pending":
        raise SuggestionAlreadyResolved(
            f"Suggestion is already '{suggestion_row['status']}'"
        )

    if body.action == "accept":
        if body.author == suggestion_row["author"]:
            raise SelfApproval()

        content = doc_row["content"]
        position = suggestion_row["position"]
        original_text = suggestion_row["original_text"]
        replacement_text = suggestion_row["replacement_text"]

        end_pos = position + len(original_text)
        if end_pos <= len(content) and content[position:end_pos] == original_text:
            pass
        else:
            found_pos = content.find(original_text)
            if found_pos == -1:
                raise SuggestionConflict(
                    "Document text has changed since the suggestion was created — "
                    "the original text can no longer be found"
                )
            position = found_pos
            end_pos = position + len(original_text)

        change = Change(
            operation="replace",
            range=ChangeRange(start=position, end=end_pos),
            replacement=replacement_text,
        )
        new_content, result = apply_single_change(content, change, 0)

        if not result.success:
            raise SuggestionConflict(
                f"Failed to apply suggestion: {result.detail}"
            )

        new_version = doc_row["version"] + 1
        updated = db.execute(
            """UPDATE documents
               SET content = %s, version = %s, updated_at = NOW()
               WHERE id = %s AND version = %s""",
            (new_content, new_version, doc_id, doc_row["version"]),
        ).rowcount

        if updated == 0:
            raise VersionConflict("Concurrent modification detected")

        history_id = str(uuid.uuid4())
        summary = (
            f"Accepted suggestion by {suggestion_row['author']} "
            f"(approved by {body.author}): "
            f"Replaced '{original_text}' "
            f"with '{replacement_text}'"
        )
        db.execute(
            "INSERT INTO change_history (id, document_id, version, changes_json, summary) "
            "VALUES (%s, %s, %s, %s, %s)",
            (
                history_id,
                doc_id,
                new_version,
                json.dumps([
                    {
                        "operation": "replace",
                        "target": {"text": original_text},
                        "range": {"start": position, "end": end_pos},
                        "replacement": replacement_text,
                    }
                ]),
                summary,
            ),
        )

    db.execute(
        "UPDATE suggestions SET status = %s, resolved_at = NOW(), resolved_by = %s WHERE id = %s",
        (body.action + "ed", body.author, suggestion_id),
    )
    db.commit()

    row = db.execute(
        "SELECT * FROM suggestions WHERE id = %s", (suggestion_id,)
    ).fetchone()
    comments = _fetch_comments(db, suggestion_id)
    return _row_to_suggestion(row, comments)


@router.post(
    "/{doc_id}/suggestions/{suggestion_id}/comments",
    status_code=201,
    response_model=CommentResponse,
)
def add_comment(
    doc_id: str,
    suggestion_id: str,
    body: CommentCreate,
    db: psycopg.Connection = Depends(get_db),
) -> CommentResponse:
    """Add a comment or reply to a suggestion."""
    _get_document_or_404(db, doc_id)
    _get_suggestion_or_404(db, doc_id, suggestion_id)

    comment_id = str(uuid.uuid4())
    db.execute(
        "INSERT INTO suggestion_comments (id, suggestion_id, author, content) "
        "VALUES (%s, %s, %s, %s)",
        (comment_id, suggestion_id, body.author, body.content),
    )
    db.commit()

    row = db.execute(
        "SELECT * FROM suggestion_comments WHERE id = %s", (comment_id,)
    ).fetchone()
    return CommentResponse(**serialize_row(row))


@router.delete(
    "/{doc_id}/suggestions/{suggestion_id}",
    status_code=204,
    response_model=None,
)
def delete_suggestion(
    doc_id: str,
    suggestion_id: str,
    db: psycopg.Connection = Depends(get_db),
) -> Response:
    """Delete a suggestion and its comments."""
    _get_document_or_404(db, doc_id)
    _get_suggestion_or_404(db, doc_id, suggestion_id)

    db.execute("DELETE FROM suggestions WHERE id = %s", (suggestion_id,))
    db.commit()
    return Response(status_code=204)
