# Deployment Guide — Jetson Orin Nano Super

> 目標硬體：Jetson Orin Nano Super（8GB unified memory, JetPack 6）

---

## 前置要求

### 硬體
- Jetson Orin Nano Super 開發板
- 最少 16GB microSD 卡（推薦 32GB）
- 電源供應器（5A 5V 或 USB-C PD）
- 網絡連接

### 軟體
- JetPack 6.x（含 CUDA 12.2）
- Python 3.8+
- Docker CE

### 外部服務
- LLM Router（執行 Claude API 代理）
- Discord Bot（用於推播）

---

## 安裝步驟

### 1. 準備 Jetson

```bash
# 更新系統
sudo apt update && sudo apt upgrade -y

# 安裝必要套件
sudo apt install -y python3-pip python3-dev build-essential
sudo apt install -y docker.io
sudo apt install -y git

# 將當前使用者加入 docker 群組
sudo usermod -aG docker $USER
newgrp docker

# 檢查 CUDA
nvidia-smi  # 應顯示 CUDA 12.2
```

### 2. 複製和配置 claw-python

```bash
# 複製專案
git clone https://github.com/yourusername/claw-python.git ~/claw-python
cd ~/claw-python

# 安裝 Python 依賴
pip install -e .

# 驗證安裝
python -c "import claw; print('✓ claw imported successfully')"
```

### 3. 配置環境變數

```bash
cp .env.example .env
nano .env
```

必填項：

```bash
LLM_ROUTER_URL=http://localhost:8000
LLM_ROUTER_KEY=your_api_key_here

# Discord（可選）
DISCORD_TOKEN=your_bot_token_here
DISCORD_CHANNEL_ID=your_channel_id_here
```

### 4. 啟動伺服器

```bash
# 前景模式（用於測試）
python -m claw.main

# 檢查狀態
curl -s http://localhost:8000/admin/health | python -m json.tool
```

---

## Jetson 優化

### CPU 效能設定

```bash
# 設定 CPU governor 為 performance
echo performance | sudo tee /sys/devices/system/cpu/cpu*/cpufreq/scaling_governor
```

### 記憶體管理

```bash
# 查看記憶體使用
free -h

# 擴展 swap（如需）
sudo fallocate -l 2G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile
```

---

## 監控和維護

### 健康檢查

```bash
# 即時指標
curl -s http://localhost:8000/admin/metrics | python -m json.tool

# 日誌監控
tail -f ~/.claw/claw.log | grep -E 'ERROR|WARNING'
```

### 備份

```bash
# 備份資料庫（每日）
mkdir -p ~/backups
cp ~/.claw/data/*.db ~/backups/$(date +%Y%m%d_%H%M%S).db.backup
```

---

## 生產 Checklist

- [ ] LLM Router 正常執行
- [ ] Discord credentials 已設定
- [ ] 資料庫備份計劃已設立
- [ ] 日誌監控已設定
- [ ] 定期更新計劃已制定

---

見 [README.md](../README.md) 了解更多。
