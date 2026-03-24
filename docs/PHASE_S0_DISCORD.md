# Phase S0 Worker Prompt — Discord Embed + Egress Whitelist

> 發給：**Codex**
> 當前狀態：174 tests passing（Phase 15 完成）
> 目標狀態：178+ tests + Discord Embed 功能完整
> 耗時預估：1-2 小時

---

## 背景說明

Phase S0 是台股分析系統的基礎設施。Discord channel 現在只支援純文字推送。為了推播結構化報告和圖表，需要擴充 Discord adapter 支援 **Embed + File + 主動推送**。

---

## Task 1 — 擴充 `claw/channels/discord.py`

在 DiscordChannel class 加入 4 個新方法（import `io` 必須）：

**方法 1：send_embed(session_id, embed) → None**
- 參數：session_id (str), embed (discord.Embed)
- 功能：推送 Embed 到該 session 的 channel
- 錯誤處理：如果找不到 channel，log warning

**方法 2：send_file(session_id, file_bytes, filename, caption="") → None**
- 參數：session_id, file_bytes (bytes), filename (str), caption (str)
- 功能：推送檔案附件（e.g., 圖表 PNG）
- 使用 discord.File 包裝 io.BytesIO

**方法 3：send_embed_with_file(session_id, embed, file_bytes, filename) → None**
- 參數：session_id, embed (discord.Embed), file_bytes (bytes), filename (str)
- 功能：同時推送 Embed + File（股票報告的標準格式）

**方法 4：send_to_channel_id(channel_id, embed=None, text=None, file_bytes=None, filename=None) → None**
- 參數：channel_id (int), 可選的 embed/text/file
- 功能：主動推送到指定 channel_id（Cron job 用）
- 使用 `bot.fetch_channel(channel_id)` 來取得 channel 物件
- 支援多種組合（embed alone, file alone, embed+file）

參考實現（根據 PHASE_STOCK_S1_SPEC.md 中的代碼）

---

## Task 2 — 更新 `config/default.yaml`

在 `discord:` 區塊加入新欄位（用於 Cron job 的 channel IDs）：

```yaml
discord:
  enabled: false
  token: ""
  stock_channel_id: 0       # 股票分析頻道（Cron job 用）
  morning_report_channel_id: 0  # 晨報頻道（可選，不指定則用 stock_channel_id）
```

---

## Task 3 — 更新 `claw/core/config.py`

在 DiscordConfig dataclass 加入新欄位：

```python
@dataclass
class DiscordConfig:
    enabled: bool = False
    token: str = ""
    stock_channel_id: int = 0
    morning_report_channel_id: int = 0
```

---

## Task 4 — 更新 `config/egress_policy.yaml`

在 `egress_rules:` 下新增台股資料源白名單（4 條規則）：

```yaml
  # Taiwan Stock Data Sources (Stock Analysis System)
  - dest: "query.sse.com.tw"
    verdict: allow
    # TWSE official API - historical quotes

  - dest: "mds.twse.com.tw"
    verdict: allow
    # TWSE market data server

  - dest: "query1.finance.yahoo.com"
    verdict: allow
    # Yahoo Finance backup source

  - dest: "finance.yahoo.com"
    verdict: allow
    # Yahoo Finance primary source
```

---

## Task 5 — 建立單元測試 `tests/test_discord_embed.py`

4 個新測試（使用 mock）：

1. **test_discord_send_embed()** — 驗證 Embed 能被推送
2. **test_discord_send_file()** — 驗證 File 附件能被推送
3. **test_discord_send_embed_with_file()** — 驗證 Embed + File 一起推送
4. **test_discord_send_to_channel_id()** — 驗證主動推送到 channel_id

每個測試用 AsyncMock 模擬 Discord channel 物件，驗證正確的方法被呼叫。

參考：PHASE_STOCK_S0_PROMPT_FOR_CODEX.md 中的 Task 4

---

## Task 6 — 執行測試

```bash
cd /home/martin/Desktop/claw-python-personal
python -m pytest tests/test_discord*.py -v
python -m pytest tests/ -q --tb=short
```

預期：174 + 4 = **178 tests passed, 3 skipped**

---

## Task 7 — 驗證 egress 規則載入

```bash
python -c "
from claw.tools.policy import EgressPolicy
from pathlib import Path
policy = EgressPolicy.from_yaml(Path('config/egress_policy.yaml'), db_path='~/.claw/claw.db')
twse_rules = [r for r in policy.rules if 'sse' in r.dest or 'twse' in r.dest.lower() or 'yahoo' in r.dest.lower()]
print(f'Stock data source rules: {len(twse_rules)}')
for r in twse_rules:
    print(f'  - {r.dest}: {r.verdict}')
assert len(twse_rules) >= 4, 'Should have at least 4 stock data source rules'
print('✅ egress policy loaded correctly')
"
```

預期輸出：4 個 TWSE/Yahoo Finance 規則被成功載入

---

## 交付清單

完成後回報：

1. **修改的檔案絕對路徑**
2. **新建的檔案絕對路徑**
3. **pytest 最終輸出**（應為 178+ passed）
4. **egress 規則驗證結果**（應為 4+ rules）
5. **遇到的問題和解決方式**

---

## 完成標準

✅ Discord 可推送 Embed（test_discord_send_embed 通過）
✅ Discord 可推送 File（test_discord_send_file 通過）
✅ Discord 支援主動推送到 channel_id（test_discord_send_to_channel_id 通過）
✅ egress 規則正確載入（4 個台股資料源白名單）
✅ 178+ tests pass, 0 failures
✅ 伺服器啟動無誤（新增的 config 欄位被正確載入）

---

## 注意事項

- 不要改動 S1-S4 的代碼（只做 Discord 擴充）
- `send_to_channel_id()` 是關鍵方法，被後續 S2b 的 Cron job 使用
- egress 白名單要確保 S1-S4 的股票資料源能夠訪問

