# Phase 15 Worker Prompt — 完工收尾 (Cleanup & Documentation)

> 發給：**Codex**
> 當前狀態：183 tests passing
> 目標狀態：185+ tests + 完整文檔更新
> 耗時預估：2-3 小時

---

## 背景說明

claw-python 從 Phase 1-14 + S0 已完成所有核心功能。Phase 15 是最後的「收尾」階段：

1. **刪除過時的工作提示檔案** — repo 根層有大量 PHASE*.md prompt 檔案（歷史工作痕跡），需要清理
2. **更新 README.md** — 標記當前狀態（183 tests，所有組件已接線）
3. **更新 ROADMAP.md** — 完整記錄 Phase 1-15 的進度
4. **建立 integration tests 邊界** — 為後續真實 API 測試預留空間

這個 Phase 完成後，repo 會很乾淨，文檔會清晰記錄所有已完成的功能。

---

## Task 1 — 刪除過時的 PHASE*.md 檔案

在 `/home/martin/Desktop/claw-python-personal/` 根層，有大量的 `PHASE*.md` 檔案。

**要刪除的檔案清單**（確認無誤後刪除）：
- `PHASE1.md` through `PHASE9B_PROMPT_FOR_CODEX.md` 等所有歷史 prompt 檔案
- `PHASE_STRUCTURE_REPORT.md`
- 其他任何名稱為 `PHASE*.md` 的檔案

**例外**（保留）：
- `docs/` 目錄內的檔案（那是新的集中管理位置）

**命令**：
```bash
cd /home/martin/Desktop/claw-python-personal
# 列出要刪除的檔案
ls -1 PHASE*.md

# 確認後刪除（不要用 rm -f，要逐個確認）
rm PHASE1.md PHASE2.md ... PHASE15_PROMPT_FOR_CODEX.md
```

或者用 git：
```bash
git rm PHASE*.md
```

**驗收**：執行 `ls PHASE*.md` 後應該無檔案（或只有 docs/ 內的）

---

## Task 2 — 更新 README.md

找到 README.md 開頭的狀態行（目前應該是 Phase 8a 或類似的舊版）。

**當前狀態行**（大約在檔案最上方）：
```markdown
> **當前狀態：** Phase 8a 完成 — 135 tests pass | ...
```

