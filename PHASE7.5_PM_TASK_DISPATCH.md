# PHASE 7.5 — PM 任務分配通知

**日期**：2026-03-21
**狀態**：✅ PM 審計完成，任務分配文檔已生成，可執行

---

## 📢 PM 正式指令

基於完整的 PHASE 7.5 PM 審計報告，我現在正式分配修復任務給兩個 Worker Agents。

### 任務總體目標

**修復所有 Pylance issues，提升代碼品質從 8.4/10 至 9.5+/10**

- 修復 8 個 critical issues（Codex）
- 修復 12 個 warning issues（Gemini）
- 新增 8-10 個補充測試
- 維持 106/106 existing tests passing
- 完成後達到 114+ tests passing

**預期工作量**：8-10 小時（兩個 worker 並行）
**預期完成時間**：5 個工作天

---

## 👨‍💼 Codex Worker — 關鍵修復

### 任務指派

**檔案**：`PHASE7.5_PROMPT_FOR_CODEX.md`

**修復範圍**：4 個 critical issues + 補充測試

| 優先級 | Issue | 位置 | 工作量 |
|--------|-------|------|--------|
| P1 | Type narrowing | gateway.py:23 | 5 min |
| P2 | None guard (updater) | telegram.py:44 | 10 min |
| P3 | None guard (socket) | slack.py:48 | 10 min |
| P4 | Private API access | memory/manager.py:58 | 30 min |

**補充工作**：
- 在 `LLMRouterClient` 中添加公開方法 `get_embedding()`
- 添加 4 個補充測試確保邏輯正確

**預期完成時間**：4-6 小時

### 驗收標準

- [ ] 所有 4 個 critical issues 已修復
- [ ] 0 個 Pylance critical 錯誤（gateway.py, telegram.py, slack.py, memory/manager.py）
- [ ] 4 個新增補充測試全部通過
- [ ] `pytest tests/ -v` 結果：110+ passed（106 existing + 4 new）
- [ ] 無新引入的代碼邏輯錯誤

### 交付清單

Codex 應交付：

```
✓ gateway.py - _require_dependencies() 已修復
✓ telegram.py - start() None guard 已添加
✓ slack.py - start() 異常處理已改進
✓ router_client.py - get_embedding() 公開方法已添加
✓ memory/manager.py - _get_embedding() 已改用公開 API
✓ tests/test_gateway.py - 補充測試 1 個
✓ tests/test_telegram.py - 補充測試 1 個
✓ tests/test_slack.py - 補充測試 1 個
✓ tests/test_router_client.py - 補充測試 1 個
✓ 測試運行結果：全部通過

回報格式：按 PHASE7.5_PROMPT_FOR_CODEX.md 最後的「回報格式」部分
```

---

## 👩‍💼 Gemini Worker — 警告和類型改進

### 任務指派

**檔案**：`PHASE7.5_PROMPT_FOR_GEMINI.md`

**修復範圍**：12 個 warning issues + 6 個 info issues + 補充測試

| STEP | 修復類型 | 優先級 | 工作量 |
|------|---------|--------|--------|
| 1 | Type annotation 統一 | 🟡 高 | 20 min |
| 2 | Memory result 型別檢查 | 🟡 高 | 15 min |
| 3 | Config 驗證 | 🟡 高 | 30 min |
| 4 | Error handling 細分 | 🟡 中 | 1 h |
| 5 | 其他 type 改進 | 🟡 中 | 1 h |
| 6 | 補充測試 | 🟢 必需 | 1.5 h |

**預期完成時間**：4-6 小時

### 驗收標準

- [ ] 所有 `Optional[X]` 改為 `X | None`（通過 grep 驗證）
- [ ] 12 個 warning issues 已修復
- [ ] 4-5 個補充測試全部通過
- [ ] `pytest tests/ -v` 結果：110+ passed
- [ ] Config 驗證邏輯清晰，缺失配置時記錄有用的錯誤訊息
- [ ] Error handling 區分 TimeoutError/HTTPStatusError

### 交付清單

Gemini 應交付：

```
✓ Type annotations 風格統一
  - Optional → | None 轉換完成
  - Dict/List 泛型參數補全
  - from __future__ import annotations 添加

✓ Code fixes
  - loop.py - Memory recall 型別檢查已改進
  - main.py - Telegram/Slack 配置驗證已添加
  - telegram.py - Error handling 已細分
  - slack.py - Error handling 已細分

✓ Tests
  - tests/test_main.py - 配置驗證測試 1 個
  - tests/test_agent_loop.py - Memory empty list 測試 1 個
  - tests/test_channels.py - Error handling 測試 2-3 個

✓ 測試運行結果：全部通過

回報格式：按 PHASE7.5_PROMPT_FOR_GEMINI.md 最後的「回報格式」部分
```

