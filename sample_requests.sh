#!/bin/bash
# Sample requests for the Redline Service API
# Usage: Start the server first with `make dev` or `uvicorn app.main:app --port 8000`

BASE_URL="http://localhost:8000"

echo "=== Health Check ==="
curl -s "$BASE_URL/health" | python -m json.tool

# ─── Document CRUD ──────────────────────────────────────────────

echo -e "\n=== Create Document ==="
DOC=$(curl -s -X POST "$BASE_URL/documents" \
  -H "Content-Type: application/json" \
  -d '{
    "title": "NDA Agreement",
    "content": "This Non-Disclosure Agreement (the \"Agreement\") is entered into by and between Party A (\"Disclosing Party\") and Party B (\"Receiving Party\"). Party A agrees to disclose certain confidential information to Party B. Party B agrees not to disclose such information to any third party. This Agreement shall be governed by the laws of the State of Delaware."
  }')
echo "$DOC" | python -m json.tool
DOC_ID=$(echo "$DOC" | python -c "import sys,json; print(json.load(sys.stdin)['id'])")

echo -e "\n=== Get Document ==="
curl -s "$BASE_URL/documents/$DOC_ID" | python -m json.tool

echo -e "\n=== List Documents ==="
curl -s "$BASE_URL/documents?limit=5&offset=0" | python -m json.tool

# ─── Inline Editing (auto-save) ─────────────────────────────────

echo -e "\n=== Inline Edit (PUT content with version) ==="
curl -s -X PUT "$BASE_URL/documents/$DOC_ID/content" \
  -H "Content-Type: application/json" \
  -d "{
    \"content\": \"This Non-Disclosure Agreement (the 'Agreement') is entered into by and between Party A ('Disclosing Party') and Party B ('Receiving Party'). Party A agrees to disclose certain confidential information to Party B. Party B agrees not to disclose such information to any third party. This Agreement shall be governed by the laws of the State of California.\",
    \"version\": 1
  }" | python -m json.tool

# ─── Redline Changes ────────────────────────────────────────────

echo -e "\n=== Redline: Replace by target (occurrence-based) ==="
curl -s -X PATCH "$BASE_URL/documents/$DOC_ID" \
  -H "Content-Type: application/json" \
  -d "{
    \"version\": 2,
    \"changes\": [
      {
        \"target\": { \"text\": \"Party A\", \"occurrence\": 0 },
        \"replacement\": \"Acme Corp\"
      },
      {
        \"target\": { \"text\": \"Party B\", \"occurrence\": 0 },
        \"replacement\": \"Beta Inc\"
      }
    ]
  }" | python -m json.tool

echo -e "\n=== Redline: Replace by range (position-based) ==="
curl -s -X PATCH "$BASE_URL/documents/$DOC_ID" \
  -H "Content-Type: application/json" \
  -d "{
    \"version\": 3,
    \"changes\": [
      {
        \"range\": { \"start\": 0, \"end\": 4 },
        \"replacement\": \"That\"
      }
    ]
  }" | python -m json.tool

echo -e "\n=== Version Conflict (stale version) ==="
curl -s -X PATCH "$BASE_URL/documents/$DOC_ID" \
  -H "Content-Type: application/json" \
  -d "{
    \"version\": 1,
    \"changes\": [
      {
        \"target\": { \"text\": \"Agreement\" },
        \"replacement\": \"Contract\"
      }
    ]
  }" | python -m json.tool

echo -e "\n=== Change History ==="
curl -s "$BASE_URL/documents/$DOC_ID/history" | python -m json.tool

# ─── Search ─────────────────────────────────────────────────────

echo -e "\n=== Search across all documents ==="
curl -s "$BASE_URL/search?q=confidential&limit=10" | python -m json.tool

echo -e "\n=== Search within a document ==="
curl -s "$BASE_URL/documents/$DOC_ID/search?q=Agreement" | python -m json.tool

# ─── Freeze & Suggestion Workflow ───────────────────────────────

echo -e "\n=== Create a new document for suggestion demo ==="
DOC2=$(curl -s -X POST "$BASE_URL/documents" \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Employment Agreement",
    "content": "This Employment Agreement is between Employer Corp and Employee Jane Doe. The Employee shall receive a salary of $100,000 per year. The term of employment is 2 years from the effective date."
  }')
echo "$DOC2" | python -m json.tool
DOC2_ID=$(echo "$DOC2" | python -c "import sys,json; print(json.load(sys.stdin)['id'])")

echo -e "\n=== Freeze document (enter redlining phase) ==="
curl -s -X POST "$BASE_URL/documents/$DOC2_ID/freeze" | python -m json.tool

echo -e "\n=== Create a suggestion (propose a text change) ==="
SUG=$(curl -s -X POST "$BASE_URL/documents/$DOC2_ID/suggestions" \
  -H "Content-Type: application/json" \
  -d "{
    \"original_text\": \"Employee Jane Doe\",
    \"replacement_text\": \"Employee John Smith\",
    \"position\": 51,
    \"author\": \"alice\"
  }")
echo "$SUG" | python -m json.tool
SUG_ID=$(echo "$SUG" | python -c "import sys,json; print(json.load(sys.stdin)['id'])")

echo -e "\n=== Add a comment to the suggestion ==="
curl -s -X POST "$BASE_URL/documents/$DOC2_ID/suggestions/$SUG_ID/comments" \
  -H "Content-Type: application/json" \
  -d '{
    "author": "bob",
    "content": "Should we also update the salary to match the new hire?"
  }' | python -m json.tool

echo -e "\n=== List suggestions (with comments) ==="
curl -s "$BASE_URL/documents/$DOC2_ID/suggestions" | python -m json.tool

echo -e "\n=== Accept suggestion (by a different author) ==="
curl -s -X PATCH "$BASE_URL/documents/$DOC2_ID/suggestions/$SUG_ID" \
  -H "Content-Type: application/json" \
  -d '{
    "action": "accept",
    "author": "bob"
  }' | python -m json.tool

echo -e "\n=== Verify document content updated ==="
curl -s "$BASE_URL/documents/$DOC2_ID" | python -m json.tool

echo -e "\n=== List suggestions (filter: accepted) ==="
curl -s "$BASE_URL/documents/$DOC2_ID/suggestions?status=accepted" | python -m json.tool

# ─── Cleanup ────────────────────────────────────────────────────

echo -e "\n=== Delete Documents ==="
curl -s -X DELETE "$BASE_URL/documents/$DOC_ID" -w "\nHTTP Status: %{http_code}\n"
curl -s -X DELETE "$BASE_URL/documents/$DOC2_ID" -w "\nHTTP Status: %{http_code}\n"
