import asyncio
import os
import uvicorn
from contextlib import asynccontextmanager
from dotenv import load_dotenv
from fastapi import FastAPI

load_dotenv()

from claw.core.storage import Storage
from claw.core.queue import MessageQueue
from claw.llm.router_client import LLMRouterClient
import claw.core.gateway as gateway_module
import claw.tools.bash  # 觸發 bash tool 的注冊


@asynccontextmanager
async def lifespan(app: FastAPI):
    storage = Storage()
    await storage.init()

    llm = LLMRouterClient(
        base_url=os.getenv("LLM_ROUTER_URL", "http://127.0.0.1:8000"),
        api_key=os.getenv("LLM_ROUTER_API_KEY", ""),
    )

    gateway_module.storage = storage
    gateway_module.queue = MessageQueue()
    gateway_module.llm = llm

    yield

    await llm.close()


gateway_module.app.router.lifespan_context = lifespan


if __name__ == "__main__":
    host = os.getenv("CLAW_HOST", "127.0.0.1")
    port = int(os.getenv("CLAW_PORT", "18790"))
    uvicorn.run(gateway_module.app, host=host, port=port, reload=False)
