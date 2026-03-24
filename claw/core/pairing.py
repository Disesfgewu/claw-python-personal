from __future__ import annotations

import secrets
import time
from dataclasses import dataclass

PAIRING_CODE_TTL = 300


@dataclass
class PairingEntry:
    code: str
    created_at: float
    peer_id: str | None = None


_pending: dict[str, PairingEntry] = {}
_paired: set[str] = set()


def generate_code(session_id: str) -> str:
    """產生一個 6 位數配對碼，並暫存"""
    code = str(100000 + secrets.randbelow(900000))
    _pending[session_id] = PairingEntry(code=code, created_at=time.time())
    return code


def verify_code(session_id: str, code: str, peer_id: str) -> bool:
    """驗證配對碼，成功後把 peer_id 加入已配對集合"""
    entry = _pending.get(session_id)
    if not entry:
        return False
    if time.time() - entry.created_at > PAIRING_CODE_TTL:
        _pending.pop(session_id, None)
        return False
    if entry.code != code:
        return False
    _paired.add(peer_id)
    _pending.pop(session_id, None)
    return True


def is_paired(peer_id: str) -> bool:
    return peer_id in _paired


def unpair(peer_id: str) -> None:
    _paired.discard(peer_id)
