"""Embedding service for semantic search.

Uses an OpenAI-compatible embeddings API (default: Jina AI free tier).
Falls back gracefully when no API key is configured or the API is unavailable.

Vector storage and similarity computation are handled by PostgreSQL + pgvector.
This module is responsible only for calling the embedding API and text processing.
"""

from __future__ import annotations

import logging
import re

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

# Type alias for chunk data: [(text, position, embedding), ...]
ChunkData = list[tuple[str, int, list[float]]]


def split_into_sentences(content: str, min_length: int = 20) -> list[tuple[str, int]]:
    """Split content into sentences with their positions in the original text.

    Returns [(sentence_text, start_position), ...]. Strips HTML tags for
    splitting but preserves original positions. Merges very short fragments.
    """
    clean = re.sub(r'<[^>]+>', ' ', content)
    clean = re.sub(r'\s+', ' ', clean).strip()

    if not clean:
        return []

    sentences: list[tuple[str, int]] = []
    start = 0
    for m in re.finditer(r'[.!?]\s+', clean):
        sentence = clean[start:m.start() + 1].strip()
        if sentence:
            if len(sentence) < min_length and sentences:
                prev_text, prev_pos = sentences[-1]
                sentences[-1] = (prev_text + " " + sentence, prev_pos)
            else:
                sentences.append((sentence, start))
        start = m.end()

    remainder = clean[start:].strip()
    if remainder:
        if len(remainder) < min_length and sentences:
            prev_text, prev_pos = sentences[-1]
            sentences[-1] = (prev_text + " " + remainder, prev_pos)
        else:
            sentences.append((remainder, start))

    return sentences


def get_embedding(text: str) -> list[float] | None:
    """Get an embedding vector for the given text via the configured API.

    Returns None if no API key is configured or the API call fails.
    """
    if not settings.embedding_api_key:
        return None

    truncated = text[:8000]

    try:
        with httpx.Client(timeout=settings.llm_timeout) as client:
            resp = client.post(
                f"{settings.embedding_base_url}/embeddings",
                headers={"Authorization": f"Bearer {settings.embedding_api_key}"},
                json={
                    "model": settings.embedding_model,
                    "input": truncated,
                },
            )
            resp.raise_for_status()
            data = resp.json()
            return data["data"][0]["embedding"]
    except httpx.HTTPStatusError as exc:
        logger.warning("Embedding API returned %s", exc.response.status_code)
        return None
    except httpx.TimeoutException:
        logger.warning("Embedding API timed out after %ss", settings.llm_timeout)
        return None
    except (httpx.RequestError, KeyError, IndexError) as exc:
        logger.warning("Embedding request failed (%s)", type(exc).__name__)
        return None


def get_embeddings_batch(texts: list[str]) -> list[list[float]] | None:
    """Get embeddings for multiple texts in a single API call.

    Returns a list of embedding vectors (one per input text), or None on failure.
    """
    if not settings.embedding_api_key or not texts:
        return None

    truncated = [t[:8000] for t in texts]

    try:
        with httpx.Client(timeout=settings.llm_timeout * 3) as client:
            resp = client.post(
                f"{settings.embedding_base_url}/embeddings",
                headers={"Authorization": f"Bearer {settings.embedding_api_key}"},
                json={
                    "model": settings.embedding_model,
                    "input": truncated,
                },
            )
            resp.raise_for_status()
            data = resp.json()
            items = sorted(data["data"], key=lambda x: x["index"])
            return [item["embedding"] for item in items]
    except httpx.HTTPStatusError as exc:
        logger.warning("Batch embedding API returned %s", exc.response.status_code)
        return None
    except httpx.TimeoutException:
        logger.warning("Batch embedding API timed out")
        return None
    except (httpx.RequestError, KeyError, IndexError) as exc:
        logger.warning("Batch embedding request failed (%s)", type(exc).__name__)
        return None


def compute_chunk_embeddings(content: str) -> ChunkData | None:
    """Split content into sentences and embed them in a single batch API call.

    Returns [(sentence_text, position, embedding), ...] or None on failure.
    """
    sentences = split_into_sentences(content)
    if not sentences:
        return None

    texts = [s[0] for s in sentences]
    embeddings = get_embeddings_batch(texts)
    if embeddings is None:
        return None

    return [
        (text, pos, emb)
        for (text, pos), emb in zip(sentences, embeddings)
    ]
