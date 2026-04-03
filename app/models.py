from __future__ import annotations

from pydantic import BaseModel, Field, model_validator


# --- Change request models ---


class ChangeTarget(BaseModel):
    """Occurrence-based targeting: find text and replace the Nth occurrence."""

    text: str
    occurrence: int = Field(
        default=1,
        description="1-indexed occurrence to replace. 0 means replace all.",
    )


class ChangeRange(BaseModel):
    """Position-based targeting: replace text between start and end offsets."""

    start: int = Field(ge=0)
    end: int = Field(ge=0)


class Change(BaseModel):
    """A single change operation within a redline request."""

    operation: str = Field(default="replace", pattern="^replace$")
    target: ChangeTarget | None = None
    range: ChangeRange | None = None
    replacement: str

    @model_validator(mode="after")
    def check_target_or_range(self) -> "Change":
        if self.target is None and self.range is None:
            raise ValueError("Either 'target' or 'range' must be provided")
        if self.target is not None and self.range is not None:
            raise ValueError("Provide either 'target' or 'range', not both")
        return self


class ContentUpdate(BaseModel):
    """Full content update from inline editing."""

    content: str
    version: int = Field(ge=1)


class RedlineRequest(BaseModel):
    """Request body for PATCH /documents/{id}."""

    version: int = Field(ge=1)
    changes: list[Change] = Field(min_length=1)


# --- Change result models ---


class ChangeResult(BaseModel):
    index: int
    success: bool
    detail: str
    original_text: str = ""
    replacement_text: str = ""
    position: int = -1


# --- Document models ---


class DocumentCreate(BaseModel):
    title: str = Field(min_length=1, max_length=500)
    content: str


class DocumentResponse(BaseModel):
    id: str
    title: str
    content: str
    version: int
    created_at: str
    updated_at: str
    frozen_at: str | None = None


class FreezeRequest(BaseModel):
    """Freeze a document to enter redlining phase."""
    pass  # No body needed, but having the model is cleaner


class DocumentListResponse(BaseModel):
    documents: list[DocumentResponse]
    total: int
    limit: int
    offset: int


class RedlineResponse(BaseModel):
    id: str
    content: str
    version: int
    changes_applied: int
    results: list[ChangeResult]
    summary: str


# --- History models ---


class HistoryEntry(BaseModel):
    id: str
    version: int
    changes_json: str
    summary: str | None
    created_at: str
    phase: str = "drafting"  # "drafting" or "redlining"


class HistoryResponse(BaseModel):
    document_id: str
    history: list[HistoryEntry]


# --- Search models ---


# --- Suggestion models ---


class SuggestionCreate(BaseModel):
    original_text: str = Field(min_length=1)
    replacement_text: str
    position: int = Field(ge=0)
    author: str = Field(min_length=1, max_length=50)


class CommentCreate(BaseModel):
    author: str = Field(default="User", max_length=100)
    content: str = Field(min_length=1)


class CommentResponse(BaseModel):
    id: str
    author: str
    content: str
    created_at: str


class SuggestionResponse(BaseModel):
    id: str
    document_id: str
    original_text: str
    replacement_text: str
    position: int
    author: str
    status: str  # pending, accepted, rejected
    created_at: str
    resolved_at: str | None
    resolved_by: str | None = None
    comments: list[CommentResponse]


class SuggestionListResponse(BaseModel):
    document_id: str
    suggestions: list[SuggestionResponse]
    total: int


# --- Search models ---


class SearchSnippet(BaseModel):
    text: str
    position: int
    context_before: str
    context_after: str


class ScoreBreakdown(BaseModel):
    text_score: float
    semantic_score: float | None = None
    text_weight: float
    semantic_weight: float


class SearchDocumentResult(BaseModel):
    document_id: str
    document_title: str
    snippets: list[SearchSnippet]
    score: float = 0.0
    score_breakdown: ScoreBreakdown | None = None


class SearchResponse(BaseModel):
    query: str
    results: list[SearchDocumentResult]
    total_matches: int
