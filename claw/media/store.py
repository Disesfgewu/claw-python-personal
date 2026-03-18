from __future__ import annotations
import os
import uuid
import aiofiles


class MediaStore:
    def __init__(self, base_dir: str = "~/.claw/media"):
        self.base_dir = os.path.expanduser(base_dir)

    def _ensure_dir(self) -> None:
        os.makedirs(self.base_dir, exist_ok=True)

    async def save(self, data: bytes, mime_type: str, filename: str = "") -> str:
        self._ensure_dir()
        ext = filename.rsplit(".", 1)[-1] if "." in filename else mime_type.split("/")[-1]
        path = os.path.join(self.base_dir, f"{uuid.uuid4().hex}.{ext}")
        async with aiofiles.open(path, "wb") as f:
            await f.write(data)
        return path

    async def load(self, path: str) -> bytes:
        async with aiofiles.open(path, "rb") as f:
            return await f.read()

    async def delete(self, path: str) -> None:
        try:
            os.remove(path)
        except FileNotFoundError:
            pass
