"""Integration tests for document CRUD and redline endpoints."""

from unittest.mock import patch

import pytest
from tests.conftest import SAMPLE_CONTENT, SAMPLE_TITLE


class TestCreateDocument:
    def test_create_success(self, client):
        resp = client.post("/documents", json={"title": "Test", "content": "Hello"})
        assert resp.status_code == 201
        data = resp.json()
        assert data["title"] == "Test"
        assert data["content"] == "Hello"
        assert data["version"] == 1
        assert "id" in data

    def test_create_empty_title_rejected(self, client):
        resp = client.post("/documents", json={"title": "", "content": "Hello"})
        assert resp.status_code == 422


class TestGetDocument:
    def test_get_success(self, client, sample_doc):
        resp = client.get(f"/documents/{sample_doc['id']}")
        assert resp.status_code == 200
        assert resp.json()["id"] == sample_doc["id"]

    def test_get_not_found(self, client):
        resp = client.get("/documents/nonexistent-id")
        assert resp.status_code == 404
        assert resp.json()["code"] == 404


class TestListDocuments:
    def test_list_empty(self, client):
        resp = client.get("/documents")
        assert resp.status_code == 200
        data = resp.json()
        assert data["documents"] == []
        assert data["total"] == 0

    def test_list_with_documents(self, client, sample_doc):
        resp = client.get("/documents")
        data = resp.json()
        assert data["total"] == 1
        assert data["documents"][0]["id"] == sample_doc["id"]

    def test_list_pagination(self, client):
        for i in range(5):
            client.post("/documents", json={"title": f"Doc {i}", "content": f"Content {i}"})
        resp = client.get("/documents?limit=2&offset=0")
        data = resp.json()
        assert data["total"] == 5
        assert len(data["documents"]) == 2


class TestDeleteDocument:
    def test_delete_success(self, client, sample_doc):
        resp = client.delete(f"/documents/{sample_doc['id']}")
        assert resp.status_code == 204
        # Verify deleted
        resp = client.get(f"/documents/{sample_doc['id']}")
        assert resp.status_code == 404

    def test_delete_not_found(self, client):
        resp = client.delete("/documents/nonexistent-id")
        assert resp.status_code == 404


