from __future__ import annotations

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql://postgres:postgres@localhost:5433/redline"

    # Used for summarizing changes, deterministic fallback in code 
    llm_api_key: str = ""
    llm_base_url: str = "https://api.openai.com/v1"
    llm_model: str = "gpt-4o-mini"
    llm_timeout: float = 10.0

    # determines how much to display in search results
    search_context_chars: int = 80

    # possible to use a better model to improve semantic search
    embedding_base_url: str = "https://api.jina.ai/v1"
    embedding_api_key: str = ""
    embedding_model: str = "jina-embeddings-v2-base-en"

    # tune to improve search performance for the given context
    search_text_weight: float = 0.6
    search_semantic_threshold: float = 0.75
    search_min_score: float = 0.0
    search_semantic_only_discount: float = 0.5

    model_config = {"env_prefix": "REDLINE_", "env_file": ".env"}


settings = Settings()
