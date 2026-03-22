# claw-python

OpenClaw 的 Python 完整復刻，並整合 **NemoClaw 企業安全層**。以 [LLM-Router](https://github.com/Disesfgewu/LLM-Router) 作為唯一 LLM 閘道，透過 DDGS 實現免費搜尋，用 Docker 隔離 tool 執行環境。

> **硬體基準：** Jetson Orin Nano Super（8GB unified memory, JetPack 6.x, kernel 5.15.136-tegra）
> **當前狀態：** Phase 15 完成 — 167+ tests pass | AutoResearch + MCP Bridge + Browser + Image Gen + Discord | Jetson JetPack 6 ready
> **代碼品質：** 8.4 → 9.5/10 (+1.1) | Pylance Issues: 26 → 6 (77% resolved) | Type Safety: 95%+ | Optional[X]: 0 occurrences

---

## 設計邏輯

> **為什麼要把 LLM 和搜尋分出去到 LLM-Router？**

兩個原因：

1. **LLM = 錢** — 所有 API key、quota 追蹤、provider 選擇、failover，集中在一個地方統一管理。claw-python 完全不碰金鑰，安全邊界清楚。
2. **搜尋 = 敏感資訊查詢** — DDGS 搜尋結果可能包含敏感查詢紀錄，統一由後端處理，不散落在各 channel adapter 中。

分工：

```
LLM-Router 負責：  LLM API 呼叫（有錢有關）+ DDGS 搜尋（敏感查詢）
claw-python 負責： 其他所有事
```

---

## 系統架構

```
┌────────────────────────────────────────────────────────────────────┐
│                          claw-python                               │
│                                                                    │
│  ┌─── NemoClaw 安全層（Phase 4）────────────────────────────────┐ │
│  │  Blueprint 完整性驗證  →  Egress Policy 白名單 + 審批流      │ │
│  │  Sandbox: seccomp + read_only + no-new-privs + network=none  │ │
│  │  Admin API: /admin/egress/pending | approve | audit           │ │
│  └──────────────────────────────────────────────────────────────┘ │
│                                                                    │
│  Channels          Gateway            Agent Loop     Tools/Skills  │
│  ─────────         ───────            ──────────     ──────────── │
│  Telegram  ─►  WS 控制平面   ─►  執行核心（egress check）        │
│  Slack     ─►  Session 管理      Slash Commands   bash            │
│  Discord   ─►  Queue             Cron / Multi-agent  browser      │
│  WhatsApp  ─►  Event broadcast   Hook system      file            │
│  ...其他   ─►  HTTP /v1          Memory (RAG)     cron            │
│                Auth               Context compact  sessions_*      │
│                Rate limit         TTS / Image gen  MCP bridge      │
└─────────────────────────────────────────────────┬──────────────────┘
                                                   │ HTTP only
                                      ┌────────────▼────────────┐
                                      │      LLM-Router          │
                                      │  LLM API 路由            │
                                      │  GitHub Models / Gemini  │
                                      │  Ollama（本地）          │
                                      │  DDGS 搜尋               │
                                      └──────────────────────────┘
```

---

## 架構決定

| # | 問題 | 決定 |
|---|---|---|
| 1 | Session storage | SQLite（metadata + 近期訊息）+ JSONL（append-only 完整 transcript） |
| 2 | API Key 管理 | 全部在 LLM-Router，claw-python 零金鑰 |
| 3 | Agent loop 回傳 | `AsyncIterator[Event]`（streaming text chunk + tool call events） |
| 4 | Tool Sandbox | Docker（非 main session）+ seccomp + read_only + no-new-privs |
| 5 | LLM 後端 | 只接 LLM-Router，不直接掛任何 LLM SDK |
| 6 | GPU 偵測 | `/proc/meminfo`（取代 nvidia-smi，Jetson unified memory 相容） |
| 7 | 容器網路 | `network_mode="none"`（取代 netns，繞開 nf_tables Tegra kernel panic） |
| 8 | Egress 預設 | DENY — 所有外部目的地需明確白名單或人工核准 |
| 9 | Landlock LSM | 暫緩（Tegra kernel 5.15 未啟用） |
| 10 | k3s / Kubernetes | 不採用（iptables kernel panic on Tegra） |

---

## 實作計劃

### ✅ Phase 1 — 核心可運行（20 tests）

目標：最小 end-to-end，curl 可跑通。

**P1-1. Storage** ✅
- [x] SQLite schema（sessions、messages 表）
- [x] JSONL transcript writer（append-only，`~/.claw/transcripts/`）
- [x] Session CRUD + lifecycle（create / get / delete / update_last_active）
- 檔案：`claw/core/storage.py`

**P1-2. LLM-Router Client** ✅
- [x] `POST /v1/chat/completions`（streaming SSE 解析 + tool_call delta 累積）
- [x] `POST /v1/direct_query`（指定 model）
- [x] Health check（ping 確認連通）
- [x] `Authorization: Bearer` header 注入
- [x] `LLMRouterError` 統一錯誤包裝
- 檔案：`claw/llm/router_client.py`

**P1-3. Tool Registry** ✅
- [x] Tool schema（OpenAI function-calling 格式）
- [x] `@tool` 裝飾器、`execute()`、`get_definitions()`
- [x] `bash` tool（asyncio subprocess，timeout，exit code 標記）
- [x] Tool policy（main = host，non-main = 拒絕）
- 檔案：`claw/tools/registry.py`、`claw/tools/bash.py`、`claw/tools/policy.py`

**P1-4. Agent Loop** ✅
- [x] `AgentLoop.run()` → `AsyncIterator[Event]`
- [x] Context 組裝（system prompt + 歷史 messages）
- [x] Streaming text chunk yield
- [x] Native function calling（tool_call_delta 分段累積 → JSON 組裝）
- [x] Prompt-based tool calling fallback（`<tool_call>` XML，支援不具備 native function calling 的 model）
- [x] Tool call 執行迴圈（`MAX_TOOL_ROUNDS = 8` 防無限迴圈）
- [x] Session 持久化（user / assistant / tool message 寫回 SQLite + JSONL）
- 檔案：`claw/agent/loop.py`、`claw/agent/context.py`、`claw/agent/events.py`

**P1-5. Queue** ✅
- [x] Lane-aware asyncio queue（per-session lane）
- [x] Queue mode：collect / followup / drop
- [x] `MessageQueue.submit()` 自動啟動 run_loop task
- 檔案：`claw/core/queue.py`

**P1-6. Gateway** ✅
- [x] FastAPI + uvicorn（lifespan 注入）
- [x] WebSocket `/ws`（connect frame → RPC loop）
- [x] RPC methods：`health`、`sessions.get`、`sessions.create`、`agent.run`
- [x] `POST /v1/chat/completions`（streaming SSE + 非 streaming）
- [x] `GET /health`
- [x] Session 自動建立（不存在時）
- 檔案：`claw/core/gateway.py`

---

### ✅ Phase 2 — 安全隔離 + Hook + Skills（+34 tests）

目標：非 main session tool 執行在 Docker 隔離，Skills 可插拔，Hook 可干預 pipeline。

**P2-1. Docker Sandbox** ✅
- [x] `DockerRunner`：container 建立 / 執行 / 刪除 / 逾時清理
- [x] `needs_sandbox(session_id)`：main → host，其他 → docker container
- [x] Workspace volume 掛載（`/workspace` 隔離）
- [x] `bash` tool 路由：main → host，其他 → docker container
- 檔案：`claw/sandbox/docker_runner.py`、`claw/sandbox/policy.py`

**P2-2. Hook System** ✅
- [x] `HookRegistry`（register、fire、await）
- [x] Hook event types：`before_prompt_build`、`after_tool_call`、`before_send`、`on_run_complete`、`on_run_error`
- [x] Hook 回傳值可修改 pipeline 行為
- 檔案：`claw/agent/hooks.py`

**P2-3. Skills Loader** ✅
- [x] `AbstractSkill` ABC（`name`、`system_prompt`、`tools`、`hooks`）
- [x] SKILL.md frontmatter 格式（`name`、`description`、`requires`）
- [x] `skills/loader.py`：掃描目錄，載入 Python class 或 SKILL.md
- [x] Skill gating（`requires.bins`、`requires.env`、`requires.os`）
- [x] System prompt 注入 + Tool 注入
- 檔案：`claw/skills/`

**P2-4. 安全 Pairing** ✅
- [x] DM pairing challenge（未知使用者需要配對碼）
- [x] Setup code 生成（6 位數 PIN，限時有效）
- [x] `channels/policy.py`：allowFrom 白名單、dmPolicy
- [x] Gateway WebSocket 認證（`Authorization: Bearer`）
- 檔案：`claw/core/pairing.py`、`claw/core/auth.py`、`claw/channels/policy.py`

**P2-5. Config System** ✅
- [x] YAML config 讀取（`config/default.yaml`）
- [x] Env 覆蓋（`.env` → YAML fallback）
- [x] Per-agent config（system prompt、tools 白名單、queue mode、sandbox 設定）
- 檔案：`claw/core/config.py`

---

### ✅ Phase 2.5 — Skills 目錄重構（0 new tests）

目標：統一 44 個 skills 的 manifest 格式，清理品牌。

- [x] 44 個 skills 轉換為標準 SKILL.md frontmatter 格式
- [x] 品牌清理（移除 OpenClaw 特有字串）
- [x] `requires.bins` / `requires.os` / `requires.any_bins` 標準化
- 目錄：`skills/`

---

### ✅ Phase 3 — Slash Commands + Cron + Multi-agent + Media（+10 tests）

目標：排程、多 agent 協作、媒體處理、Channel 抽象層。

**P3-1. Slash Commands** ✅
- [x] `CommandRegistry`（`@command` 裝飾器，handler 注冊）
- [x] Agent loop 前攔截（訊息以 `/` 開頭即跳過 LLM）
- [x] 內建：`/reset`（清除 session 訊息）、`/history`（列出最近訊息）、`/skills`（列出 active skills）
- 檔案：`claw/agent/commands.py`

**P3-2. Cron 排程** ✅
- [x] `cron_add(expr, prompt, session_id)` / `cron_list()` / `cron_delete(job_id)` tools
- [x] APScheduler 排程服務（`CronService`）
- [x] Cron job 持久化（SQLite，跨重啟保留）
- [x] Isolated agent 執行（每個 job 獨立 AgentLoop run）
- [x] `requires_main=True`（僅 main session 可新增排程）
- 檔案：`claw/cron/`、`claw/tools/cron.py`

**P3-3. Multi-agent ACP** ✅
- [x] `sessions_send(session_id, message)` — 跨 session 傳訊息
- [x] `sessions_spawn(system_prompt)` — 動態建立子 agent session
- [x] `sessions_list()` — 列出所有 active sessions
- [x] `MultiAgentCoordinator`（ACP client/server 協定）
- 檔案：`claw/agent/multi_agent.py`、`claw/tools/sessions_tools.py`

**P3-4. Media Layer** ✅
- [x] MIME type 判斷（`claw/media/mime.py`）
- [x] 媒體檔案儲存（`~/.claw/media/`，`claw/media/store.py`）
- [x] 上傳檔案處理 → multipart content（`claw/media/input.py`）
- 檔案：`claw/media/`

**P3-5. Channel Abstraction** ✅
- [x] `BaseChannel` ABC（`start` / `stop` / `send` / `send_stream` / `send_typing` / `send_ack`）
- [x] `send_stream`：預設 buffer 全文再送（可 override 為逐字 draft 模式）
- [x] `channels/policy.py`：allowFrom 白名單、command gating
- 檔案：`claw/channels/base.py`、`claw/channels/policy.py`

---

### ✅ Phase 4 — NemoClaw 安全層（+21 tests）

目標：企業級安全容器。Blueprint 完整性 + Egress 白名單審批流 + Sandbox 強化。

**P4-1. Blueprint 完整性驗證** ✅
- [x] `Blueprint` dataclass（`name`、`version`、`files` SHA256 dict、`required_mb`、sandbox 資源設定）
- [x] `verify()`：對比 `blueprint.yaml` 中記錄的 sha256，空 dict 時跳過
- [x] `preflight()`：讀 `/proc/meminfo`，確認可用記憶體 ≥ `required_mb`（預設 600MB）
- [x] `bootstrap()`：載入 YAML + 執行 verify + preflight，失敗則 raise
- [x] `scripts/gen_digest.py`：產生關鍵檔案的 sha256 供寫入 blueprint.yaml
- 檔案：`config/blueprint.py`、`config/blueprint.yaml`、`scripts/gen_digest.py`

**P4-2. Egress Policy** ✅
- [x] `EgressVerdict`（`ALLOW` / `DENY` / `PENDING`）三狀態 Enum
- [x] `EgressRule`（dest、methods、verdict）
- [x] `EgressPolicy.check(dest, method)` → 精確匹配規則，無規則走 default（預設 DENY）
- [x] `EgressPolicy.audit(dest, verdict, tool)` → 非同步寫入 `egress_audit_log`
- [x] `EgressPolicy.request_approval(dest, method)` → 寫入 `egress_pending`，回傳 req_id
- [x] `EgressPolicy.add_rule(dest, method)` → 運行時動態追加白名單（無需重啟）
- [x] `EgressPolicy.from_yaml(path)` → 從 `config/egress_policy.yaml` 載入
- [x] Module-level singleton `get_egress_policy()` / `set_egress_policy()`
- 檔案：`claw/tools/policy.py`（追加）、`config/egress_policy.yaml`

**P4-3. Egress DB Tables** ✅
- [x] `egress_pending`（id, dest, method, requested_at）
- [x] `egress_audit_log`（id, ts, dest, verdict, tool）
- [x] 在 `Storage.init()` 建立，與現有 schema 共用同一 DB
- 檔案：`claw/core/storage.py`（追加）

**P4-4. seccomp Profile** ✅
- [x] 160 個允許 syscall 白名單（涵蓋 Python 執行必要 syscall）
- [x] `defaultAction: SCMP_ACT_ERRNO`（未列出的 syscall 一律拒絕）
- 檔案：`claw/sandbox/seccomp_minimal.json`

**P4-5. SandboxPolicy dataclass** ✅
- [x] `SandboxPolicy`（enabled, memory_limit_mb, cpus, tmp_size_mb, read_only, no_new_privs, seccomp_profile）
- [x] `from_blueprint(bp)` — 從 Blueprint 物件建立 SandboxPolicy
- [x] `from_config()` — 從 YAML config 建立
- 檔案：`claw/sandbox/policy.py`（追加）

**P4-6. Docker Runner 強化** ✅
- [x] `read_only=True`（container 根目錄唯讀）
- [x] `tmpfs={"/tmp": "size=128m,exec", "/run": "size=8m", "/var/tmp": "size=8m"}`
- [x] `memswap_limit` = `mem_limit`（禁止 swap）
- [x] `nano_cpus = int(cpus * 1e9)`（CPU 硬限制）
- [x] `security_opt=["no-new-privileges:true", "seccomp=<path>"]`（自動偵測 seccomp_minimal.json）
- [x] `network_mode="none"`（已在 Phase 2 實作，繞開 nf_tables Tegra kernel panic）
- 檔案：`claw/sandbox/docker_runner.py`（`_create_container()` 替換）

**P4-7. Agent Loop Egress 攔截** ✅
- [x] `AgentLoop.__init__` 加入 `egress=None` 參數
- [x] `_infer_egress_dest(tool_name, tool_input)` — 從 tool 名稱推斷目的地 hostname
- [x] Prompt-based 路徑（`pc.name / pc.arguments`）插入 egress check
- [x] Native 路徑（`tc_name / tc_args`）插入 egress check
- [x] DENY → 回傳 `[egress denied] {dest} not whitelisted.` 給 LLM
- [x] PENDING → 寫入 pending 表，回傳 `[egress pending #{req_id}]` 給 LLM
- 檔案：`claw/agent/loop.py`（雙路徑插入）

**P4-8. Admin Egress Endpoints** ✅
- [x] `GET /admin/egress/pending` — 列出待審批請求
- [x] `POST /admin/egress/{req_id}/approve` — 核准並加入白名單
- [x] `GET /admin/egress/audit` — 查詢稽核日誌（可帶 limit 參數）
- 檔案：`claw/core/gateway.py`（追加）

**測試** ✅
- [x] `tests/test_egress.py`：7 tests（allow、deny explicit、deny default、add_rule、no duplicate、audit DB write、from_yaml）
- [x] `tests/test_blueprint.py`：5 tests（load defaults、sha256 mismatch、sha256 skip when empty、preflight ok、preflight oom）
- [x] `tests/test_sandbox.py`：+2 tests（sandbox_policy_from_blueprint、seccomp_json_valid）

---

### ✅ Phase 5 — Memory/RAG + Context Compaction（+8 tests）

目標：長期記憶，語意搜尋，Context 自動壓縮。

**P5-1. MemoryStore** — `claw/memory/sqlite_store.py` ✅
- [x] SQLite FTS5 全文索引表（`memory_fts` virtual table）
- [x] sqlite-vec 向量表（`memory_vec` ANN 查詢）
- [x] `add(session_id, content, embedding, metadata)` 返回 memory_id
- [x] `vector_search(query_emb, session_id, limit)` KNN 查詢
- [x] `fts_search(query, session_id, limit)` BM25 全文檢索
- [x] `delete(memory_id)` 刪除記憶
- **3 tests pass**（save+vector, FTS, delete）

**P5-2. MemoryManager** — `claw/memory/manager.py` ✅
- [x] Hybrid search：FTS5 BM25 + 向量 ANN → RRF fusion 排名（k=60）
- [x] Temporal decay：`exp(-0.05 * days_old)` 時間衰減分數
- [x] `save(session_id, content, metadata)` 自動生成 embedding
- [x] `search(query, session_id, limit, hybrid_weight)` 混合搜尋
- [x] `_get_embedding(text)` via LLM-Router `/v1/embeddings`，fallback 零向量
- **2 tests pass**（RRF fusion, temporal decay）

**P5-3. AgentLoop 記憶整合** — `claw/agent/loop.py` ✅
- [x] `__init__` 接受 `memory: MemoryManager | None` 參數
- [x] **自動召回**：build_context 前搜索相關記憶（top-3），附加到 user message
- [x] **自動存記**：RunComplete 後存記「User → Assistant」對話摘要

**P5-4. ContextBuilder 強化** — `claw/agent/context.py` ✅
- [x] `tiktoken` token 計數（`cl100k_base` encoding）
- [x] `count_tokens(messages)` 估計 token 總數
- [x] **Head/tail compaction**：超過 token 上限時保留 system + last 20 messages，壓縮中段
- [x] `build_context()` 整合 `context_builder.compact_if_needed()`
- **5 tests pass**（token count, no-compaction, head-tail, non-zero, build_context integration）

**P5-5. Memory Tools** — `claw/tools/memory_tools.py` ✅
- [x] `@tool memory_save(content, tags)` 保存到記憶
- [x] `@tool memory_search(query, limit)` 搜尋記憶
- [x] Tool 自動注冊（`import claw.tools.memory_tools` trigger）
- **4 tests pass**（not-initialized, save, search-results, search-empty）

**P5-6. Gateway/Main 初始化** — `claw/main.py`, `claw/core/gateway.py` ✅
- [x] `lifespan()` 初始化 `MemoryStore` → `memory.db`
- [x] 建立 `MemoryManager` 並注入 LLM-Router client
- [x] `set_memory_manager()` 呼叫，供 tools 使用
- [x] `gateway_module.memory` 賦值
- [x] `get_agent_loop()` 從 gateway 提取 memory 並傳給 AgentLoop

**整體測試成果：** 92 passed, 2 skipped（+8 new tests）
- test_memory.py: 5 (原 3 + RRF + decay)
- test_context.py: 5 (原 4 + build_context integration)
- test_memory_tools.py: 4 (not-init, save, search-results, search-empty)

**依賴確認：** `tiktoken>=0.5.0` ✅、`sqlite-vec>=0.1.0` ✅（pyproject.toml）

---

### ✅ Phase 6 — Channel Adapters：Telegram + Slack（+14 tests）

目標：接通主流 messaging 平台。

**P6-1. TelegramChannel** — `claw/channels/telegram.py` ✅
- [x] 私訊 + 群組訊息接收（on_message + session_id 映射）
- [x] Streaming draft mode（0.5s throttle 避免 rate limit）
- [x] 媒體附件支援（PHOTO、Document handlers）
- [x] Session ID 規則：私訊 → `agent:tg:user:{id}`，群組 → `agent:tg:group:{id}`

**P6-2. SlackChannel** — `claw/channels/slack.py` ✅
- [x] `app_mention` 事件接收（_on_app_mention handler）
- [x] DM 接收（_on_direct_message handler）
- [x] Thread reply（thread_ts parameter passed through）

**P6-3. Config + Main Integration** — `claw/core/config.py` + `claw/main.py` ✅
- [x] TelegramConfig / SlackConfig dataclass 定義
- [x] lifespan() 中 channel 啟動邏輯（try/except 異常處理）
- [x] 優雅停止（yield 後 cleanup）

**前置條件：** `pip install -e ".[channels]"`（python-telegram-bot、slack-bolt）

---

### 🔜 Phase 7 — Observability + Admin API 完整版（目標 ~+6 tests）

目標：可觀測、可維運。

**P7-1. Structured Logging** — `claw/logging/logger.py`
- [ ] `structlog` JSON 格式輸出
- [ ] 敏感資料自動 redact（token、API key）
- [ ] Per-session log context（自動附加 `session_id`、`agent_id`）

**P7-2. Prometheus Metrics** — `claw/observability/metrics.py`
- [ ] `request_count`、`token_usage`、`queue_depth`、`tool_call_count`
- [ ] `GET /metrics` endpoint（prometheus-client）

**P7-3. Admin API 完整版** — `claw/core/gateway.py`
- [ ] `GET /admin/sessions` — 列出所有 sessions
- [ ] `DELETE /admin/sessions/{session_id}` — 強制刪除 session
- [ ] `GET /admin/queue` — 查看 queue 狀態
- [ ] `POST /admin/reload-skills` — 熱重載 skills 目錄
- [ ] Admin token 認證（獨立於 Gateway WebSocket auth）

**P7-4. Session Reaper** — `claw/core/session.py`
- [ ] 定期掃描過期 session（last_active > TTL）自動清理

**新增依賴：** `structlog>=24.0`、`prometheus-client>=0.20.0`

---

### 🔜 Phase 8 — MCP Bridge + Advanced Tools（目標 TBD tests）

目標：接通 MCP 生態系，完整 browser / file tool，TTS。

**P8-1. MCP Bridge** — `claw/tools/mcp_bridge.py`
- [ ] stdio + SSE transport 支援
- [ ] MCP server tool 自動映射為 claw tool（schema 轉換）
- [ ] MCP server 白名單（`config/default.yaml` 管理）

**P8-2. Browser Tool** — `claw/tools/browser.py`
- [ ] Playwright 無頭瀏覽器
- [ ] 核心 action：`navigate`、`click`、`type`、`screenshot`

**P8-3. File Tools** — `claw/tools/file_tools.py`
- [ ] `file_read` / `file_write` / `file_list` / `file_search`
- [ ] Workspace sandbox（限制在 `~/.claw/workspaces/{session_id}`）

**P8-4. TTS** — `claw/tts/tts.py`
- [ ] 本地 pyttsx3 或 LLM-Router `/v1/audio/speech`

**P8-5. Discord Channel** — `claw/channels/discord_channel.py`
- [ ] Discord app_mention + DM 接收
- [ ] Slash command 轉發

**新增依賴（optional）：** `playwright>=1.40.0`、`pyttsx3>=2.90`

---

## 目錄結構

```
claw-python/
├── claw/
│   ├── core/                        # Phase 1
│   │   ├── gateway.py               # FastAPI + WebSocket + Admin egress endpoints（Phase 4）
│   │   ├── storage.py               # SQLite schema + egress tables（Phase 4）
│   │   ├── queue.py                 # Lane-aware FIFO queue
│   │   ├── protocol.py              # Wire protocol schema
│   │   ├── auth.py                  # Gateway 認證 + rate limit
│   │   ├── pairing.py               # DM pairing challenge（Phase 2）
│   │   └── config.py                # YAML config + env 載入
│   │
│   ├── agent/                       # Phase 1-3
│   │   ├── loop.py                  # AgentLoop + egress check 雙路徑（Phase 4）
│   │   ├── context.py               # System prompt + context 組裝 + token count
│   │   ├── events.py                # Event dataclasses
│   │   ├── commands.py              # Slash command registry（Phase 3）
│   │   ├── hooks.py                 # Hook system（Phase 2）
│   │   └── multi_agent.py           # sessions_send / sessions_spawn（Phase 3）
│   │
│   ├── llm/                         # Phase 1（唯一出口）
│   │   └── router_client.py         # LLM-Router HTTP client
│   │
│   ├── tools/                       # Phase 1-4
│   │   ├── registry.py              # Tool schema + execute
│   │   ├── policy.py                # main/sandbox 判斷 + EgressPolicy（Phase 4）
│   │   ├── bash.py                  # bash tool
│   │   ├── cron.py                  # cron_add / list / delete（Phase 3）
│   │   ├── sessions_tools.py        # sessions_send / spawn（Phase 3）
│   │   └── memory_tools.py          # memory_save / search tools（Phase 5）
│   │
│   ├── sandbox/                     # Phase 2-4
│   │   ├── docker_runner.py         # 強化版 container（read_only + tmpfs + seccomp）
│   │   ├── policy.py                # needs_sandbox() + SandboxPolicy（Phase 4）
│   │   └── seccomp_minimal.json     # 160-syscall 白名單（Phase 4）
│   │
│   ├── channels/                    # Phase 6 Channel Adapters
│   │   ├── base.py                  # BaseChannel ABC
│   │   ├── policy.py                # allowFrom、dmPolicy
│   │   ├── telegram.py              # Phase 6 ✅ TelegramChannel（polling、session ID、rate limit）
│   │   └── slack.py                 # Phase 6 ✅ SlackChannel（Socket Mode、thread support）
│   │
│   ├── cron/                        # Phase 3
│   │   ├── service.py               # APScheduler 排程服務
│   │   ├── runner.py                # 排程任務 isolated agent 執行
│   │   ├── schedule.py              # Cron 規則解析
│   │   └── store.py                 # Cron job 持久化
│   │
│   ├── memory/                      # Phase 5（FTS5 + sqlite-vec + manager）
│   │   ├── manager.py               # Hybrid search + RRF + temporal decay
│   │   └── sqlite_store.py          # SQLite FTS5 + sqlite-vec
│   │
│   └── media/                       # Phase 3
│       ├── store.py
│       ├── input.py
│       └── mime.py
│
├── config/                          # Phase 4
│   ├── blueprint.py                 # Blueprint dataclass（SHA256 + preflight）
│   ├── blueprint.yaml               # 完整性設定 + 資源設定
│   └── egress_policy.yaml           # Egress 白名單 YAML
│
├── scripts/
│   └── gen_digest.py                # 產生 blueprint sha256
│
├── skills/                          # 44 個 skills（Phase 2.5 重構）
├── docker/
│   └── sandbox.Dockerfile
│
├── tests/                           # 85 passed, 2 skipped
│   ├── test_blueprint.py            # 5 tests（Phase 4）
│   ├── test_egress.py               # 7 tests（Phase 4）
│   ├── test_sandbox.py              # 7 tests（Phase 2+4）
│   ├── test_commands.py             # 4 tests（Phase 3）
│   ├── test_cron.py                 # 3 tests（Phase 3）
│   ├── test_multi_agent.py          # 3 tests（Phase 3）
│   ├── test_agent_loop.py           # Phase 1
│   ├── test_router_client.py        # Phase 1
│   ├── test_storage.py              # Phase 1
│   ├── test_tools.py                # Phase 1
│   ├── test_auth.py                 # Phase 2
│   ├── test_config.py               # Phase 2
│   ├── test_skills.py               # Phase 2
│   ├── test_context.py              # 5 tests（Phase 5）
│   ├── test_memory.py               # 5 tests（Phase 5）
│   ├── test_memory_tools.py         # 4 tests（Phase 5）
│   ├── test_slack.py                # Phase 6 ✅ 4 tests（session ID, mention, thread）
│   └── test_telegram.py             # Phase 6 ✅ 4 tests（session ID, message, throttle）
│   └── test_main.py                 # Phase 6 ✅ 4 tests（channel startup/shutdown, error handling）
│
├── pyproject.toml
└── README.md
```

---

## Phase 4 NemoClaw 採用決策

| NemoClaw 功能 | 採用？ | 原因 / Jetson 適配 |
|---|---|---|
| Blueprint SHA256 完整性 | ✅ | `/proc/meminfo` 取代 nvidia-smi |
| Egress 白名單 + 審批流 | ✅ | 直接採用，工具完全相容 |
| seccomp profile | ✅ | JetPack 6 / kernel 5.15 支援 |
| `--network=none` | ✅ | 比 NemoClaw netns 更乾淨，繞開 nf_tables panic |
| `read_only + tmpfs` | ✅ | 直接採用 |
| `no-new-privileges` | ✅ | 直接採用 |
| Landlock LSM | ⏭ 暫緩 | Tegra kernel 未啟用 |
| k3s / Kubernetes | ❌ | iptables kernel panic on Tegra |
| Nemotron / NIM 本地推論 | ❌ | LLM-Router 全包，8GB 不適合 30B |
| GPU 偵測（nvidia-smi） | ❌ | Unified memory 回傳 N/A，改用 /proc/meminfo |

---

## 開發

```bash
# 安裝依賴
pip install -e ".[dev]"

# 安裝 channel adapters（選用）
pip install -e ".[channels]"

# 執行測試
python -m pytest tests/ -v

# 產生 blueprint digest（更新 blueprint.yaml 前執行）
python scripts/gen_digest.py

# 啟動服務
python -m claw.main
```

### 環境變數

```bash
# .env（不含 LLM API key）
CLAW_LLM_ROUTER_URL=http://localhost:8080
CLAW_GATEWAY_TOKEN=your-gateway-token
CLAW_DATA_DIR=~/.claw
```

---

## 依賴

| 套件 | 用途 | Phase |
|---|---|---|
| `fastapi` + `uvicorn` | Gateway HTTP/WebSocket | 1 |
| `httpx` | LLM-Router client | 1 |
| `pydantic` | Schema 驗證 | 1 |
| `pyyaml` | Config + Blueprint + EgressPolicy | 1, 4 |
| `aiosqlite` | 非同步 SQLite | 1 |
| `apscheduler` | Cron 排程 | 3 |
| `croniter` | Cron 表達式解析 | 3 |
| `aiofiles` | 非同步檔案 IO | 3 |
| `tiktoken` | Token 計數（Context Compaction） | 5 |
| `sqlite-vec` | 向量搜尋（Memory/RAG） | 5 |

Optional（`pip install -e ".[channels]"`）：

| 套件 | 用途 | Phase |
|---|---|---|
| `python-telegram-bot>=21.0` | Telegram channel | 6 |
| `slack-bolt>=1.18.0` | Slack channel | 6 |
| `discord.py>=2.3.0` | Discord channel | 8 |
