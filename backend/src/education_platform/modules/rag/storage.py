"""Local filesystem blob storage for uploaded source PDFs."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path
from uuid import UUID, uuid4

from education_platform.core.config import get_settings

_SAFE_SEGMENT = re.compile(r"[^a-zA-Z0-9._-]+")


def ensure_upload_dir() -> Path:
    settings = get_settings()
    settings.upload_dir.mkdir(parents=True, exist_ok=True)
    return settings.upload_dir


def build_object_key(*, institution_id: UUID, kind: str, filename: str) -> str:
    safe_name = _SAFE_SEGMENT.sub("_", Path(filename).name).strip("._") or "upload.pdf"
    return f"{institution_id}/{kind}/{uuid4().hex}_{safe_name}"


def store_bytes(object_key: str, data: bytes) -> Path:
    root = ensure_upload_dir()
    path = root / object_key
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path


def resolve_blob_path(object_key: str) -> Path:
    root = ensure_upload_dir().resolve()
    path = (root / object_key).resolve()
    if not str(path).startswith(str(root)):
        raise ValueError("Invalid blob object key")
    return path


def read_bytes(object_key: str) -> bytes:
    return resolve_blob_path(object_key).read_bytes()


def delete_blob(object_key: str) -> None:
    path = resolve_blob_path(object_key)
    if path.is_file():
        path.unlink()


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()
