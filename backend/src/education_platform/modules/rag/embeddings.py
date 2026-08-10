"""Local sentence-transformers embeddings (lazy-loaded)."""

from __future__ import annotations

from typing import Any

from education_platform.core.config import get_settings

_model: Any | None = None


def embedding_dimensions() -> int:
    # all-MiniLM-L6-v2
    return 384


def _load_model() -> Any:
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer

        settings = get_settings()
        _model = SentenceTransformer(settings.embedding_model_name)
    return _model


def embed_texts(texts: list[str]) -> list[list[float]]:
    if not texts:
        return []
    model = _load_model()
    vectors = model.encode(texts, normalize_embeddings=True, show_progress_bar=False)
    return [list(map(float, row)) for row in vectors]


def reset_embedding_model() -> None:
    """Test helper to clear the cached model."""
    global _model
    _model = None
