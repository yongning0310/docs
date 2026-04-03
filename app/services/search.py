"""Text search utilities.

Full-text ranking is handled by PostgreSQL's tsvector + ts_rank_cd.
This module provides snippet extraction for displaying search results.
"""

from __future__ import annotations

import re

from app.config import settings
from app.models import SearchSnippet


def search_text(
    content: str,
    query: str,
    context_chars: int | None = None,
) -> list[SearchSnippet]:
    """Find all occurrences of query in content with surrounding context."""
    ctx = context_chars if context_chars is not None else settings.search_context_chars
    pattern = re.compile(re.escape(query), re.IGNORECASE)
    snippets: list[SearchSnippet] = []

    for match in pattern.finditer(content):
        start = match.start()
        end = match.end()
        ctx_start = max(0, start - ctx)
        ctx_end = min(len(content), end + ctx)

        snippets.append(
            SearchSnippet(
                text=content[start:end],
                position=start,
                context_before=content[ctx_start:start],
                context_after=content[end:ctx_end],
            )
        )

    return snippets
