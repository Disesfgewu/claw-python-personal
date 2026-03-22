# Phase 15 Worker Prompt — 完工收尾

你是實作 claw-python Phase 15 的 worker。工作目錄：`/home/martin/Desktop/claw-python-personal/`。
當前狀態：167 tests 通過（Phase 14 完成），0 failures。**嚴格按照順序，每步驗證後再繼續。**

---

## 背景說明

Phase 12-14 完成了所有主要功能。Phase 15 是最後收尾：更新文件、清理過時的 phase prompt、運行完整測試。

---

## Task 1 — 更新 `README.md`

將 README.md 開頭的狀態更新。找到這一行：

```markdown
> **當前狀態：** Phase 8a 完成 — 135 tests pass | ...
```

改成：

```markdown
> **當前狀態：** Phase 15 完成 — 167+ tests pass | AutoResearch + MCP Bridge + Browser + Image Gen + Discord | Jetson JetPack 6 ready
```

並在 README 末尾（或適當位置）加入完整功能列表，說明所有 Phase 1-15 完成的內容。

---

## Task 2 — 更新 `ROADMAP.md`

檢查 ROADMAP.md，加入 Phase 9b, 10, 10.5, 11-15 的行：

```markdown
| Phase 9b | ResearchLoop → AgentLoop 接線 | 148 | ✅ |
| Phase 10 | MCP Bridge (stdio + SSE) | 151 | ✅ |
| Phase 10.5 | Production 接線 (Cron, EgressPolicy, embedding model) | 157 | ✅ |
| Phase 11 | Wiring 補全 (Cron + EgressPolicy + MultiAgent scaffold) | 157 | ✅ |
| Phase 12 | Image Generation Tool | 160 | ✅ |
| Phase 13 | Browser Tool (Playwright) | 164 | ✅ |
| Phase 14 | Discord Channel | 167 | ✅ |
| Phase 15 | 完工收尾 (README/ROADMAP 更新, cleanup) | 167+ | ✅ |
```

---

## Task 3 — 清理過時 phase prompt 檔案

刪除這些不再需要的 phase prompt 檔案（已完成，保留在 git history 即可）：

```bash
rm -f PHASE8A_PROMPT_FOR_GEMINI.md
rm -f PHASE9_PROMPT_FOR_GEMINI.md
rm -f PHASE9B_PROMPT_FOR_CODEX.md
rm -f PHASE10_PROMPT_FOR_GEMINI.md
rm -f PHASE10_5_PROMPT_FOR_CODEX.md
```

或者保留在 repo 中但新增 `.gitignore` 規則排除它們（根據你的偏好）。

---

## Task 4 — 驗證所有工具已註冊

執行以下檢查程式確認所有 19 個工具已正確註冊：

```bash
python -c "
from claw.tools.registry import get_tools
import claw.tools.bash
import claw.tools.search
import claw.tools.memory_tools
import claw.tools.web_fetch
import claw.tools.file_tools
import claw.tools.research_tools
import claw.tools.cron
import claw.tools.sessions_tools
import claw.tools.image_gen
import claw.tools.browser

tools = get_tools()
print(f'Total tools registered: {len(tools)}')
for t in sorted(tools, key=lambda x: x.name):
    print(f'  ✓ {t.name}')
"
```

預期輸出包含 19 個工具。如果少於 19 個，檢查是否有 module 未正確 import。

---

## Task 5 — 建立 Integration Test Marker

建立 `tests/integration/` 目錄和 `tests/integration/__init__.py`（空檔案）：

```bash
mkdir -p tests/integration
touch tests/integration/__init__.py
```

建立 `tests/integration/test_live_backend.py`：

