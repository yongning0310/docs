"""Integration tests for suggestion and comment endpoints."""

from tests.conftest import SAMPLE_CONTENT


class TestCreateSuggestion:
    def test_create_on_frozen_doc(self, client, frozen_doc):
        resp = client.post(
            f"/documents/{frozen_doc['id']}/suggestions",
            json={
                "original_text": "Party A",
                "replacement_text": "Acme Corp",
                "position": SAMPLE_CONTENT.index("Party A"),
                "author": "alice",
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["original_text"] == "Party A"
        assert data["replacement_text"] == "Acme Corp"
        assert data["author"] == "alice"
        assert data["status"] == "pending"

    def test_create_on_non_frozen_doc_rejected(self, client, sample_doc):
        resp = client.post(
            f"/documents/{sample_doc['id']}/suggestions",
            json={
                "original_text": "Party A",
                "replacement_text": "Acme Corp",
                "position": 0,
                "author": "alice",
            },
        )
        assert resp.status_code == 400

    def test_create_on_nonexistent_doc(self, client):
        resp = client.post(
            "/documents/nonexistent/suggestions",
            json={
                "original_text": "x",
                "replacement_text": "y",
                "position": 0,
                "author": "alice",
            },
        )
        assert resp.status_code == 404


class TestListSuggestions:
    def test_list_all(self, client, frozen_doc, suggestion):
        resp = client.get(f"/documents/{frozen_doc['id']}/suggestions")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert data["suggestions"][0]["id"] == suggestion["id"]

    def test_filter_by_status(self, client, frozen_doc, suggestion):
        resp = client.get(f"/documents/{frozen_doc['id']}/suggestions?status=pending")
        assert resp.json()["total"] == 1

        resp = client.get(f"/documents/{frozen_doc['id']}/suggestions?status=accepted")
        assert resp.json()["total"] == 0

    def test_list_empty(self, client, frozen_doc):
        resp = client.get(f"/documents/{frozen_doc['id']}/suggestions")
        assert resp.json()["total"] == 0


class TestAcceptSuggestion:
    def test_accept_by_different_author(self, client, frozen_doc, suggestion):
        resp = client.patch(
            f"/documents/{frozen_doc['id']}/suggestions/{suggestion['id']}",
            json={"action": "accept", "author": "bob"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "accepted"
        assert data["resolved_by"] == "bob"

        # Document content should be updated
        doc = client.get(f"/documents/{frozen_doc['id']}").json()
        assert "Acme Corp" in doc["content"]
        assert doc["version"] == frozen_doc["version"] + 1

    def test_self_approval_blocked(self, client, frozen_doc, suggestion):
        resp = client.patch(
            f"/documents/{frozen_doc['id']}/suggestions/{suggestion['id']}",
            json={"action": "accept", "author": "alice"},  # same as creator
        )
        assert resp.status_code == 403

    def test_accept_already_resolved(self, client, frozen_doc, suggestion):
        # Reject first
        client.patch(
            f"/documents/{frozen_doc['id']}/suggestions/{suggestion['id']}",
            json={"action": "reject", "author": "bob"},
        )
        # Try to accept
        resp = client.patch(
            f"/documents/{frozen_doc['id']}/suggestions/{suggestion['id']}",
            json={"action": "accept", "author": "charlie"},
        )
        assert resp.status_code == 409


class TestRejectSuggestion:
    def test_reject(self, client, frozen_doc, suggestion):
        resp = client.patch(
            f"/documents/{frozen_doc['id']}/suggestions/{suggestion['id']}",
            json={"action": "reject", "author": "bob"},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "rejected"

        # Document content should NOT change
        doc = client.get(f"/documents/{frozen_doc['id']}").json()
        assert "Acme Corp" not in doc["content"]
        assert doc["version"] == frozen_doc["version"]  # unchanged


class TestDeleteSuggestion:
    def test_delete(self, client, frozen_doc, suggestion):
        resp = client.delete(
            f"/documents/{frozen_doc['id']}/suggestions/{suggestion['id']}"
        )
        assert resp.status_code == 204

        # Should be gone
        resp = client.get(f"/documents/{frozen_doc['id']}/suggestions")
        assert resp.json()["total"] == 0

    def test_delete_nonexistent(self, client, frozen_doc):
        resp = client.delete(f"/documents/{frozen_doc['id']}/suggestions/nonexistent")
        assert resp.status_code == 404


class TestComments:
    def test_add_comment(self, client, frozen_doc, suggestion):
        resp = client.post(
            f"/documents/{frozen_doc['id']}/suggestions/{suggestion['id']}/comments",
            json={"author": "bob", "content": "Looks good to me"},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["author"] == "bob"
        assert data["content"] == "Looks good to me"

    def test_comment_appears_in_suggestion(self, client, frozen_doc, suggestion):
        client.post(
            f"/documents/{frozen_doc['id']}/suggestions/{suggestion['id']}/comments",
            json={"author": "bob", "content": "Why this change?"},
        )
        resp = client.get(f"/documents/{frozen_doc['id']}/suggestions")
        s = resp.json()["suggestions"][0]
        assert len(s["comments"]) == 1
        assert s["comments"][0]["content"] == "Why this change?"

    def test_comment_on_nonexistent_suggestion(self, client, frozen_doc):
        resp = client.post(
            f"/documents/{frozen_doc['id']}/suggestions/nonexistent/comments",
            json={"author": "bob", "content": "Hello"},
        )
        assert resp.status_code == 404
