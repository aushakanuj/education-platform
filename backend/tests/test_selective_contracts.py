"""Unit tests for selective RAG/materials Pydantic contracts."""

from __future__ import annotations

from uuid import uuid4

import pytest
from pydantic import ValidationError

from education_platform.modules.materials.markdown_parser import (
    AnswerKeyEntry,
    ParsedOption,
    ParsedQuestion,
)
from education_platform.modules.rag.chunking import content_hash
from education_platform.modules.rag.contracts import (
    IngestJobClaim,
    TextChunk,
    VectorRow,
    parse_required_roles,
)


def test_text_chunk_rejects_blank_and_bad_hash() -> None:
    with pytest.raises(ValidationError):
        TextChunk(
            ordinal=1,
            text="   ",
            content_hash=content_hash("x"),
            token_count=1,
        )
    with pytest.raises(ValidationError):
        TextChunk(
            ordinal=1,
            text="ok",
            content_hash="not-a-sha",
            token_count=1,
        )


def test_vector_row_enforces_embedding_dims_and_roles() -> None:
    base = {
        "chunk_id": uuid4(),
        "doc_id": uuid4(),
        "doc_kind": "knowledge_document_version",
        "institution_id": uuid4(),
        "doc_type": "policy",
        "page_number": 1,
        "version_id": uuid4(),
    }
    with pytest.raises(ValidationError):
        VectorRow(**base, embedding=[0.1] * 10, required_roles=["administrator"])
    with pytest.raises(ValidationError):
        VectorRow(**base, embedding=[0.1] * 384, required_roles=["hacker"])
    ok = VectorRow(**base, embedding=[0.1] * 384, required_roles=["administrator", "teacher"])
    assert len(ok.embedding) == 384


def test_parse_required_roles_defaults_and_rejects_unknown() -> None:
    assert parse_required_roles(None) == ["administrator", "teacher"]
    assert parse_required_roles('["student"]') == ["student"]
    assert parse_required_roles("administrator, teacher") == ["administrator", "teacher"]
    with pytest.raises(ValidationError):
        parse_required_roles("administrator,root")


def test_ingest_job_claim_from_mapping() -> None:
    job_id = uuid4()
    target_id = uuid4()
    claim = IngestJobClaim(id=job_id, knowledge_document_version_id=target_id)
    assert claim.knowledge_document_version_id == target_id
    assert claim.source_material_version_id is None


def test_ingest_job_claim_rejects_zero_or_two_targets() -> None:
    job_id = uuid4()
    with pytest.raises(ValidationError):
        IngestJobClaim(id=job_id)
    with pytest.raises(ValidationError):
        IngestJobClaim(
            id=job_id,
            source_material_version_id=uuid4(),
            knowledge_document_version_id=uuid4(),
        )


def test_parsed_question_requires_options_and_unique_labels() -> None:
    with pytest.raises(ValidationError):
        ParsedQuestion(number=1, prompt="Q?", options=[], correct_option_label="A")
    with pytest.raises(ValidationError):
        ParsedQuestion(
            number=1,
            prompt="Q?",
            options=[
                ParsedOption(label="A", text="one"),
                ParsedOption(label="A", text="two"),
            ],
            correct_option_label="A",
        )
    entry = AnswerKeyEntry(label="B", explanation="because")
    assert entry.label == "B"