---

## ⚙️ 執行方式

### 並行執行（推薦）

**Codex 和 Gemini 可以同時進行工作，無相互依賴**：

```
時間軸：
Day 1-2: Codex STEP 1-4    |  Gemini STEP 1-3
         (修復 4 critical)  |  (修復 warning)

Day 3:   Codex STEP 5      |  Gemini STEP 4-5
         (補充測試)        |  (改進 + 補充測試)

Day 4-5: 集成測試 + 最終驗證  |
         (確保 110+ tests)    |
```

### 依賴檢查

**確認無交叉依賴**：

- ✅ Codex 修改的文件：gateway.py, telegram.py, slack.py, router_client.py, memory/manager.py
- ✅ Gemini 修改的文件：loop.py, main.py, 各 channel 的 error handling
- ✅ 重疊文件：**無** — Codex 的修改在 start/stop，Gemini 在 error handling
- ✅ 可以安全地並行進行

---

## 🎯 具體指令

### 給 Codex 的指令

```
Codex，你好！

根據 PM 的 PHASE 7.5 審計報告，我現在指示你執行以下任務：

【任務】修復 4 個 critical Pylance issues

【詳細指令】
  1. 閱讀 PHASE7.5_PROMPT_FOR_CODEX.md（此文件包含所有詳細規格）
  2. 按 STEP 1-4 逐個修復 4 個 critical issues
  3. 按 STEP 5 添加補充單元測試（4 個）
  4. 確保所有測試通過（`pytest tests/ -v` → 110+ passed）
  5. 按指定格式回報每個 STEP 的完成情況

【預期工作量】4-6 小時
【預期完成時間】可立即開始，預計 1-2 天內完成

【驗收】完成後 PM 將驗證：
  - 4 個 critical issues 已修復
  - 4 個新增測試通過
  - 所有現有測試仍通過（106）
  - 總計 110 tests passing

開始吧！
```

### 給 Gemini 的指令

```
Gemini，你好！

根據 PM 的 PHASE 7.5 審計報告，我現在指示你執行以下任務：

【任務】修復 12 個 warning issues + 6 個 info issues

【詳細指令】
  1. 閱讀 PHASE7.5_PROMPT_FOR_GEMINI.md（此文件包含所有詳細規格）
  2. 按 STEP 1 統一 type annotation 風格（Optional → | None）
  3. 按 STEP 2-5 逐個修復各類 warning issues
  4. 按 STEP 6 添加補充測試（4-5 個）
  5. 確保所有測試通過（`pytest tests/ -v` → 110+ passed）
  6. 按指定格式回報每個 STEP 的完成情況

【預期工作量】4-6 小時
【預期完成時間】可立即開始，預計 1-2 天內完成

【驗收】完成後 PM 將驗證：
  - 12 個 warning issues 已修復
  - Type annotation coverage ≥ 90%
  - 4-5 個新增測試通過
  - 所有現有測試仍通過（106）
  - 總計 110+ tests passing

開始吧！
```

---

## 📋 PM 監督與驗收

### 監督計劃

PM 將按以下時間表進行監督：

| 時間 | 活動 | PM 檢查項 |
|------|------|----------|
| Day 1 早上 | Codex/Gemini 開始工作 | 確認理解指令 |
| Day 1-2 | Codex STEP 1-4 進行中 | 進度檢查（每 2 小時） |
| Day 1-2 | Gemini STEP 1-3 進行中 | 進度檢查（每 2 小時） |
| Day 3 | 補充測試編寫 | 確認測試覆蓋範圍 |
| Day 4 早上 | 集成測試運行 | 驗證 110+ tests passing |
| Day 4 中午 | 最終驗收 | 確認無新 Pylance 警告 |
| Day 4 下午 | 提交最終報告 | PM 生成 PHASE 7.5 完成報告 |

### 驗收檢查清單

PM 將使用以下清單驗收完成：

