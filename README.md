# claw-python

OpenClaw 的 Python 完整復刻，並整合 **NemoClaw 企業安全層**。以 [LLM-Router](https://github.com/Disesfgewu/LLM-Router) 作為唯一 LLM 閘道，透過 DDGS 實現免費搜尋，用 Docker 隔離 tool 執行環境。

> **硬體基準：** Jetson Orin Nano Super（8GB unified memory, JetPack 6.x, kernel 5.15.136-tegra）
> **當前狀態：** Phase 4 完成 — 85 tests pass, 2 skipped（channel optional deps）

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

## 完成進度

| Phase | 內容 | Tests |
|---|---|---|
| ✅ Phase 1 | Core: Storage, LLM-Router Client, Tool Registry, Agent Loop, Queue, Gateway | 20 |
| ✅ Phase 2 | Docker Sandbox, Hook System, Skills Loader, Security Pairing, Config System | +34 |
| ✅ Phase 2.5 | Skills 目錄重構（44 skills，manifest 標準化） | 0 new |
| ✅ Phase 3 | Slash Commands, Cron, Multi-agent ACP, Media Layer, Channel Abstraction | +10 |
| ✅ Phase 4 | NemoClaw 安全層: Blueprint, EgressPolicy, Sandbox 強化, Admin API | +21 |
| 🔜 Phase 5 | Memory/RAG + Context Compaction（FTS5 + sqlite-vec） | ~+8 |
| 🔜 Phase 6 | Channel Adapters: Telegram + Slack | ~+3 |
| 🔜 Phase 7 | Observability: structlog + Prometheus + Admin API 完整版 | ~+6 |
| 🔜 Phase 8 | MCP Bridge + Browser + File Tools + TTS | TBD |

**當前：85 passed, 2 skipped**（skipped = test_slack / test_telegram，slack-bolt / python-telegram-bot 未安裝）

---

## 目錄結構

```
claw-python/
├── claw/
│   ├── core/                        # Phase 1
│   │   ├── gateway.py               # FastAPI + WebSocket 控制平面 + Admin egress endpoints
│   │   ├── storage.py               # SQLite schema + egress_pending + egress_audit_log
│   │   ├── queue.py                 # Lane-aware FIFO queue
│   │   ├── protocol.py              # Wire protocol schema
│   │   ├── auth.py                  # Gateway 認證 + rate limit
│   │   ├── pairing.py               # DM pairing challenge（Phase 2）
│   │   └── config.py                # YAML config + env 載入
│   │
│   ├── agent/                       # Phase 1-3
│   │   ├── loop.py                  # AgentLoop（egress check 雙路徑插入，Phase 4）
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
│   │   ├── cron.py                  # cron_add / cron_list / cron_delete（Phase 3）
│   │   ├── sessions_tools.py        # sessions_send / sessions_spawn（Phase 3）
│   │   └── memory_tools.py          # memory_save / memory_search（Phase 5 準備）
│   │
│   ├── sandbox/                     # Phase 2-4
│   │   ├── docker_runner.py         # 強化版 container（read_only + tmpfs + seccomp）
│   │   ├── policy.py                # needs_sandbox() + SandboxPolicy dataclass（Phase 4）
│   │   └── seccomp_minimal.json     # 160-syscall 白名單，SCMP_ACT_ERRNO 預設（Phase 4）
│   │
│   ├── channels/                    # Phase 1-3
│   │   ├── base.py                  # BaseChannel ABC
│   │   ├── policy.py                # allowFrom、dmPolicy
│   │   ├── telegram.py              # Phase 6
│   │   └── slack.py                 # Phase 6
│   │
│   ├── cron/                        # Phase 3
│   │   ├── service.py               # APScheduler 排程服務
│   │   ├── runner.py                # 排程任務 isolated agent 執行
│   │   ├── schedule.py              # Cron 規則解析
│   │   └── store.py                 # Cron job 持久化
│   │
│   ├── memory/                      # Phase 5 準備
│   │   ├── manager.py               # Hybrid search + RRF fusion + temporal decay
│   │   └── sqlite_store.py          # SQLite FTS5 + sqlite-vec
│   │
│   └── media/                       # Phase 3
│       ├── store.py
│       ├── input.py
│       └── mime.py
│
├── config/                          # Phase 4
│   ├── __init__.py
│   ├── blueprint.py                 # Blueprint dataclass（SHA256 + /proc/meminfo preflight）
│   ├── blueprint.yaml               # 專案完整性 + 資源設定
│   └── egress_policy.yaml           # Egress 白名單 YAML
│
├── scripts/
│   └── gen_digest.py                # 產生 blueprint sha256
│
├── skills/                          # 44 個使用者技能（Phase 2.5 重構）
├── docker/
│   └── sandbox.Dockerfile
├── tests/                           # 85 tests
│   ├── test_blueprint.py            # 5 tests（Phase 4）
│   ├── test_egress.py               # 7 tests（Phase 4）
│   ├── test_sandbox.py              # 7 tests（Phase 2 + 4）
│   ├── test_agent_loop.py           # Phase 1
│   ├── test_commands.py             # Phase 3
│   ├── test_cron.py                 # Phase 3
│   ├── test_multi_agent.py          # Phase 3
│   ├── test_context.py              # Phase 5 準備
│   ├── test_memory.py               # Phase 5 準備
│   ├── test_slack.py                # Phase 6（skipped: optional dep）
│   └── test_telegram.py             # Phase 6（skipped: optional dep）
│
├── pyproject.toml
└── README.md
```

---

## Phase 4 NemoClaw 安全層說明

NemoClaw（NVIDIA, GTC 2026-03-16）是企業級安全容器架構。claw-python 採用其核心安全設計，針對 Jetson 硬體調整。

### 採用決策

| NemoClaw 功能 | 採用？ | Jetson 適配 |
|---|---|---|
| Blueprint SHA256 完整性 | ✅ | `/proc/meminfo` 取代 nvidia-smi |
| Egress 白名單 + 審批流 | ✅ | 直接採用 |
| seccomp profile | ✅ | JetPack 6 / kernel 5.15 支援 |
| `--network=none` | ✅ | 比 netns 更乾淨，繞開 nf_tables panic |
| `read_only + tmpfs` | ✅ | 直接採用 |
| `no-new-privileges` | ✅ | 直接採用 |
| Landlock LSM | ⏭ 暫緩 | Tegra kernel 未啟用 |
| k3s / Kubernetes | ❌ | iptables kernel panic on Tegra |
| Nemotron / NIM 本地推論 | ❌ | LLM-Router 全包，8GB 不適合 30B |

### Egress Policy 三狀態機

```
工具呼叫觸發外部連線
         │
    egress.check(dest)
         │
   ┌─────┴─────┐
ALLOW       DENY / PENDING
   │              │
正常執行    [egress denied/pending] 回傳給 LLM
                  │ (PENDING)
         /admin/egress/pending → 人工核准
         /admin/egress/{id}/approve
         /admin/egress/audit
```

### Blueprint Preflight

啟動時驗證：
1. **SHA256 完整性** — `config/blueprint.yaml` 中記錄的關鍵檔案 hash
2. **記憶體預檢** — 讀 `/proc/meminfo`，確認可用記憶體 ≥ `required_mb`（預設 600MB）

---

## 開發

```bash
# 安裝依賴
pip install -e ".[dev]"

# 安裝 channel adapters（選用）
pip install -e ".[channels]"

# 執行測試
python -m pytest tests/ -v

# 產生 blueprint digest
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

| 套件 | 用途 |
|---|---|
| `fastapi` + `uvicorn` | Gateway HTTP/WebSocket |
| `httpx` | LLM-Router client |
| `pydantic` | Schema 驗證 |
| `pyyaml` | Config + Blueprint + EgressPolicy |
| `aiosqlite` | 非同步 SQLite |
| `apscheduler` | Cron 排程 |
| `croniter` | Cron 表達式解析 |
| `aiofiles` | 非同步檔案 IO |
| `tiktoken` | Token 計數（Phase 5 Context Compaction） |
| `sqlite-vec` | 向量搜尋（Phase 5 Memory/RAG） |

Optional（channel adapters）：
- `python-telegram-bot>=21.0`
- `slack-bolt>=1.18.0`
- `discord.py>=2.3.0`
