"""Search endpoints with hybrid PostgreSQL tsvector + pgvector scoring."""

from __future__ import annotations

import psycopg
from fastapi import APIRouter, Depends, Query

from app.config import settings
from app.database import get_db, serialize_row
from app.errors import DocumentNotFound
from app.models import ScoreBreakdown, SearchDocumentResult, SearchResponse, SearchSnippet
from app.services.embeddings import get_embedding
from app.services.search import search_text

router = APIRouter(tags=["search"])


def _normalize_text_score(score: float) -> float:
    """Saturation normalization: score / (score + k) where k=1.5."""
    if score <= 0:
        return 0.0
    return score / (score + 1.5) * 100


def _compute_hybrid(
    text_score: float,
    semantic_score: float | None,
    alpha: float,
    discount: float,
) -> tuple[float, ScoreBreakdown]:
    """Compute hybrid score and breakdown from raw text and semantic scores."""
    norm_text = _normalize_text_score(text_score)

    if semantic_score is not None:
        sem_pct = max(0.0, semantic_score) * 100
        if text_score <= 0:
            sem_pct *= discount
        hybrid = alpha * (norm_text / 100) + (1 - alpha) * (sem_pct / 100)
        hybrid_pct = round(hybrid * 100, 1)
        breakdown = ScoreBreakdown(
            text_score=round(norm_text, 1),
            semantic_score=round(sem_pct, 1),
            text_weight=alpha,
            semantic_weight=1 - alpha,
        )
    else:
        hybrid_pct = round(norm_text, 1)
        breakdown = ScoreBreakdown(
            text_score=round(norm_text, 1),
            semantic_score=None,
            text_weight=1.0,
            semantic_weight=0.0,
        )

    return hybrid_pct, breakdown


def _get_semantic_snippets(
    db: psycopg.Connection,
    doc_id: str,
    query_embedding: list[float],
    threshold: float,
) -> list[SearchSnippet]:
    """Get semantically similar sentence chunks from the database."""
    rows = db.execute(
        """SELECT chunk_text, position, 1 - (embedding <=> %s::vector) AS similarity
           FROM chunk_embeddings
           WHERE document_id = %s AND 1 - (embedding <=> %s::vector) > %s
           ORDER BY similarity DESC
           LIMIT 3""",
        (query_embedding, doc_id, query_embedding, threshold),
    ).fetchall()
    return [
        SearchSnippet(
            text=r["chunk_text"],
            position=r["position"],
            context_before="",
            context_after=f" [semantic: {round(r['similarity'] * 100)}%]",
        )
        for r in rows
    ]


