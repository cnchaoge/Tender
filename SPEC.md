# ClawOS X 产品规格说明书

> 版本：v1.0 MVP
> 更新：2026-05-06

---

## 一、产品定位

**ClawOS X** — 面向制造业中小企业的 AI 文档助手本地部署版。

**目标客户**：三四线城市制造业中小企业（管道管件、体育器材、机床附件），50-200 人规模。

**核心场景**：
- 投标标书制作（差异化卖点）
- 质检报告生成
- 设备台账管理
- 产品技术文档

**核心卖点**：本地部署 + 开箱即用 + 行业垂直。

---

## 二、技术架构

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

## 三、技术选型

| 层级 | 选型 | 说明 |
|------|------|------|
| 后端 | Python FastAPI | 轻量高性能 |
| 数据库 | SQLite | 零运维 |
| 向量库 | ChromaDB 嵌入式 | Python 原生，零运维 |
| 前端 | Vue3 + Element Plus | 管理后台 |
| 打包 | PyInstaller | 单文件 exe |
| AI 模型 | DeepSeek / 通义 / 智谱 | 按需配置 |
| Embedding | DeepSeek Embedding / BGE | 按需配置 |

---

## 四、部署方式

- **Windows 单文件部署**（PyInstaller）
- 双击运行，无需 Docker
- 数据全部存在本地
- 安装流程：双击 → 设置密码 → 配置 API Key → 开始使用

---

## 五、数据架构

### 5.1 存储结构

```
data/
  uploads/        # 原始上传文件
  chunks/         # 切片缓存
  generated/      # AI 生成的文件
```

### 5.2 SQLite 表

| 表名 | 用途 |
|------|------|
| users | 用户管理 |
| configs | 系统配置 |
| documents | 文档元数据 |
| chunks | 切片记录 |
| audit_logs | 操作日志 |

### 5.3 ChromaDB Collection

```
collection: documents
  - id: 切片ID
  - embedding: 向量
  - metadata: {doc_id, filename, page, chunk_index, text}
```

---

## 六、功能范围

### MVP 做（v1.0）

- [ ] 知识库：上传 / 解析 / 切片 / 检索
- [ ] AI 问答：基于文档回答，标注来源
- [ ] 标书生成：招标文件解析 → 素材匹配 → Word 导出
- [ ] 飞书集成：机器人收消息 / 回复
- [ ] 管理后台：登录 / 用户 / 配置
- [ ] Windows 单文件部署

### MVP 不做（v1.5+）

- [ ] 多租户隔离
- [ ] 钉钉 / 企微渠道
- [ ] 本地 LLM 推理
- [ ] OCR 图片文字识别
- [ ] Excel 台账自动化
- [ ] 用量计费

---

## 七、项目结构

```
clawosx/
├── server/                 # Python 后端
│   ├── main.py            # FastAPI 入口
│   ├── api/               # API 路由
│   │   ├── auth.py       # 登录认证
│   │   ├── rag.py        # RAG 核心
│   │   ├── docs.py       # 文档生成
│   │   ├── kb.py         # 知识库管理
│   │   └── feishu.py     # 飞书集成
│   ├── core/              # 核心逻辑
│   │   ├── parser/       # 文档解析
│   │   ├── chunker/      # 切片策略
│   │   ├── embedder/     # Embedding
│   │   ├── retriever/    # 检索
│   │   └── generator/    # 生成
│   ├── db/               # 数据库
│   │   ├── sqlite.py     # SQLite 元数据
│   │   └── chromadb.py   # ChromaDB 向量
│   └── tools/            # Agent 工具集
├── web/                   # Vue3 前端
├── scripts/               # 脚本
├── data/                  # 数据目录（运行时生成）
├── requirements.txt
├── PyInstaller.spec
└── README.md
```

---

## 八、API 设计

### 8.1 认证

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | /api/auth/login | 登录，返回 JWT |
| POST | /api/auth/logout | 登出 |
| GET | /api/auth/me | 当前用户信息 |

### 8.2 知识库

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | /api/kb/documents | 文档列表 |
| POST | /api/kb/documents | 上传文档 |
| DELETE | /api/kb/documents/{id} | 删除文档 |
| GET | /api/kb/documents/{id}/chunks | 查看切片 |

### 8.3 RAG 问答

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | /api/rag/query | 提问，返回回答 |
| POST | /api/rag/chat | 多轮对话 |

### 8.4 标书生成

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | /api/bid/parse | 解析招标文件 |
| POST | /api/bid/generate | 生成标书 |
| GET | /api/bid/download/{id} | 下载标书文件 |

### 8.5 飞书

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | /api/feishu/webhook | 接收飞书消息 |
| GET | /api/feishu/config | 飞书配置状态 |

### 8.6 管理后台

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | /api/admin/users | 用户列表 |
| POST | /api/admin/users | 添加用户 |
| PUT | /api/admin/users/{id} | 编辑用户 |
| DELETE | /api/admin/users/{id} | 删除用户 |
| GET | /api/admin/stats | 用量统计 |
| PUT | /api/admin/config | 更新配置 |

---

## 九、飞书机器人集成

- 机器人通过长连接接收消息
- AI 处理后通过发送消息 API 回复
- 支持：文本、图片、文件
- 文件上传走飞书上传 API

---

## 十、质量标准

- 文档上传到返回切片结果 < 10 秒（PDF < 5MB）
- 问答响应 < 5 秒（不含 LLM 延迟）
- 飞书消息响应 < 5 秒
- 所有 API 返回统一格式 `{code, message, data}`
