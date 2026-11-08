#!/usr/bin/env bash
# 一键启动本地开发环境：后端 8010 + 前端 3010
# 用法：bash scripts/dev.sh      （Ctrl+C 结束）
set -u
ROOT="$(cd "$(dirname "$0")/.." && pwd)"

if [ ! -x "$ROOT/backend/.venv/bin/python" ]; then
  echo "首次运行：创建后端虚拟环境并安装依赖…"
  ( cd "$ROOT/backend" && python3 -m venv .venv && ./.venv/bin/pip install -q -r requirements.txt ) || exit 1
fi

if [ ! -d "$ROOT/frontend/node_modules" ]; then
  echo "首次运行：安装前端依赖…"
  ( cd "$ROOT/frontend" && npm install --no-audit --no-fund ) || exit 1
fi

cleanup() {
  [ -n "${BACK_PID:-}" ] && kill "$BACK_PID" 2>/dev/null
  [ -n "${FRONT_PID:-}" ] && kill "$FRONT_PID" 2>/dev/null
}
trap cleanup EXIT INT TERM

( cd "$ROOT/backend" && exec ./.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8010 ) &
BACK_PID=$!

( cd "$ROOT/frontend" && exec npm run dev ) &
FRONT_PID=$!

cat <<EOF

后端： http://127.0.0.1:8010/api/health
工作台：http://127.0.0.1:3010
（端口 8000/3000 被本机其他项目占用，本项目改用 8010/3010）

按 Ctrl+C 结束。
EOF

wait
