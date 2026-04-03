"""Performance benchmarks for redline and search operations on large documents."""

import time

import pytest

from app.models import Change, ChangeTarget, ChangeRange
from app.services.redline import apply_changes
from app.services.search import search_text


def _generate_large_content(size_mb: float = 1.0) -> str:
    """Generate a realistic large legal document."""
    paragraph = (
        "This Agreement shall be governed by and construed in accordance with the laws "
        "of the State of Delaware, without regard to conflict of law principles. "
        "The parties agree to submit to the exclusive jurisdiction of the courts of Delaware. "
        "Party A shall indemnify and hold harmless Party B against any claims arising from "
        "breach of this Agreement. Confidential information shall not be disclosed to any "
        "third party without prior written consent. "
    )
    target_bytes = int(size_mb * 1024 * 1024)
    repeats = target_bytes // len(paragraph) + 1
    return (paragraph * repeats)[:target_bytes]


class TestRedlinePerformance:
    def test_replace_in_large_document(self):
        """Single replacement in a ~1MB document should complete in < 1 second."""
        content = _generate_large_content(1.0)
        changes = [
            Change(
                target=ChangeTarget(text="Party A", occurrence=1),
                replacement="Acme Corporation",
            )
        ]

        start = time.perf_counter()
        new_content, results = apply_changes(content, changes)
        elapsed = time.perf_counter() - start

        assert results[0].success
        assert elapsed < 1.0, f"Single replace took {elapsed:.3f}s (expected < 1.0s)"

    def test_replace_all_in_large_document(self):
        """Replace-all in a ~1MB document should complete in < 2 seconds."""
        content = _generate_large_content(1.0)
        changes = [
            Change(
                target=ChangeTarget(text="Party A", occurrence=0),
                replacement="Acme Corporation",
            )
        ]

        start = time.perf_counter()
        new_content, results = apply_changes(content, changes)
        elapsed = time.perf_counter() - start

        assert results[0].success
        assert "Party A" not in new_content
        assert elapsed < 2.0, f"Replace-all took {elapsed:.3f}s (expected < 2.0s)"

    def test_many_sequential_replacements(self):
        """100 sequential replacements should complete in < 2 seconds."""
        content = _generate_large_content(0.5)
        # Generate unique targets
        changes = [
            Change(
                target=ChangeTarget(text="Agreement", occurrence=1),
                replacement=f"Contract_{i}",
            )
            for i in range(100)
        ]

        start = time.perf_counter()
        new_content, results = apply_changes(content, changes)
        elapsed = time.perf_counter() - start

        successful = sum(1 for r in results if r.success)
        assert successful > 0
        assert elapsed < 2.0, f"100 sequential replacements took {elapsed:.3f}s"

    def test_range_replacement_in_large_document(self):
        """Position-based replacement in a ~1MB document should be near-instant."""
        content = _generate_large_content(1.0)
        changes = [
            Change(
                range=ChangeRange(start=0, end=100),
                replacement="REPLACED HEADER",
            )
        ]

        start = time.perf_counter()
        new_content, results = apply_changes(content, changes)
        elapsed = time.perf_counter() - start

        assert results[0].success
        assert elapsed < 0.1, f"Range replace took {elapsed:.3f}s (expected < 0.1s)"


class TestSearchPerformance:
    def test_search_in_large_document(self):
        """Keyword search in a ~1MB document should complete in < 1 second."""
        content = _generate_large_content(1.0)

        start = time.perf_counter()
        snippets = search_text(content, "indemnify")
        elapsed = time.perf_counter() - start

        assert len(snippets) > 0
        assert elapsed < 1.0, f"Search took {elapsed:.3f}s (expected < 1.0s)"

    def test_search_in_10mb_document(self):
        """Search in a ~10MB document should complete in < 5 seconds."""
        content = _generate_large_content(10.0)

        start = time.perf_counter()
        snippets = search_text(content, "indemnify")
        elapsed = time.perf_counter() - start

        assert len(snippets) > 0
        assert elapsed < 5.0, f"10MB search took {elapsed:.3f}s (expected < 5.0s)"

    def test_replace_in_10mb_document(self):
        """Single replacement in a ~10MB document should complete in < 3 seconds."""
        content = _generate_large_content(10.0)
        changes = [
            Change(
                target=ChangeTarget(text="indemnify", occurrence=1),
                replacement="compensate",
            )
        ]

        start = time.perf_counter()
        new_content, results = apply_changes(content, changes)
        elapsed = time.perf_counter() - start

        assert results[0].success
        assert elapsed < 3.0, f"10MB replace took {elapsed:.3f}s (expected < 3.0s)"

