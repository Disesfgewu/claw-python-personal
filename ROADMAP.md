# claw-python 開發路線圖（NemoClaw 整合後修訂版）

> 更新日期：2026-03-20
> 硬體：Jetson Orin Nano Super（8GB unified memory, kernel 5.15.136-tegra）
> 基準：Phase 3 完成，64 tests 通過

---

## 已完成

| Phase | 內容 | Tests |
|---|---|---|
| Phase 1 | Core（Storage, LLM-Router Client, Tool Registry, Agent Loop, Queue, Gateway） | 20 |
| Phase 2 | Docker Sandbox, Hook System, Skills Loader, Security Pairing, Config System | +34 |
| Phase 2.5 | Skills 目錄重構（44 skills，品牌清理，manifest 標準化） | 0 new |
| Phase 3 | Slash Commands, Cron, Multi-agent ACP, Media Layer, Channel Abstraction | +10 |

---

## 待執行

### Phase 4 — NemoClaw 安全層（**最高優先**）

> NemoClaw = 企業安全容器。此 Phase 在 Phase 3 功能層之上加安全殼。
> 預期完成後測試：64 → ~76 tests

| 工作項目 | 檔案 | 週次 |
|---|---|---|
| Blueprint 完整性驗證 | `config/blueprint.py` + `blueprint.yaml` | W1 |
| Preflight 記憶體檢查（/proc/meminfo，不用 nvidia-smi） | `config/blueprint.py` | W1 |
| Egress Policy YAML + EgressVerdict/Rule/Policy | `claw/tools/policy.py` | W2 |
| Egress 稽核日誌 + pending 表 | `claw/core/storage.py` | W2 |
| Egress Policy YAML 設定 | `config/egress_policy.yaml` | W2 |
| Sandbox seccomp profile（JetPack 6 / kernel 5.15 相容） | `claw/sandbox/seccomp_minimal.json` | W2 |
| SandboxPolicy dataclass（from_blueprint 支援） | `claw/sandbox/policy.py` | W2 |
| Docker runner 強化（read_only + tmpfs + no-new-privs + seccomp） | `claw/sandbox/docker_runner.py` | W3 |
| Agent loop egress 攔截（4 行 diff） | `claw/agent/loop.py` | W3 |
| Admin endpoints（/admin/egress/pending + approve + audit） | `claw/core/gateway.py` | W4 |
| main.py 整合（Blueprint bootstrap + EgressPolicy 注入） | `claw/main.py` | W4 |
| Tests（test_blueprint.py 5 tests + test_egress.py 7 tests） | `tests/` | W1-4 |

**Jetson 特殊處理：**
- `network_mode="none"` 已實作（繞開 nf_tables panic）✅
- GPU 偵測改用 `/proc/meminfo` ✅
- Landlock LSM 暫時跳過（kernel 未啟用）
- 不用 k3s / Kubernetes

---

### Phase 5 — Memory/RAG + Context Compaction

> 長期記憶，語意搜尋，Context 自動壓縮。
> 預期完成後測試：~76 → ~84 tests

| 工作項目 | 檔案 |
|---|---|
| MemoryStore（SQLite FTS5 + sqlite-vec 向量表） | `claw/memory/sqlite_store.py` |
| MemoryManager（Hybrid search + RRF fusion + temporal decay） | `claw/memory/manager.py` |
| memory_save / memory_search tools | `claw/tools/memory_tools.py` |
| ContextBuilder（tiktoken 計數 + head/tail compaction） | `claw/agent/context.py` |
| 整合到 AgentLoop（自動注入相關記憶） | `claw/agent/loop.py` |
| Tests（test_memory.py 4 tests + test_context.py 2 tests） | `tests/` |

**新增依賴：** `tiktoken>=0.5.0`, `sqlite-vec>=0.1.0`（已在 pyproject.toml）

---

### Phase 6 — Channel Adapters（Telegram + Slack）

> 接通主流 messaging 平台。
> 預期完成後測試：~84 → ~90 tests

| 工作項目 | 檔案 |
|---|---|
| TelegramChannel（私訊 + 群組 + streaming draft mode + 媒體附件） | `claw/channels/telegram.py` |
| SlackChannel（app_mention + DM + thread reply） | `claw/channels/slack.py` |
| Session ID 規則（TG: agent:main / agent:tg:group:{id}） | channels/telegram.py |
| 0.5s streaming throttle（避免 Telegram rate limit） | channels/telegram.py |
| Tests（test_telegram.py 2 tests + test_slack.py 1 test） | `tests/` |

**前置條件：**
- `pip install python-telegram-bot discord.py slack-bolt`（optional dependencies）
- 需要 Telegram Bot Token / Slack App credentials

