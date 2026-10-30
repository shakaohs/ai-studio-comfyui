FROM python:3.10-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    TZ=Asia/Shanghai

WORKDIR /app

# ffmpeg：视频抽帧/封面，项目内多处调用；tzdata 保证中文时间显示正确
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg ca-certificates tzdata curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# 内置种子数据另存一份，供数据卷首次挂载时回填
RUN mkdir -p /app/_seed/data \
    && cp -a /app/data/. /app/_seed/data/ 2>/dev/null || true

# 运行时目录（即使未挂卷也能正常读写）
RUN mkdir -p assets/input assets/output assets/library assets/uploads data output logs \
    && chmod +x entrypoint.sh

EXPOSE 3000

CMD ["sh", "entrypoint.sh"]