**改為**：
```markdown
> **當前狀態：** Phase 15 完成 — 183 tests pass |
> All 22 tools + 3 channels fully operational |
> ResearchLoop + MCP Bridge + Cron Service + EgressPolicy + MultiAgentCoordinator all wired |
> Server verified on Jetson JetPack 6

## 功能清單（完整）

### ✅ Core 組件（Phase 1-11）
- FastAPI Gateway with WebSocket
- Session management + reaper
- AgentLoop with tool dispatch
- Memory RAG (sqlite-vec + FTS5 + RRF)
- EgressPolicy + Docker sandbox + seccomp
- ResearchLoop with A→C→B evaluation
- MCP Bridge (stdio + SSE)
- CronService (schedule management)
- MultiAgentCoordinator (sessions)

### ✅ 渠道（Channel）— 3 個（Phase 6 + 14）
- Telegram (polling-based)
- Slack (Socket Mode)
- Discord (discord.py)

### ✅ 工具（Tools）— 22 個
**Execution**: bash (Docker sandbox)
**Search**: search_web (DDGS via LLM-Router MCP), web_fetch
**File**: file_read, file_write, file_list, file_delete
**Memory**: memory_save, memory_search
**Research**: research_start, research_status, experiment_record
**Cron**: cron_add, cron_list, cron_delete
**Image**: image_gen (Router /v1/images/generations)
**Browser**: browser_navigate, browser_extract, browser_close
**MultiAgent**: sessions_send, sessions_spawn, sessions_list

### ✅ 安全層（NemoClaw Phase 4）
- Blueprint 驗證 (Slack/Telegram)
- EgressPolicy 白名單（5 條規則）
- Docker 隔離 (network=none, read_only, tmpfs noexec)
- seccomp + AppArmor

### ✅ 可觀測性（Phase 7）
- Structured JSON logging
- Metrics endpoint (/admin/metrics)
- Health check (/admin/health)
- Request tracing

### ✅ 技術面指標
- **Tests**: 183 passed, 3 skipped, 0 failures
- **Code Coverage**: All tools have unit tests
- **Deployment**: Ready for Jetson Orin Nano Super (JetPack 6)
- **Performance**: Memory optimized (context compaction, tmpfs isolation)

### ⏳ 後續計畫（Phase S0-S7）
- Phase S0-S4：台股分析系統（晨報、新聞、策略驗證）
- Phase S5：生產優化
- Phase S6：完整測試
- Phase S7：完整文檔和說明書

### 📚 文檔
- `/docs/00_PROJECT_STATUS.md` — 項目狀態和路線圖
- `/docs/PHASE_15_CLEANUP.md` — 本檔案
- `/manual/*` — 用戶操作手冊（後續）
```

**驗收**：README.md 開頭清晰標示當前狀態（183 tests），完整的功能列表已更新

---

## Task 3 — 更新 ROADMAP.md

ROADMAP.md 應該記錄所有 Phase 的進度。

**結構**（按照現有格式補充）：

```markdown
# claw-python 開發路線圖

| Phase | 內容 | 完成日期 | Tests | 狀態 |
|---|---|---|---|---|
| 1 | Core gateway, storage, session | 2025-10 | 20 | ✅ |
| 2 | Skills system (44 skills) | 2025-11 | 40 | ✅ |
| 3 | Memory RAG (sqlite-vec + FTS5) | 2025-11 | 60 | ✅ |
| 4 | NemoClaw 安全層 | 2025-12 | 80 | ✅ |
| 5 | Multi-agent coordination | 2025-12 | 95 | ✅ |
| 6 | Channels (Telegram, Slack) | 2026-01 | 110 | ✅ |
| 7 | Observability + Admin API | 2026-01 | 125 | ✅ |
| 7.5 | Code quality | 2026-01 | 125 | ✅ |
| 8a | Security hardening | 2026-02 | 135 | ✅ |
| 9 | AutoResearch framework | 2026-02 | 145 | ✅ |
| 9b | ResearchLoop ↔ AgentLoop wiring | 2026-02 | 148 | ✅ |
| 10 | MCP Bridge | 2026-03 | 151 | ✅ |
| fix | search_web → /mcp/messages | 2026-03 | 154 | ✅ |
| 10.5 | Production wiring (main.py) | 2026-03 | 157 | ✅ |
| 11 | Wiring completion (Cron + Egress + Coordinator) | 2026-03 | 157 | ✅ |
| 12 | Image Generation Tool | 2026-03 | 160 | ✅ |
| 13 | Browser Tool (Playwright) | 2026-03 | 164 | ✅ |
| 14 | Discord Channel | 2026-03 | 167 | ✅ |
| S0 | Discord Embed + egress whitelist | 2026-03 | 183 | ✅ |
| **15** | **Cleanup + documentation** | **2026-03** | **185+** | **⏳ 進行中** |
| S1-S4 | Taiwan Stock Analysis System | TBD | TBD | ⏳ |
| S5 | Production Optimization | TBD | TBD | ⏳ |
| S6 | Complete Testing | TBD | TBD | ⏳ |
| S7 | Documentation + User Guide | TBD | TBD | ⏳ |

---

## 項目狀態

- **核心功能**：✅ 完整（22 個工具，3 個渠道，所有組件已接線）
- **測試覆蓋**：✅ 183 tests pass, 0 failures
- **部署就緒**：✅ Jetson JetPack 6 優化完成
- **空殼功能**：✅ 已修復（所有組件真實啟動）

---

## 下一步

後續開發計畫見 `/docs/00_PROJECT_STATUS.md`
```

**驗收**：ROADMAP.md 完整記錄所有 Phase（1-15 + S0-S7），當前狀態標記為進行中

---

## Task 4 — 建立 Integration Tests 邊界

後續 Phase S5-S6 會需要實際的 API 端對端測試（不只 mock）。現在預先建立邊界。

**建立目錄**：
```bash
mkdir -p tests/integration
touch tests/integration/__init__.py
```

**建立 `tests/integration/test_live_api.py`**（框架，暫時跳過）：

```python
"""
Integration tests for live API endpoints.
These tests require LIVE_BACKEND=1 environment variable and a running server.
Skipped by default during unit test runs.
"""
from __future__ import annotations

import os
import pytest

# Integration tests only run if LIVE_BACKEND=1
pytestmark = pytest.mark.skipif(
    os.getenv("LIVE_BACKEND") != "1",
    reason="Integration tests require LIVE_BACKEND=1 env var"
)


@pytest.mark.asyncio
async def test_chat_completions_endpoint():
    """POST /v1/chat/completions returns valid response."""
    # TODO: S6 實作 — 真實 API 測試
    pytest.skip("Awaiting Phase S6 implementation")


@pytest.mark.asyncio
async def test_stock_analysis_live():
    """Real stock analysis via POST /v1/chat/completions."""
    # TODO: S6 實作
    pytest.skip("Awaiting Phase S6 implementation")


@pytest.mark.asyncio
async def test_discord_pushback_live():
    """Real Discord message push (requires Discord token)."""
    # TODO: S6 實作
    pytest.skip("Awaiting Phase S6 implementation")
```

**驗收**：目錄結構建立，框架代碼就位，不會破壞現有測試

---

## Task 5 — 執行最終測試

```bash
cd /home/martin/Desktop/claw-python-personal

# 確保沒有語法錯誤
python -m pytest tests/ -q --tb=short

# 預期輸出
# 183 passed, 3 skipped
```

---

## Task 6 — 最終 Commit

```bash
git add -A
git commit -m "feat: Phase 15 — cleanup and documentation

- Deleted all legacy PHASE*.md prompt files (repo cleanup)
- Updated README.md with complete feature list (22 tools, 3 channels)
- Updated ROADMAP.md with full Phase history (1-15 + S0-S7 roadmap)
- Created integration tests directory structure (/tests/integration)
- All tests still passing (183 passed, 3 skipped)

Project now in clean state:
✅ No hollow features (all components wired)
✅ 183 tests passing, 0 failures
✅ Clear documentation of all features
✅ Ready for Phase S0-S7 (Taiwan Stock Analysis + Production)

Co-Authored-By: Claude Haiku 4.5 <noreply@anthropic.com>"
```

---

## 交付清單

完成後回報：

1. **已刪除的 PHASE*.md 檔案清單** — 確認無誤
2. **README.md 和 ROADMAP.md 的更新摘要** — 新增了哪些內容
3. **pytest 最終輸出** — 應為 183 passed, 3 skipped（或更多新增的測試）
4. **git log 最後 3 行** — 確認 commit 成功
5. **遇到的問題和解決方式**

---

## 完成標準

✅ 過時的 PHASE*.md 檔案全部刪除（repo 根層乾淨）
✅ README.md 清晰標示當前狀態（183 tests，所有功能清單）
✅ ROADMAP.md 完整記錄 Phase 1-15 + S0-S7 路線圖
✅ Integration tests 目錄已建立，框架就位
✅ 所有測試通過（183+ passed, 0 failures）
✅ 最終 commit 成功

---

## 注意事項

- **只刪除 PHASE*.md**（歷史工作提示），不要刪除其他檔案
- **不要改動 src 代碼**（只改文檔）
- **保持 git history 清潔**（一個 commit）
- **確保測試仍然通過**（cleanup 不應破壞任何功能）

