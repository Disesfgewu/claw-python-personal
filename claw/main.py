import asyncio
import uvicorn
from contextlib import asynccontextmanager
from fastapi import FastAPI

from claw.core.storage import Storage
from claw.core.queue import MessageQueue
from claw.llm.router_client import LLMRouterClient
from claw.core.config import get_config
from claw.core.logger import configure_logging
from claw.core.session_reaper import SessionReaper
from claw.sandbox.docker_runner import get_runner
from claw.skills.loader import load_skills
import claw.core.gateway as gateway_module
import claw.tools.bash    # 觸發 bash tool 的注冊
import claw.tools.search  # 觸發 search_web tool 的注冊
import claw.tools.memory_tools  # 觸發 memory_save / memory_search 工具注冊
import claw.tools.web_fetch      # 觸發 web_fetch tool 的注冊
import claw.tools.file_tools     # 觸發 file_read/write/list/delete 工具注冊
import claw.tools.research_tools  # 觸發 research_start/experiment_record/research_status 工具注冊
import claw.tools.cron           # 觸發 cron_add/list/delete 工具注冊
import claw.tools.image_gen      # 觸發 image_gen tool 的注冊
import claw.tools.browser         # 觸發 browser_navigate/extract/close 工具注冊
import claw.tools.sessions_tools  # 觸發 sessions_send/spawn/list 工具注冊
import logging

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    cfg = get_config()
    configure_logging(
        level=cfg.logging.level,
        fmt=cfg.logging.format,
    )
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

    # Memory 初始化 — 先檢測 embedding 實際維度
    mem_db_path = os.path.join(
        os.path.dirname(storage.db_path),
        "memory.db"
    )

    # 檢測 LLM Router 的 embedding 維度
    actual_embedding_dim = 768  # 預設值
    try:
        test_emb = await llm.get_embedding("test")
        actual_embedding_dim = len(test_emb)
        logger.info(f"Detected embedding dimension: {actual_embedding_dim}")
    except Exception as e:
        logger.warning(f"Failed to detect embedding dimension: {e}, using default 768")

    mem_store = MemoryStore(db_path=mem_db_path, embedding_dim=actual_embedding_dim)
    await mem_store.init()
    memory_manager = MemoryManager(store=mem_store, llm=llm)
    _mem_tools.set_memory_manager(memory_manager)
    gateway_module.memory = memory_manager

    # ResearchLoop 初始化（AutoResearch 功能）
    from claw.research.loop import init_research_loop
    init_research_loop(llm=llm, storage=storage, memory=memory_manager)
    logger.info("ResearchLoop initialized")

    # MCP Bridge 初始化（連接外部 MCP servers）
    from claw.tools.mcp_bridge import MCPBridge, MCPServerConfig, set_mcp_bridge
    mcp_bridge = MCPBridge()
    mcp_cfg = getattr(cfg, "mcp", None)
    if mcp_cfg and getattr(mcp_cfg, "servers", None):
        mcp_server_configs = []
        for s in (getattr(mcp_cfg, "servers", [])):
            if isinstance(s, dict) and s.get("enabled", True):
                mcp_server_configs.append(MCPServerConfig(
                    name=s.get("name", "unknown"),
                    transport=s.get("transport", "stdio"),
                    command=s.get("command", []),
                    url=s.get("url", ""),
                    enabled=s.get("enabled", True),
                ))
        if mcp_server_configs:
            count = await mcp_bridge.load_servers(mcp_server_configs)
            logger.info(f"MCPBridge loaded {count} tools from {len(mcp_server_configs)} servers")
    set_mcp_bridge(mcp_bridge)
    gateway_module.mcp_bridge = mcp_bridge

    # CronService 初始化
    from claw.cron.store import CronStore
    from claw.cron.service import CronService
    from claw.tools.cron import set_cron_service
    cron_store = CronStore(db_path=storage.db_path)
    await cron_store.init()
    cron_service = CronService(store=cron_store, storage=storage, llm=llm)
    await cron_service.start()
    set_cron_service(cron_service)
    gateway_module.cron_service = cron_service
    logger.info("CronService initialized and started")

    # 晨報 Cron Job（每個交易日 08:00）
    # Schedule: "0 8 * * 1-5" = 08:00, 週一至週五
    morning_job = {
        "name": "morning_report",
        "schedule": "0 8 * * 1-5",
        "prompt": "執行台股晨報：掃 Taiwan 50 強勢股，生成圖表，推送到 Discord",
        "callable": "claw.cron.jobs.morning_report:morning_report_job",
        "enabled": True,
    }
    try:
        await cron_service.add_job(
            session_id="cron:morning_report",
            schedule=morning_job["schedule"],
            prompt=morning_job["prompt"],
        )
        logger.info("Morning report Cron job registered (0 8 * * 1-5 / 08:00 weekdays)")
    except Exception as e:
        logger.warning(f"Failed to register morning report job: {e}")

    # 週報 Cron Job（每週五 18:00）
    # Schedule: "0 18 * * 5" = 18:00, 週五
    weekly_job = {
        "name": "weekly_report",
        "schedule": "0 18 * * 5",
        "prompt": "執行策略驗證週報：對比動能/反轉/基本面策略，生成推薦清單",
        "callable": "claw.cron.jobs.weekly_report:weekly_report_job",
        "enabled": True,
    }
    try:
        await cron_service.add_job(
            session_id="cron:weekly_report",
            schedule=weekly_job["schedule"],
            prompt=weekly_job["prompt"],
        )
        logger.info("Weekly report Cron job registered (0 18 * * 5 / 18:00 Friday)")
    except Exception as e:
        logger.warning(f"Failed to register weekly report job: {e}")

    # EgressPolicy 初始化（從 config/egress_policy.yaml 載入白名單）
    from claw.tools.policy import EgressPolicy, set_egress_policy
    from pathlib import Path
    egress_policy_path = Path("config/egress_policy.yaml")
    if egress_policy_path.exists():
        egress_policy = EgressPolicy.from_yaml(egress_policy_path, db_path=storage.db_path)
        set_egress_policy(egress_policy)
        logger.info(f"EgressPolicy loaded from {egress_policy_path} with {len(egress_policy.rules)} rules")
    else:
        egress_policy = EgressPolicy(db_path=storage.db_path)
        set_egress_policy(egress_policy)
        logger.warning(f"EgressPolicy config not found at {egress_policy_path}, using default (DENY all)")

    # 將 egress_policy 暴露給 gateway（供 AgentLoop 使用）
    gateway_module.egress_policy = egress_policy

    # MultiAgentCoordinator 初始化（連接 sessions_send/spawn/list 工具）
    from claw.agent.multi_agent import MultiAgentCoordinator
    from claw.tools.sessions_tools import set_coordinator
    coordinator = MultiAgentCoordinator(storage=storage, llm=llm)
    set_coordinator(coordinator)
    logger.info("MultiAgentCoordinator initialized")

    gateway_module.storage = storage
    gateway_module.queue = MessageQueue()
    gateway_module.llm = llm
    if cfg.skills.autoload:
        load_skills(cfg.skills.dir)

    session_cfg = getattr(cfg, "session", None)
    ttl_hours = getattr(session_cfg, "ttl_hours", 24) if session_cfg else 24
    interval_seconds = (
        getattr(session_cfg, "reaper_interval_seconds", 60) if session_cfg else 60
    )
    reaper = SessionReaper(
        storage=storage,
        ttl_hours=ttl_hours,
        interval_seconds=interval_seconds,
    )
    reaper.start()

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

    if cfg.discord.enabled:
        if not cfg.discord.token or not cfg.discord.token.strip():
            logger.error(
                "Discord is enabled but token is empty. "
                "Set DISCORD_TOKEN environment variable or "
                "configure discord.token in config/default.yaml"
            )
        else:
            try:
                from claw.channels.discord import DiscordChannel
                discord = DiscordChannel(
                    token=cfg.discord.token.strip(),
                    base_url=f"http://localhost:{cfg.gateway.port}",
                    router_url=cfg.llm_router.url,
                    intent_model=cfg.discord.intent_model,
                )
                await discord.start()
                channels.append(discord)
                logger.info("Discord channel started successfully")
            except Exception as e:
                logger.error(f"Failed to start Discord channel: {e}")

    yield

    logger.info("Starting graceful shutdown...")

    try:
        if hasattr(gateway_module, 'cron_service') and gateway_module.cron_service:
            await gateway_module.cron_service.stop()
            logger.info("CronService stopped")
    except Exception as e:
        logger.error(f"Error stopping CronService: {e}")

    try:
        if hasattr(gateway_module, 'mcp_bridge') and gateway_module.mcp_bridge:
            await gateway_module.mcp_bridge.close_all()
            logger.info("MCPBridge closed")
    except Exception as e:
        logger.error(f"Error closing MCPBridge: {e}")

    try:
        for channel in channels:
            await channel.stop()
        logger.info(f"All channels stopped ({len(channels)} channels)")
    except Exception as e:
        logger.error(f"Error stopping channels: {e}")

    try:
        await get_runner().destroy_all()
        logger.info("Docker containers destroyed")
    except Exception as e:
        logger.error(f"Error destroying Docker containers: {e}")

    try:
        if hasattr(gateway_module, 'llm') and gateway_module.llm:
            await gateway_module.llm.close()
            logger.info("LLM client closed")
    except Exception as e:
        logger.error(f"Error closing LLM client: {e}")

    reaper.stop()

    logger.info("Graceful shutdown completed")


gateway_module.app.router.lifespan_context = lifespan


if __name__ == "__main__":
    cfg = get_config()
    host = cfg.gateway.host
    port = cfg.gateway.port
    uvicorn.run(gateway_module.app, host=host, port=port, reload=False)
