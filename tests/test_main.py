import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from claw.main import lifespan


@pytest.mark.asyncio
async def test_main_lifespan_telegram_disabled():
    """Telegram disabled 時，不應啟動"""
    mock_app = MagicMock()

    with patch("claw.main.get_config") as mock_get_cfg:
        mock_cfg = MagicMock()
        mock_cfg.telegram.enabled = False
        mock_cfg.slack.enabled = False
        mock_get_cfg.return_value = mock_cfg

        with patch("claw.main.Storage", return_value=AsyncMock()):
            with patch("claw.main.LLMRouterClient", return_value=AsyncMock()):
                with patch("claw.memory.sqlite_store.MemoryStore", return_value=AsyncMock()):
                    async with lifespan(mock_app):
                        pass  # No exception


@pytest.mark.asyncio
async def test_main_lifespan_telegram_starts():
    """Telegram enabled 時，應呼叫 start()"""
    mock_app = MagicMock()

    with patch("claw.main.get_config") as mock_get_cfg:
        mock_cfg = MagicMock()
        mock_cfg.telegram.enabled = True
        mock_cfg.telegram.token = "test_token"
        mock_cfg.telegram.polling = True
        mock_cfg.slack.enabled = False
        mock_cfg.gateway.port = 8000
        mock_get_cfg.return_value = mock_cfg

        mock_tg = AsyncMock()

        with patch("claw.main.Storage", return_value=AsyncMock()):
            with patch("claw.main.LLMRouterClient", return_value=AsyncMock()):
                with patch("claw.memory.sqlite_store.MemoryStore", return_value=AsyncMock()):
                    with patch("claw.channels.telegram.TelegramChannel", return_value=mock_tg):
                        async with lifespan(mock_app):
                            pass

                        # Verify start() and stop() were called
                        mock_tg.start.assert_called_once()
                        mock_tg.stop.assert_called_once()


@pytest.mark.asyncio
async def test_main_lifespan_slack_starts():
    """Slack enabled 時，應呼叫 start()"""
    mock_app = MagicMock()

    with patch("claw.main.get_config") as mock_get_cfg:
        mock_cfg = MagicMock()
        mock_cfg.telegram.enabled = False
        mock_cfg.slack.enabled = True
        mock_cfg.slack.bot_token = "xoxb-test"
        mock_cfg.slack.app_token = "xapp-test"
        mock_cfg.gateway.port = 8000
        mock_get_cfg.return_value = mock_cfg

        mock_slack = AsyncMock()

        with patch("claw.main.Storage", return_value=AsyncMock()):
            with patch("claw.main.LLMRouterClient", return_value=AsyncMock()):
                with patch("claw.memory.sqlite_store.MemoryStore", return_value=AsyncMock()):
                    with patch("claw.channels.slack.SlackChannel", return_value=mock_slack):
                        async with lifespan(mock_app):
                            pass

                        mock_slack.start.assert_called_once()
                        mock_slack.stop.assert_called_once()


@pytest.mark.asyncio
async def test_main_lifespan_channel_error_not_fatal():
    """Channel 啟動失敗應被 try/except 捕捉，不中斷"""
    mock_app = MagicMock()

    with patch("claw.main.get_config") as mock_get_cfg:
        mock_cfg = MagicMock()
        mock_cfg.telegram.enabled = True
        mock_cfg.telegram.token = "test_token"
        mock_cfg.slack.enabled = False
        mock_cfg.gateway.port = 8000
        mock_get_cfg.return_value = mock_cfg

        # Mock TelegramChannel 建立失敗
        with patch("claw.main.Storage", return_value=AsyncMock()):
            with patch("claw.main.LLMRouterClient", return_value=AsyncMock()):
                with patch("claw.memory.sqlite_store.MemoryStore", return_value=AsyncMock()):
                    with patch("claw.channels.telegram.TelegramChannel", side_effect=Exception("Token invalid")):
                        # 應不拋出異常
                        async with lifespan(mock_app):
                            pass


@pytest.mark.asyncio
async def test_main_lifespan_telegram_empty_token():
    """Telegram enabled 但 token 為空時應跳過啟動"""
    mock_app = MagicMock()

    with patch("claw.main.get_config") as mock_get_cfg:
        mock_cfg = MagicMock()
        mock_cfg.telegram.enabled = True
        mock_cfg.telegram.token = ""  # 空 token
        mock_cfg.slack.enabled = False
        mock_get_cfg.return_value = mock_cfg

        with patch("claw.main.Storage", return_value=AsyncMock()):
            with patch("claw.main.LLMRouterClient", return_value=AsyncMock()):
                with patch("claw.memory.sqlite_store.MemoryStore", return_value=AsyncMock()):
                    # 應不拋出異常，但不啟動 Telegram
                    async with lifespan(mock_app):
                        pass
