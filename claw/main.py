import asyncio
import uvicorn
from contextlib import asynccontextmanager
from fastapi import FastAPI

from claw.core.storage import Storage
from claw.core.queue import MessageQueue
from claw.llm.router_client import LLMRouterClient
from claw.core.config import get_config
from claw.sandbox.docker_runner import get_runner
from claw.skills.loader import load_skills
import claw.core.gateway as gateway_module
import claw.tools.bash    # 觸發 bash tool 的注冊
import claw.tools.search  # 觸發 search_web tool 的注冊
import claw.tools.memory_tools  # 觸發 memory_save / memory_search 工具注冊
import logging

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    cfg = get_config()
    storage = Storage(
        db_path=cfg.storage.db_path,
        transcript_dir=cfg.storage.transcript_dir,
    )
    await storage.init()

    llm = LLMRouterClient(
        base_url=cfg.llm_router.url,
        api_key=cfg.llm_router.api_key,
    )

    import os
    import claw.tools.memory_tools as _mem_tools
    from claw.memory.sqlite_store import MemoryStore
    from claw.memory.manager import MemoryManager

    # Memory 初始化
    mem_db_path = os.path.join(
        os.path.dirname(os.path.expanduser(cfg.storage.db_path)),
        "memory.db"
    )
    mem_store = MemoryStore(db_path=mem_db_path)
    await mem_store.init()
    memory_manager = MemoryManager(store=mem_store, llm=llm)
    _mem_tools.set_memory_manager(memory_manager)
    gateway_module.memory = memory_manager

    gateway_module.storage = storage
    gateway_module.queue = MessageQueue()
    gateway_module.llm = llm
    if cfg.skills.autoload:
        load_skills(cfg.skills.dir)

    channels = []

    if cfg.telegram.enabled:
        # ✅ 驗證必需配置
        if not cfg.telegram.token or not cfg.telegram.token.strip():
            logger.error(
                "Telegram is enabled but token is empty or whitespace. "
                "Set TELEGRAM_TOKEN environment variable or "
                "configure telegram.token in config/default.yaml"
            )
        else:
            try:
                from claw.channels.telegram import TelegramChannel
                tg = TelegramChannel(
                    token=cfg.telegram.token.strip(),
                    base_url=f"http://localhost:{cfg.gateway.port}",
                    polling=cfg.telegram.polling,
                )
                await tg.start()
                channels.append(tg)
                logger.info("Telegram channel started successfully")
            except Exception as e:
                logger.error(f"Failed to start Telegram channel: {e}")

    if cfg.slack.enabled:
        # ✅ 驗證必需配置
        if not cfg.slack.bot_token or not cfg.slack.app_token:
            logger.error(
                "Slack is enabled but bot_token or app_token is empty. "
                "Set SLACK_BOT_TOKEN and SLACK_APP_TOKEN environment variables or "
                "configure slack.bot_token and slack.app_token in config/default.yaml"
            )
        else:
            try:
                from claw.channels.slack import SlackChannel
                slack = SlackChannel(
                    bot_token=cfg.slack.bot_token.strip(),
                    app_token=cfg.slack.app_token.strip(),
                    base_url=f"http://localhost:{cfg.gateway.port}",
                )
                await slack.start()
                channels.append(slack)
                logger.info("Slack channel started successfully")
            except Exception as e:
                logger.error(f"Failed to start Slack channel: {e}")

    yield

    for channel in channels:
        try:
            await channel.stop()
        except Exception as e:
            logger.error(f"Error stopping channel: {e}")

    await get_runner().destroy_all()
    await llm.close()


gateway_module.app.router.lifespan_context = lifespan


if __name__ == "__main__":
    cfg = get_config()
    host = cfg.gateway.host
    port = cfg.gateway.port
    uvicorn.run(gateway_module.app, host=host, port=port, reload=False)
