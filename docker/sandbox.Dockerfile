# docker/sandbox.Dockerfile
FROM python:3.11-slim

# 基本工具
RUN apt-get update && apt-get install -y \
    bash curl wget git jq unzip \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# 工作目錄
WORKDIR /workspace

# 非 root 使用者（安全）
RUN useradd -m -u 1000 sandbox
USER sandbox

CMD ["/bin/bash"]
