#!/usr/bin/env bash
# 重启恢复检查钩子（由 verify.sh 调用）。
# 契约：起服务 → 写入一条带唯一标记的记录 → 杀掉服务 → 再起 → 读回比对。
# 不碰 backend/data，不调真实模型。
set -u
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PY="$ROOT/backend/.venv/bin/python"; [ -x "$PY" ] || PY="$(command -v python3)"
PORT="${RESTART_CHECK_PORT:-8766}"
TMP="$(mktemp -d)"
export DATA_DIR="$TMP/data"
export DATABASE_URL="sqlite:///$TMP/restart.db"
export IMAGE_API_KEY=""
export WORKER_ENABLED="0"
BASE="http://127.0.0.1:$PORT"

# 用 exec 让子 shell 直接变成 uvicorn 进程，$! 即 uvicorn 的 PID，kill 不留孤儿
start() { ( cd "$ROOT/backend" && exec "$PY" -m uvicorn app.main:app --host 127.0.0.1 --port "$PORT" ) >>"$TMP/server.log" 2>&1 & echo $! > "$TMP/pid"; disown; }
stop()  { [ -f "$TMP/pid" ] || return 0; PID="$(cat "$TMP/pid")"; kill "$PID" 2>/dev/null; for i in 1 2 3 4 5 6 7 8 9 10; do kill -0 "$PID" 2>/dev/null || break; sleep 0.3; done; kill -9 "$PID" 2>/dev/null; rm -f "$TMP/pid"; }
wait_up() { for i in $(seq 1 40); do curl -s -o /dev/null "$BASE/api/health" && return 0; sleep 0.25; done; return 1; }
cleanup() { stop; rm -rf "$TMP"; }
trap cleanup EXIT

if curl -s -o /dev/null "$BASE/api/health"; then echo "端口 $PORT 已被占用，无法检查。"; exit 2; fi

start; wait_up || { echo "服务首次启动失败："; cat "$TMP/server.log"; exit 1; }
"$PY" "$ROOT/scripts/check-persistence.py" write "$BASE" "$TMP" || exit 1

stop; echo "服务已停止。"
start; wait_up || { echo "服务第二次启动失败："; cat "$TMP/server.log"; exit 1; }
"$PY" "$ROOT/scripts/check-persistence.py" read "$BASE" "$TMP" || exit 1
exit 0
