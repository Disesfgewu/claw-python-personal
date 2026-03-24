# Discord Bot 配置指南

> 清楚的步驟指南，用於部署 claw-python Discord Bot

---

## Step 1：在 Discord Developer Portal 建立 Bot

1. 進入 https://discord.com/developers/applications
2. 點擊 **New Application**
3. 輸入名稱（例如 `claw-stock-bot`）
4. 左側菜單選 **Bot** → 點 **Add Bot**
5. 在 **TOKEN** 下方點 **Reset Token** → **Copy**（這就是你的 `DISCORD_BOT_TOKEN`）

**重要：此 token 絕不要洩露，視同密碼。**

---

## Step 2：配置 Bot 權限

1. 仍在 Developer Portal，選 **OAuth2** → **URL Generator**
2. **Scopes** 勾選：
   - `bot`
3. **Permissions** 勾選：
   - `Send Messages`
   - `Embed Links`
   - `Attach Files`
   - `Read Message History`（可選，用於回復訊息）
   - `Add Reactions`（可選，用於互動反應）

4. 複製生成的 URL，在瀏覽器開啟，選擇要邀請 Bot 的 Discord 伺服器

**完成後，Bot 會出現在你的伺服器成員清單。**

---

## Step 3：取得 Discord 頻道 ID

在 Discord app 中：

1. 打開你要推播股票報告的頻道
2. 右擊頻道名 → **複製頻道 ID**（如果沒看到此選項，在 Discord Settings → Advanced → 開啟 **Developer Mode**）
3. 貼到文本編輯器，得到類似 `123456789012345678` 的十位數字

這就是你的 `DISCORD_CHANNEL_ID`。

---

## Step 4：配置 .env 檔案

在 Jetson 上編輯 `~/.claw/.env`（或 `/home/martin/Desktop/claw-python-personal/.env`）：

```bash
# Discord 推播配置
DISCORD_BOT_TOKEN=你的_Bot_Token_這裡
DISCORD_CHANNEL_ID=123456789012345678

# LLM Router（已有）
LLM_ROUTER_URL=http://localhost:8000
LLM_ROUTER_KEY=your_api_key

# Telegram/Slack（如有）
TELEGRAM_TOKEN=...
SLACK_TOKEN=...
```

**重要：.env 檔案不要提交到 git。**

---

## Step 5：驗證 Bot 連接

啟動 claw-python：

```bash
python -m claw.main
```

檢查日誌：

```
[INFO] Discord bot logged in as claw-stock-bot#1234
[INFO] Discord channel started successfully
```

在 Discord 頻道中手動測試（輸入訊息，看 bot 是否回應）：

```
user: 查詢 2330
bot: (應該在幾秒後回覆台積電資料)
```

---

## Step 6：驗證 Cron 推播

晨報會在**每個交易日 08:00**（台灣時間）推播到 `DISCORD_CHANNEL_ID`。

檢查方法：

1. 查看日誌是否有排程執行記錄
2. 在指定頻道看是否有晨報 Embed 推播

如果沒有推播，檢查：
- Bot 是否有該頻道的 **Send Messages** 權限
- 時區是否正確設定（應該是 `Asia/Taipei`）
- `DISCORD_CHANNEL_ID` 是否正確

---

## 常見問題

### Q：Bot 上線但無法回應

**A：檢查**
1. Bot 權限 — 右擊 Bot 使用者 → 確認有 **Send Messages** 和 **Embed Links**
2. 頻道權限 — 右擊頻道 → 設定 → 角色/使用者 → 確認 Bot 有發送消息權限
3. Message Content Intent — 在 Developer Portal → Bot → **Message Content Intent** 開啟

### Q：晨報沒有在 08:00 推播

**A：檢查**
1. Cron job 是否已登錄 — 看啟動日誌是否有 "Morning report Cron job registered"
2. 時區 — 確認 Jetson 時區是 UTC+8，或代碼用 `timezone="Asia/Taipei"`
3. 頻道 ID — 確認 `DISCORD_CHANNEL_ID` 正確
4. Bot 權限 — 確認 Bot 有該頻道的發送權限

### Q：圖表發不出來

**A：檢查**
1. `Attach Files` 權限是否已啟用
2. 圖表生成是否成功 — 查看日誌中是否有 `generate_chart` 的錯誤
3. 檔案大小 — Discord 單檔案限制 8MB

### Q：Token 洩露了怎辦

**A：立即**
1. 進入 Discord Developer Portal
2. 找到洩露的 Application → Bot → **Reset Token**
3. 複製新 token
4. 更新 `.env` 中的 `DISCORD_BOT_TOKEN`
5. 重啟 bot

---

## 安全性建議

- ✅ 使用 `.env` 存放敏感資料，不要寫進代碼
- ✅ `.env` 已在 `.gitignore` 中，不會被提交
- ✅ Token 定期輪換（建議每 3 個月一次）
- ✅ 只給 Bot 必要的權限（Send Messages, Embed Links, Attach Files）

---

## 測試清單

部署前請確認：

- [ ] Bot Token 已取得並放入 `.env`
- [ ] Channel ID 已取得並放入 `.env`
- [ ] Bot 已邀請到 Discord 伺服器
- [ ] Bot 有必要的權限（Send, Embed, Attach）
- [ ] 手動測試：在頻道輸入訊息，bot 能回覆
- [ ] 日誌中能看到 "Discord channel started successfully"
- [ ] Jetson 時區設定為 Asia/Taipei

---

**準備好？告訴我 Bot Token 和 Channel ID，我幫你驗證配置。**
