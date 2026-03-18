# claw-python

OpenClaw 的 Python 完整復刻。以 [LLM-Router](https://github.com/Disesfgewu/LLM-Router) 作為唯一 LLM 閘道，透過 DDGS 實現免費搜尋，並用 Docker 隔離 tool 執行環境。

---

## 設計邏輯

> **為什麼要把 LLM 和搜尋分出去到 LLM-Router？**

兩個原因：

1. **LLM = 錢** — 所有 API key、quota 追蹤、provider 選擇、failover，集中在一個地方統一管理。claw-python 完全不碰金鑰，安全邊界清楚。
2. **搜尋 = 敏感資訊查詢** — DDGS 搜尋結果可能包含敏感查詢紀錄，統一由後端處理，不散落在各 channel adapter 中。

所以分工是：

```
LLM-Router 負責：  LLM API 呼叫（有錢有關）+ DDGS 搜尋（敏感查詢）
claw-python 負責： 其他所有事
```

---

## 系統架構

```
┌─────────────────────────────────────────────────────────────────────┐
│                         claw-python                                 │
│                                                                     │
│  Channels         Gateway           Agent Loop      Tools/Skills    │
│  ─────────        ───────           ──────────      ────────────    │
│  Telegram    ─►   WS 控制平面   ─►  執行核心    ─►  bash            │
│  Discord     ─►   Session 管理       Hook system     browser        │
│  Slack       ─►   Queue              Docker sandbox  file           │
│  WhatsApp    ─►   Event broadcast    Multi-agent     cron           │
│  LINE        ─►   HTTP /v1           Pairing         MCP bridge     │
│  Signal      ─►   Auth               TTS             skills/...     │
│  iMessage    ─►   Rate limit         Image gen                      │
│  Teams       ─►   Daemon/service     Memory (RAG)                   │
│  ...其他     ─►                      Canvas                         │
│                                      Markdown render                │
└──────────────────────────────────────────────────────┬─────────────┘
                                                        │ HTTP only
                                           ┌────────────▼────────────┐
                                           │      LLM-Router          │
                                           │  ┌──────────────────┐   │
                                           │  │   LLM API 路由   │   │
                                           │  │  GitHub Models   │   │
                                           │  │  Google Gemini   │   │
                                           │  │  Ollama（本地）  │   │
                                           │  └──────────────────┘   │
                                           │  ┌──────────────────┐   │
                                           │  │   DDGS 搜尋      │   │
                                           │  └──────────────────┘   │
                                           └──────────────────────────┘
```

---

## 架構決定（已確認）

| # | 問題 | 決定 |
|---|---|---|
| 1 | Session storage | SQLite（metadata + 近期訊息）+ JSONL（append-only 完整 transcript） |
| 2 | API Key 管理 | 全部在 LLM-Router，claw-python 零金鑰 |
| 3 | Agent loop 回傳 | `AsyncIterator[Event]`（streaming text chunk + tool call events） |
| 4 | Hook system | 先文件化介面，Phase 2 實作 |
| 5 | Tool Sandbox | Docker（非 main session 的 tool 執行在隔離 container） |
| 6 | LLM 後端 | 只接 LLM-Router，不直接掛任何 LLM SDK |

---

## OpenClaw TS 原始碼對照表

openclaw 有 2000+ 個 `.ts` 檔案，分佈在 45+ 個目錄。
以下按「你需要去看哪些 `.ts` 檔」來分類，並標明對應的 Python 模組和優先順序。

### 凡例

| 標記 | 意思 |
|---|---|
| ✅ claw-python | 要在 claw-python 實作 |
| 🔀 LLM-Router | 已由 LLM-Router 處理，claw-python 只需呼叫 API |
| ⏭ Phase 2+ | 第一階段跳過，先預留介面 |
| ❌ 不需要 | OpenClaw 有但 Python 版不需要（TypeScript/Node 特有） |

---

### 第一批要看的 .ts（Phase 1 核心）

這些是你開始動工前必須讀懂的檔案：

#### Gateway 控制平面

| OpenClaw `.ts` 檔 | 看什麼 | Python 對應 |
|---|---|---|
| `src/gateway/server.ts` | WebSocket 控制平面入口；connect frame 格式；client 生命週期 | `claw/core/gateway.py` |
| `src/gateway/server.impl.ts` | 實作細節；event broadcast 邏輯 | `claw/core/gateway.py` |
| `src/gateway/server-chat.ts` | 訊息進入後如何分派到 agent run | `claw/core/gateway.py` |
| `src/gateway/chat-abort.ts` | 如何中止進行中的 agent run | `claw/core/gateway.py` |
| `src/gateway/auth.ts` | Gateway 連線認證邏輯 | `claw/core/auth.py` |
| `src/gateway/protocol/` | Wire protocol 格式（req/res/event 的 schema） | `claw/core/protocol.py` |
| `src/gateway/server-methods/` | 所有 RPC methods（sessions.*、agent.*、tools.*） | `claw/core/rpc_methods.py` |

#### Session 系統

| OpenClaw `.ts` 檔 | 看什麼 | Python 對應 |
|---|---|---|
| `src/sessions/session-id.ts` | Session ID 格式規則（`agent:x:main`、`agent:x:channel:group:y`） | `claw/core/session.py` |
| `src/sessions/session-id-resolution.ts` | 如何從 channel message 解析出 session ID | `claw/core/session.py` |
| `src/sessions/send-policy.ts` | 訊息傳送策略（什麼情況下可以 send） | `claw/core/session.py` |
| `src/sessions/transcript-events.ts` | Transcript 的事件格式（JSONL 每行存什麼） | `claw/core/storage.py` |
| `src/channels/session.ts` | Channel 層的 session state | `claw/core/session.py` |
| `src/channels/session-meta.ts` | Session metadata schema | `claw/core/session.py` |
| `src/channels/session-envelope.ts` | 訊息 envelope 格式 | `claw/core/protocol.py` |

#### Queue 系統

| OpenClaw `.ts` 檔 | 看什麼 | Python 對應 |
|---|---|---|
| `src/process/lanes.ts` | Lane-aware queue 的核心邏輯 | `claw/core/queue.py` |
| `src/process/command-queue.ts` | Command queue 實作 | `claw/core/queue.py` |
| `src/channels/inbound-debounce-policy.ts` | 訊息 debounce（防止過快觸發） | `claw/core/queue.py` |

#### Agent Loop

| OpenClaw `.ts` 檔 | 看什麼 | Python 對應 |
|---|---|---|
| `src/agents/pi-embedded-runner.ts` | Agent 執行迴圈的頂層邏輯 | `claw/agent/loop.py` |
| `src/agents/pi-embedded-subscribe.ts` | 如何 subscribe LLM streaming events | `claw/agent/loop.py` |
| `src/agents/pi-embedded-helpers/` | Loop 內的各種 helper（context 組裝、tool 結果處理） | `claw/agent/context.py` |
| `src/agents/workspace.ts` | Workspace 管理（agent 的工作目錄） | `claw/agent/workspace.py` |
| `src/agents/session-write-lock.ts` | 防止 concurrent write 到同一 session | `claw/core/session.py` |
| `src/auto-reply/reply.ts` | 回覆生成的頂層邏輯 | `claw/agent/loop.py` |
| `src/auto-reply/chunk.ts` | Streaming chunk 處理 | `claw/agent/events.py` |
| `src/auto-reply/dispatch.ts` | 回覆如何 dispatch 到 channel | `claw/agent/loop.py` |
| `src/auto-reply/thinking.ts` | Thinking/reasoning 邏輯 | `claw/agent/loop.py` |
| `src/auto-reply/command-detection.ts` | 偵測 slash command 觸發 | `claw/agent/commands.py` |
| `src/auto-reply/commands-registry.ts` | Command 注冊表 | `claw/agent/commands.py` |

#### Tool 系統

| OpenClaw `.ts` 檔 | 看什麼 | Python 對應 |
|---|---|---|
| `src/agents/tool-catalog.ts` | 所有 tool 的定義與注冊方式 | `claw/tools/registry.py` |
| `src/agents/tool-policy.ts` | Tool 執行策略（main vs sandbox） | `claw/tools/policy.py` |
| `src/agents/bash-tools.ts` | Bash tool 實作 | `claw/tools/bash.py` |
| `src/agents/openclaw-tools.ts` | OpenClaw 原生 tool（sessions_*、canvas 等） | `claw/tools/builtin.py` |
| `src/node-host/invoke.ts` | 系統指令執行的核心 | `claw/tools/bash.py` |
| `src/node-host/invoke-browser.ts` | Browser 呼叫 | `claw/tools/browser.py` |
| `src/node-host/exec-policy.ts` | 執行策略（allowlist） | `claw/tools/policy.py` |
| `src/node-host/invoke-system-run-allowlist.ts` | 指令 allowlist | `claw/tools/policy.py` |

---

### 第二批要看的 .ts（Phase 2：Hook + Sandbox + Channels）

#### Hook System

| OpenClaw `.ts` 檔 | 看什麼 | Python 對應 |
|---|---|---|
| `src/hooks/hooks.ts` | Hook 系統的核心（register、fire、await） | `claw/agent/hooks.py` |
| `src/hooks/types.ts` | 所有 hook event 的 type 定義 | `claw/agent/hooks.py` |
| `src/hooks/loader.ts` | Hook 載入方式（從 skills/ 動態載入） | `claw/agent/hooks.py` |
| `src/plugins/hooks.ts` | Plugin 層的 hook 整合 | `claw/skills/loader.py` |
| `src/plugins/hook-runner-global.ts` | 全域 hook runner | `claw/agent/hooks.py` |

#### Docker Sandbox

| OpenClaw `.ts` 檔 | 看什麼 | Python 對應 |
|---|---|---|
| `src/agents/sandbox/` | Sandbox 執行環境（container 生命週期、volume 掛載） | `claw/sandbox/docker_runner.py` |
| `src/agents/acp-spawn.ts` | 如何 spawn agent process（可參考 sandbox spawn 模式） | `claw/sandbox/docker_runner.py` |

#### Channel Adapters

| OpenClaw `.ts` 檔 | 看什麼 | Python 對應 |
|---|---|---|
| `src/plugin-sdk/runtime.ts` | Plugin SDK 的 channel runtime 基底 | `claw/channels/base.py` |
| `src/plugin-sdk/telegram.ts` | Telegram channel 實作參考 | `claw/channels/telegram.py` |
| `src/plugin-sdk/discord.ts` | Discord channel | `claw/channels/discord_channel.py` |
| `src/plugin-sdk/slack.ts` | Slack channel | `claw/channels/slack.py` |
| `src/plugin-sdk/whatsapp.ts` | WhatsApp channel | `claw/channels/whatsapp.py` |
| `src/plugin-sdk/channel-runtime.ts` | Channel 共用 runtime（typing、ack、reply）| `claw/channels/base.py` |
| `src/channels/typing.ts` | Typing indicator 邏輯 | `claw/channels/base.py` |
| `src/channels/ack-reactions.ts` | Ack reaction（✅ 等表情回應） | `claw/channels/base.py` |
| `src/channels/allow-from.ts` | allowFrom 設定邏輯 | `claw/channels/policy.py` |
| `src/channels/command-gating.ts` | Command 存取控制 | `claw/channels/policy.py` |
| `src/channels/draft-stream-loop.ts` | 串流回覆的 draft 更新邏輯 | `claw/channels/base.py` |

#### Security / Pairing

| OpenClaw `.ts` 檔 | 看什麼 | Python 對應 |
|---|---|---|
| `src/pairing/pairing-challenge.ts` | DM pairing challenge 邏輯 | `claw/core/pairing.py` |
| `src/pairing/setup-code.ts` | Setup code 生成 | `claw/core/pairing.py` |
| `src/security/dm-policy-shared.ts` | DM policy（誰可以傳訊息給 bot） | `claw/channels/policy.py` |
| `src/security/dangerous-tools.ts` | 哪些 tool 被視為危險操作 | `claw/tools/policy.py` |
| `src/gateway/auth-mode-policy.ts` | Gateway 層的 auth mode 規則 | `claw/core/auth.py` |

---

### 第三批要看的 .ts（Phase 3：進階功能）

#### Cron / 排程

| OpenClaw `.ts` 檔 | 看什麼 | Python 對應 |
|---|---|---|
| `src/cron/service.ts` | Cron job 排程服務 | `claw/cron/service.py` |
| `src/cron/isolated-agent.ts` | 排程任務用獨立 agent 執行 | `claw/cron/runner.py` |
| `src/cron/schedule.ts` | Cron 時間規則解析 | `claw/cron/schedule.py` |
| `src/cron/store.ts` | Cron job 持久化 | `claw/cron/store.py` |
| `src/cron/session-reaper.ts` | 過期 session 清理 | `claw/core/session.py` |

#### Multi-agent

| OpenClaw `.ts` 檔 | 看什麼 | Python 對應 |
|---|---|---|
| `src/acp/client.ts` | ACP client（agent 呼叫 agent 的協定） | `claw/agent/multi_agent.py` |
| `src/acp/server.ts` | ACP server | `claw/agent/multi_agent.py` |
| `src/acp/session.ts` | ACP session 管理 | `claw/agent/multi_agent.py` |
| `src/acp/persistent-bindings.ts` | 持久的 agent 綁定關係 | `claw/agent/multi_agent.py` |
| `src/agents/bash-process-registry.ts` | 跨 agent 的 process 共享 | `claw/agent/multi_agent.py` |

#### Memory / RAG

| OpenClaw `.ts` 檔 | 看什麼 | Python 對應 |
|---|---|---|
| `src/memory/manager.ts` | Memory 管理器頂層邏輯 | `claw/memory/manager.py` |
| `src/memory/manager-search.ts` | 語意搜尋實作 | `claw/memory/manager.py` |
| `src/memory/sqlite.ts` | SQLite 向量資料庫操作 | `claw/memory/sqlite_store.py` |
| `src/memory/hybrid.ts` | Hybrid search（BM25 + 向量） | `claw/memory/manager.py` |
| `src/memory/temporal-decay.ts` | 時間衰減相關性 | `claw/memory/manager.py` |
| `src/memory/embeddings.ts` | Embedding 入口 | 🔀 交給 LLM-Router |
| `src/memory/embeddings-*.ts` | 各 provider 的 embedding 實作 | 🔀 交給 LLM-Router |

#### Media / TTS / Image Gen

| OpenClaw `.ts` 檔 | 看什麼 | Python 對應 |
|---|---|---|
| `src/media/store.ts` | 媒體檔案儲存 | `claw/media/store.py` |
| `src/media/input-files.ts` | 上傳檔案處理 | `claw/media/input.py` |
| `src/media/mime.ts` | MIME type 判斷 | `claw/media/mime.py` |
| `src/media-understanding/runner.ts` | 媒體理解（圖片/PDF 分析）Runner | 🔀 透過 LLM-Router `/v1/file/generate_content` |
| `src/tts/tts.ts` | TTS 頂層邏輯 | `claw/tts/tts.py` ⏭ Phase 3 |
| `src/tts/provider-registry.ts` | TTS provider 注冊 | `claw/tts/providers.py` ⏭ Phase 3 |
| `src/image-generation/runtime.ts` | 圖片生成 | 🔀 透過 LLM-Router `/v1/images/generations` |

#### Plugin / Skill System

| OpenClaw `.ts` 檔 | 看什麼 | Python 對應 |
|---|---|---|
| `src/plugins/loader.ts` | Plugin 動態載入 | `claw/skills/loader.py` |
| `src/plugins/discovery.ts` | Plugin 發現（從目錄掃描） | `claw/skills/loader.py` |
| `src/plugins/manifest.ts` | Plugin manifest 格式 | `claw/skills/manifest.py` |
| `src/agents/skills/` | Agent 層的 skill 管理 | `claw/skills/registry.py` |
| `src/plugin-sdk/core.ts` | Plugin SDK 核心 API（skill 怎麼定義自己） | `claw/skills/base.py` |

#### Canvas / WebChat

| OpenClaw `.ts` 檔 | 看什麼 | Python 對應 |
|---|---|---|
| `src/canvas-host/server.ts` | Canvas 服務（A2UI 渲染） | `claw/canvas/server.py` ⏭ Phase 4 |
| `src/canvas-host/a2ui.ts` | A2UI 協定 | `claw/canvas/a2ui.py` ⏭ Phase 4 |
| `src/channels/web/` | WebChat channel | `claw/channels/webchat.py` ⏭ Phase 3 |

---

### 不需要看的 .ts（LLM-Router 已處理或 Node.js 特有）

| 目錄 | 原因 |
|---|---|
| `src/providers/` | LLM provider auth（GitHub Copilot、Qwen OAuth 等）→ 全由 LLM-Router 負責 |
| `src/memory/embeddings-*.ts` | Embedding provider → LLM-Router 負責 |
| `src/web-search/` | Web search → LLM-Router 的 DDGS 負責 |
| `src/image-generation/providers/` | Image gen providers → LLM-Router |
| `src/tts/providers/` | TTS provider（ElevenLabs 等）→ Phase 3，有需要再評估 |
| `src/daemon/` | systemd / launchd / schtasks → Python 用 `systemd` 套件或直接 shell |
| `src/infra/` | Node.js 特有 infra（npm 管理、Homebrew、napi 等） |
| `src/types/` | TS type declarations（Python 用 Pydantic） |

---

## 完整目錄結構

```
claw-python/
├── claw/
│   ├── core/                    # Phase 1
│   │   ├── gateway.py           # FastAPI + WebSocket 控制平面
│   │   ├── session.py           # Session CRUD + lifecycle + write lock
│   │   ├── storage.py           # SQLite schema + JSONL transcript writer
│   │   ├── queue.py             # Lane-aware FIFO queue
│   │   ├── protocol.py          # Wire protocol schema（connect/req/res/event）
│   │   ├── auth.py              # Gateway 連線認證 + rate limit
│   │   ├── rpc_methods.py       # RPC method handlers（sessions.*、agent.*）
│   │   ├── pairing.py           # DM pairing challenge（Phase 2）
│   │   └── config.py            # YAML config + env 載入
│   │
│   ├── agent/                   # Phase 1
│   │   ├── loop.py              # AsyncIterator[Event] agent 執行迴圈
│   │   ├── context.py           # System prompt + session context 組裝
│   │   ├── events.py            # Event dataclasses（TextChunk、ToolCallStart 等）
│   │   ├── workspace.py         # Agent workspace 管理
│   │   ├── commands.py          # Slash command 偵測 + registry
│   │   ├── hooks.py             # Hook system（Phase 2）
│   │   └── multi_agent.py       # sessions_send / sessions_spawn（Phase 3）
│   │
│   ├── llm/                     # Phase 1（唯一出口）
│   │   └── router_client.py     # LLM-Router HTTP client（streaming + direct_query）
│   │
│   ├── tools/                   # Phase 1
│   │   ├── registry.py          # Tool 定義（OpenAI function-calling schema）+ 執行
│   │   ├── policy.py            # main vs sandbox 判斷 + allowlist
│   │   ├── bash.py              # bash tool（host 執行）
│   │   ├── browser.py           # Playwright browser tool
│   │   ├── file_tools.py        # 檔案讀寫
│   │   ├── cron.py              # cron tool（新增/刪除排程）
│   │   ├── sessions_tools.py    # sessions_send / sessions_spawn tool 定義
│   │   └── builtin.py           # OpenClaw 原生工具（canvas、notify 等）
│   │
│   ├── sandbox/                 # Phase 2
│   │   ├── docker_runner.py     # Docker container 建立/執行/刪除
│   │   └── policy.py            # 哪些 session 需要 sandbox
│   │
│   ├── channels/                # Phase 1（http_api）/ Phase 3（其他）
│   │   ├── base.py              # BaseChannel ABC（typing、ack、draft stream）
│   │   ├── policy.py            # allowFrom、dmPolicy、command gating
│   │   ├── http_api.py          # 直接 HTTP POST channel（Phase 1 測試用）
│   │   ├── telegram.py          # Phase 3
│   │   ├── discord_channel.py   # Phase 3
│   │   ├── slack.py             # Phase 3
│   │   ├── whatsapp.py          # Phase 3
│   │   └── webchat.py           # WebSocket WebChat（Phase 3）
│   │
│   ├── cron/                    # Phase 3
│   │   ├── service.py           # Cron scheduler 服務
│   │   ├── runner.py            # 排程任務 isolated agent 執行
│   │   ├── schedule.py          # Cron 時間規則解析
│   │   └── store.py             # Cron job 持久化（SQLite）
│   │
│   ├── memory/                  # Phase 3
│   │   ├── manager.py           # Memory 管理（hybrid search + temporal decay）
│   │   └── sqlite_store.py      # SQLite 向量儲存（sqlite-vec）
│   │
│   ├── media/                   # Phase 3
│   │   ├── store.py             # 媒體檔案儲存
│   │   ├── input.py             # 上傳檔案處理
│   │   └── mime.py              # MIME type 判斷
│   │
│   ├── skills/                  # Phase 3
│   │   ├── base.py              # AbstractSkill ABC
│   │   ├── loader.py            # 從 skills/ 目錄動態載入
│   │   ├── registry.py          # Skill registry
│   │   └── manifest.py          # Skill manifest 格式
│   │
│   ├── tts/                     # Phase 4
│   │   └── tts.py
│   │
│   ├── canvas/                  # Phase 4
│   │   ├── server.py
│   │   └── a2ui.py
│   │
│   └── logging/                 # Phase 1
│       ├── logger.py            # structured logging + redact
│       └── levels.py
│
├── skills/                      # 使用者自訂技能放置目錄
├── docker/
│   └── sandbox.Dockerfile       # Sandbox container image
├── config/
│   └── default.yaml
├── .env.example                 # 只有 channel token，無 LLM API key
├── pyproject.toml
└── README.md
```

---

## 實作計劃書

### Phase 1：核心可運行（最小 end-to-end）✅ 完成

**P1-1. Storage** ✅
- [x] SQLite schema（sessions、messages 表）
- [x] JSONL transcript writer（append-only，`~/.claw/transcripts/`）
- [x] Session CRUD + lifecycle（create / get / delete / update_last_active）
- 參考：`src/sessions/session-id.ts`、`src/sessions/transcript-events.ts`

**P1-2. LLM-Router Client** ✅
- [x] `POST /v1/chat/completions`（streaming SSE 解析 + tool_call delta 累積）
- [x] `POST /v1/direct_query`（指定 model）
- [x] Health check（ping chat completions 確認連通）
- [x] `Authorization: Bearer` header 注入
- [x] `LLMRouterError` 統一錯誤包裝

**P1-3. Tool Registry** ✅
- [x] Tool schema（OpenAI function-calling 格式）
- [x] Tool registry（`@tool` 裝飾器、execute、get_definitions）
- [x] `bash` tool（asyncio subprocess，timeout，exit code 標記）
- [x] Tool policy（main = host，non-main = 拒絕執行）
- 參考：`src/agents/tool-catalog.ts`、`src/agents/tool-policy.ts`

**P1-4. Agent Loop** ✅
- [x] `AgentLoop.run()` → `AsyncIterator[Event]`
- [x] Context 組裝（system prompt + 歷史 messages）
- [x] Streaming text chunk yield
- [x] Native function calling（tool_call_delta 分段累積 → JSON 組裝）
- [x] **Prompt-based tool calling fallback**（`<tool_call>` XML，支援不具備 native function calling 的 model）
- [x] Tool call 執行迴圈（MAX_TOOL_ROUNDS = 8 防無限迴圈）
- [x] Session 持久化（user/assistant/tool message 寫回 SQLite + JSONL）
- 參考：`src/agents/pi-embedded-runner.ts`、`src/auto-reply/reply.ts`

**P1-5. Queue** ✅
- [x] Lane-aware asyncio queue（per-session lane）
- [x] Queue mode：collect / followup / drop
- [x] `MessageQueue.submit()` 自動啟動 run_loop task
- 參考：`src/process/lanes.ts`

**P1-6. Gateway** ✅
- [x] FastAPI app + uvicorn（lifespan 注入）
- [x] WebSocket `/ws`（connect frame → RPC loop）
- [x] RPC methods：`health`、`sessions.get`、`sessions.create`、`agent.run`
- [x] `POST /v1/chat/completions`（streaming SSE + 非 streaming）
- [x] `GET /health`
- [x] Session 自動建立（不存在時）
- 參考：`src/gateway/server.ts`、`src/gateway/server-chat.ts`

**P1-7. HTTP Channel / End-to-End** ✅
- [x] curl `POST /v1/chat/completions` streaming 通過
- [x] Prompt-based tool calling end-to-end（bash `date` 實際執行成功）
- [x] LLM-Router 連線驗證（`Authorization: Bearer` API key）

**測試** ✅
- [x] 20/20 單元測試通過（`pytest tests/`）
- [x] `test_storage`、`test_router_client`、`test_tools`、`test_agent_loop`、`test_queue`、`test_gateway`

---

### Phase 2：安全隔離 + Hook System + 基礎 Skills

> 目標：非 main session 的 tool 執行在 Docker 隔離，Skills 可插拔，Hook 可干預 pipeline。

**P2-1. Docker Sandbox**
- [ ] `sandbox/docker_runner.py`：container 建立/執行/刪除/逾時清理
- [ ] `sandbox/policy.py`：哪些 session scope 走 sandbox（non-main 預設 sandbox）
- [ ] Workspace volume 掛載（`/workspace` 隔離）
- [ ] `bash` tool 路由：main → host，其他 → docker container
- [ ] `docker/sandbox.Dockerfile`（最小 image）
- 參考：`src/agents/sandbox/`、`src/node-host/invoke.ts`

**P2-2. Hook System**
- [ ] `agent/hooks.py`：`HookRegistry`（register、fire、await）
- [ ] Hook event types：`before_prompt_build`、`after_tool_call`、`before_send`、`on_run_complete`、`on_run_error`
- [ ] Hook 回傳值可修改 pipeline 行為（修改 system prompt、攔截訊息）
- [ ] Skills 可透過 `hooks.register()` 注入自訂邏輯
- 參考：`src/hooks/hooks.ts`、`src/hooks/types.ts`

**P2-3. Skills Loader（基礎版）**
- [ ] `skills/base.py`：`AbstractSkill` ABC（`name`、`system_prompt`、`tools`、`hooks`）
- [ ] `skills/manifest.py`：SKILL.md frontmatter 格式（`name`、`description`、`requires`）
- [ ] `skills/loader.py`：掃描 `skills/` 目錄，載入 Python class 或 SKILL.md
- [ ] `skills/registry.py`：skill 注冊 + gating 檢查（`requires.bins`、`requires.env`）
- [ ] System prompt 注入：active skills 的 prompt 段落合併到 context
- [ ] Tool 注入：skill 定義的 tools 自動加入 registry
- 參考：`src/plugins/loader.ts`、`src/plugin-sdk/core.ts`、`src/agents/skills/`

**P2-4. 安全 Pairing**
- [ ] `core/pairing.py`：DM pairing challenge（未知使用者需要配對碼）
- [ ] Setup code 生成（6 位數 PIN，限時有效）
- [ ] `channels/policy.py`：allowFrom 白名單、dmPolicy 設定
- [ ] `core/auth.py`：Gateway WebSocket 認證
- 參考：`src/pairing/pairing-challenge.ts`、`src/security/dm-policy-shared.ts`

**P2-5. Config System**
- [ ] `core/config.py`：YAML config 讀取（`config/default.yaml`）
- [ ] Env 覆蓋（`.env` → YAML fallback）
- [ ] Per-agent config（system prompt、tools 白名單、queue mode）

---

### Phase 3：Channels + Cron + Multi-agent

> 目標：Telegram、Discord 接通，cron 排程，多 agent 協作。

**P3-1. Channel 抽象層**
- [ ] `channels/base.py`：`BaseChannel` ABC
  - `on_message(msg)` → 丟入 queue
  - `send(session_id, text)`
  - `send_stream(session_id, async_iter)` （draft 模式逐字更新）
  - typing indicator（`send_typing()`）
  - ack reaction（收到訊息打 ✅）
- [ ] `channels/policy.py`：per-channel allowFrom、command gating
- 參考：`src/plugin-sdk/channel-runtime.ts`、`src/channels/draft-stream-loop.ts`

**P3-2. Telegram Channel**
- [ ] `channels/telegram.py`（`python-telegram-bot`）
- [ ] 私訊 + 群組訊息接收
- [ ] Markdown streaming（逐步更新訊息）
- [ ] 圖片/檔案附件接收 → 轉發給 media store
- [ ] `/command` slash command 觸發
- 參考：`src/plugin-sdk/telegram.ts`

**P3-3. Discord Channel**
- [ ] `channels/discord_channel.py`（`discord.py`）
- [ ] DM + 伺服器頻道接收
- [ ] Thread 模式（每次對話開新 thread）
- [ ] Embed 格式化回覆
- 參考：`src/plugin-sdk/discord.ts`

**P3-4. Slash Command System**
- [ ] `agent/commands.py`：Command 注冊（`/reset`、`/history`、`/skill`、`/cron`）
- [ ] Command 解析（從訊息開頭偵測 `/`）
- [ ] Permission gating（哪些 user 可以用哪些 command）
- 參考：`src/auto-reply/command-detection.ts`、`src/auto-reply/commands-registry.ts`

**P3-5. Cron Scheduler**
- [ ] `cron/service.py`：APScheduler 或 `schedule` 排程服務
- [ ] `cron/store.py`：SQLite 持久化（cron jobs 表）
- [ ] `cron/runner.py`：排程觸發時以 isolated agent session 執行
- [ ] `tools/cron.py`：`cron_add`、`cron_list`、`cron_delete` tool
- [ ] `/cron` command：從 chat 管理排程
- 參考：`src/cron/service.ts`、`src/cron/isolated-agent.ts`

**P3-6. Multi-agent（sessions_send / sessions_spawn）**
- [ ] `agent/multi_agent.py`：ACP（Agent Communication Protocol）
- [ ] `tools/sessions_tools.py`：
  - `sessions_send(target_session, message)` — 送訊息給另一個 agent session
  - `sessions_spawn(agent_id, goal)` — 建立子 agent，繁殖到新 session
  - `sessions_list()` — 列出目前所有 active sessions
- [ ] Subagent announce flow（子 agent 完成後回報 parent）
- [ ] Per-session write lock（防止 concurrent write）
- 參考：`src/acp/client.ts`、`src/acp/server.ts`、`src/acp/persistent-bindings.ts`

**P3-7. Media Handling（基礎版）**
- [ ] `media/store.py`：本地媒體檔案暫存
- [ ] `media/input.py`：接收來自 channel 的圖片/PDF，轉為 base64 → 送 LLM-Router
- [ ] `media/mime.py`：MIME type 判斷
- 參考：`src/media/input-files.ts`

---

### Phase 4：Skills 生態系 + Memory / RAG

> 目標：完整 skill 擴充能力，長期記憶。

**P4-1. Skills Extension System（完整版）**
- [ ] Python class-based skill（繼承 `AbstractSkill`）
- [ ] SKILL.md 純 prompt skill（無程式碼，只注入 system prompt）
- [ ] Skill 的 lifecycle hooks（`on_load`、`on_unload`、`before_prompt_build`）
- [ ] Skill 可定義自己的 tools（自動注冊到 tool registry）
- [ ] Skill 可定義自己的 commands（`/skill-name:command`）
- [ ] Skill gating：`requires.bins`（檢查可執行檔存在）、`requires.env`（檢查 env var）
- [ ] Hot reload（`watchdog` 監聽 `skills/` 目錄變更）
- [ ] 內建 skill 範例：`skills/search/`、`skills/code_review/`、`skills/daily_brief/`
- 參考：`src/plugins/`、`src/plugin-sdk/core.ts`

**P4-2. Memory / RAG**
- [ ] `memory/manager.py`：Memory 管理器（save、search、forget）
- [ ] `memory/sqlite_store.py`：`sqlite-vec` 向量儲存
- [ ] Hybrid search：BM25（關鍵字）+ 向量（語意）
- [ ] Temporal decay：舊記憶相關性衰減
- [ ] Embedding：透過 LLM-Router `/v1/embeddings`
- [ ] `tools/memory_tools.py`：`memory_save`、`memory_search` tool
- [ ] Session context 自動注入相關記憶
- 參考：`src/memory/manager.ts`、`src/memory/hybrid.ts`、`src/memory/temporal-decay.ts`

**P4-3. Context Compaction**
- [ ] Token 計數（`tiktoken` 或 LLM-Router 回傳的 usage）
- [ ] 超過 context window 時自動截斷（head + tail 策略）
- [ ] Summarization compaction（呼叫 LLM-Router 把舊訊息壓縮成摘要）
- 參考：`src/agents/pi-embedded-runner/tool-result-truncation.ts`

**P4-4. Slack Channel**
- [ ] `channels/slack.py`（`slack-bolt`）
- [ ] App mention + DM 接收
- [ ] Thread reply 模式
- 參考：`src/plugin-sdk/slack.ts`

---

### Phase 5：進階工具 + MCP Bridge

> 目標：接通 MCP 生態，TTS，完整 file/browser tool。

**P5-1. MCP Bridge**
- [ ] `tools/mcp_bridge.py`：MCP client（連接外部 MCP server）
- [ ] MCP tool 自動映射到 claw tool registry
- [ ] 支援 stdio 和 SSE transport
- [ ] MCP server 白名單管理（config 設定）

**P5-2. Browser Tool（完整版）**
- [ ] `tools/browser.py`：Playwright 無頭瀏覽器
- [ ] `browser_navigate(url)`、`browser_screenshot()`、`browser_click(selector)`、`browser_type(selector, text)`
- [ ] Sandbox 模式（browser 在 Docker 內執行）

**P5-3. File Tools（完整版）**
- [ ] `tools/file_tools.py`：`file_read`、`file_write`、`file_list`、`file_search`
- [ ] Path sandbox（限制在 workspace 目錄內）
- [ ] 大檔案截斷（head + tail）

**P5-4. TTS**
- [ ] `tts/tts.py`：TTS 頂層邏輯
- [ ] 支援本地 TTS（`pyttsx3`）或 LLM-Router `/v1/audio/speech`
- [ ] Channel 整合（Telegram voice message、Discord voice channel）
- 參考：`src/tts/tts.ts`

**P5-5. WhatsApp / LINE Channel（選做）**
- [ ] `channels/whatsapp.py`（WhatsApp Business API）
- [ ] `channels/line.py`（LINE Messaging API）

---

### Phase 6：Admin + Observability

> 目標：可觀測、可維運。

**P6-1. Structured Logging**
- [ ] `logging/logger.py`：structlog JSON 格式
- [ ] 敏感資料 redact（`Authorization` header、API key）
- [ ] Per-session log context（session_id、agent_id 自動附加）

**P6-2. Metrics**
- [ ] Prometheus metrics（request count、token usage、tool call count、queue depth）
- [ ] `/metrics` endpoint

**P6-3. Admin API**
- [ ] `GET /admin/sessions`：列出所有 active sessions
- [ ] `DELETE /admin/sessions/{id}`：強制關閉 session
- [ ] `GET /admin/queue`：queue 狀態
- [ ] `POST /admin/reload-skills`：熱重載 skills
- [ ] Admin token 認證（與 Gateway WebSocket 分開）

**P6-4. Canvas / A2UI（選做）**
- [ ] `canvas/server.py`：A2UI 渲染服務
- [ ] `canvas/a2ui.py`：A2UI 協定（結構化 UI 元件）
- [ ] WebChat channel + Canvas 整合
- 參考：`src/canvas-host/`、`src/channels/web/`

---

## 依賴

```toml
[project]
dependencies = [
    # Core
    "fastapi>=0.110.0",
    "uvicorn[standard]>=0.27.0",
    "httpx>=0.27.0",           # LLM-Router client（唯一 LLM 出口）
    "pydantic>=2.6.0",
    "pyyaml>=6.0",
    "python-dotenv>=1.0.0",
    # Tools
    "docker>=7.0.0",           # sandbox 管理
    "playwright>=1.40.0",      # browser tool
    # Storage
    "aiosqlite>=0.20.0",       # async SQLite
]

[project.optional-dependencies]
channels = [
    "python-telegram-bot>=21.0",
    "discord.py>=2.3.0",
    "slack-bolt>=1.18.0",
]
memory = [
    "sqlite-vec",              # 向量搜尋
]
```

**claw-python 不依賴任何 LLM SDK**。所有 LLM 呼叫透過 LLM-Router HTTP API，只用 `httpx`。

---

## License

MIT