---

### Phase 7 — Observability + Admin API

> 可觀測、可維運。
> 預期完成後測試：~90 → ~96 tests

| 工作項目 | 檔案 |
|---|---|
| Structured logging（structlog JSON 格式，敏感資料 redact） | `claw/logging/logger.py` |
| Per-session log context（session_id, agent_id 自動附加） | `claw/logging/logger.py` |
| Prometheus metrics（request count, token usage, queue depth, tool calls） | `claw/observability/metrics.py` |
| `/metrics` endpoint | `claw/core/gateway.py` |
| Admin API 完整版（/admin/sessions GET/DELETE, /admin/queue, /admin/reload-skills） | `claw/core/gateway.py` |
| Admin token 認證（獨立於 Gateway WebSocket auth） | `claw/core/auth.py` |
| Session reaper（過期 session 自動清理） | `claw/core/session.py` |

**新增依賴：** `structlog>=24.0`, `prometheus-client>=0.20.0`

---

### Phase 8 — MCP Bridge + Advanced Tools

> 接通 MCP 生態系，完整 browser/file tool，TTS。

| 工作項目 | 檔案 |
|---|---|
| MCP client（stdio + SSE transport，tool 自動映射） | `claw/tools/mcp_bridge.py` |
| MCP server 白名單（config 管理） | `config/default.yaml` |
| Browser tool（Playwright 無頭，4 個核心 action） | `claw/tools/browser.py` |
| File tools（file_read/write/list/search，workspace sandbox） | `claw/tools/file_tools.py` |
| TTS（本地 pyttsx3 或 LLM-Router `/v1/audio/speech`） | `claw/tts/tts.py` |
| Discord Channel adapter | `claw/channels/discord_channel.py` |
| WhatsApp Channel（選做） | `claw/channels/whatsapp.py` |

**新增依賴：** `playwright>=1.40.0`, `pyttsx3>=2.90`（optional）

---

## 架構演進圖

```
Phase 1-3（完成）：
┌────────────────────────────────────────────────┐
│  Channels(base)  →  Gateway  →  AgentLoop      │
│  Cron / Multi-agent / Media                    │
│  Skills / Tools / Sandbox(基礎)                │
└────────────────────────────────────────────────┘

Phase 4（NemoClaw 安全層）：
┌────────────────────────────────────────────────┐
│  Blueprint(完整性)  →  EgressPolicy(白名單)    │
│  Sandbox(seccomp + read_only + no-new-privs)   │
│  Admin API(egress approve/audit)               │
└────────────────────────────────────────────────┘

Phase 5（記憶）：
┌────────────────────────────────────────────────┐
│  MemoryManager(hybrid search + decay)          │
│  ContextBuilder(token count + compaction)      │
└────────────────────────────────────────────────┘

Phase 6（Channel）：
┌────────────────────────────────────────────────┐
│  TelegramChannel + SlackChannel                │
└────────────────────────────────────────────────┘

Phase 7（可觀測性）：
┌────────────────────────────────────────────────┐
│  structlog + Prometheus + Admin API 完整版      │
└────────────────────────────────────────────────┘

Phase 8（工具生態）：
┌────────────────────────────────────────────────┐
│  MCP Bridge + Browser + File + TTS             │
└────────────────────────────────────────────────┘
```

---

## NemoClaw 功能採用決策表

| NemoClaw 功能 | 採用？ | 原因 / Jetson 適配 |
|---|---|---|
| Blueprint（sha256 完整性）| ✅ Phase 4 | 直接採用，/proc/meminfo 取代 nvidia-smi |
| Egress 白名單 + 審批流 | ✅ Phase 4 | 直接採用，工具完全相容 |
| seccomp profile | ✅ Phase 4 | JetPack 6 / kernel 5.15 支援 |
| `--network=none` | ✅ 已實作 | 比 NemoClaw netns 更乾淨，繞開 nf_tables |
| `read_only + tmpfs` | ✅ Phase 4 | 直接採用 |
| `no-new-privileges` | ✅ Phase 4 | 直接採用 |
| Landlock LSM | ⏭ 暫緩 | Tegra kernel 未啟用，未來可加 graceful fallback |
| k3s / Kubernetes | ❌ 不採用 | iptables kernel panic on Tegra |
| Nemotron / NIM 本地推論 | ❌ 不採用 | 由 LLM-Router 全包，8GB unified memory 不適合 30B |
| GPU 偵測（nvidia-smi） | ❌ 不採用 | Unified memory 回傳 N/A，改用 /proc/meminfo |
| DGX Spark blueprint | ❌ 不採用 | 不是我們的硬體 |
