#!/bin/sh
# 容器启动脚本：准备可写目录 → 首次挂卷补种子 → history 落到数据卷 → 启动服务
set -eu

cd /app

# 1) 运行时目录（Zeabur 卷首次挂载时是空目录，必须兜底创建）
mkdir -p assets/input assets/output assets/library assets/uploads data output logs

# 2) 数据卷为空时，把镜像内置的默认配置补进去（只补缺失文件，绝不覆盖线上数据）
if [ -d /app/_seed/data ]; then
  for f in /app/_seed/data/*; do
    [ -f "$f" ] || continue
    base=$(basename "$f")
    if [ ! -f "/app/data/$base" ]; then
      cp "$f" "/app/data/$base"
      echo "[entrypoint] seeded data/$base"
    fi
  done
fi

# 3) history.json 指向数据卷，避免每次重新部署丢失历史记录
if [ ! -e /app/history.json ]; then
  if ln -sfn /app/data/history.json /app/history.json 2>/dev/null; then
    echo "[entrypoint] history.json -> /app/data/history.json"
  fi
fi

# 4) 兜底：若目标端口被平台改写，交给 server.py 读取 PORT
exec python server.py
