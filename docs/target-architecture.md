# Tender 目标架构

设计日期：2026-11-07。对照的是仓库里正在运行的本地单体（FastAPI + Vue 3 + Element Plus + SQLite + ChromaDB + JWT）。本文只定结构和迁移顺序，不改产品代码。

运维差距仍以 [生产就绪评估](/production-readiness) 为准。那里的 P0（备份、误删原文件、启动方式、CI）暂停，不在本文的实施范围里。下面的数据布局会让那些加固做得动，但不代替那份评估。

读者是后续改代码的人，以及要拍板「项目归谁」的负责人。开放项集中在文末。

## 目标

在一台 Mac、一个小团队能看懂的前提下，把现有能力收成一条清楚的业务链：

1. **投标项目是聚合根。** 一次投标的招标文件、选用的资料、解析结果、目录、生成版本、报价和检查清单，都挂在同一个项目上。刷新页面还能回到这次投标。
2. **长工作是作业。** 解析、入库、生成、导出、重建索引走同一套进程内队列：排队、进度、取消、结果。浏览器只负责发起和观看。
3. **正文只有一份原件，向量索引可以推倒重建。** SQLite 保存文件副本、抽出的文本和切片。Chroma 只是某一套 Embedding 模型的派生索引，并记下模型身份。
4. **大文件拆成领域模块。** HTTP 层只做鉴权、校验和状态码。`server/api/bid.py`（约 1800 行）和 `web/src/pages/BidGenerate.vue`（约 2900 行）里的规则搬到领域模块，路由和页面地址保持不变。
5. **模型和 Embedding 在作业创建时抄一份快照。** 保存设置后，下一笔作业用新配置。作业进行中不换供应商。本地模型和云端模型的数据出境写在设置页和作业记录上。
6. **交付形态定成「本机一个进程 + 浏览器」。** 页面和接口同一来源，请求使用相对路径 `/api`。SQLite 和 Chroma 只由这一个进程打开。

## 非目标

- 微服务、Kubernetes、独立消息队列、把 Postgres 当成必选项。SQLite 继续是业务库。
- 多机同时写同一份 `data/`。一台机器上只跑一个服务进程，不加 `uvicorn --workers`。
- 改写已有的标书草稿流水线（`server/core/bidgen/pipeline.py` 的提示词、质检和最多重写一轮）。它迁入领域模块，行为先保持。
- 换掉 Vue 3、Element Plus，或推倒现有管理界面。
- 扫描件 OCR、多租户 SaaS、令牌吊销。扫描件今天就不能解析；令牌吊销记在生产就绪评估的 P1。
- 在本设计的第一批改动里实现 P0 备份脚本、launchd 或 CI 修复。

## 现状与目标

| | 现在 | 目标 |
|--|------|------|
| 业务对象 | 没有项目表。标书版本和报价各存一份自由文本 `project_name`。检查清单挂在 `bid_version_id`。解析结果停在浏览器里，直到 SSE 结束才写入 `bid_versions.parse_result_json` | 项目保存这次投标的解析、目录、素材选择和清单。版本、报价、清单用 `project_id` 关联 |
| 招标文件 | 走知识库上传，进入全局 `documents`，并开始向量化。解析接口要的是服务端路径 `file_path`（`BidParseReq`）。上传响应只有 `doc_id`，生成页仍提交 `uploadResp.data.file_path` | 招标文件属于该项目，按文档 id 解析。调用方不传磁盘路径 |
| 资料库 | 全局一份。上传按文件名去重。文件夹扫描把原路径写入 `file_path`，删除时 `os.remove` 该路径 | 受管副本放在 `data/library/`。按内容哈希识别同一文件。删除只删副本、切片和向量 |
| 长任务 | 入库：进程内最多 2 个线程，状态写在文档行上，能在重启后续跑，没有进度百分比和取消。解析、规划、生成、匹配、废标、查重、报价：占着当前请求。生成的进度只存在 SSE 连接上 | 一张 `jobs` 表。页面断开后作业继续。进度可查询，取消是协作式的。SSE 改为回放已写下的事件 |
| 向量 | 集合名固定 `documents`，不记录模型。切片正文在 SQLite 和 Chroma 各一份。换 Embedding 后新旧向量混在一起。术语表向量失败仍把文档标成可用 | 切片正文以 SQLite 为准。Chroma 记下 Embedding 身份。身份不一致时拒绝检索并提示重建。术语表走同一套入库，失败就是失败 |
| 配置 | `llm.py`、`embedder.py` 在导入时执行 `settings = get_settings()`。设置写入 `.env` 并清掉缓存后，这些模块仍读导入时的那份 | 创建作业时读取当前设置，写入 `jobs.runtime_json`，执行时只用这份快照 |
| 代码形状 | 路由文件里含 Word 排版、解析、规划、SSE、推荐、版本、模板、废标和查重。生成页把上传、解析编辑、素材、目录、流式生成、质检和版本历史放在一个组件里 | 领域模块负责规则。`api/` 和页面壳只做适配。工作台、生成、解析、报价、问答读同一份项目状态 |
| 运行 | 默认 `0.0.0.0`。生产构建把接口写成 `http://localhost:8000`（`web/src/api/index.js`）。开发服务带 `--reload`。注释已写明不能多进程同时写 Chroma 和 SQLite（`server/workers/executor.py`） | 支持的用法是绑定本机的单个进程，浏览器请求相对 `/api`。开发时的 Vite 代理只是开发便利 |

