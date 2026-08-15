"""Layout-aware chunking for Docling documents."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any

SECTION_HEADING_MAX_LEN = 500
EMBEDDING_TOKENIZER_MODEL = "sentence-transformers/all-MiniLM-L6-v2"


@dataclass(frozen=True, slots=True)
class TextChunk:
    ordinal: int
    text: str
    content_hash: str
    token_count: int
    page_number: int | None = None
    section_heading: str | None = None


def estimate_token_count(text: str) -> int:
    """Approximate tokens without a tokenizer dependency (words ≈ tokens)."""
    return len(text.split())


def content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _page_number_from_meta(meta: Any) -> int | None:
    """Return the first provenance page number from chunk meta, if any."""
    doc_items = getattr(meta, "doc_items", None) or []
    for item in doc_items:
        for prov in getattr(item, "prov", None) or []:
            page_no = getattr(prov, "page_no", None)
            if page_no is not None:
                return int(page_no)
    return None


def _section_heading_from_meta(meta: Any) -> str | None:
    """Join Docling headings with ' > ', clipped to the DB column limit."""
    headings = getattr(meta, "headings", None)
    if not headings:
        return None
    joined = " > ".join(str(heading) for heading in headings if heading)
    if not joined:
        return None
    return joined[:SECTION_HEADING_MAX_LEN]


def chunk_docling_document(document: Any) -> list[TextChunk]:
    """Chunk a DoclingDocument with HybridChunker (MiniLM tokenizer).

    Stored text is ``chunker.contextualize(chunk)`` so embeddings include heading
    context. Table markdown is preserved (no normalize + word-split flatten).
    """
    from docling_core.transforms.chunker.hybrid_chunker import HybridChunker
    from docling_core.transforms.chunker.tokenizer.huggingface import HuggingFaceTokenizer
    from transformers import AutoTokenizer

    # MiniLM max_seq_length is 256 (sentence_bert_config); do not rely on BERT's 512 default.
    tokenizer = HuggingFaceTokenizer(
        tokenizer=AutoTokenizer.from_pretrained(EMBEDDING_TOKENIZER_MODEL),
        max_tokens=256,
    )
    chunker = HybridChunker(
        tokenizer=tokenizer,
        merge_peers=True,
        repeat_table_header=True,
    )

    chunks: list[TextChunk] = []
    seen_hashes: set[str] = set()
    ordinal = 1
    for chunk in chunker.chunk(dl_doc=document):
        text = chunker.contextualize(chunk).strip()
        if not text:
            continue
        digest = content_hash(text)
        if digest in seen_hashes:
            continue
        seen_hashes.add(digest)
        try:
            token_count = int(tokenizer.count_tokens(text))
        except Exception:
            token_count = estimate_token_count(text)
        chunks.append(
            TextChunk(
                ordinal=ordinal,
                text=text,
                content_hash=digest,
                token_count=token_count,
                page_number=_page_number_from_meta(chunk.meta),
                section_heading=_section_heading_from_meta(chunk.meta),
            )
        )
        ordinal += 1
    return chunks