@router.get("/search", response_model=SearchResponse)
def search_documents(
    q: str = Query(min_length=1),
    limit: int = Query(default=10, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: psycopg.Connection = Depends(get_db),
) -> SearchResponse:
    """Search across all documents with hybrid tsvector + pgvector scoring."""
    query_embedding = get_embedding(q) if settings.embedding_api_key else None
    alpha = settings.search_text_weight
    threshold = settings.search_semantic_threshold
    discount = settings.search_semantic_only_discount

    # Text matches via PostgreSQL tsvector
    text_rows = db.execute(
        """SELECT id, title, content,
                  ts_rank_cd(search_vector, websearch_to_tsquery('english', %s)) AS text_score
           FROM documents
           WHERE search_vector @@ websearch_to_tsquery('english', %s)""",
        (q, q),
    ).fetchall()

    # Build candidate map: {doc_id: {title, content, text_score, semantic_score}}
    candidates: dict[str, dict] = {}
    for r in text_rows:
        candidates[r["id"]] = {
            "title": r["title"],
            "content": r["content"],
            "text_score": r["text_score"],
            "semantic_score": None,
        }

    # Semantic matches via pgvector (only documents with embeddings above threshold)
    if query_embedding is not None:
        sem_rows = db.execute(
            """SELECT id, title, content,
                      1 - (embedding <=> %s::vector) AS semantic_score
               FROM documents
               WHERE embedding IS NOT NULL
                 AND 1 - (embedding <=> %s::vector) > %s""",
            (query_embedding, query_embedding, threshold),
        ).fetchall()
        for r in sem_rows:
            if r["id"] in candidates:
                candidates[r["id"]]["semantic_score"] = r["semantic_score"]
            else:
                candidates[r["id"]] = {
                    "title": r["title"],
                    "content": r["content"],
                    "text_score": 0,
                    "semantic_score": r["semantic_score"],
                }

    # Score, filter, and build results
    results: list[SearchDocumentResult] = []
    total_matches = 0

    for doc_id, info in candidates.items():
        text_snippets = search_text(info["content"], q)
        total_matches += len(text_snippets)

        semantic_snippets: list[SearchSnippet] = []
        if query_embedding is not None:
            semantic_snippets = _get_semantic_snippets(
                db, doc_id, query_embedding, threshold
            )

        all_snippets = text_snippets + semantic_snippets
        if not all_snippets:
            continue

        score_pct, breakdown = _compute_hybrid(
            info["text_score"], info["semantic_score"], alpha, discount
        )

        if score_pct < settings.search_min_score:
            continue

        results.append(
            SearchDocumentResult(
                document_id=doc_id,
                document_title=info["title"],
                snippets=all_snippets,
                score=score_pct,
                score_breakdown=breakdown,
            )
        )

    results.sort(key=lambda r: r.score, reverse=True)
    paginated = results[offset : offset + limit]

    return SearchResponse(
        query=q,
        results=paginated,
        total_matches=total_matches,
    )


@router.get("/documents/{doc_id}/search", response_model=SearchResponse)
def search_in_document(
    doc_id: str,
    q: str = Query(min_length=1),
    db: psycopg.Connection = Depends(get_db),
) -> SearchResponse:
    """Search within a specific document with relevance scoring."""
    row = db.execute(
        "SELECT id, title, content FROM documents WHERE id = %s", (doc_id,)
    ).fetchone()
    if row is None:
        raise DocumentNotFound(f"No document with id '{doc_id}'")

    query_embedding = get_embedding(q) if settings.embedding_api_key else None
    alpha = settings.search_text_weight
    threshold = settings.search_semantic_threshold
    discount = settings.search_semantic_only_discount

    text_snippets = search_text(row["content"], q)

    # Get text score for this document
    text_score_row = db.execute(
        """SELECT ts_rank_cd(search_vector, websearch_to_tsquery('english', %s)) AS text_score
           FROM documents
           WHERE id = %s AND search_vector @@ websearch_to_tsquery('english', %s)""",
        (q, doc_id, q),
    ).fetchone()
    text_score = text_score_row["text_score"] if text_score_row else 0

    # Semantic score
    semantic_score = None
    semantic_snippets: list[SearchSnippet] = []
    if query_embedding is not None:
        sem_row = db.execute(
            """SELECT 1 - (embedding <=> %s::vector) AS semantic_score
               FROM documents
               WHERE id = %s AND embedding IS NOT NULL""",
            (query_embedding, doc_id),
        ).fetchone()
        if sem_row and sem_row["semantic_score"] > threshold:
            semantic_score = sem_row["semantic_score"]

        semantic_snippets = _get_semantic_snippets(
            db, doc_id, query_embedding, threshold
        )

    all_snippets = text_snippets + semantic_snippets

    results = []
    if all_snippets:
        score_pct, breakdown = _compute_hybrid(
            text_score, semantic_score, alpha, discount
        )
        results.append(
            SearchDocumentResult(
                document_id=row["id"],
                document_title=row["title"],
                snippets=all_snippets,
                score=score_pct,
                score_breakdown=breakdown,
            )
        )

    return SearchResponse(
        query=q,
        results=results,
        total_matches=len(text_snippets),
    )