```
【Codex 驗收】
  ☐ gateway.py:23 - Type narrowing 已修復
  ☐ telegram.py:44 - None guard 已添加
  ☐ slack.py:48 - Error handling 已改進
  ☐ router_client.py - get_embedding() 公開方法已添加
  ☐ memory/manager.py - 改用公開 API
  ☐ 4 個補充測試已添加並通過
  ☐ pytest tests/ -v → 110+ passed
  ☐ 無新的 Pylance critical 錯誤

【Gemini 驗收】
  ☐ Type annotation 統一（grep 驗證無 Optional）
  ☐ Memory result 型別檢查已改進
  ☐ Config 驗證邏輯已添加
  ☐ Error handling 已細分
  ☐ 4-5 個補充測試已添加並通過
  ☐ pytest tests/ -v → 110+ passed
  ☐ Type coverage ≥ 90%
  ☐ 無 warning level 的 Pylance 錯誤

【整體驗收】
  ☐ 全套測試 106/106 existing 仍通過
  ☐ 新增 8-10 個補充測試全部通過
  ☐ 總計 110+ tests passing
  ☐ Code quality score 從 8.4 → 9.5+
  ☐ 所有文件無 critical Pylance 錯誤
```

---

## 📚 參考文檔

两个 worker agents 可以參考以下文檔：

### Codex 參考

1. **PHASE7.5_PROMPT_FOR_CODEX.md** — 詳細任務規格（STEP 1-5）
2. **PYLANCE_FIXES.md** — Pylance 錯誤詳細解說 + 修復方案
3. **PHASE7.5_PM_AUDIT.md** — 完整審計報告（背景信息）

### Gemini 參考

1. **PHASE7.5_PROMPT_FOR_GEMINI.md** — 詳細任務規格（STEP 1-6）
2. **PYLANCE_FIXES.md** — Pylance 警告詳細解說
3. **PHASE7.5_PM_AUDIT.md** — 完整審計報告（背景信息）

### 共同參考

- **PHASE7.5_FINAL_REPORT.md** — PM 最終報告（概況）
- **PHASE7.5_SUMMARY.md** — 執行摘要（快速了解）

---

## ✅ 下一步確認

### 用戶需要確認

為了開始執行，用戶需要確認：

- [ ] 確認已閱讀 PHASE7.5_PM_AUDIT.md（PM 審計報告）
- [ ] 確認同意 8-10 小時的修復工作量估算
- [ ] 確認指派 Codex 執行 critical fixes
- [ ] 確認指派 Gemini 執行 warning fixes
- [ ] 確認可在 5 個工作天內完成（Day 1-4 實施，Day 5 驗證）

### 一旦確認

PM 將：

1. ✅ 正式向 Codex 和 Gemini 發送詳細工作指令
2. ✅ 每日進行進度監督
3. ✅ 在 Day 4 下午進行最終驗收
4. ✅ 生成 PHASE 7.5 完成報告
5. ✅ 宣布可進行 Phase 7

---

## 📞 聯絡與支持

如果 Codex 或 Gemini 在執行過程中遇到問題：

1. 可查閱 PYLANCE_FIXES.md 中的詳細解說
2. 可查閱 ARCHITECTURE_*.md 文件了解架構背景
3. 可向 PM 報告遇到的問題，PM 將提供指導

---

## 🎁 附加資源

已準備的所有文檔：

```
審計文檔：
  ✓ PHASE7.5_PM_AUDIT.md (294 行)
  ✓ PHASE7.5_SUMMARY.md (267 行)
  ✓ PHASE7.5_FINAL_REPORT.md (441 行)
  ✓ PYLANCE_FIXES.md (450+ 行)

Worker Prompts：
  ✓ PHASE7.5_PROMPT_FOR_CODEX.md (400+ 行)
  ✓ PHASE7.5_PROMPT_FOR_GEMINI.md (450+ 行)

架構參考：
  ✓ ARCHITECTURE_COMPARISON.md (19 KB)
  ✓ ARCHITECTURE_COMPONENTS.md (23 KB)
  ✓ FEATURE_MATRIX.md (14 KB)
```

**所有文檔已提交至 git，可隨時訪問。**

---

## 最後的話

這是 PM 從審計、分析、規劃到任務分配的完整工作流程。現在已經：

1. ✅ 完整審計了代碼品質
2. ✅ 識別了所有 26 個 Pylance issues
3. ✅ 規劃了詳細的修復方案
4. ✅ 估算了工作量和時間
5. ✅ 生成了執行指令文檔

**最後一步**：執行這些修復，並讓代碼品質提升到 9.5+/10。

---

**PM 簽署**
日期：2026-03-21
狀態：✅ 任務分配完成，等待用戶確認執行

