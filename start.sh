#!/bin/bash
cd "$(dirname "$0")"
export PYTHONPATH="$(pwd)"
export ENV_FILE="$(pwd)/.env"

echo "启动 Tender..."
echo "后端: http://localhost:8000"
echo "前端: http://localhost:4173"
echo "文档: http://localhost:8000/docs"
echo "首次安装会在下方日志打印一次性管理员密码，并写入 data/initial_admin_password.txt"
echo ""

uvicorn server.main:app --host 0.0.0.0 --port 8000 --reload
