from __future__ import annotations

import hmac
import logging
from fastapi import WebSocket

from claw.core.config import get_config

logger = logging.getLogger(__name__)


def verify_gateway_token(token: str) -> bool:
    """
    驗證 WebSocket 連線的 auth token。
    config.gateway.auth_token 為空 → 不驗證（開發模式）。
    """
    expected = get_config().gateway.auth_token
    if not expected:
        return True
    if not token:
        return False
    return hmac.compare_digest(expected.encode(), token.encode())


async def ws_auth_middleware(ws: WebSocket, token: str) -> bool:
    """
    WebSocket 連線認證。
    失敗時關閉連線，回傳 False。
    """
    if not verify_gateway_token(token):
        logger.warning(f"ws auth failed from {ws.client}")
        await ws.close(code=4003)
        return False
    return True
