# 六、技术架构

> **阅读说明（2026-11-07）**
>
> 本页保留 2026-05-15 的 MVP 记录，下面的图和表仍是当时的写法。图中只画了云端模型 API，部署写成 PyInstaller 单文件。对照当前代码：默认 LLM 与 Embedding 是本机 Ollama（`LLM_PROVIDER` / `EMBED_PROVIDER`），也可以选用 DeepSeek、通义、OpenAI、MiniMax；切片正文同时在 SQLite `chunks` 和 ChromaDB，Chroma 是检索用的向量副本。
>
> 下一步的结构设计见 [目标架构](/target-architecture)。备份、单进程和相对路径 `/api` 等运行差距见 [生产就绪评估](/production-readiness)。

## 系统架构图

```
┌─────────────────────────────────────┐
│          Tender 客户端             │
│  浏览器 (Vue3 SPA)                   │
└─────────────────────────────────────┘
                │ HTTP
                ↓
┌─────────────────────────────────────┐
│          FastAPI 后端服务            │
│  Python + SQLite + ChromaDB          │
│  ├── 认证 (JWT)                      │
│  ├── RAG 检索引擎                   │
│  ├── 标书解析 / 生成                │
│  ├── 废标检测                       │
│  └── 管理后台                       │
└─────────────────────────────────────┘
                │ HTTPS
                ↓
┌─────────────────────────────────────┐
│       AI 模型 API (DeepSeek 等)      │
└─────────────────────────────────────┘
```

## 数据存储

| 存储 | 内容 |
|------|------|
| **SQLite** | 元数据（用户、文档记录、配置等） |
| **ChromaDB** | 向量数据（文档切片） |
| **文件系统** | `data/uploads/` 原始文件，`data/generated/` 生成文件 |

## 关键技术栈

| 层级 | 技术 |
|------|------|
| 前端 | Vue3 + Vite + Element Plus |
| 后端 | Python FastAPI |
| 数据库 | SQLite（结构化数据） + ChromaDB（向量） |
| AI | DeepSeek API（LLM）+ 通义 Embedding |
| 部署 | PyInstaller 单文件打包 |

---

## 版本信息

- 当前版本：v1.0 MVP
- 最后更新：2026-05-15
- 产品主页：https://github.com/cnchaoge/tender