已经值得留下的部分：登录门槛、标书草稿流水线、知识库的进程内线程池和失败清理、版本 diff、模板库、废标规则库、工作台和设置页的界面。迁移是把它们接到项目和作业上，不是换一套产品。

## 运行形态

```
浏览器  Vue 3 SPA
   │  相对路径 /api ，Cookie 之外仍用现有 JWT
   ▼
一个进程  uvicorn（不要 --workers，正式启动不要 --reload）
   ├── HTTP 适配层
   ├── 领域模块
   ├── 作业运行器（进程内线程池）
   ├── SQLite   data/tender.db          业务原件与作业
   └── Chroma   data/chromadb           可丢弃的向量索引
   │
   ▼
模型调用
   本地：Ollama、BGE、M3E     文本留在这台机器
   云端：DeepSeek、通义、OpenAI、MiniMax
         只发送该次提示词和必要正文，不发送整个 data 目录
```

生产包由这个进程同时提供 `/api`、`web/dist` 和 `/docs`。开发时 Vite 在 5173 把 `/api` 代理到该进程。PyInstaller 若继续做，只是把同一个进程打成可执行文件，不另设一套部署结构。

## 领域模型

```
User
  │ created_by（记是谁做的；能否看见别人的项目见开放决定 1）
  ▼
Project  一次投标
  ├── ProjectDocument ── Document     角色：tender 招标文件 / material 选用资料
  ├── ParseSnapshot                   解析结果，可保留多次
  ├── outline                         目录，存在项目上
  ├── BidVersion                      一次生成的正文、质检摘要、Word
  ├── PriceAnalysis                   报价
  ├── ChecklistItem                   材料清单，挂在项目上
  └── Job                             解析、规划、生成、导出

Document  资料库或项目文件
  └── Chunk                           切片正文（检索的原文）

IndexBuild                            当前生效的 Embedding 身份
  └── Chroma 集合                     由 Chunk 重建，不单独当业务数据

Job 也可只挂 Document（入库、重建索引），没有项目。

全局参考数据，不放进项目：
  BidTemplate、disqualify_rules、violation_cases、users、configs
```

### 项目 Project

一次投标的工作区。字段包括：名称、状态（`draft` / `active` / `archived`）、采购人、工期或截止日期、`created_by`、时间戳、当前采用的 `parse_id`。

名称可以改。关联用数字 id，不再用 `project_name` 字符串把版本和报价对在一起。生成页上现在能改的项目名和工期，改的是项目记录，而不是只改浏览器里的 `parseResult`。

工作台的「最近标书」改为最近项目，链到该项目的生成页。今天每一行都链到没有版本号的 `/bid`。

### 文档 Document 与切片 Chunk

文档是受管内容：

| 字段 | 作用 |
|------|------|
| `scope` | `library` 公司资料，可被多个项目选用；`project` 招标文件，默认不进全局问答；`system` 内置术语表 |
| `storage` | `managed` 副本在 `data/library/{id}/`；遗留行在迁完之前可以是 `external` |
| `content_sha256` | 同一字节序列不重复入库。取代「同名文件直接返回旧记录」 |
| `status` | 最近一次入库作业的投影：`pending` / `processing` / `ready` / `failed` |