class TestRedlineDocument:
    def test_replace_by_target(self, client, sample_doc):
        resp = client.patch(
            f"/documents/{sample_doc['id']}",
            json={
                "version": 1,
                "changes": [
                    {
                        "target": {"text": "Party A", "occurrence": 1},
                        "replacement": "Acme Corp",
                    }
                ],
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["version"] == 2
        assert data["changes_applied"] == 1
        assert "Acme Corp" in data["content"]
        # Only first occurrence replaced
        assert data["content"].count("Acme Corp") == 1

    def test_replace_all_occurrences(self, client, sample_doc):
        resp = client.patch(
            f"/documents/{sample_doc['id']}",
            json={
                "version": 1,
                "changes": [
                    {
                        "target": {"text": "Party A", "occurrence": 0},
                        "replacement": "Acme Corp",
                    }
                ],
            },
        )
        data = resp.json()
        assert data["changes_applied"] == 1
        assert "Party A" not in data["content"]

    def test_replace_by_range(self, client, sample_doc):
        resp = client.patch(
            f"/documents/{sample_doc['id']}",
            json={
                "version": 1,
                "changes": [
                    {
                        "range": {"start": 0, "end": 4},
                        "replacement": "That",
                    }
                ],
            },
        )
        data = resp.json()
        assert data["content"].startswith("That")
        assert data["version"] == 2

    def test_bulk_changes(self, client, sample_doc):
        resp = client.patch(
            f"/documents/{sample_doc['id']}",
            json={
                "version": 1,
                "changes": [
                    {"target": {"text": "Party A", "occurrence": 0}, "replacement": "Acme"},
                    {"target": {"text": "Party B", "occurrence": 0}, "replacement": "Beta Inc"},
                ],
            },
        )
        data = resp.json()
        assert data["changes_applied"] == 2
        assert "Party A" not in data["content"]
        assert "Party B" not in data["content"]

    def test_target_not_found_partial_success(self, client, sample_doc):
        resp = client.patch(
            f"/documents/{sample_doc['id']}",
            json={
                "version": 1,
                "changes": [
                    {"target": {"text": "NONEXISTENT"}, "replacement": "X"},
                    {"target": {"text": "Party A", "occurrence": 1}, "replacement": "Acme"},
                ],
            },
        )
        data = resp.json()
        assert data["changes_applied"] == 1
        assert data["results"][0]["success"] is False
        assert data["results"][1]["success"] is True

    def test_document_not_found(self, client):
        resp = client.patch(
            "/documents/nonexistent-id",
            json={"version": 1, "changes": [{"target": {"text": "a"}, "replacement": "b"}]},
        )
        assert resp.status_code == 404

    def test_invalid_payload_no_changes(self, client, sample_doc):
        resp = client.patch(
            f"/documents/{sample_doc['id']}",
            json={"version": 1, "changes": []},
        )
        assert resp.status_code == 422

    def test_summary_in_response(self, client, sample_doc):
        resp = client.patch(
            f"/documents/{sample_doc['id']}",
            json={
                "version": 1,
                "changes": [
                    {"target": {"text": "Party A", "occurrence": 1}, "replacement": "Acme"},
                ],
            },
        )
        data = resp.json()
        assert data["summary"]  # non-empty summary
        assert "Acme" in data["summary"] or "Party A" in data["summary"]


class TestChangeHistory:
    def test_history_after_changes(self, client, sample_doc):
        # Apply a change
        client.patch(
            f"/documents/{sample_doc['id']}",
            json={
                "version": 1,
                "changes": [{"target": {"text": "Party A", "occurrence": 1}, "replacement": "Acme"}],
            },
        )
        resp = client.get(f"/documents/{sample_doc['id']}/history")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["history"]) == 1
        assert data["history"][0]["version"] == 2
        assert data["history"][0]["summary"]  # non-empty summary

    def test_history_empty(self, client, sample_doc):
        resp = client.get(f"/documents/{sample_doc['id']}/history")
        data = resp.json()
        assert data["history"] == []

    def test_history_document_not_found(self, client):
        resp = client.get("/documents/nonexistent-id/history")
        assert resp.status_code == 404


class TestConcurrency:
    def test_sequential_version_increments(self, client, sample_doc):
        """Two sequential PATCH requests should bump version correctly."""
        resp1 = client.patch(
            f"/documents/{sample_doc['id']}",
            json={
                "version": 1,
                "changes": [{"target": {"text": "Party A", "occurrence": 1}, "replacement": "Acme"}],
            },
        )
        assert resp1.status_code == 200
        assert resp1.json()["version"] == 2

        resp2 = client.patch(
            f"/documents/{sample_doc['id']}",
            json={
                "version": 2,
                "changes": [{"target": {"text": "Party B", "occurrence": 1}, "replacement": "Beta"}],
            },
        )
        assert resp2.status_code == 200
        assert resp2.json()["version"] == 3

    def test_stale_version_rejected(self, client, sample_doc):
        """A PATCH with a stale version (after another update) should return 409."""
        # First update succeeds
        client.patch(
            f"/documents/{sample_doc['id']}",
            json={
                "version": 1,
                "changes": [{"target": {"text": "Party A", "occurrence": 1}, "replacement": "Acme"}],
            },
        )
        # Second update with stale version=1 should fail
        resp = client.patch(
            f"/documents/{sample_doc['id']}",
            json={
                "version": 1,
                "changes": [{"target": {"text": "Party B"}, "replacement": "Beta"}],
            },
        )
        assert resp.status_code == 409


class TestFreezeDocument:
    def test_freeze_success(self, client, sample_doc):
        resp = client.post(f"/documents/{sample_doc['id']}/freeze")
        assert resp.status_code == 200
        data = resp.json()
        assert data["frozen_at"] is not None

    def test_freeze_already_frozen(self, client, sample_doc):
        client.post(f"/documents/{sample_doc['id']}/freeze")
        resp = client.post(f"/documents/{sample_doc['id']}/freeze")
        assert resp.status_code == 409

    def test_freeze_not_found(self, client):
        resp = client.post("/documents/nonexistent/freeze")
        assert resp.status_code == 404


class TestContentUpdate:
    def test_update_content(self, client, sample_doc):
        resp = client.put(
            f"/documents/{sample_doc['id']}/content",
            json={"content": "Updated content here.", "version": 1},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["content"] == "Updated content here."
        assert data["version"] == 2

    def test_update_version_conflict(self, client, sample_doc):
        resp = client.put(
            f"/documents/{sample_doc['id']}/content",
            json={"content": "New", "version": 999},
        )
        assert resp.status_code == 409

    def test_update_frozen_doc_blocked(self, client, sample_doc):
        client.post(f"/documents/{sample_doc['id']}/freeze")
        resp = client.put(
            f"/documents/{sample_doc['id']}/content",
            json={"content": "Sneaky edit", "version": 1},
        )
        assert resp.status_code == 403

    def test_update_records_history(self, client, sample_doc):
        client.put(
            f"/documents/{sample_doc['id']}/content",
            json={"content": "Changed text.", "version": 1},
        )
        resp = client.get(f"/documents/{sample_doc['id']}/history")
        history = resp.json()["history"]
        assert len(history) == 1
        assert history[0]["summary"]  # non-empty summary


class TestEdgeCases:
    def test_empty_content_document(self, client):
        resp = client.post("/documents", json={"title": "Empty", "content": ""})
        assert resp.status_code == 201
        assert resp.json()["content"] == ""

    def test_redline_empty_document(self, client):
        resp = client.post("/documents", json={"title": "Empty", "content": ""})
        doc = resp.json()
        resp = client.patch(
            f"/documents/{doc['id']}",
            json={
                "version": 1,
                "changes": [{"target": {"text": "anything"}, "replacement": "new"}],
            },
        )
        data = resp.json()
        assert data["changes_applied"] == 0
        assert data["results"][0]["success"] is False

    def test_malformed_json_returns_422(self, client, sample_doc):
        resp = client.patch(
            f"/documents/{sample_doc['id']}",
            content=b"not json",
            headers={"Content-Type": "application/json"},
        )
        assert resp.status_code == 422
        data = resp.json()
        assert data["code"] == 422

    def test_missing_required_field(self, client, sample_doc):
        resp = client.patch(
            f"/documents/{sample_doc['id']}",
            json={"changes": [{"target": {"text": "a"}, "replacement": "b"}]},
        )
        assert resp.status_code == 422

    def test_llm_failure_uses_deterministic_fallback(self, client, sample_doc):
        """When LLM is configured but fails, the service should still return a summary."""
        with patch("app.services.llm.settings") as mock_settings:
            mock_settings.llm_api_key = "fake-key"
            mock_settings.llm_base_url = "http://localhost:1"  # unreachable
            mock_settings.llm_model = "test"
            mock_settings.llm_timeout = 0.1

            resp = client.patch(
                f"/documents/{sample_doc['id']}",
                json={
                    "version": 1,
                    "changes": [
                        {"target": {"text": "Party A", "occurrence": 1}, "replacement": "Acme"},
                    ],
                },
            )
            assert resp.status_code == 200
            data = resp.json()
            # Should still have a deterministic summary despite LLM failure
            assert data["summary"]
            assert "Party A" in data["summary"] or "Acme" in data["summary"]
