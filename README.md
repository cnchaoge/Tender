# ⚡ Tender

**制造业投标标书 AI 助手 — 本地部署，开箱即用**

---

## 🎯 解决什么问题

制造业中小企业（管道管件、体育器材、机床附件等）在投标时面临三大痛点：

- **时间紧** — 标书编写耗时长，反复修改易出错
- **经验少** — 缺乏专业文档人员，模板难找
- **数据安全** — 工厂资料不想上传到外部服务器

**Tender** 将 AI 能力本地化，让标书生成在工厂自己的电脑上完成，文件永不离开。

---

## ✨ 核心功能

| 功能 | 说明 |
|------|------|
| 📄 **知识库管理** | 上传产品资料（PDF/Word/Excel），AI 自动理解内容 |
| 💬 **RAG 智能问答** | 基于文档内容的精准问答检索 |
| 📋 **投标标书生成** | 选择模板 + 补充信息 = 生成专业投标文件 |
| 📑 **专业排版导出** | 封面、目录、页眉页脚、标题样式自动排版 |
| 💰 **报价分析计算器** | 根据评分公式计算最优报价，多策略对比 |
| ✅ **投标材料检查清单** | 自动生成盖章签字材料清单，防废标 |
| 🔍 **历史标书智能推荐** | 自动匹配知识库中最相似的章节供参考 |
| 📚 **内置招投标词汇表** | 44 条行业术语，提升 AI 理解准确度 |

---

## 🛡️ 为什么选择本地部署

```
┌─────────────────────────────────────────────┐
│  数据不出厂                                  │
│  所有文档存储在工厂自有电脑或服务器           │
│  不上传任何文件到第三方云平台                 │
│                                              │
│  ✓ 符合企业数据安全要求                       │
│  ✓ 无需依赖外网连接                           │
│  ✓ IT 管理更可控                              │
└─────────────────────────────────────────────┘
```

---

## 🚀 快速体验

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 配置 AI 模型

创建 `.env` 文件（已提供模板），配置 LLM_PROVIDER 和 API Key，或使用本地 Ollama：

```env
# 云端方案（选一）
DEEPSEEK_API_KEY=your_api_key
LLM_PROVIDER=deepseek

# 或本地 Ollama（无需 API Key）
LLM_PROVIDER=ollama
OLLAMA_MODEL=qwen3:4b
```

### 3. 构建前端并启动一个进程

```bash
cd web && npm install && npm run build && cd ..
bash start.sh
```

`start.sh` 只启动一个 uvicorn 进程，不使用 `--reload`，也不要再加 `--workers`。Chroma 和 SQLite 不能被两个进程同时打开。默认绑定 `127.0.0.1`。

### 4. 打开浏览器

- 访问 http://127.0.0.1:8000
- 全新安装时，启动日志会打印一次性管理员密码，并写入 `data/initial_admin_password.txt`。该文件权限为仅当前用户可读，且已被 gitignore
- 用户名是 `admin`。用该一次性密码登录后，必须立刻修改密码，然后删除密码文件
- 修改完成或管理员被删除之后，重启不会再创建账号，也不会再写回旧的公开密码

### 5. 配置 JWT 密钥（`SECRET_KEY`）

签名密钥不再有公开的默认值。

| 环境 | 行为 |
|------|------|
| 本地 / 开发（`DEBUG=true`，且 `APP_ENV` 不是 `production`） | 未设置 `SECRET_KEY` 时，首次启动在 `data/.secret_key` 生成随机密钥，之后每次启动复用。不写入 `.env` |
| 生产（`DEBUG=false` 或 `APP_ENV=production`） | 必须自行设置 `SECRET_KEY`，否则进程拒绝启动 |
| 任意环境 | 历史默认值 `tender-secret-key-change-in-production` 视为未设置，不会用来签名 |

生成一个密钥：

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

生产环境写入 `.env`（不要提交这个文件）：

```env
DEBUG=false
APP_ENV=production
SECRET_KEY=上一步生成的字符串
```

已有部署在切换到生产模式之前必须设置 `SECRET_KEY`。用旧默认密钥签发的登录态会失效，重新登录即可。若管理员密码仍是以前随版本写入的 `admin123`，还可以用它登录一次，登录后必须修改；已经改过的密码不会被重置，删除用户也不会自动加回 `admin`。

---

## 🖥️ 部署方式

在 macOS、Linux 或 Windows 上用 Python 虚拟环境和已构建的 `web/dist` 运行，无需 Docker。仓库没有 GitHub Release，也没有可下载的 `Tender.exe`。只有本机已经生成 `web/dist` 时，才可以用 `Tender.spec` 打包装包。

备份见 `docs/ops/backup-and-recovery.md`。先停进程，再把 SQLite、Chroma、`data/library/`、`.env` 和 `data/.secret_key` 作为同一套拷走。`.env` 和 `data/.secret_key` 是机密。

---

## 🏭 适用场景

- 管道管件行业投标（中石油/中石化/中海油）
- 体育器材制造商
- 机床附件供应商
- 其他制造业中小型企业

---

## 📂 项目结构

```
Tender/
├── server/              # FastAPI 后端
│   ├── api/             # API 路由
│   ├── core/            # 核心服务（RAG/嵌入/分词/质检）
│   ├── data/            # 内置数据（词汇表）
│   └── db/              # 数据库（SQLite + ChromaDB）
├── web/                 # Vue3 前端
│   └── src/
│       ├── pages/       # 页面
│       ├── components/  # 组件
│       └── api/         # API 调用层
├── docs/                # 使用说明文档
└── requirements.txt     # Python 依赖
```

---

## 🧩 技术栈

| 层级 | 选型 | 说明 |
|------|------|------|
| 后端 | Python FastAPI | 高性能异步 API |
| 前端 | Vue3 + Element Plus | 线性浅色主题 |
| 向量库 | ChromaDB | 本地嵌入式向量检索 |
| AI 模型 | DeepSeek / Ollama / 通义 | 按需配置，支持本地 |
| 数据库 | SQLite | 零运维，轻量 |

---

## 📄 License

[MIT](./LICENSE)
