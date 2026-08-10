"""Text normalization and chunking for ingest."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

_WHITESPACE_RE = re.compile(r"[ \t]+")
_BLANK_LINES_RE = re.compile(r"\n{3,}")
_HEADER_FOOTER_RE = re.compile(
    r"^(page\s+\d+(\s+of\s+\d+)?|confidential|draft)\s*$",
    re.IGNORECASE | re.MULTILINE,
)

DEFAULT_CHUNK_TOKENS = 400
DEFAULT_OVERLAP_RATIO = 0.15


@dataclass(frozen=True, slots=True)
class TextChunk:
    ordinal: int
    text: str
    content_hash: str
    token_count: int
    page_number: int | None = None
    section_heading: str | None = None


def normalize_text(text: str) -> str:
    cleaned = text.replace("\r\n", "\n").replace("\r", "\n")
    cleaned = _HEADER_FOOTER_RE.sub("", cleaned)
    cleaned = _WHITESPACE_RE.sub(" ", cleaned)
    cleaned = _BLANK_LINES_RE.sub("\n\n", cleaned)
    return cleaned.strip()


def estimate_token_count(text: str) -> int:
    """Approximate tokens without a tokenizer dependency (words ≈ tokens)."""
    return len(text.split())


def content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def chunk_text(
    text: str,
    *,
    chunk_tokens: int = DEFAULT_CHUNK_TOKENS,
    overlap_ratio: float = DEFAULT_OVERLAP_RATIO,
    page_number: int | None = None,
    section_heading: str | None = None,
) -> list[TextChunk]:
    normalized = normalize_text(text)
    if not normalized:
        return []

    words = normalized.split()
    if not words:
        return []

    overlap = max(1, int(chunk_tokens * overlap_ratio))
    step = max(1, chunk_tokens - overlap)
    chunks: list[TextChunk]
    chunks = []
    seen_hashes: set[str] = set()
    ordinal = 1
    start = 0
    while start < len(words):
        end = min(len(words), start + chunk_tokens)
        piece = " ".join(words[start:end]).strip()
        if piece:
            digest = content_hash(piece)
            if digest not in seen_hashes:
                seen_hashes.add(digest)
                chunks.append(
                    TextChunk(
                        ordinal=ordinal,
                        text=piece,
                        content_hash=digest,
                        token_count=estimate_token_count(piece),
                        page_number=page_number,
                        section_heading=section_heading,
                    )
                )
                ordinal += 1
        if end >= len(words):
            break
        start += step
    return chunks
