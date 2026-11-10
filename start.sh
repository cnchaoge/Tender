#!/bin/bash
# Official local start: one process, no --reload, loopback unless HOST is set.
# Do not add --workers. ChromaDB and SQLite are not safe when two processes
# open the same data/ directory.
set -euo pipefail
cd "$(dirname "$0")"
export PYTHONPATH="$(pwd)"
export ENV_FILE="$(pwd)/.env"

read_env_key() {
  local key="$1"
  local file=".env"
  [ -f "$file" ] || return 0
  local line
  line="$(grep -E "^[[:space:]]*${key}=" "$file" | tail -n 1 || true)"
  [ -n "$line" ] || return 0
  local value="${line#*=}"
  value="${value#"${value%%[![:space:]]*}"}"
  value="${value%"${value##*[![:space:]]}"}"
  value="${value%\"}"
  value="${value#\"}"
  value="${value%\'}"
  value="${value#\'}"
  printf '%s' "$value"
}

if [ -z "${HOST:-}" ]; then
  HOST="$(read_env_key HOST)"
fi
if [ -z "${PORT:-}" ]; then
  PORT="$(read_env_key PORT)"
fi
HOST="${HOST:-127.0.0.1}"
PORT="${PORT:-8000}"

echo "启动 Tender（单个进程，不使用 --reload，不使用 --workers）"
echo "监听 ${HOST}:${PORT}"
echo "浏览器打开 http://127.0.0.1:${PORT}"
if [ ! -f web/dist/index.html ]; then
  echo "未找到 web/dist/index.html。请先在 web/ 执行 npm install && npm run build。"
  echo "只启动 API 时，开发前端可以用 cd web && npm run dev（它把 /api 代理到本机 ${PORT}）。"
fi
echo "首次安装的一次性管理员密码写在 data/initial_admin_password.txt"
echo "同一份 data/ 不能同时被第二个进程打开。"
echo ""

exec uvicorn server.main:app --host "$HOST" --port "$PORT"
