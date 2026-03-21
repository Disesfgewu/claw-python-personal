# PHASE 7 — Observability + Admin API 完整版

**狀態**：🔜 規劃中
**PM**：Claude Code
**日期**：2026-03-21
**前置條件**：Phase 7.5 完成（125 tests passing）

---

## 目標

在現有架構之上加入**可觀測性層**，使系統在生產環境可監控、可偵錯、可維運。
不修改任何現有功能邏輯，純粹新增觀測與管理能力。

---

## 新增依賴

```toml
# pyproject.toml 新增
structlog>=24.0
prometheus-client>=0.20.0
```

---

## 工作項目拆分

### P7-1：Structured Logging（Codex 負責）

**檔案**：`claw/core/logger.py`（新建）
**整合點**：`claw/core/gateway.py`, `claw/agent/loop.py`, `claw/main.py`

#### 功能需求

1. **JSON 格式輸出**：使用 `structlog` 的 `JSONRenderer`，每行一個 JSON object
2. **敏感資料 redact**：自動遮蔽 token、api_key、password、secret、authorization 欄位
3. **Session 上下文自動附加**：所有 log 自動帶 `session_id`, `agent_id`（透過 `contextvars`）
4. **Log level 設定**：從 `config.yaml` 讀取，預設 `INFO`

#### 預期輸出格式

```json
{"timestamp": "2026-03-21T10:00:00Z", "level": "info", "event": "agent.run_start", "session_id": "agent:main", "agent_id": "default"}
{"timestamp": "2026-03-21T10:00:01Z", "level": "info", "event": "tool.call", "session_id": "agent:main", "tool": "search", "query": "..."}
{"timestamp": "2026-03-21T10:00:02Z", "level": "warning", "event": "egress.denied", "session_id": "agent:main", "dest": "evil.com"}
```

#### 整合要求

- `AgentLoop.run()` 的開始/結束：log event
- Tool call 執行前後：log event
- Egress 決策（ALLOW/DENY/PENDING）：log event
- `main.py` bootstrap：structlog 初始化（在 `configure_logging()` 中）

#### 補充測試（4 個）

```python
# tests/test_logger.py
def test_json_output_format()          # 驗證輸出是有效 JSON
def test_sensitive_redact()            # token/api_key 不出現在 log 中
def test_session_context_propagation() # session_id 自動附加
def test_log_level_from_config()       # INFO/DEBUG/WARNING 正確切換
```

---

### P7-2：Prometheus Metrics（Gemini 負責）

**檔案**：`claw/core/metrics.py`（新建）
**整合點**：`claw/core/gateway.py`（新增 `/metrics` endpoint）

#### 指標定義（9 個核心指標）

```python
# claw/core/metrics.py
from prometheus_client import Counter, Histogram, Gauge, CollectorRegistry

REGISTRY = CollectorRegistry()

# 請求計數
agent_runs_total = Counter(
    "claw_agent_runs_total",
    "Total agent run requests",
    ["session_id", "model"],
    registry=REGISTRY,
)

# Token 使用量
tokens_used_total = Counter(
    "claw_tokens_used_total",
    "Total LLM tokens consumed",
    ["type"],  # prompt / completion
    registry=REGISTRY,
)

# Tool call 計數
tool_calls_total = Counter(
    "claw_tool_calls_total",
    "Total tool calls executed",
    ["tool_name", "verdict"],  # verdict: success / error / egress_denied
    registry=REGISTRY,
)

# Egress 決策
egress_decisions_total = Counter(
    "claw_egress_decisions_total",
    "Egress policy decisions",
    ["verdict"],  # allow / deny / pending
    registry=REGISTRY,
)

# 請求延遲
agent_run_duration_seconds = Histogram(
    "claw_agent_run_duration_seconds",
    "Agent run duration in seconds",
    registry=REGISTRY,
)

# Queue 深度（Gauge）
queue_depth = Gauge(
    "claw_queue_depth",
    "Current number of items in message queue",
    registry=REGISTRY,
)

# Active sessions（Gauge）
active_sessions = Gauge(
    "claw_active_sessions",
    "Number of active sessions",
    registry=REGISTRY,
)

# LLM error rate
llm_errors_total = Counter(
    "claw_llm_errors_total",
    "Total LLM router errors",
    ["error_type"],
    registry=REGISTRY,
)

# Sandbox container count（Gauge）
sandbox_containers = Gauge(
    "claw_sandbox_containers",
    "Number of active sandbox containers",
    registry=REGISTRY,
)
```

#### `/metrics` Endpoint（加入 gateway.py）

```python
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST
from claw.core.metrics import REGISTRY

@app.get("/metrics")
async def metrics():
    return Response(
        content=generate_latest(REGISTRY),
        media_type=CONTENT_TYPE_LATEST,
    )
```