```python
from __future__ import annotations

import os
import pytest

# Integration tests only run if LIVE_BACKEND=1
pytestmark = pytest.mark.skipif(
    os.getenv("LIVE_BACKEND") != "1",
    reason="Integration tests require LIVE_BACKEND=1 env var"
)


@pytest.mark.asyncio
async def test_search_web_real_router():
    """Integration: search_web actually queries LLM-Router MCP endpoint."""
    # TODO: Implement when LLM-Router is running
    pytest.skip("Awaiting live router instance")


@pytest.mark.asyncio
async def test_embedding_real_router():
    """Integration: get_embedding queries Router /v1/embeddings."""
    # TODO: Implement when LLM-Router is running
    pytest.skip("Awaiting live router instance")


@pytest.mark.asyncio
async def test_image_gen_real_router():
    """Integration: image_gen queries Router /v1/images/generations."""
    # TODO: Implement when LLM-Router is running
    pytest.skip("Awaiting live router instance")
```

---

## Task 6 — 執行完整測試

```bash
cd /home/martin/Desktop/claw-python-personal
python -m pytest tests/ -x --tb=short -v
```

預期：**167+ tests 通過**（Phase 14 所有測試）

驗證沒有新 failures 引入。

---

## Task 7 — 最終 Commit

清理完成後，commit 此 Phase：

```bash
git add README.md ROADMAP.md
git rm PHASE8A_PROMPT_FOR_GEMINI.md PHASE9_PROMPT_FOR_GEMINI.md PHASE9B_PROMPT_FOR_CODEX.md PHASE10_PROMPT_FOR_GEMINI.md PHASE10_5_PROMPT_FOR_CODEX.md
git commit -m "feat: Phase 15 — project completion: README/ROADMAP update, cleanup"
```

---

## 交付清單

完成後回報：
1. README 和 ROADMAP 更新的具體內容
2. pytest 最終輸出 (應為 167+ tests)
3. 工具清單驗證結果 (應為 19 個)
4. 遇到的問題和解決方式

---

## 項目完成檢查清單

確認以下所有項目：

- [ ] Phase 1-15 全部 commit
- [ ] README.md 更新到當前狀態
- [ ] ROADMAP.md 包含 Phase 15
- [ ] 所有 19 個工具都已正確註冊
- [ ] tests/ 包含 167+ test cases
- [ ] 所有測試通過，0 failures
- [ ] integration test placeholder 已建立
- [ ] 過時的 phase prompt 已清理
- [ ] git log 顯示完整 phase history（最少 20 commits）

---

## 預期最終狀態

```
git log --oneline | head -20
> 應顯示：Phase 15, 14, 13, 12, 11, 10.5, 10, 9b, 9, 8a, ...

pytest tests/ -q --tb=short
> ============================== 167+ passed in X.XXs ==============================

README.md
> 標明 Phase 15 完成，所有功能清單已列

ROADMAP.md
> 所有 Phase 完整記錄，state 為 ✅
```

---

## 預期測試計數（最終）

| 來源 | 數量 |
|---|---|
| Phase 14 測試 | 167 |
| Phase 15 新增 | 0（清理和文件更新，無新測試） |
| **最終目標** | **167+** |

---

## 專案完成宣言

完成此 Phase 後，claw-python OpenClaw 復刻專案達到功能完整狀態：

✅ **Core**: Storage, Session, AgentLoop, Tool Registry
✅ **Channels**: Telegram, Slack, Discord
✅ **Security**: EgressPolicy, Docker Sandbox, seccomp, tmpfs noexec
✅ **Memory**: SQLite-vec + FTS5 + RRF hybrid search
✅ **Tools**: 19 個工具，涵蓋 bash, web, file, memory, research, cron, sessions, mcp, image_gen, browser
✅ **Research**: AutoResearch loop with A→C→B evaluation
✅ **MCP**: Bridge 支援外部 MCP server
✅ **Skills**: SKILL.md + Python 動態載入
✅ **Observability**: Metrics, structured logging, /admin/* endpoints
✅ **Jetson**: JetPack 6 優化，tmpfs 隔離，network=none sandbox

**Ready for production on Jetson Orin Nano Super.**
