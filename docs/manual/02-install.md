# 二、安装与启动

官方用法是在本机用 Python 虚拟环境从源码运行。仓库没有 GitHub Release，也没有可下载的 `Tender.exe`。Mac 和 Linux 不需要装 Windows 虚拟机。

## 准备环境

需要 Python 3.10 或 3.11（与 CI 相同）、Node.js，以及一份只给这一台机器用的 `.env`。

```bash
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
```

本地开发不填写 `SECRET_KEY` 时，首次启动会在 `data/.secret_key` 生成密钥并在以后复用，权限 `0600`，不写回 `.env`。`DEBUG=false` 或 `APP_ENV=production` 时必须自己设置 `SECRET_KEY`，否则进程拒绝启动。

`.env` 和 `data/.secret_key` 都是机密，不要发到聊天或网盘公开链接。

## 先构建前端，再启动一个进程

浏览器请求的是相对路径 `/api`，所以页面和接口必须由同一个进程提供。先构建 `web/dist`，再启动。

```bash
cd web
npm install
npm run build
cd ..
bash start.sh
```

`start.sh`（Windows 用 `run.bat`）只启动**一个** uvicorn 进程：

- 不使用 `--reload`
- 不要再加 `--workers`。多个进程同时打开同一份 Chroma 和 SQLite 会损坏数据
- 默认绑定 `127.0.0.1:8000`。只给本机用时保持这样

浏览器打开 `http://127.0.0.1:8000`。

同事要从别的电脑访问时，不要把 FastAPI 直接铺到办公室局域网。HTTPS 反向代理不在本文范围内。

## 首次登录

全新安装会把一次性管理员密码写入 `data/initial_admin_password.txt`（仅当前用户可读），用户名是 `admin`。用该密码登录后按提示修改，然后删除这个密码文件。

## 配置 AI 模型

登录后进入 **系统设置**。Ollama、BGE、M3E 标为 `local`，文本留在本机。DeepSeek、通义、OpenAI、MiniMax 标为 `cloud`：提示词和该次作业需要的正文会离开本机。保存后下一笔作业就使用新模型，不必为了换模型重启进程。页面上写着这段说明，不需要再确认一次。`mock` 只用于开发，不能当成检索索引。

| 模型 | 获取地址 |
|------|----------|
| **DeepSeek** | [platform.deepseek.com](https://platform.deepseek.com) |
| **通义千问** | 阿里云百炼平台 |
| **Ollama** | 本机 `http://localhost:11434`，无需 API Key |

## 开发时的前端热更新

后端仍然用 `bash start.sh`，不要改成 `uvicorn --reload`。另开一个终端：

```bash
cd web
npm install
npm run dev
```

开发服务器在 `http://127.0.0.1:5173`，把浏览器的 `/api` 代理到本机 `8000`。页面里的接口地址仍然是相对路径 `/api`。

## 交给同事之前

1. 在 `web/` 执行 `npm run build`，确认生成了 `web/dist`。
2. 用虚拟环境、`.env` 和 `bash start.sh` 从源码启动。不要从 Releases 下载程序。
3. 只有本机已经有 `web/dist` 时，才可以用 `pyinstaller Tender.spec` 打包装包。没有 dist 时不要承诺有 exe。

## 可选：macOS launchd 示例

`docs/ops/com.tender.local.plist.example` 是一份示例，**不会**被 `start.sh` 安装。若要使用，把其中的绝对路径改成这台机器的仓库和 `.venv`，不要加入 `--workers` 或 `--reload`。需要开机拉起时再把 `RunAtLoad` / `KeepAlive` 改成 `true`，并保证同时只有这一个进程打开 `data/`。

备份和恢复见 [备份与恢复](/ops/backup-and-recovery)。