抽出的全文放在 `data/library/{id}/extracted.txt`。切片表继续放正文，供预览和索引重建。重新切片优先读这份抽出的文本，不必再次解析 PDF。

项目和资料是引用关系 `project_documents(project_id, document_id, role)`。一份历史标书可以被多个项目选用。招标文件用 `role=tender`，不复制进公司资料库。生成当时把选用的文档 id 抄进版本，避免日后资料库删除改写历史。

内置术语表仍是一条 `scope=system` 的文档，走入库作业。向量失败时状态为 `failed`，下次启动再试。今天 `server/core/glossary.py` 在嵌入失败后仍提交，并把状态留成可用。

### 解析快照与版本

`ParseSnapshot` 保存招标文件 id、解析 JSON（项目名、工期、资格、评分、体检）、正文摘录、对应作业。用户在页面上的修改写回当前快照。再次解析新增一条快照，不覆盖旧的。

`BidVersion` 属于项目，并记下：所用 `parse_id`、策略、目录、素材 id 列表、Markdown 正文、质检 / 废标 / 查重摘要、Word 的相对路径、作业 id、当时的模型供应商和是否出境。版本状态：`draft`（生成中，按章节把已写出的正文落盘）、`ready`、`cancelled`、`interrupted`。

报价沿用现有公式和策略字段，补上 `project_id`。清单条目挂在项目上，并记住生成它的 `source_version_id`。换一版标书时，已经勾过的准备状态还在。

模板仍是全局的。选用模板只影响该项目的目录，不把模板本身放进项目。

### 作业 Job

| 字段 | 作用 |
|------|------|
| `type` | `document.ingest`、`document.reindex`、`project.parse`、`project.plan`、`bid.generate`、`bid.export` |
| `status` | `queued`、`running`、`succeeded`、`failed`、`cancelled`、`interrupted` |
| `progress`、`message` | 0–100 和一句给人看的说明 |
| `payload_json`、`result_json` | 输入与结果（版本 id、文档 id 或错误摘要） |
| `cancel_requested` | 运行器在下一处安全点停下 |
| `runtime_json` | 供应商、模型名、Embedding 身份、`egress`（`local` 或 `cloud`） |
| `idempotency_key` | 同项目、同解析、同素材、同策略已有未完成生成时，返回那一笔作业 |

`job_events(job_id, seq, kind, payload_json)` 按顺序记下阶段和增量，供刷新后的 SSE 回放。事件是作业的日志，作业本身在表里。

```
queued ──► running ──► succeeded
                 ├──► failed
                 ├──► cancelled      用户取消，在安全点生效
                 └──► interrupted    进程退出时仍在 running

排队中的作业也可以直接 cancelled。
进程再次启动：入库类 interrupted / running 回到 queued，并清掉半成品切片。
生成类保持 interrupted，已写入的草稿正文保留。
```

短请求继续同步返回：登录、列表、下载、改清单勾选、读版本 diff。它们不进队列。

### 用户 User

沿用 `users`：用户名、角色 `admin` / `user`、是否必须改密。JWT 仍由现有登录签发。本文不改角色种类。`created_by` 先表示「谁创建的」，过滤规则等负责人确认开放决定 1。

### 索引 IndexBuild

一条记录描述一套向量：`embed_provider`、`embed_model`、维度、状态（`building` / `active` / `retired` / `failed`）。同一时间只有一条 `active`。Chroma 集合的元数据写上这条记录的 id。检索时当前 Embedding 身份必须和 `active` 一致，否则接口返回「索引与当前模型不一致」，页面提供重建。`mock` 的向量是随机的，不能标成可供检索的 `active` 索引。

## 生命周期

### 知识库入库

1. 客户端上传字节，或选择允许的目录做导入。接口把每个文件复制到 `data/library/{id}/original.*`，写入 `documents`（`pending`）和一条 `document.ingest` 作业，马上返回文档 id 和作业 id。
2. 进程内运行器领取作业，标成 `running`。解析与嵌入仍离开 asyncio 事件循环，池大小保持今天的 2。
3. 解析原件，写下 `extracted.txt`，再切块。SQLite 在一个事务里替换该文档的 `chunks`。
4. 用作业快照里的 Embedding 把切片写入当前有效集合。进度大致为：排队 0、解析 20、切块 40、嵌入 70、完成 100。嵌入按批更新进度。
5. 成功则文档 `ready`。失败则删掉该文档的切片和向量，文档与作业都是 `failed`。这和今天 `cleanup_partial_document` 的方向一致。
6. 取消在两个批次之间查看 `cancel_requested`，清掉半成品，状态 `cancelled`。
7. 重启时未完成的入库作业重新排队。原件还在，就可以再跑。

