"""Unit tests for the pure-function redline engine."""

from app.models import Change, ChangeRange, ChangeTarget
from app.services.redline import (
    apply_changes,
    apply_single_change,
    find_all_occurrences,
    generate_deterministic_summary,
)


class TestFindAllOccurrences:
    def test_multiple_occurrences(self):
        assert find_all_occurrences("abcabc", "abc") == [0, 3]

    def test_no_occurrences(self):
        assert find_all_occurrences("hello", "xyz") == []

    def test_overlapping_search_positions(self):
        assert find_all_occurrences("aaa", "aa") == [0, 1]


class TestApplySingleChange:
    def test_target_first_occurrence(self):
        content = "Party A and Party A agree"
        change = Change(
            target=ChangeTarget(text="Party A", occurrence=1),
            replacement="Acme Corp",
        )
        new_content, result = apply_single_change(content, change, 0)
        assert new_content == "Acme Corp and Party A agree"
        assert result.success is True
        assert result.position == 0

    def test_target_second_occurrence(self):
        content = "Party A and Party A agree"
        change = Change(
            target=ChangeTarget(text="Party A", occurrence=2),
            replacement="Acme Corp",
        )
        new_content, result = apply_single_change(content, change, 0)
        assert new_content == "Party A and Acme Corp agree"
        assert result.success is True

    def test_target_replace_all(self):
        content = "Party A and Party A agree"
        change = Change(
            target=ChangeTarget(text="Party A", occurrence=0),
            replacement="Acme Corp",
        )
        new_content, result = apply_single_change(content, change, 0)
        assert new_content == "Acme Corp and Acme Corp agree"
        assert result.success is True

    def test_target_not_found(self):
        content = "Hello world"
        change = Change(
            target=ChangeTarget(text="xyz"),
            replacement="abc",
        )
        new_content, result = apply_single_change(content, change, 0)
        assert new_content == content  # unchanged
        assert result.success is False
        assert "not found" in result.detail.lower()

    def test_target_occurrence_out_of_range(self):
        content = "Party A agrees"
        change = Change(
            target=ChangeTarget(text="Party A", occurrence=5),
            replacement="Acme",
        )
        new_content, result = apply_single_change(content, change, 0)
        assert new_content == content
        assert result.success is False
        assert "occurrence 5" in result.detail.lower()

    def test_range_replacement(self):
        content = "Hello world"
        change = Change(
            range=ChangeRange(start=6, end=11),
            replacement="earth",
        )
        new_content, result = apply_single_change(content, change, 0)
        assert new_content == "Hello earth"
        assert result.success is True
        assert result.original_text == "world"

    def test_range_out_of_bounds(self):
        content = "Hello"
        change = Change(
            range=ChangeRange(start=0, end=100),
            replacement="Hi",
        )
        new_content, result = apply_single_change(content, change, 0)
        assert new_content == content
        assert result.success is False

    def test_range_start_greater_than_end(self):
        content = "Hello"
        change = Change(
            range=ChangeRange(start=3, end=1),
            replacement="Hi",
        )
        _, result = apply_single_change(content, change, 0)
        assert result.success is False

    def test_empty_replacement_deletes_text(self):
        content = "Hello world"
        change = Change(
            target=ChangeTarget(text=" world"),
            replacement="",
        )
        new_content, result = apply_single_change(content, change, 0)
        assert new_content == "Hello"
        assert result.success is True

    def test_replacement_longer_than_original(self):
        content = "Hi"
        change = Change(
            range=ChangeRange(start=0, end=2),
            replacement="Hello there",
        )
        new_content, result = apply_single_change(content, change, 0)
        assert new_content == "Hello there"

    def test_replacement_shorter_than_original(self):
        content = "Hello there"
        change = Change(
            range=ChangeRange(start=0, end=11),
            replacement="Hi",
        )
        new_content, result = apply_single_change(content, change, 0)
        assert new_content == "Hi"


class TestApplyChanges:
    def test_sequential_target_changes(self):
        content = "Party A and Party B agree. Party A pays."
        changes = [
            Change(target=ChangeTarget(text="Party A", occurrence=0), replacement="Acme"),
            Change(target=ChangeTarget(text="Party B"), replacement="Beta Inc"),
        ]
        new_content, results = apply_changes(content, changes)
        assert new_content == "Acme and Beta Inc agree. Acme pays."
        assert all(r.success for r in results)

    def test_sequential_range_changes_with_offset(self):
        content = "aaabbbccc"
        changes = [
            # Replace "aaa" (0-3) with "xx" — content becomes "xxbbbccc", delta = -1
            Change(range=ChangeRange(start=0, end=3), replacement="xx"),
            # Replace "bbb" (originally 3-6, adjusted to 2-5) with "yyyy"
            Change(range=ChangeRange(start=3, end=6), replacement="yyyy"),
        ]
        new_content, results = apply_changes(content, changes)
        assert new_content == "xxyyyyccc"
        assert all(r.success for r in results)

    def test_mixed_target_and_range_changes(self):
        content = "Hello world, Hello again"
        changes = [
            Change(target=ChangeTarget(text="Hello", occurrence=1), replacement="Hi"),
            Change(range=ChangeRange(start=13, end=24), replacement="Bye now"),
        ]
        new_content, results = apply_changes(content, changes)
        # After first: "Hi world, Hello again" (delta = -3 for positions)
        # Range 13-24 adjusted to 10-21: "Hello again" -> "Bye now"
        assert new_content == "Hi world, Bye now"
        assert all(r.success for r in results)

    def test_partial_failure(self):
        content = "Hello world"
        changes = [
            Change(target=ChangeTarget(text="xyz"), replacement="abc"),  # fails
            Change(target=ChangeTarget(text="world"), replacement="earth"),  # succeeds
        ]
        new_content, results = apply_changes(content, changes)
        assert new_content == "Hello earth"
        assert results[0].success is False
        assert results[1].success is True


class TestDeterministicSummary:
    def test_no_successful_changes(self):
        from app.models import ChangeResult

        results = [ChangeResult(index=0, success=False, detail="not found")]
        assert generate_deterministic_summary(results) == "No changes were applied."

    def test_single_replacement(self):
        from app.models import ChangeResult

        results = [
            ChangeResult(
                index=0, success=True, detail="ok",
                original_text="old", replacement_text="new",
            )
        ]
        summary = generate_deterministic_summary(results)
        assert "Replaced 'old' with 'new'" in summary

    def test_multiple_replacements(self):
        from app.models import ChangeResult

        results = [
            ChangeResult(index=0, success=True, detail="ok", original_text="a", replacement_text="b"),
            ChangeResult(index=1, success=True, detail="ok", original_text="c", replacement_text="d"),
        ]
        summary = generate_deterministic_summary(results)
        assert ";" in summary
