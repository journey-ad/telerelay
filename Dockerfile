# 多阶段构建，优化镜像大小
FROM python:3.11-slim as builder

# 设置工作目录
WORKDIR /app

# 安装依赖
COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

# 最终镜像
FROM python:3.11-slim

# 创建非 root 用户
RUN useradd -m -u 1000 appuser && \
    mkdir -p /app /app/logs /app/sessions /app/config && \
    chown -R appuser:appuser /app

# 设置工作目录
WORKDIR /app

# 从 builder 复制依赖到 appuser 目录
COPY --from=builder --chown=appuser:appuser /root/.local /home/appuser/.local

# 设置环境变量（PATH 指向 appuser 的 .local）
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH=/home/appuser/.local/bin:$PATH

# 复制应用代码
COPY --chown=appuser:appuser src/ ./src/
COPY --chown=appuser:appuser static/ ./static/
COPY --chown=appuser:appuser config/*.example ./config/

# 切换到非 root 用户
USER appuser

# 暴露端口
EXPOSE 8080

# 健康检查
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import requests; requests.get('http://localhost:8080/api/bot/status')" || exit 1

# 启动命令
CMD ["python", "-m", "src.main"]
