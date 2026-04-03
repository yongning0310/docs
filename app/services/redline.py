"""Pure-function redline engine for document text replacement.

All functions in this module are stateless — no database, no HTTP.
This makes the core algorithm easy to test and reason about independently.
"""

from __future__ import annotations

from app.models import Change, ChangeResult


def find_all_occurrences(content: str, text: str) -> list[int]:
    """Return starting positions of all occurrences of text in content."""
    positions: list[int] = []
    start = 0
    while True:
        idx = content.find(text, start)
        if idx == -1:
            break
        positions.append(idx)
        start = idx + 1
    return positions


def apply_single_change(
    content: str, change: Change, index: int
) -> tuple[str, ChangeResult]:
    """Apply a single change to content. Returns (new_content, result).

    For occurrence-based changes: finds the Nth occurrence of the target text
    and replaces it. occurrence=0 replaces all occurrences.

    For range-based changes: replaces the text between the given byte offsets.

    Changes that cannot be applied (e.g., occurrence not found, range out of
    bounds) return the original content unchanged with a failure result.
    """
    if change.target is not None:
        return _apply_target_change(content, change, index)
    else:
        assert change.range is not None
        return _apply_range_change(content, change, index)


def _apply_target_change(
    content: str, change: Change, index: int
) -> tuple[str, ChangeResult]:
    assert change.target is not None
    target_text = change.target.text
    occurrence = change.target.occurrence
    positions = find_all_occurrences(content, target_text)

    if not positions:
        return content, ChangeResult(
            index=index,
            success=False,
            detail=f"Target text not found: '{target_text}'",
        )

    if occurrence == 0:
        # Replace all occurrences — iterate in reverse to preserve positions
        new_content = content
        for pos in reversed(positions):
            new_content = (
                new_content[:pos]
                + change.replacement
                + new_content[pos + len(target_text) :]
            )
        return new_content, ChangeResult(
            index=index,
            success=True,
            detail=f"Replaced all {len(positions)} occurrences of '{target_text}'",
            original_text=target_text,
            replacement_text=change.replacement,
            position=positions[0],
        )

    if occurrence < 0 or occurrence > len(positions):
        return content, ChangeResult(
            index=index,
            success=False,
            detail=(
                f"Occurrence {occurrence} not found for '{target_text}' "
                f"(document has {len(positions)} occurrence(s))"
            ),
        )

    pos = positions[occurrence - 1]
    new_content = (
        content[:pos] + change.replacement + content[pos + len(target_text) :]
    )
    return new_content, ChangeResult(
        index=index,
        success=True,
        detail=f"Replaced occurrence {occurrence} of '{target_text}'",
        original_text=target_text,
        replacement_text=change.replacement,
        position=pos,
    )


def _apply_range_change(
    content: str, change: Change, index: int
) -> tuple[str, ChangeResult]:
    assert change.range is not None
    start = change.range.start
    end = change.range.end

    if start > end:
        return content, ChangeResult(
            index=index,
            success=False,
            detail=f"Invalid range: start ({start}) > end ({end})",
        )

    if end > len(content):
        return content, ChangeResult(
            index=index,
            success=False,
            detail=(
                f"Range end ({end}) exceeds document length ({len(content)})"
            ),
        )

    original_text = content[start:end]
    new_content = content[:start] + change.replacement + content[end:]
    return new_content, ChangeResult(
        index=index,
        success=True,
        detail=f"Replaced text at range [{start}:{end}]",
        original_text=original_text,
        replacement_text=change.replacement,
        position=start,
    )


def apply_changes(
    content: str, changes: list[Change]
) -> tuple[str, list[ChangeResult]]:
    """Apply a list of changes sequentially to document content.

    Changes are applied in order. After each change, positions in the document
    may shift. Occurrence-based changes naturally handle this since they search
    by text. Range-based changes accumulate an offset delta to adjust positions.

    Returns (modified_content, list_of_results).
    """
    results: list[ChangeResult] = []
    offset_delta = 0

    for i, change in enumerate(changes):
        # Adjust range-based positions by the accumulated offset
        if change.range is not None:
            adjusted_change = Change(
                operation=change.operation,
                range=type(change.range)(
                    start=change.range.start + offset_delta,
                    end=change.range.end + offset_delta,
                ),
                replacement=change.replacement,
            )
        else:
            adjusted_change = change

        new_content, result = apply_single_change(content, adjusted_change, i)

        if result.success:
            # Track content length change for subsequent range-based adjustments
            offset_delta += len(new_content) - len(content)

        results.append(result)
        content = new_content

    return content, results


def generate_deterministic_summary(results: list[ChangeResult]) -> str:
    """Build a plain-English summary from change results without an LLM."""
    successful = [r for r in results if r.success]
    if not successful:
        return "No changes were applied."

    parts: list[str] = []
    for r in successful:
        if r.original_text and r.replacement_text:
            parts.append(f"Replaced '{r.original_text}' with '{r.replacement_text}'")
        elif r.original_text:
            parts.append(f"Removed '{r.original_text}'")
        else:
            parts.append(r.detail)

    return "; ".join(parts) + "."
