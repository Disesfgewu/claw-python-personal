# Phase S0 Worker Prompt — Discord Embed + Egress 擴充

你是實作 claw-python Phase S0 的 worker。工作目錄：`/home/martin/Desktop/claw-python-personal/`。

當前狀態：167 tests passing，所有核心組件已接線。

---

## 背景說明

Phase S0 是台股 AI 分析系統的基礎設施層。現有的 Discord channel adapter（Phase 14）只支援純文字推送。為了推播圖表和結構化報告，需要：
1. 擴充 Discord adapter 支援 Embed + File 附件
2. 新增 egress_policy.yaml 的台股資料源白名單

---

## Task 1 — 擴充 `claw/channels/discord.py`

在現有的 `DiscordChannel` class 加入以下方法：

```python
async def send_embed(
    self,
    session_id: str,
    embed: discord.Embed
) -> None:
    """Send a Discord Embed to session's channel."""
    channel = self._session_clients.get(session_id)
    if channel is None:
        logger.warning(f"No channel found for session {session_id}")
        return
    try:
        await channel.send(embed=embed)
    except Exception as e:
        logger.error(f"Failed to send embed to {session_id}: {e}")

async def send_file(
    self,
    session_id: str,
    file_bytes: bytes,
    filename: str,
    caption: str = ""
) -> None:
    """Send a file attachment (e.g., chart image) to session's channel."""
    channel = self._session_clients.get(session_id)
    if channel is None:
        logger.warning(f"No channel found for session {session_id}")
        return
    try:
        file = discord.File(
            io.BytesIO(file_bytes),
            filename=filename
        )
        await channel.send(content=caption, file=file)
    except Exception as e:
        logger.error(f"Failed to send file to {session_id}: {e}")

async def send_embed_with_file(
    self,
    session_id: str,
    embed: discord.Embed,
    file_bytes: bytes,
    filename: str
) -> None:
    """Send Embed + File together (for stock reports with charts)."""
    channel = self._session_clients.get(session_id)
    if channel is None:
        logger.warning(f"No channel found for session {session_id}")
        return
    try:
        file = discord.File(
            io.BytesIO(file_bytes),
            filename=filename
        )
        await channel.send(embed=embed, file=file)
    except Exception as e:
        logger.error(f"Failed to send embed+file to {session_id}: {e}")

async def send_to_channel_id(
    self,
    channel_id: int,
    embed: discord.Embed = None,
    text: str = None,
    file_bytes: bytes = None,
    filename: str = None
) -> None:
    """
    Proactive push to a specific channel ID (for Cron jobs).
    Used by scheduled tasks to push morning/evening reports.
    """
    try:
        channel = await self.bot.fetch_channel(channel_id)
        if embed and file_bytes:
            file = discord.File(
                io.BytesIO(file_bytes),
                filename=filename
            )
            await channel.send(embed=embed, file=file)
        elif embed:
            await channel.send(embed=embed)
        elif file_bytes:
            file = discord.File(
                io.BytesIO(file_bytes),
                filename=filename
            )
            await channel.send(content=text or "", file=file)
        elif text:
            await channel.send(text)
    except Exception as e:
        logger.error(f"Failed to send to channel {channel_id}: {e}")
```

**需要新增的 import：**
```python
import io
```

---

## Task 2 — 更新 `config/default.yaml`

在 `discord:` 段落加入新欄位：

```yaml
discord:
  enabled: false
  token: ""
  # Cron jobs 用的 channel IDs（可選）
  stock_channel_id: 0       # 股票分析頻道
  morning_report_channel_id: 0  # 晨報頻道（可選，沒設就用 stock_channel_id）
```

---

## Task 3 — 更新 `config/egress_policy.yaml`

在 `egress_rules:` 下新增台股資料源白名單：

```yaml
egress_rules:
  # 既有的規則保持不變
  - dest: "localhost"
    verdict: allow
  - dest: "127.0.0.1"
    verdict: allow
  - dest: "duckduckgo.com"
    verdict: allow

  # 新增：台股資料源（股票分析系統用）
  - dest: "query.sse.com.tw"
    verdict: allow  # TWSE 官方 API —— 歷史行情查詢

  - dest: "mds.twse.com.tw"
    verdict: allow  # TWSE 行情資料伺服器

  - dest: "query1.finance.yahoo.com"
    verdict: allow  # Yahoo Finance 備用源

  - dest: "finance.yahoo.com"
    verdict: allow  # Yahoo Finance 主源

  # 可選：AKShare（用於財報資料，非必須）
  # - dest: "api.akshare.com"
  #   verdict: allow
```

---

## Task 4 — 建立單元測試 `tests/test_discord_embed.py`

