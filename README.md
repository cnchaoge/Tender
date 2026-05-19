# ⚡ Tender

**制造业投标标书 AI 助手 — 本地部署，开箱即用**

[![Stars](https://img.shields.io/github/stars/cnchaoge/tender?style=flat-square)](https://github.com/cnchaoge/tender)
[![License](https://img.shields.io/github/license/cnchaoge/tender?style=flat-square)](./LICENSE)

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

创建 `.env` 文件：

```env
DEEPSEEK_API_KEY=your_api_key
LLM_PROVIDER=deepseek
EMBED_PROVIDER=deepseek
SECRET_KEY=your-secret-key
```

### 3. 启动服务

```bash
cd server
uvicorn main:app --reload --port 8000
```

### 4. 打开浏览器

- 控制台：http://localhost:8000/web
- 默认账号：`admin` / `admin123`

---

## 🖥️ 部署方式

支持 **Windows** 和 **Linux** 双系统，无需 Docker。

离线网络环境也可交付，依赖可打包本地安装。

---

## 🏭 适用场景

- 管道管件行业投标
- 体育器材制造商
- 机床附件供应商
- 其他制造业中小型企业

---

## 📂 项目结构

```
Tender/
├── server/              # FastAPI 后端
│   ├── api/             # API 路由（管理/知识库/标书）
│   ├── core/            # 核心配置
│   └── services/        # AI 服务层（RAG/标书生成）
├── web/                 # Vue3 前端
│   └── src/
│       ├── pages/       # 页面（登录/仪表盘/知识库/问答/标书）
│       └── assets/      # 样式（Linear Light 主题）
├── docs/                # 文档
└── requirements.txt     # Python 依赖
```

---

## 🧩 技术栈

| 层级 | 选型 | 说明 |
|------|------|------|
| 后端 | Python FastAPI | 高性能异步 API |
| 前端 | Vue3 + Element Plus | 线性浅色主题 |
| 向量库 | ChromaDB | 本地嵌入式向量检索 |
| AI 模型 | DeepSeek / 通义 / 智谱 | 按需配置 |
| 数据库 | SQLite | 零运维，轻量 |
| 部署 | 双系统原生运行 | 无需 Docker |

---

## 🔮 后续方向

- 📊 质检报告自动生成
- 🔧 设备台账管理系统
- 📱 移动端支持
- 🤖 更多 AI 模型适配

---

## 📄 License

[MIT](./LICENSE)
