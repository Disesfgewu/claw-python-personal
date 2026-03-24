# claw-python 文檔索引

> **完整文檔導航指南**

---

## 📚 主要文檔

### 給新手

1. **[README](../README.md)** — 開始這裡
   - 項目概述
   - 核心特徵
   - 快速開始
   - 系統架構圖

2. **[部署指南](DEPLOYMENT_GUIDE.md)** — 安裝和配置
   - Jetson Orin Nano Super 專用步驟
   - 環境變數配置
   - Docker 設置
   - 系統優化

3. **[常見問題](FAQ.md)** — 17 個 Q&A
   - 安裝問題
   - 功能使用
   - 效能和故障排除
   - 開發定製

### 給開發者

1. **[API 參考](API_REFERENCE.md)** — 28 工具完整文檔
   - 工具分類（基礎、檔案、記憶體、股票等）
   - 簽名和參數
   - 範例程式碼
   - 返回值格式

2. **[架構設計](ARCHITECTURE.md)** — 系統深度分析
   - 6 層架構（通訊→網關→代理→工具→存儲→外部服務）
   - 數據流範例
   - 設計決策
   - 擴展點

3. **[貢獻指南](../CONTRIBUTING.md)** — 參與開發
   - 開發環境設置
   - 編碼風格
   - 測試指南
   - PR 流程

---

## 🗺️ 按功能區分

### 基礎系統

| 文件 | 位置 | 用途 |
|---|---|---|
| README | 項目根目錄 | 項目總覽 |
| 架構設計 | docs/ | 技術深度 |
| API 參考 | docs/ | 工具文檔 |

### 部署和運維

| 文件 | 位置 | 用途 |
|---|---|---|
| 部署指南 | docs/ | Jetson 部署 |
| 常見問題 | docs/ | 故障排除 |

### 開發

| 文件 | 位置 | 用途 |
|---|---|---|
| 貢獻指南 | 項目根目錄 | 開發流程 |
| API 參考 | docs/ | 工具使用 |

---

## 🔍 按使用場景查找

### 「我想快速開始」

1. 讀 [README](../README.md) 項目概述
2. 按 [部署指南](DEPLOYMENT_GUIDE.md) 安裝
3. 驗證 `/admin/health` 端點

**預期時間：10-15 分鐘**

### 「我想添加新工具」

1. 學習 [API 參考](API_REFERENCE.md) 現有工具
2. 參考 [貢獻指南](../CONTRIBUTING.md) 中的「添加新工具」部分
3. 查看 `claw/tools/` 中的實現範例

**預期時間：30-45 分鐘**

### 「我想部署到生產環境」

1. 讀 [部署指南](DEPLOYMENT_GUIDE.md) 完整
2. 檢查部署檢查清單
3. 查看 [常見問題](FAQ.md) Q13-Q14（監控和指標）

**預期時間：1-2 小時**

### 「我想理解系統架構」

1. 看 [README](../README.md) 中的架構圖
2. 深入讀 [架構設計](ARCHITECTURE.md)
3. 瀏覽 `claw/` 目錄結構

**預期時間：1 小時**

### 「某功能出了問題」

1. 查看 [常見問題](FAQ.md)（涵蓋大多數常見問題）
2. 檢查 [部署指南](DEPLOYMENT_GUIDE.md) 中的健康檢查步驟
3. 查閱 [API 參考](API_REFERENCE.md) 了解工具行為

**預期時間：10-20 分鐘**

---

## 📖 文件詳細內容

### README.md
- **內容** — 項目概述、特徵列表、快速開始、系統架構、功能清單、性能指標、路線圖
- **目標讀者** — 所有人
- **長度** — ~220 行

### docs/DEPLOYMENT_GUIDE.md
- **內容** — 前置要求、安裝步驟、環境變數、Jetson 優化、監控、備份、生產檢查清單
- **目標讀者** — 部署工程師、系統管理員
- **長度** — ~150 行
- **涵蓋平台** — Jetson Orin Nano Super (JetPack 6)

### docs/API_REFERENCE.md
- **內容** — 28 工具的完整文檔，含簽名、參數、返回值、範例
- **目標讀者** — 開發者、工具集成者
- **長度** — ~270 行
- **工具分類** — 9 種（基礎、檔案、記憶體、股票、研究、時間、生成、瀏覽器、多代理）

### docs/FAQ.md
- **內容** — 17 個常見問題及答案
- **目標讀者** — 用戶、問題排查
- **長度** — ~155 行
- **分類** — 安裝、功能、效能、開發、監控、更新

### docs/ARCHITECTURE.md
- **內容** — 6 層架構、數據流範例、設計決策、擴展點
- **目標讀者** — 架構師、貢獻者
- **長度** — ~160 行
- **深度** — 系統級別

### CONTRIBUTING.md
- **內容** — 開發環境設置、編碼風格、測試指南、commit 規範、常見貢獻場景、安全性、文檔標準
- **目標讀者** — 貢獻者、開發者
- **長度** — ~280 行

### ROADMAP.md
- **內容** — 完整開發歷史（Phase 1-S7）、當前狀態、未來計畫（S8-S12）、性能基線、檢查清單
- **目標讀者** — 項目跟進者、貢獻規劃者
- **長度** — ~200 行
- **更新頻率** — 每個 phase 完成時更新

---

## 🔗 快速連結

### 代碼位置

| 功能 | 檔案 |
|---|---|
| 網關和 HTTP API | `claw/core/gateway.py` |
| 代理循環 | `claw/agent/loop.py` |
| 工具系統 | `claw/tools/` |
| 記憶體系統 | `claw/memory/` |
| 研究框架 | `claw/research/` |
| 通訊渠道 | `claw/channels/` |
| 安全層 | `claw/tools/policy.py` |
| 配置 | `config/` |

### 外部資源

| 資源 | 連結 |
|---|---|
| GitHub Issues | https://github.com/yourusername/claw-python/issues |
| GitHub Discussions | https://github.com/yourusername/claw-python/discussions |
| LLM Router | http://localhost:8000 |

---

## 💡 文檔貢獻

發現文檔有誤或缺少內容？

1. 提交 Issue（帶上 `docs` 標籤）
2. 或直接提交 PR（參見 [CONTRIBUTING.md](../CONTRIBUTING.md)）

---

## 📊 文檔統計

| 文件 | 行數 | 更新日期 |
|---|---|---|
| README.md | ~220 | 2026-03-23 |
| docs/DEPLOYMENT_GUIDE.md | ~150 | 2026-03-23 |
| docs/API_REFERENCE.md | ~270 | 2026-03-23 |
| docs/FAQ.md | ~155 | 2026-03-23 |
| docs/ARCHITECTURE.md | ~160 | 2026-03-23 |
| CONTRIBUTING.md | ~280 | 2026-03-23 |
| ROADMAP.md | ~200 | 2026-03-23 |
| **合計** | **~1,435** | |

---

## 🎯 下一步

- **新手** → 閱讀 [README](../README.md) 和 [部署指南](DEPLOYMENT_GUIDE.md)
- **開發者** → 查看 [API 參考](API_REFERENCE.md) 和 [貢獻指南](../CONTRIBUTING.md)
- **架構師** → 深入 [架構設計](ARCHITECTURE.md)
- **問題解決** → 搜索 [常見問題](FAQ.md)

---

最後更新：2026-03-23