文件夹导入是「复制进资料库 + 每个文件一笔作业」。库里不把用户磁盘上的原始路径当作唯一副本。删除文档只删除 `data/library/{id}/`、切片和向量。

超过 `MAX_FILE_SIZE`（现有配置，默认 50MB）的上传在写盘时停止，并删掉半截文件。

### 标书生成

今天的主路径是：知识库上传 → `POST /api/bid/parse` 阻塞调用模型 → 结果留在 `BidGenerate.vue` 的 ref 里 → 用户改解析、选素材、可选规划 → `POST /api/bid/generate/stream` 在一条 SSE 里做废标预检、生成、章节事件、再检、质检、可能的重写、格式、查重、写 Word、保存版本。非流式 `POST /api/bid/generate` 还在，页面没有调用它。连接断开时，服务端没有一笔可查询的作业。

目标顺序：

1. 在工作台创建项目，或打开已有项目。生成、解析、报价都带这个 `project_id`。
2. 招标文件作为 `scope=project` 的文档上传。解析不等待整份向量化完成。
3. `project.parse` 作业读取受管原件，用作业快照调用模型，写入一条 `ParseSnapshot`，并把建议的项目名和工期填到项目上（用户已改过的字段不被覆盖）。
4. 用户确认解析、从资料库勾选素材、选定模板和策略。`project.plan` 作业把目录写到项目上。指定模板时仍可直接采用模板章节，与今天 `POST /api/bid/plan` 的短路一致。
5. `bid.generate` 作业开始时就插入 `status=draft` 的版本。运行步骤与现在的 SSE 阶段对应，但每步先写入 `job_events`：
   - 生成前废标预检。必废标则作业 `failed`，不调用长生成。
   - 只在勾选的资料（以及该项目招标文件的切片，若已入库）里检索。沿用 `server/core/bidgen/pipeline.py`。
   - 模型增量写入事件；每完成一章，把已累积的 Markdown 更新到草稿版本。
   - 质检不通过则重写一轮，仍是现有规则。
   - 格式、查重、废标复检的摘要写入版本。
   - `bid.export` 可以是生成的最后一步：Word 写到 `data/generated/{version_id}.docx`。
   - 版本改为 `ready`，作业 `succeeded`，结果里带 `version_id`。
6. 页面用 `GET /api/jobs/{id}/events` 订阅。刷新后从已有事件继续显示。作业不绑在这条 HTTP 连接上，浏览器关掉后生成继续。
7. 取消在「下一次模型调用之前」或章节边界生效。草稿改为 `cancelled`，已写出的正文留下。
8. 下载只打开 `data/generated/` 下的该版本文件。

同一项目若已有相同解析、素材和策略的未完成生成，接口返回已有作业，避免连点启动两份。

报价页读取该项目当前解析快照里的评分办法。检查清单针对项目生成，来源版本记在条目上。智能问答默认只检索 `scope=library` 且状态 `ready` 的文档；从项目里打开问答时，可以额外带上该项目的招标文件和已选素材。

## 模块地图

仍是一个 Python 包、一个 Vue 应用。下面的目录是落点，阶段 1 开始搬，阶段 4 之后路由文件应当变薄。

### 后端

```
server/
├── api/                      鉴权、参数、HTTP 状态码
│   ├── auth.py
│   ├── projects.py           项目、招标文件、素材引用
│   ├── documents.py          资料库上传、列表、删除
│   ├── jobs.py               创建、查询、取消、事件流
│   ├── generation.py         由现有 /api/bid 收成适配层
│   ├── pricing.py
│   ├── checklist.py
│   ├── rag.py
│   └── admin.py
├── domain/
│   ├── projects/
│   ├── documents/            受管副本、哈希、入库步骤
│   ├── jobs/                 状态机、幂等、启动时对账
│   ├── generation/
│   │   ├── parse.py          今天 bid.py 里的解析与字段补全
│   │   ├── outline.py        规划；模板命中时直接返回章节
│   │   ├── draft.py          现有 BidDraftPipeline
│   │   ├── versions.py
│   │   └── run.py            把废标、质检、查重、导出串成一笔作业
│   ├── retrieval/            今天的 retriever、章节推荐、历史标书拆节
│   ├── review/               废标、查重、格式、匹配度
│   ├── pricing/
│   ├── checklist/
│   └── export/docx.py        今天 bid.py 前半的 Word 排版
├── infra/
│   ├── sqlite.py
│   ├── chroma_index.py       只负责派生索引
│   ├── files.py              路径限制在 data/library 与 data/generated
│   ├── llm.py                按快照构造，不在导入时绑定配置
│   ├── embedder.py
│   └── config.py
└── workers/
    └── runner.py             进程内线程池领取 jobs
```

