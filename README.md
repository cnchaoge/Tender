# ClawOS X

> 面向制造业中小企业的 AI 文档助手 — 本地部署，开箱即用

---

## 产品定位

解决制造业中小企业（管道管件、体育器材、机床附件等）的文档处理痛点：

- **投标标书制作**（差异化卖点）
- 质检报告生成
- 设备台账管理
- 产品技术文档

**核心卖点**：本地部署 + 开箱即用 + 行业垂直。

---

## 技术架构

```
用户（浏览器 / 飞书）
       ↓
┌─────────────────────┐
│   ClawOS X 服务端     │
│   (Python FastAPI)   │
├─────────────────────┤
│  管理后台 (Vue3)     │
│  知识库管理          │
│  用户/配置管理       │
├─────────────────────┤
│  AI 核心            │
│  ├─ RAG 检索引擎    │
│  ├─ 文档生成器      │
│  └─ Agent 工具集    │
├─────────────────────┤
│  数据层             │
│  ├─ SQLite (元数据) │
│  └─ ChromaDB (向量) │
└─────────────────────┘
       ↓
  AI 模型 API
(DeepSeek / 通义 / 智谱)
```

---

## 技术选型

| 层级 | 选型 | 说明 |
|------|------|------|
| 后端 | Python FastAPI | 轻量高性能 |
| 数据库 | SQLite | 零运维 |
| 向量库 | ChromaDB 嵌入式 | Python 原生，零运维 |
| 前端 | Vue3 + Element Plus | 管理后台 |
| 打包 | PyInstaller | 单文件 exe |
| AI 模型 | DeepSeek / 通义 / 智谱 | 按需配置 |

---

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 配置

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

### 4. 访问

- API：http://localhost:8000
- 管理后台：http://localhost:8000/web
- 默认账号：admin / admin123

---

## 部署方式

- **Windows 单文件部署**（PyInstaller）
- 双击运行，无需 Docker
- 数据全部存在本地

---

## 项目地址

https://github.com/cnchaoge/clawosx
