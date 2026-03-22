# claw-python 開發路線圖

> 更新日期：2026-03-22
> 硬體：Jetson Orin Nano Super（8GB unified memory, kernel 5.15.136-tegra）
> 當前狀態：Phase 15 完成，**183 tests 通過，所有核心功能已完成**

---

## 完整開發里程表

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
| **15** | **Cleanup + documentation** | **2026-03** | **183+** | **✅ 完成** |

---

## 項目狀態

- **核心功能**：✅ 完整（22 個工具，3 個渠道，所有組件已接線）
- **測試覆蓋**：✅ 183 tests pass, 0 failures
- **部署就緒**：✅ Jetson JetPack 6 優化完成
- **空殼功能**：✅ 已修復（所有組件真實啟動）

---

## 後續計畫（Phase S0-S7）

| Phase | 內容 | 狀態 |
|---|---|---|
| S1-S4 | Taiwan Stock Analysis System | ⏳ 計畫中 |
| S5 | Production Optimization | ⏳ 計畫中 |
| S6 | Complete Testing | ⏳ 計畫中 |
| S7 | Documentation + User Guide | ⏳ 計畫中 |