`server/api/bid.py` 在迁移期间保留旧 URL，内部调用领域模块。旧 URL 包括 `/api/bid/parse`、`/plan`、`/generate`、`/generate/stream`、版本、模板、推荐、废标和查重。至少保留一个版本周期，等页面改调用作业接口后再删。

`server/workers/executor.py` 的约束继续有效：工作线程和 API 同进程，避免再起一个解释器去打开 Chroma 和 SQLite。

### 前端

路由地址保持不变：`/dashboard`、`/bid`、`/bid-analyze`、`/price`、`/kb`、`/chat`、`/settings`。页面变成组合层。

```
web/src/
├── pages/                    路由壳，从 query 读取 project
├── features/
│   ├── workbench/            项目列表与最近作业
│   ├── projects/             创建、归档、当前项目
│   ├── generation/
│   │   ├── TenderUpload.vue
│   │   ├── ParseEditor.vue
│   │   ├── MaterialPicker.vue
│   │   ├── OutlinePlan.vue
│   │   ├── GeneratePanel.vue
│   │   └── VersionHistory.vue
│   ├── analyze/              历史标书拆节，结果仍是资料库文档上的数据
│   ├── pricing/
│   ├── library/
│   ├── chat/
│   ├── settings/             供应商旁显示本地 / 云端
│   └── jobs/                 进度、取消、重连后回放
├── stores/
│   ├── auth.js               现有
│   └── workspace.js          当前项目、资料库列表、进行中的作业
└── api/                      相对路径 /api
```

`BidGenerate.vue` 的上传、解析编辑、素材、目录、流式输出、质检和版本历史拆进 `features/generation/`。拆完之后页面壳负责按项目把这些块排起来。

工作台、生成页和报价页通过 `workspace` 读取同一项目。生成页写回的解析和素材，报价页打开时能看到。资料库列表只在 `workspace` 里拉一次，生成页的素材选择和知识库页用同一份数据。

## 数据布局

### SQLite

业务数据仍在 `data/tender.db`。用一张 `schema_version` 做加法迁移（缺列就 `ALTER`），已有库能直接打开。新的外键在应用层保证，旧行的新列允许为空。

在现有表上追加，而不是换库：

| 表 | 要点 |
|----|------|
| `projects` | 新表。名称、状态、采购人、工期、`created_by`、当前 `parse_id` |
| `documents` | 已有。追加 `scope`、`storage`、`content_sha256`、`extracted_relpath`。`file_path` 改为相对 `data/` 的路径 |
| `chunks` | 已有，继续是正文来源 |
| `project_documents` | 新表。`project_id`、`document_id`、`role` |
| `parse_snapshots` | 新表。`project_id`、`document_id`、`result_json`、`job_id` |
| `bid_versions` | 已有。追加 `project_id`、`parse_id`、`status`、`outline_json`、`runtime_json`、`job_id`。正文仍在 `bid_content` |
| `price_analyses` | 已有。追加 `project_id` |
| `checklist_items` | 已有。追加 `project_id`、`source_version_id`。保留 `bid_version_id` 直到调用方改完 |
| `jobs`、`job_events` | 新表。见上一节 |
| `index_builds` | 新表。当前 Embedding 身份 |
| `bid_templates`、`users`、`violation_cases`、`disqualify_rules`、`audit_logs` | 保持。长作业的「谁在何时生成」用作业行回答；`audit_logs` 仍留给登录、删除和改配置，那部分见生产就绪评估 |

`project_name` 列先留着，给旧页面和回填用。新代码读写 `project_id`。

### 文件