```python
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import discord
import io


@pytest.mark.asyncio
async def test_discord_send_embed():
    """send_embed() sends an Embed to session's channel."""
    from claw.channels.discord import DiscordChannel

    channel = DiscordChannel(token="test_token", base_url="http://localhost:18790")
    mock_discord_channel = AsyncMock()
    channel._session_clients["test_session"] = mock_discord_channel

    embed = discord.Embed(title="Test", description="Test Embed")
    await channel.send_embed("test_session", embed)

    mock_discord_channel.send.assert_called_once()
    call_args = mock_discord_channel.send.call_args
    assert call_args[1]["embed"] == embed


@pytest.mark.asyncio
async def test_discord_send_file():
    """send_file() sends a file attachment."""
    from claw.channels.discord import DiscordChannel

    channel = DiscordChannel(token="test_token", base_url="http://localhost:18790")
    mock_discord_channel = AsyncMock()
    channel._session_clients["test_session"] = mock_discord_channel

    file_bytes = b"PNG_DATA_HERE"
    await channel.send_file("test_session", file_bytes, "chart.png", "Stock Chart")

    mock_discord_channel.send.assert_called_once()
    call_args = mock_discord_channel.send.call_args
    assert call_args[1]["content"] == "Stock Chart"
    # File object 被傳入，檢查是否呼叫了 send


@pytest.mark.asyncio
async def test_discord_send_embed_with_file():
    """send_embed_with_file() sends both Embed and File."""
    from claw.channels.discord import DiscordChannel

    channel = DiscordChannel(token="test_token", base_url="http://localhost:18790")
    mock_discord_channel = AsyncMock()
    channel._session_clients["test_session"] = mock_discord_channel

    embed = discord.Embed(title="Stock Report")
    file_bytes = b"PNG_DATA"
    await channel.send_embed_with_file("test_session", embed, file_bytes, "chart.png")

    mock_discord_channel.send.assert_called_once()
    call_args = mock_discord_channel.send.call_args
    assert call_args[1]["embed"] == embed


@pytest.mark.asyncio
async def test_discord_send_to_channel_id():
    """send_to_channel_id() uses bot.fetch_channel() for proactive push."""
    from claw.channels.discord import DiscordChannel

    channel = DiscordChannel(token="test_token", base_url="http://localhost:18790")

    mock_fetched_channel = AsyncMock()
    channel.bot.fetch_channel = AsyncMock(return_value=mock_fetched_channel)

    embed = discord.Embed(title="Morning Report")
    await channel.send_to_channel_id(123456, embed=embed)

    channel.bot.fetch_channel.assert_called_once_with(123456)
    mock_fetched_channel.send.assert_called_once()
```

---

## Task 5 — 驗證現有 Discord 測試通過

執行：
```bash
cd /home/martin/Desktop/claw-python-personal
python -m pytest tests/test_discord.py tests/test_discord_embed.py -v
```

預期：所有測試通過（既有 3 個 + 新增 4 個 = 7 個 tests）

---

## 交付清單

完成後回報：

1. **修改的檔案絕對路徑：**
   - `/home/martin/Desktop/claw-python-personal/claw/channels/discord.py`
   - `/home/martin/Desktop/claw-python-personal/config/default.yaml`
   - `/home/martin/Desktop/claw-python-personal/config/egress_policy.yaml`

2. **新建的檔案絕對路徑：**
   - `/home/martin/Desktop/claw-python-personal/tests/test_discord_embed.py`

3. **pytest 最終輸出最後 5 行**
   預期：7 tests passed

4. **驗證步驟：**
   ```bash
   # 確認 egress 規則已載入
   python -c "
   from claw.tools.policy import EgressPolicy
   from pathlib import Path
   policy = EgressPolicy.from_yaml(Path('config/egress_policy.yaml'), db_path='~/.claw/claw.db')
   twse_rules = [r for r in policy.rules if 'sse' in r.dest or 'twse' in r.dest.lower()]
   print(f'TWSE egress rules: {len(twse_rules)}')
   for r in twse_rules:
       print(f'  - {r.dest}: {r.verdict}')
   "
   ```
   預期：至少 2 個 TWSE 規則被載入

5. **遇到的問題和解決方式**

---

## 預期測試計數

| 來源 | 數量 |
|---|---|
| 既有 tests（Phase 14） | 3 |
| 新增 test_discord_embed.py | 4 |
| **合計** | **7** |

總測試數應該從 167 增加到 171。

---

## 完成標準

✅ Discord 可發送 Embed
✅ Discord 可發送檔案附件
✅ Discord 支援主動推送到指定 channel_id
✅ egress_policy 白名單已更新
✅ 所有測試通過
✅ 伺服器啟動無錯誤
