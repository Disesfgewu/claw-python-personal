from __future__ import annotations

from dataclasses import dataclass, field
from typing import AsyncIterator
import httpx
import json
import logging

logger = logging.getLogger(__name__)


class LLMRouterError(Exception):
    pass


@dataclass
class ChatMessage:
    role: str       # "system" | "user" | "assistant" | "tool"
    content: str | list
    tool_call_id: str | None = None
    tool_calls: list | None = None    # assistant 呼叫 tool 時


@dataclass
class ToolDefinition:
    name: str
    description: str
    parameters: dict              # JSON Schema


@dataclass
class CompletionRequest:
    messages: list[ChatMessage]
    model: str = "auto"           # "auto" | "TextOnlyLow" | "TextOnlyHigh"
    temperature: float = 0.7
    max_tokens: int = 4096
    tools: list[ToolDefinition] | None = None
    tool_choice: str = "auto"     # "auto" | "none" | "required"
    system: str | None = None     # 若有，插入 messages[0] 作為 system role


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict               # 已解析的 JSON


@dataclass
class CompletionResponse:
    content: str
    model: str
    tool_calls: list[ToolCall] = field(default_factory=list)
    finish_reason: str = "stop"
    usage: dict = field(default_factory=dict)


@dataclass
class StreamChunk:
    content: str = ""
    tool_call_delta: dict | None = None  # partial tool call
    finish_reason: str | None = None
    usage: dict | None = None            # 最後一個 chunk 才有


class LLMRouterClient:
    def __init__(self, base_url: str = "http://127.0.0.1:8000", api_key: str = ""):
        self.base_url = base_url.rstrip("/")
        headers = {}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            headers=headers,
            timeout=httpx.Timeout(connect=5.0, read=120.0, write=10.0, pool=5.0)
        )

    async def complete(self, req: CompletionRequest) -> CompletionResponse:
        """單次完整回應（不 streaming）"""
        payload = self._build_payload(req, stream=False)
        try:
            resp = await self._client.post("/v1/chat/completions", json=payload)
            resp.raise_for_status()
            return self._parse_response(resp.json())
        except httpx.HTTPError as e:
            raise LLMRouterError(str(e)) from e

    async def stream(self, req: CompletionRequest) -> AsyncIterator[StreamChunk]:
        """串流回應，yield StreamChunk"""
        payload = self._build_payload(req, stream=True)
        try:
            async with self._client.stream(
                "POST", "/v1/chat/completions", json=payload
            ) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    data = line[6:].strip()
                    if data == "[DONE]":
                        break
                    try:
                        chunk = json.loads(data)
                    except json.JSONDecodeError:
                        continue
                    yield self._parse_stream_chunk(chunk)
        except httpx.HTTPError as e:
            raise LLMRouterError(str(e)) from e

    async def direct_query(
        self,
        prompt: str,
        model_name: str,
        provider: str,
        temperature: float = 0.7,
        max_tokens: int = 2048,
    ) -> str:
        """指定 provider + model，繞過自動路由"""
        try:
            resp = await self._client.post("/v1/direct_query", json={
                "model_name": model_name,
                "provider": provider,
                "prompt": prompt,
                "temperature": temperature,
                "max_tokens": max_tokens,
            })
            resp.raise_for_status()
            data = resp.json()
            return data.get("content", "")
        except httpx.HTTPError as e:
            raise LLMRouterError(str(e)) from e

    async def health_check(self) -> dict:
        """健康檢查：用 1 token 的 chat request 確認 LLM-Router 可達"""
        try:
            resp = await self._client.post(
                "/v1/chat/completions",
                json={
                    "model": "auto",
                    "messages": [{"role": "user", "content": "ping"}],
                    "max_tokens": 1,
                },
                timeout=10.0,
            )
            resp.raise_for_status()
            return {"status": "ok", "model": resp.json().get("model", "")}
        except httpx.HTTPError as e:
            raise LLMRouterError(str(e)) from e

    async def get_embedding(self, text: str) -> list[float]:
        """
        Generate embedding via /v1/embeddings endpoint.

        Args:
            text: Input text to embed

        Returns:
            Embedding vector as list of floats

        Raises:
            Exception: If embedding generation fails
        """
        try:
            resp = await self._client.post(
                f"{self.base_url}/v1/embeddings",
                json={"input": text, "model": "default"},
            )
            resp.raise_for_status()
            data = resp.json()
            if "data" not in data or len(data["data"]) == 0:
                raise ValueError("Invalid embedding response format")
            return data["data"][0]["embedding"]
        except Exception as e:
            logger.error(f"Embedding request failed: {e}")
            raise

    async def close(self) -> None:
        await self._client.aclose()

    # --- private ---

    def _build_payload(self, req: CompletionRequest, stream: bool) -> dict:
        messages = []
        if req.system:
            messages.append({"role": "system", "content": req.system})
        for m in req.messages:
            msg: dict = {"role": m.role, "content": m.content}
            if m.tool_call_id:
                msg["tool_call_id"] = m.tool_call_id
            if m.tool_calls:
                msg["tool_calls"] = m.tool_calls
            messages.append(msg)

        payload: dict = {
            "model": req.model,
            "messages": messages,
            "temperature": req.temperature,
            "max_tokens": req.max_tokens,
            "stream": stream,
        }
        if req.tools:
            payload["tools"] = [
                {
                    "type": "function",
                    "function": {
                        "name": t.name,
                        "description": t.description,
                        "parameters": t.parameters,
                    }
                }
                for t in req.tools
            ]
            payload["tool_choice"] = req.tool_choice
        return payload

    def _parse_response(self, data: dict) -> CompletionResponse:
        choice = data["choices"][0]
        msg = choice["message"]
        tool_calls = []
        for tc in msg.get("tool_calls") or []:
            try:
                args = json.loads(tc["function"]["arguments"])
            except Exception:
                args = {}
            tool_calls.append(ToolCall(
                id=tc["id"],
                name=tc["function"]["name"],
                arguments=args,
            ))
        return CompletionResponse(
            content=msg.get("content") or "",
            model=data.get("model", ""),
            tool_calls=tool_calls,
            finish_reason=choice.get("finish_reason", "stop"),
            usage=data.get("usage", {}),
        )

    def _parse_stream_chunk(self, data: dict) -> StreamChunk:
        choice = data["choices"][0]
        delta = choice.get("delta", {})
        return StreamChunk(
            content=delta.get("content") or "",
            tool_call_delta=delta.get("tool_calls"),
            finish_reason=choice.get("finish_reason"),
            usage=data.get("usage"),
        )
