"""Integration tests for search endpoints."""


class TestSearchScoring:
    """Tests for hybrid search scoring (tsvector + pgvector)."""

    def test_search_results_include_score_and_breakdown(self, client, sample_doc):
        resp = client.get("/search?q=confidential")
        data = resp.json()
        assert data["total_matches"] >= 1
        result = data["results"][0]
        assert "score" in result
        assert result["score"] >= 0
        breakdown = result["score_breakdown"]
        assert breakdown is not None
        assert "text_score" in breakdown
        assert "text_weight" in breakdown

    def test_results_sorted_by_score(self, client):
        """More relevant documents should appear first."""
        client.post("/documents", json={
            "title": "Low relevance",
            "content": "This document mentions contract once"
        })
        client.post("/documents", json={
            "title": "High relevance",
            "content": "contract contract contract clause contract terms contract"
        })
        resp = client.get("/search?q=contract")
        data = resp.json()
        results = data["results"]
        assert len(results) >= 2
        scores = [r["score"] for r in results]
        assert scores == sorted(scores, reverse=True)

    def test_single_doc_search_includes_score(self, client, sample_doc):
        resp = client.get(f"/documents/{sample_doc['id']}/search?q=Agreement")
        data = resp.json()
        if data["results"]:
            assert data["results"][0]["score"] >= 0

    def test_no_semantic_score_without_embeddings(self, client, sample_doc):
        """Without embeddings available, semantic_score should be None."""
        resp = client.get("/search?q=confidential")
        data = resp.json()
        if data["results"]:
            breakdown = data["results"][0]["score_breakdown"]
            assert breakdown["semantic_score"] is None
            assert breakdown["text_weight"] == 1.0
            assert breakdown["semantic_weight"] == 0.0


class TestSearchAcrossDocuments:
    def test_search_finds_match(self, client, sample_doc):
        resp = client.get("/search?q=confidential")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_matches"] >= 1
        assert data["results"][0]["document_id"] == sample_doc["id"]
        assert data["results"][0]["snippets"][0]["text"].lower() == "confidential"

    def test_search_no_results(self, client, sample_doc):
        resp = client.get("/search?q=xyznonexistent")
        data = resp.json()
        assert data["total_matches"] == 0
        assert data["results"] == []

    def test_search_multiple_documents(self, client):
        client.post("/documents", json={"title": "Doc A", "content": "The contract is binding"})
        client.post("/documents", json={"title": "Doc B", "content": "This contract is void"})
        client.post("/documents", json={"title": "Doc C", "content": "No relevant text here"})

        resp = client.get("/search?q=contract")
        data = resp.json()
        assert data["total_matches"] == 2
        assert len(data["results"]) == 2

    def test_search_pagination(self, client):
        for i in range(5):
            client.post("/documents", json={"title": f"Doc {i}", "content": f"contract clause {i}"})

        resp = client.get("/search?q=contract&limit=2&offset=0")
        data = resp.json()
        assert len(data["results"]) == 2
        assert data["total_matches"] == 5

    def test_search_empty_query_rejected(self, client):
        resp = client.get("/search?q=")
        assert resp.status_code == 422

    def test_search_case_insensitive(self, client):
        client.post("/documents", json={"title": "Test", "content": "CONFIDENTIAL information"})
        resp = client.get("/search?q=confidential")
        data = resp.json()
        assert data["total_matches"] >= 1


class TestSearchInDocument:
    def test_search_in_specific_document(self, client, sample_doc):
        resp = client.get(f"/documents/{sample_doc['id']}/search?q=Party A")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_matches"] >= 1

    def test_search_in_document_not_found(self, client):
        resp = client.get("/documents/nonexistent-id/search?q=test")
        assert resp.status_code == 404

    def test_search_in_document_no_match(self, client, sample_doc):
        resp = client.get(f"/documents/{sample_doc['id']}/search?q=xyznonexistent")
        data = resp.json()
        assert data["total_matches"] == 0

    def test_snippets_include_context(self, client, sample_doc):
        resp = client.get(f"/documents/{sample_doc['id']}/search?q=Agreement")
        data = resp.json()
        snippets = data["results"][0]["snippets"]
        assert snippets[0]["text"] == "Agreement"
        # context_before or context_after should be non-empty for mid-document matches
        has_context = any(s["context_before"] or s["context_after"] for s in snippets)
        assert has_context


class TestSearchIndexSync:
    """Verify the inverted index stays in sync with document writes."""

    def test_new_document_is_searchable_via_index(self, client):
        """Documents created after startup should be findable via search."""
        client.post(
            "/documents",
            json={"title": "New Doc", "content": "supercalifragilistic content"},
        )
        resp = client.get("/search?q=supercalifragilistic")
        data = resp.json()
        assert data["total_matches"] == 1

    def test_updated_document_reflects_in_search(self, client, sample_doc):
        """After a redline change, search should find the new text."""
        client.patch(
            f"/documents/{sample_doc['id']}",
            json={
                "version": 1,
                "changes": [
                    {"target": {"text": "Party A", "occurrence": 0}, "replacement": "Xylophone Corp"},
                ],
            },
        )
        resp = client.get("/search?q=Xylophone")
        data = resp.json()
        assert data["total_matches"] >= 1

    def test_deleted_document_removed_from_search(self, client, sample_doc):
        """After deleting a document, it should not appear in search results."""
        # Verify it's searchable first
        resp = client.get("/search?q=confidential")
        assert resp.json()["total_matches"] >= 1

        # Delete it
        client.delete(f"/documents/{sample_doc['id']}")

        # Should no longer appear
        resp = client.get("/search?q=confidential")
        assert resp.json()["total_matches"] == 0