```
data/
├── tender.db
├── library/{document_id}/original.*      受管原件
├── library/{document_id}/extracted.txt   抽出的文本
├── generated/{version_id}.docx           导出
├── chromadb/                             派生索引，可整目录重建
├── .secret_key                           现有
└── initial_admin_password.txt            现有，用后删除
```

今天的 `data/uploads/` 和按随机文件名放的 `data/generated/bid_*.docx` 视为遗留。迁移把还能找到的上传文件复制进 `library/`，版本文件改记相对路径。复制完成前，旧路径仍可读。

Chroma 集合元数据至少包含 `index_build_id`、供应商、模型和维度。向量 id 维持 `doc{id}_chunk{index}` 这种可按文档删除的形式。重建索引只读 SQLite 切片，不重新解析 PDF：嵌入写入新集合，抽查后再把 `index_builds.active` 指过去，旧集合标 `retired`。

备份时需要同一时刻的 `tender.db`、`library/`、`generated/` 和 `chromadb/`。只拷数据库会丢掉原件；只拷 Chroma 无法恢复正文。具体脚本仍属于生产就绪评估的 P0，这里只固定「哪些目录是一套」。

### 配置快照与出境

创建作业时调用 `get_settings()`，把结果抄进 `runtime_json`：

| 供应商 | `egress` |
|--------|----------|
| `ollama`、`bge`、`m3e` | `local`。文本留在本机 |
| `deepseek`、`dashscope`、`openai`、`minimax` | `cloud`。提示词和该次需要的正文发往该服务商。通义 Embedding 同样是 cloud |
| `mock` | 只用于开发。不建立可供检索的有效索引 |

作业执行过程只读自己的快照。用户在设置里改了供应商，已经在跑的生成继续用原来的模型，下一笔作业再用新的。封面用的 `COMPANY_NAME` 在导出时抄进版本，避免以后改设置改写旧标书封面。

设置页在云端供应商旁边写明正文会离开本机。这个说明是本架构的一部分；是否必须先勾选确认，见开放决定 6。

## 迁移阶段

五个阶段都单独可合并。每一阶段结束时，现有测试仍然针对当时的行为。不安排一次换库或停机重写。开始改 `data/` 布局之前，先有生产就绪评估里的那份成套备份；那份备份不在本设计的实施清单里，但是阶段 2 的前提。

### 阶段 1 — 划出模块，行为不变

- 从 `server/api/bid.py` 挪出 Word 排版、解析补全、版本读写、推荐和查重调用。路由的 URL、请求体和响应保持原样，文件变成转发。
- `BidDraftPipeline` 以领域模块的身份被两条生成路径调用，提示词和重写次数不变。
- `BidGenerate.vue` 按功能拆成子组件，路由仍是 `/bid`，数据仍先留在页面状态里。
- 新模块在函数内部读取 `get_settings()`，不再增加导入期绑定。旧模块可以暂时保持原样，直到阶段 5 删除。
- 不改表。

完成的标志：页面流程与接口形状和拆分前一致，pytest 通过。

### 阶段 2 — 受管原件与可重建索引

- 加法列：`content_sha256`、`scope`、`storage`、抽出文本的相对路径，以及 `index_builds`。
- 新上传写入 `data/library/`。新文件按哈希去重。旧的「同名即同一份」只对尚未回填的行保留。
- 文件夹导入改为复制。删除只删除受管副本。仍指向外部路径的旧行标 `storage=external`，读得到就继续用，删除时不删除该外部路径。
- 管理动作「重建索引」用现有线程池从 `chunks` 重嵌，写上 Embedding 身份。检索发现身份不一致时给出明确错误。
- 术语表嵌入失败则文档为 `failed`，启动时重试。
- 这一阶段还没有统一作业表。入库仍用现有 `schedule_document`。

完成的标志：换 Embedding 模型后，旧结果不会和新向量混在一次检索里；新上传的删除不会碰到资料库以外的路径。

### 阶段 3 — 投标项目

- 新表 `projects`、`project_documents`、`parse_snapshots`。`bid_versions`、`price_analyses`、`checklist_items` 增加可空的 `project_id`。
- 回填规则见开放决定 7 的默认：`project_name` 完全相同的标书版本合成一个项目；名称为空的各成一个；报价按相同字符串挂上。不按相似名称合并。
- 工作台列出项目。`/bid` 带项目 id。创建标书会先有项目。
- 解析改为接受文档 id。带 `file_path` 的旧接口保留到阶段 5，内部改成先找到受管文件再解析。
- 解析快照和素材选择写入服务器。刷新生成页能恢复，不必重新调用模型。
- 清单增加 `project_id`。旧的 `bid_version_id` 仍可读。

