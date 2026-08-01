from pathlib import Path

from education_platform.core.config import get_settings


class LocalObjectStorage:
    """Development adapter; production can replace this with an S3-compatible adapter."""

    def __init__(self) -> None:
        self.root = Path(get_settings().local_storage_path)

    async def save(self, object_key: str, content: bytes) -> None:
        target = self.root / object_key
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)

    async def read(self, object_key: str) -> bytes:
        return (self.root / object_key).read_bytes()


storage = LocalObjectStorage()
