import mimetypes


def guess_mime(data: bytes, filename: str = "") -> str:
    """Guess MIME type. Try filename first, fallback to magic bytes."""
    if filename:
        mime, _ = mimetypes.guess_type(filename)
        if mime:
            return mime
    # Magic bytes fallback
    if data[:4] == b"\x89PNG":
        return "image/png"
    if data[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if data[:4] == b"%PDF":
        return "application/pdf"
    if data[:3] in (b"ID3", b"\xff\xfb", b"\xff\xf3"):
        return "audio/mpeg"
    return "application/octet-stream"