完成的标志：同一次投标的解析、版本、报价和清单能从项目 id 一起查到。旧版本列表还能打开。

### 阶段 4 — 统一作业

- 增加 `jobs` 与 `job_events`。运行器与 API 同进程。
- 入库状态改为最新入库作业的投影。重启后续跑的行为保持。
- 解析、规划、生成改为创建作业后立即返回。`/api/bid/generate/stream` 保留为兼容壳：创建作业并把它的事件流出去。
- 生成开始即写草稿版本，章节边界更新正文。取消和 `interrupted` 按上文的状态机处理。
- 生成页的进度组件订阅作业。工作台能看到进行中的作业。
- 本地模型的 `bid.generate` 同时只跑 1 笔；入库仍最多 2 笔。数字若要调整，见开放决定 8。

完成的标志：生成过程中刷新页面，进度还在，草稿正文还在；关掉浏览器再打开，已完成的版本在项目下。

### 阶段 5 — 配置快照与交付收口

- 每笔作业写入 `runtime_json`。设置页标出 `local` / `cloud`，并说明云端会发送哪些文本。
- 更换 Embedding 只通过阶段 2 的重建切换 `active` 索引，不在一次查询里混用。
- 生产构建和开发构建的接口都使用相对 `/api`。支持的启动方式写成单个进程，并写明不要加 `--workers`。
- 页面不再调用 `file_path` 解析和无人使用的非流式生成之后，删除这两条兼容路径。
- 导入期的 `settings = get_settings()` 从 `llm.py`、`embedder.py` 以及仍残留的 `bid.py`、`chromadb.py` 去掉。Chroma 客户端可以继续在进程内单例，因为它只跟目录有关。

完成的标志：保存一个新的本地模型后，下一笔生成使用新模型，不必为了换模型重启；用局域网地址打开页面时，请求发往该页面所在的主机。

## 开放决定

下面每条都有一个默认，方便按默认开工。负责人否决某条时，只改对应规则，不用改聚合形状。

1. **项目和资料库归谁看。** 默认：这台机器上所有登录用户共用项目和资料库，`created_by` 只用于记录。生产就绪评估已经把「共用还是按人隔离」留给负责人。若要隔离：列表按 `created_by` 过滤，管理员看全部。表结构不用推倒。
2. **招标文件进不进全局问答。** 默认：`scope=project`，智能问答不搜它。生成只检索本项目勾选的资料库文档；招标文件自身的切片仅供该项目使用。这样甲方原文不会变成公司素材。
3. **关掉浏览器后生成是否继续。** 默认：继续，直到进程还在。进程退出则作业 `interrupted`，草稿保留。若希望退出后丢弃半成品，只改对账规则。
4. **换 Embedding 模型后的旧索引。** 默认：新建完成后切换 `active`，旧集合标为 `retired`，确认备份之后再删目录。检索在身份不一致时不返回混合结果。
5. **检查清单挂在哪里。** 默认：挂在项目上，条目记住 `source_version_id`。勾选状态不随「再生成一版」清空。
6. **云端模型要不要额外确认。** 默认：允许保存，设置页和作业记录写明 `egress=cloud`。若要求必须由管理员确认一次才允许云端供应商，在设置保存处加一道确认即可。`mock` 在两种选择下都不用于真实检索。
7. **历史数据如何收成项目。** 默认：`bid_versions.project_name` 全字匹配的归为一个项目；空名称各成一个；`price_analyses.project_name` 用同一规则挂接。不合并仅仅相似的名称。有歧义的行保持未挂接，在工作台单独列出。
8. **同时生成几份。** 默认：`bid.generate` 同时 1 笔，入库同时 2 笔，和当前线程池一致。云端模型是否放宽到 2 笔，由负责人定。再大的并发不适合这台机器上的单进程 SQLite。

## 相关文档

- [六、技术架构](/manual/06-architecture)：2026-05 的 MVP 记录，保留原图。
- [生产就绪评估](/production-readiness)：备份、进程边界、CI、审计。P0 暂停。本文的阶段 2 依赖其中的成套备份，但不实施它。
