"""LLM integration for generating human-readable change summaries.

Uses an OpenAI-compatible API. Falls back to deterministic summaries when
the LLM is unavailable — the service works fully without an API key.
"""

from __future__ import annotations

import json
import logging

import httpx

from app.config import settings
from app.models import ChangeResult
from app.services.redline import generate_deterministic_summary

logger = logging.getLogger(__name__)


def summarize_changes(
    title: str,
    results: list[ChangeResult],
) -> str:
    """Generate a plain-English summary of applied changes.

    Attempts an LLM API call; falls back to a rule-based summary on failure
    or when no API key is configured.
    """
    deterministic = generate_deterministic_summary(results)

    if not settings.llm_api_key:
        return deterministic

    successful = [r for r in results if r.success]
    if not successful:
        return deterministic

    changes_desc = json.dumps(
        [
            {
                "original": r.original_text,
                "replacement": r.replacement_text,
                "detail": r.detail,
            }
            for r in successful
        ],
        indent=2,
    )

    prompt = (
        "You are a legal document assistant. Summarize the following changes "
        "to a legal document in 1-2 concise sentences.\n\n"
        f"Document title: {title}\n"
        f"Changes applied:\n{changes_desc}"
    )

    try:
        with httpx.Client(timeout=settings.llm_timeout) as client:
            resp = client.post(
                f"{settings.llm_base_url}/chat/completions",
                headers={"Authorization": f"Bearer {settings.llm_api_key}"},
                json={
                    "model": settings.llm_model,
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": 150,
                    "temperature": 0.3,
                },
            )
            resp.raise_for_status()
            data = resp.json()
            return data["choices"][0]["message"]["content"].strip()
    except httpx.HTTPStatusError as exc:
        logger.warning("LLM API returned %s, using fallback", exc.response.status_code)
        return deterministic
    except httpx.TimeoutException:
        logger.warning("LLM API timed out after %ss, using fallback", settings.llm_timeout)
        return deterministic
    except (httpx.RequestError, KeyError, IndexError) as exc:
        logger.warning("LLM summarization failed (%s), using fallback", type(exc).__name__)
        return deterministic
