"""Central configuration. All secrets and swappable knobs live here.

Load order: process env > .env file (via pydantic-settings). The single most
important knob is `model_id` — change it to swap LLMs through OpenRouter.
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # --- LLM via OpenRouter (OpenAI-compatible) ---
    openrouter_api_key: str = ""
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    # Swap this to change models later (e.g. "openai/gpt-4o", "google/gemini-2.5-pro").
    model_id: str = "anthropic/claude-opus-4-8"

    # --- Ingestion: Unstructured serverless ---
    unstructured_api_key: str = ""
    unstructured_api_url: str = "https://api.unstructuredapp.io"

    # --- Truth store: MongoDB Atlas ---
    mongodb_uri: str = ""
    mongodb_db: str = "lexigraph"

    # --- Vector store: Qdrant Cloud ---
    qdrant_url: str = ""
    qdrant_api_key: str = ""
    qdrant_collection: str = "index_a"

    # --- Retrieval: Cohere rerank ---
    cohere_api_key: str = ""
    cohere_rerank_model: str = "rerank-v3.5"

    # --- Embeddings (fastembed local defaults) ---
    dense_embed_model: str = "BAAI/bge-small-en-v1.5"
    dense_embed_dim: int = 384
    sparse_embed_model: str = "Qdrant/bm25"

    # --- Chunking ---
    parent_max_chars: int = 1500
    child_target_tokens: int = 256
    child_overlap_tokens: int = 20


@lru_cache
def get_settings() -> Settings:
    """Cached singleton so we parse env once per process."""
    return Settings()
