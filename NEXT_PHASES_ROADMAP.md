# claw-python 後續開發規劃
> 當前狀態：167 tests | 所有空殼功能已修復 | 伺服器已驗證

---

## 現況快照

| 項目 | 狀態 |
|---|---|
| **Core Components** | ✅ 5/5 fully wired (ResearchLoop, MCPBridge, CronService, EgressPolicy, MultiAgentCoordinator) |
| **Tools** | ✅ 22/22 registered |
| **Channels** | ✅ 3/3 (Telegram, Slack, Discord) |
| **Database Path** | ✅ Fixed (使用 storage.db_path) |
| **Tests** | ✅ 167 passing, 0 failures |
| **Server** | ✅ Startup verified, API responding |

---

## Phase 15：完工收尾

**目標**：清理代碼、更新文件、建立測試邊界

### Task 15.1 — 清理過時 PHASE*.md 檔案
```bash
rm -f PHASE8A_PROMPT_FOR_GEMINI.md \
      PHASE9_PROMPT_FOR_GEMINI.md \
      PHASE9B_PROMPT_FOR_CODEX.md \
      PHASE10_PROMPT_FOR_GEMINI.md \
      PHASE10_5_PROMPT_FOR_CODEX.md
```
**理由**：這些是歷史工作提示，已完成，無需保留在 repo

### Task 15.2 — 更新 README.md
當前狀態行：
```markdown
> **當前狀態：** Phase 8a 完成 — 135 tests pass | ...
```

改為：
```markdown
> **當前狀態：** Phase 14 完成 — 167 tests pass |
> All 22 tools + 3 channels + 5 core services fully wired |
> Server verified on Jetson JetPack 6
```

### Task 15.3 — 更新 ROADMAP.md
加入完整的 Phase 歷史和當前狀態表

### Task 15.4 — 建立 Integration Tests 邊界
```bash
mkdir -p tests/integration
touch tests/integration/__init__.py
```

建立 `tests/integration/test_live_backend.py`（跳過，需要 LIVE_BACKEND=1）

### Task 15.5 — 最終 Commit
```bash
git add README.md ROADMAP.md ARCHITECTURE_VERIFICATION_REPORT.md
git rm PHASE8A_PROMPT_FOR_GEMINI.md ...
git commit -m "feat: Phase 15 — completion and documentation"
```

**預期結果**：
- 167+ tests passing
- 清潔的 repo（無過時 prompt 檔）
- 完整文件記錄

---

## Phase 16：性能優化（可選）

**現有痛點**：
1. 內存搜尋慢（FTS5 syntax 錯誤 → fallback）
2. embedding 模型 401（需要 Router 實例）
3. 工具呼叫延遲（無本地快取）

**可選優化**：
- 改進 memory_search 的 FTS5 查詢
- 本地 embedding 快取層
- Tool call 結果快取

**優先級**：Low —— 現有架構可工作

---

## Phase 17：實驗工作流（AutoResearch 增強）

**目標**：強化 ResearchLoop 的 A→C→B 循環

### Task 17.1 — 新增 Research 評估指標
```python
# research_status 回傳：
{
    "task_id": "...",
    "status": "running|complete",
    "iteration": 5,
    "candidates": ["plan A", "plan B", "plan C"],
    "best_so_far": "plan B (score: 0.87)",
    "convergence": "88%",
    "estimated_time_to_completion": "2h3m"
}
```

### Task 17.2 — 建立 Research 範例集
- 實驗任務：優化代碼效率
- 實驗任務：比較設計方案
- 實驗任務：驗證假設

### Task 17.3 — 檢驗點系統
```python
research_save_checkpoint(task_id, iteration, state)
research_load_checkpoint(task_id, iteration)
research_resume(task_id, from_iteration=5)
```

---

## Phase 18：多代理協調（Sessions 強化）

**目標**：充分利用 MultiAgentCoordinator

### Task 18.1 — 代理角色系統
```python
await sessions_spawn(
    goal="Analyze security report",
    agent_id="security_analyst",  # 可帶專用 system_prompt
)
```