#### 補充測試（3 個）

```python
# tests/test_metrics.py
def test_metrics_endpoint_returns_200()       # /metrics 回傳 200
def test_agent_run_increments_counter()       # agent run 後計數器 +1
def test_tool_call_counter_with_label()       # tool_name label 正確記錄
```

---

### P7-3：Admin API 完整版（Gemini 負責）

**整合點**：`claw/core/gateway.py`（新增 endpoints）
**前置條件**：需要 Admin Token 認證

#### Admin Token 認證

```python
# claw/core/auth.py 新增
def verify_admin_token(token: str) -> bool:
    """Compare against config.admin_token (env var CLAW_ADMIN_TOKEN)."""
    expected = os.environ.get("CLAW_ADMIN_TOKEN", "")
    if not expected:
        return False  # Admin API disabled if no token configured
    return hmac.compare_digest(token, expected)
```

所有 `/admin/*` endpoints 都要求 `Authorization: Bearer <admin_token>` header。

#### 新增 Endpoints

```
GET  /admin/sessions            — 列出所有 sessions（含 last_active, channel, scope）
DELETE /admin/sessions/{id}     — 強制終止並刪除 session
GET  /admin/queue               — 查看 queue 狀態（depth, active tasks）
POST /admin/reload-skills       — 熱重載 skills 目錄（不重啟服務）
GET  /admin/status              — 系統整體狀態（uptime, sessions count, queue depth）
```

#### 補充測試（3 個）

```python
# tests/test_admin_api.py
def test_admin_requires_token()              # 無 token 回傳 401
def test_list_sessions()                     # 正確回傳 session 列表
def test_reload_skills()                     # reload 後 skill 數量正確
```

---

### P7-4：Session Reaper（Codex 負責）

**檔案**：`claw/core/session_reaper.py`（新建）
**整合點**：`claw/main.py`（background task）

#### 功能需求

- 背景 asyncio task，每 60 秒掃描一次
- 刪除 `last_active` 超過 `config.session_ttl_hours`（預設 24 小時）的 sessions
- 刪除前先呼叫 `DockerRunner.destroy(session_id)` 清理 sandbox
- Log 每次清理的 session 數量

#### 補充測試（2 個）

```python
# tests/test_session_reaper.py
def test_reaper_removes_expired_sessions()   # TTL 過期 session 被刪除
def test_reaper_skips_active_sessions()      # 活躍 session 不受影響
```

---

## 工作分配

| Worker | 任務 | 新增檔案 | 新增測試 |
|---|---|---|---|
| **Codex** | P7-1 Structured Logging | `claw/core/logger.py` | 4 個 |
| **Codex** | P7-4 Session Reaper | `claw/core/session_reaper.py` | 2 個 |
| **Gemini** | P7-2 Prometheus Metrics | `claw/core/metrics.py` | 3 個 |
| **Gemini** | P7-3 Admin API 完整版 | `claw/core/gateway.py`（修改）| 3 個 |

**並行執行**：Codex 和 Gemini 修改檔案無重疊，可完全並行。

---

## 驗收標準

```
【功能驗收】
□ structlog JSON 格式輸出（機器可讀）
□ 敏感資料不出現在 log（token, api_key, password 全 redact）
□ /metrics 回傳有效 Prometheus 文字格式
□ 所有 9 個指標正確計數
□ /admin/sessions, /admin/queue, /admin/reload-skills 正常運作
□ Admin API 未配置 token 時回傳 401
□ Session Reaper 背景任務正常運行

【測試驗收】
□ 125（現有）+ 12（新增）= 137 tests passing
□ 0 failures, 0 errors

【代碼品質】
□ Pylance issues 維持 ≤ 6 個
□ 所有新代碼有 type annotation
```

---

## 新增設定（config/default.yaml）

```yaml
observability:
  log_level: INFO          # DEBUG / INFO / WARNING / ERROR
  log_format: json         # json / text
  metrics_enabled: true
  admin_token: ""          # 由 CLAW_ADMIN_TOKEN env var 覆蓋

session:
  ttl_hours: 24            # session 過期時間
  reaper_interval_seconds: 60
```

---

## 預期成果

```
Phase 6  ✅  106 tests
Phase 7.5 ✅  125 tests（含 skills 目錄）
Phase 7  🔜  ~137 tests（+12 新增）
              完整可觀測性層
              Prometheus + Grafana 就緒
              Admin API 完整版
```

---

**PM 簽署**：Claude Code
**日期**：2026-03-21
**下一步**：分派任務給 Codex（P7-1 + P7-4）和 Gemini（P7-2 + P7-3）
