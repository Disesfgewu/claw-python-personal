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

    gateway_module.storage = storage
    gateway_module.queue = MessageQueue()
    gateway_module.llm = llm
    if cfg.skills.autoload:
        load_skills(cfg.skills.dir)

    yield

    await get_runner().destroy_all()
    await llm.close()


gateway_module.app.router.lifespan_context = lifespan


if __name__ == "__main__":
    cfg = get_config()
    host = cfg.gateway.host
    port = cfg.gateway.port
    uvicorn.run(gateway_module.app, host=host, port=port, reload=False)
