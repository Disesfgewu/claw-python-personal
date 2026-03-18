from __future__ import annotations
import base64
import httpx
from claw.media.mime import guess_mime
from claw.media.store import MediaStore


async def prepare_media_message(
    file_data: bytes,
    mime_type: str,
    store: MediaStore,
    llm_router_url: str,
    api_key: str = "",
) -> str:
    """
    Convert media into agent-understandable content description.
    - Image/PDF: POST to LLM-Router /v1/file/generate_content, return description text
    - Audio: POST to LLM-Router /v1/audio/transcriptions, return transcription
    - Other: Save to MediaStore, return path
    """
    b64 = base64.b64encode(file_data).decode()
    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}

    if mime_type.startswith("image/") or mime_type == "application/pdf":
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(
                f"{llm_router_url}/v1/file/generate_content",
                json={"data": b64, "mime_type": mime_type},
                headers=headers,
            )
            resp.raise_for_status()
            return resp.json().get("text", "(Cannot parse media content)")

    if mime_type.startswith("audio/"):
        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post(
                f"{llm_router_url}/v1/audio/transcriptions",
                json={"data": b64, "mime_type": mime_type},
                headers=headers,
            )
            resp.raise_for_status()
            return resp.json().get("text", "(Transcription failed)")

    path = await store.save(file_data, mime_type)
    return f"[Media file saved: {path}]"
