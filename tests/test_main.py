import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from types import SimpleNamespace
from claw.main import lifespan

def make_cfg(tmp_path):
    return SimpleNamespace(
        logging=SimpleNamespace(level="INFO", format="json"),
        storage=SimpleNamespace(
            db_path=str(tmp_path / "claw.db"),
            transcript_dir=str(tmp_path / "transcripts"),
        ),
        llm_router=SimpleNamespace(url="http://localhost", api_key=""),
        skills=SimpleNamespace(autoload=False, dir="skills"),
        gateway=SimpleNamespace(port=8000, host="127.0.0.1"),
        telegram=SimpleNamespace(enabled=False, token="", polling=True),
        slack=SimpleNamespace(enabled=False, bot_token="", app_token=""),
        discord=SimpleNamespace(enabled=False, token="", stock_channel_id=0, morning_report_channel_id=0),
        session=None,
        mcp=None,
    )



@pytest.mark.asyncio
async def test_main_lifespan_telegram_disabled(tmp_path):
    """Telegram disabled 時，不應啟動"""
    mock_app = MagicMock()

    with patch("claw.main.get_config") as mock_get_cfg:
        mock_cfg = make_cfg(tmp_path)
        mock_get_cfg.return_value = mock_cfg

        mock_storage = AsyncMock()
        mock_storage.db_path = str(tmp_path / "mock.db")
        with patch("claw.main.Storage", return_value=mock_storage):
            with patch("claw.main.LLMRouterClient", return_value=AsyncMock()):
                with patch("claw.memory.sqlite_store.MemoryStore", return_value=AsyncMock()):
                    with patch("claw.main.configure_logging"):
                        async with lifespan(mock_app):
                            pass  # No exception


@pytest.mark.asyncio
async def test_main_lifespan_telegram_starts(tmp_path):
    """Telegram enabled 時，應呼叫 start()"""
    mock_app = MagicMock()

    with patch("claw.main.get_config") as mock_get_cfg:
        mock_cfg = make_cfg(tmp_path)
        mock_cfg.telegram.enabled = True
        mock_cfg.telegram.token = "test_token"
        mock_cfg.telegram.polling = True
        mock_get_cfg.return_value = mock_cfg

        mock_tg = AsyncMock()

        mock_storage = AsyncMock()
        mock_storage.db_path = str(tmp_path / "mock.db")
        with patch("claw.main.Storage", return_value=mock_storage):
            with patch("claw.main.LLMRouterClient", return_value=AsyncMock()):
                with patch("claw.memory.sqlite_store.MemoryStore", return_value=AsyncMock()):
                    with patch("claw.main.configure_logging"):
                        with patch("claw.channels.telegram.TelegramChannel", return_value=mock_tg):
                            async with lifespan(mock_app):
                                pass

                            # Verify start() and stop() were called
                            mock_tg.start.assert_called_once()
                            mock_tg.stop.assert_called_once()


@pytest.mark.asyncio
async def test_main_lifespan_slack_starts(tmp_path):
    """Slack enabled 時，應呼叫 start()"""
    mock_app = MagicMock()

    with patch("claw.main.get_config") as mock_get_cfg:
        mock_cfg = make_cfg(tmp_path)
        mock_cfg.slack.enabled = True
        mock_cfg.slack.bot_token = "xoxb-test"
        mock_cfg.slack.app_token = "xapp-test"
        mock_get_cfg.return_value = mock_cfg

        mock_slack = AsyncMock()

        mock_storage = AsyncMock()
        mock_storage.db_path = str(tmp_path / "mock.db")
        with patch("claw.main.Storage", return_value=mock_storage):
            with patch("claw.main.LLMRouterClient", return_value=AsyncMock()):
                with patch("claw.memory.sqlite_store.MemoryStore", return_value=AsyncMock()):
                    with patch("claw.main.configure_logging"):
                        with patch("claw.channels.slack.SlackChannel", return_value=mock_slack):
                            async with lifespan(mock_app):
                                pass

                            mock_slack.start.assert_called_once()
                            mock_slack.stop.assert_called_once()


@pytest.mark.asyncio
async def test_main_lifespan_channel_error_not_fatal(tmp_path):
    """Channel 啟動失敗應被 try/except 捕捉，不中斷"""
    mock_app = MagicMock()

    with patch("claw.main.get_config") as mock_get_cfg:
        mock_cfg = make_cfg(tmp_path)
        mock_cfg.telegram.enabled = True
        mock_cfg.telegram.token = "test_token"
        mock_get_cfg.return_value = mock_cfg

        # Mock TelegramChannel 建立失敗
        mock_storage = AsyncMock()
        mock_storage.db_path = str(tmp_path / "mock.db")
        with patch("claw.main.Storage", return_value=mock_storage):
            with patch("claw.main.LLMRouterClient", return_value=AsyncMock()):
                with patch("claw.memory.sqlite_store.MemoryStore", return_value=AsyncMock()):
                    with patch("claw.main.configure_logging"):
                        with patch("claw.channels.telegram.TelegramChannel", side_effect=Exception("Token invalid")):
                            # 應不拋出異常
                            async with lifespan(mock_app):
                                pass


@pytest.mark.asyncio
async def test_main_lifespan_telegram_empty_token(tmp_path):
    """Telegram enabled 但 token 為空時應跳過啟動"""
    mock_app = MagicMock()

    with patch("claw.main.get_config") as mock_get_cfg:
        mock_cfg = make_cfg(tmp_path)
        mock_cfg.telegram.enabled = True
        mock_cfg.telegram.token = ""  # 空 token
        mock_get_cfg.return_value = mock_cfg

        mock_storage = AsyncMock()
        mock_storage.db_path = str(tmp_path / "mock.db")
        with patch("claw.main.Storage", return_value=mock_storage):
            with patch("claw.main.LLMRouterClient", return_value=AsyncMock()):
                with patch("claw.memory.sqlite_store.MemoryStore", return_value=AsyncMock()):
                    with patch("claw.main.configure_logging"):
                        # 應不拋出異常，但不啟動 Telegram
                        async with lifespan(mock_app):
                            pass
