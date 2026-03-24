# Frequently Asked Questions (FAQ)

---

## 安裝和配置

### Q1: 在 Jetson 上安裝失敗

**A**: 嘗試以下步驟：

```bash
pip install --upgrade pip setuptools wheel
pip install -e . --no-cache-dir
```

### Q2: Docker 容器無法啟動

**A**: 檢查 Docker daemon：

```bash
sudo systemctl status docker
sudo systemctl restart docker
docker ps
```

### Q3: Discord 推播失敗，提示 "Forbidden"

**A**: 在 Discord 伺服器設定中為 Bot 添加權限：
- Send Messages
- Embed Links
- Attach Files

---

## 功能使用

### Q4: 如何查詢特定股票？

**A**: 在 Discord 中傳送：`查詢 2330`

### Q5: 晨報何時執行？

**A**: 每個交易日 08:00（台灣時間）

### Q6: 如何手動執行晨報？

**A**:
```bash
curl -X POST http://localhost:8000/cron/exec \
  -H "Content-Type: application/json" \
  -d '{"job_name": "morning_report"}'
```

---

## 效能和故障

### Q7: 系統變慢或記憶體增長

**A**: 重啟伺服器並清理快取：

```bash
pkill -f "python.*claw.main"
sleep 2
python -m claw.main &
```

### Q8: "Connection timeout" 錯誤

**A**: 檢查 LLM Router：

```bash
curl -s http://localhost:8000/health | python -m json.tool
curl -s http://${LLM_ROUTER_URL}/health
```

### Q9: 股票資料無法拉取

**A**: 檢查網絡連接和 egress 規則：

```bash
curl -I https://finance.yahoo.com
curl -I https://query.sse.com.tw
```

---

## 開發和定製

### Q10: 如何添加新的股票工具？

**A**: 在 `claw/tools/stock_tools.py` 中實現，然後使用 `@register_tool()` 註冊。

### Q11: 如何修改 Cron job 的執行時間？

**A**: 編輯 `claw/main.py` 中的排程表達式。

### Q12: 如何自訂 Discord 推播格式？

**A**: 編輯 `claw/cron/jobs/morning_report.py`，修改 Embed 構建邏輯。

---

## 監控和日誌

### Q13: 日誌太多，如何過濾？

**A**: 修改 `config/default.yaml`：

```yaml
logging:
  level: WARNING
```

### Q14: 如何查看詳細的效能指標？

**A**:
```bash
curl http://localhost:8000/admin/metrics | python -m json.tool
```

---

## 更新和升級

### Q15: 如何升級 claw-python？

**A**:
```bash
cd ~/claw-python
git pull origin main
pip install --upgrade -e .
pkill -f "python.*claw.main"
sleep 2
python -m claw.main &
```

---

## 其他

### Q16: 系統支援哪些語言？

**A**: 主要支援中文和英文。

### Q17: 如何聯絡技術支援？

**A**:
- Issues: https://github.com/yourusername/claw-python/issues
- Discussions: https://github.com/yourusername/claw-python/discussions

---

未找到答案？提交 Issue！