### Task 18.2 — 訊息路由
支援：
- Agent A → Agent B（直接通訊）
- Agent A → Agent B → Agent C（中繼）
- Agent A ⇄ Agent B（雙向對話）

### Task 18.3 — 結果聚合
```python
results = await sessions_collect([child1, child2, child3])
summary = summarize_agent_results(results)
```

---

## Phase 19：進階 Egress 管理

**目標**：更精細的網路訪問控制

### Task 19.1 — 動態 Egress 規則
```yaml
egress_policy:
  rules:
    - name: "llm_router_only"
      allow_hosts: ["localhost:8000"]
      allow_ports: [8000]
      rate_limit: "100/min"

    - name: "duckduckgo_search"
      allow_hosts: ["api.duckduckgo.com"]
      allow_methods: ["GET"]
```

### Task 19.2 — Egress 日誌 + 統計
```python
egress_stats()
→ {
    "total_requests": 1523,
    "allowed": 1521,
    "denied": 2,
    "top_hosts": [("localhost:8000", 1200), (...)],
}
```

### Task 19.3 — Egress 批准工作流
```python
await request_egress_approval(target="example.com", reason="external research")
# Admin 通過 /admin/egress/approve API 批准
```

---

## Phase 20：Jetson 部署優化

**目標**：針對 Jetson Orin Nano Super 的生產就緒

### Task 20.1 — 記憶體監控和自動調整
```python
# 監控 /proc/meminfo
if available_memory < 500MB:
    trigger_context_compaction()
    reduce_embedding_batch_size()
```

### Task 20.2 — GPU 推理支援（如果有 CUDA）
```python
embedding_model = EmbeddingModel.load("local", use_gpu=True)  # 可選
```

### Task 20.3 — 熱管理
```python
monitor_thermal()
if device_temp > 80°C:
    reduce_docker_concurrency()
    increase_sandbox_isolation_wait()
```

---

## Phase 21：可觀測性增強

**目標**：生產級別的監控和診斷

### Task 21.1 — 結構化日誌（已有框架，擴充）
```python
# 當前已有：
{"session_id": "...", "event": "agent.run_start", ...}

# 新增：
{"session_id": "...", "event": "tool.call", "tool_name": "bash", "duration_ms": 234}
{"session_id": "...", "event": "memory.search", "query": "...", "results": 5, "duration_ms": 45}
```

### Task 21.2 — Metrics Dashboarding
- Tool 呼叫頻率
- 平均回應時間
- 失敗率
- Memory 使用趨勢

### Task 21.3 — Health Check Endpoints
```
GET /health → 200 {status: "healthy"}
GET /health/components → {storage: ok, llm: error, cron: ok, ...}
```

---

## 優先級順序

| Phase | 優先級 | 依賴 | 預估工作量 |
|---|---|---|---|
| **15** | 🔴 Critical | 當前工作 | 2-3h |
| 16 | 🟡 Medium | Phase 15 | 4-6h |
| 17 | 🟡 Medium | Phase 15 | 6-8h |
| 18 | 🟡 Medium | Phase 15, 17 | 4-6h |
| 19 | 🟢 Low | Phase 15 | 3-4h |
| 20 | 🟢 Low | Phase 15 | 4-5h |
| 21 | 🟢 Low | Phase 15 | 5-6h |

---

## 建議開發策略

### 短期（2-3 天）
1. **完成 Phase 15**（2-3h）
2. 執行完整測試和驗證
3. 提交最終版本

### 中期（1-2 週）
4. **Phase 16-18**（優先：性能、多代理）
5. 建立 integration tests
6. 真實場景測試（需要 LLM-Router 實例）

### 長期（持續改進）
7. **Phase 19-21**（可觀測性、部署優化）
8. 監控生產指標
9. 性能基準測試

---

## 完成後的項目狀態

```
✅ Phase 1-15：核心功能完整
✅ 22 個工具，3 個渠道，5 個核心服務
✅ 所有空殼功能修復
✅ 實際伺服器驗證通過
✅ 167 tests pass

下一步：
- Phase 15 cleanup（2-3h）
- Phase 16+ 可選增強（持續）
- 生產部署準備（Jetson JetPack 6）
```
