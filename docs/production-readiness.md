# Tender 生产就绪差距评估

评估日期：2026-11-07。对照的是仓库 `main`（`bc5c704`，PR #9 已合并）。本文只记录差距，不包含修复。

结论先说：**现在适合本机单人自用。** 登录、JWT 密钥和一次性管理员已经能挡住公开默认口令；标书生成和知识库异步入库也有自动化测试。把它交给业务同事每天用、并且要求数据坏了能找回来，还差一整层运行保障：成套备份与恢复、进程和网络边界、知识库不要删到原文件，以及一条真正会执行的 CI。下面的 P0 做完，才适合同一台 Mac 上的小团队试用。正式生产还要继续做 P1（令牌失效、SQLite/Chroma 一致性、日志和审计）。

## 记分卡

| 维度 | 现状 | 评级 | 说明 |
|------|------|------|------|
| 认证与权限 | 全部业务路由要登录；`/api/admin` 要 `admin`。角色每次请求查库。登出不使令牌失效，改密也不作废旧令牌。知识库、标书、报价没有按用户隔离 | 部分 | `server/deps.py`、`server/api/auth.py`。令牌默认 24 小时（`server/config.py` 的 `ACCESS_TOKEN_EXPIRE_MINUTES`），存在 `localStorage`（`web/src/stores/auth.js`） |
| 密钥与配置 | 公开默认密钥被拒绝；生产模式没有唯一 `SECRET_KEY` 会拒绝启动；开发密钥写到 `data/.secret_key` 且权限 `0600`。模型 API Key 经管理接口写入 `.env`，写入路径不收紧权限 | 部分 | `server/config.py` 的 `resolve_secret_key` / `write_private_text` / `update_env_many`。GET `/api/admin/config` 只返回 key 是否已设置 |
| HTTPS / 部署形态 | 默认 `HOST=0.0.0.0`、纯 HTTP、无反向代理、无 launchd/systemd、无 Docker、无 GitHub Release。`start.sh` 使用 `uvicorn --reload` | 缺口 | `server/config.py`、`.env.example`、`start.sh`、`restart_helper.py`。`gh release list` 为空，但使用说明指向 Releases 下载 `Tender.exe` |
| 数据持久化与备份 | SQLite 文件 `data/tender.db`，向量在 `data/chromadb`，上传在 `data/uploads`，生成件在 `data/generated`。无 WAL、无定时备份、无备份脚本 | 缺口 | `server/db/sqlite.py` 的 `get_db()` 只 `connect`，没有 `journal_mode` / `busy_timeout` |
| 知识库 / 向量库可靠性 | 异步入库、失败清理、启动时重排队已经有。文件夹扫描直接登记原路径；删文档会 `os.remove` 该路径。换 Embedding 模型没有重建索引。术语表向量失败仍会把文档标成可用 | 部分 | `server/api/kb.py`、`server/workers/document_worker.py`、`server/core/glossary.py`、`server/db/chromadb.py` |
| 并发与稳定性 | 知识库用进程内 2 线程池，Chroma 写入有锁，作者在注释里写明不能多进程同时写 Chroma 和 SQLite。标书长请求仍在 API 进程里。重启是 `os._exit(0)` | 部分 | `server/workers/executor.py`、`server/api/admin.py` 的 `_do_restart`。多 worker 会损坏向量库，这个约束没有写进运维说明 |
| 日志与可观测 | 没有统一日志配置、没有滚动文件、没有请求号。`/health` 固定返回 `{"status":"ok"}`，不检查数据库或向量库。一次性管理员密码打到标准输出 | 缺口 | `server/main.py` 的 `health()`；`server/db/sqlite.py` 启动时 `print` 密码 |
| 测试与 CI | 本机 Python 3.12 上 `pytest`：**88 passed**，覆盖率约 **52%**（门槛写的是 30%）。GitHub Actions 工作流 YAML 无法解析，最近两次 `main` 推送都是 0 个 job 的失败。`ruff` 68 个问题，`mypy server` 42 个错误，流水线即便能解析也会在测试前失败。前端没有测试 | 部分 | `.github/workflows/ci.yml` 第 46–47 行；Actions run `42382805656`、`41962209081` |
| 前端构建与发布流程 | `web/dist` 被 gitignore。CI 不跑 `npm run build`。生产构建把接口地址写成 `http://localhost:8000`。仓库里没有 `web/.env.production` | 缺口 | `web/.gitignore`、`web/vite.config.js`、`web/src/api/index.js`。`Tender.spec` 打包依赖本地已有的 `web/dist` |
| 备份恢复 | 使用说明只在「更换 exe 前建议备份 `data` 文件夹」提过一次。没有恢复步骤，没有「SQLite 和 Chroma 必须同一时刻拷贝」的说明，没有演练 | 缺口 | `docs/manual/05-faq.md` Q5、`docs/使用说明.md`。标书版本「恢复」只是把解析结果交回前端重生成（`server/api/bid.py` 的 `restore_bid_version`），不是数据库恢复 |
| 运维文档 | 有 Docsify 使用说明，日期仍是 2026-05-15，系统要求写成仅 Windows，FAQ 写 Mac 要用虚拟机。和当前 Mac 源码运行方式、README 里的 Linux 说明不一致。没有故障处理手册 | 缺口 | `docs/manual/01-intro.md`、`docs/manual/05-faq.md` Q6、`docs/_sidebar.md`（侧栏锚点仍是「什么是 clawos-x」） |
| 合规 / 审计 | 建了 `audit_logs` 表，仓库内没有任何插入或查询。选用 DeepSeek / 通义 / OpenAI 时，招标文件和标书正文会发给云端模型。README 写「文件永不离开」 | 缺口 | 表只在 `server/db/sqlite.py` 创建。云端调用见 `server/core/generator/llm.py`。本地 Ollama 才符合「数据留在本机」 |

## 已经够用的部分

这些不要推倒重做：

- **登录门槛已经铺上。** `kb`、`rag`、`bid`、`price`、`checklist` 都依赖 `get_current_user`；管理接口依赖 `require_admin`。未改密的引导账号不能调用其他接口（`server/deps.py`）。
- **公开默认 JWT 密钥已作废。** `tender-secret-key-change-in-production` 在任何环境都不会用来签名。`DEBUG=false` 或 `APP_ENV=production` 且没有唯一 `SECRET_KEY` 时进程拒绝启动。开发环境把密钥放在 `data/.secret_key`，权限 `0600`，不写回 `.env`（`server/config.py`）。对应测试在 `tests/test_auth_hardening.py`。
- **不再播种 `admin123`。** 全新安装生成一次性密码，写入仅当前用户可读的 `data/initial_admin_password.txt`，并强制改密。已经改过的密码不会被重置；管理员被删掉后也不会自动加回（`server/db/sqlite.py` 的 `bootstrap_admin`）。旧库如果密码仍是 `admin123`，下次登录必须修改。
- **管理配置能落盘，且接口不回显 API Key。** `PUT /api/admin/config` 写入 `.env` 并清掉设置缓存（`server/api/admin.py`、`tests/test_admin_config.py`）。界面保存后提示需要重启，这和 `server/core/embedder/embedder.py`、`server/core/generator/llm.py` 在导入时固定 `get_settings()` 的行为一致。
- **知识库上传不再堵死事件循环。** 上传后状态是 `pending`，解析和向量化在独立线程池（最多 2 个）里做；失败会清掉半成品；进程重启会把 `pending` / `processing` 重新排队（`server/workers/executor.py`、`server/workers/document_worker.py`、`tests/test_kb_async_upload.py`）。以前写死的 Mac 系统 Python 路径已经去掉。
- **标书主路径有共享实现和检索测试。** 批量生成和 SSE 走同一条 pipeline（`server/core/bidgen/pipeline.py`）。按章节检索、按相似度推荐历史章节，都有测试（`tests/test_bid_section_retrieval.py`、`tests/test_bid_recommend_preview.py`、`tests/test_bid_generate_pipeline.py`）。
- **标书草稿有版本记录。** 可列表、对比 unified diff、把某一版的解析结果和素材 ID 载回界面再生成（`server/api/bid.py` 约 1389–1475 行，`web/src/pages/BidGenerate.vue`）。这是草稿工作流，不是灾备。
- **敏感运行时文件默认不进 git。** `.gitignore` 忽略 `.env`、`/data/`、`data/.secret_key`、`data/initial_admin_password.txt`。`.env.example` 没有填真实密钥。

## P0

做完这些，才可以让同事在同一台机器上试用。每一项都是这个仓库里的具体行为。

### 1. 没有可执行的备份，坏了无法恢复

- **问题。** 业务数据分四处：`data/tender.db`（用户、文档元数据、标书版本、报价、清单）、`data/chromadb`（向量）、`data/uploads` 与文件夹扫描指向的原文件、`data/generated`（导出的 Word）。代码里没有备份入口。FAQ 只写「替换程序前先备份 `data` 文件夹」，而 Releases 上并没有可下载的程序。SQLite 使用默认回滚日志，没有 `PRAGMA journal_mode=WAL`，也没有 `backup` API。Chroma 的 `PersistentClient` 不能和 SQLite 分开用「各拷一次、时间对不上」的方式当备份。
- **风险。** 磁盘故障、误删 `data/`、或升级时只拷了 `tender.db`，历史标书和知识库检索会一起丢或对不上。这直接违反「数据要可依赖、出问题可恢复」。
- **建议做法。** 提供一个停写后的成套拷贝（至少 `tender.db`、`chromadb/`、`uploads/`、`generated/`、`.env`、`data/.secret_key`），以及一份按顺序停进程、替换目录、再启动的恢复说明。做一次演练：拷走副本、用副本起一个干净目录、确认能登录并看到原文档列表。副本和原目录不要同时被两个进程打开。
- **工作量。** 6–10 小时（脚本加一次真实演练）。

### 2. 文件夹扫描会读任意目录，删除会删掉原文件

- **问题。** `GET /api/kb/folder?folder_path=` 接受任意本机路径，只要进程读得到（`server/api/kb.py` 的 `add_folder`）。任何已登录用户都能调用，不要求管理员。扫描结果把**原始路径**写入 `documents.file_path`，不复制到 `data/uploads`。`DELETE /api/kb/documents/{doc_id}` 对该路径执行 `os.remove`。上传接口才会把文件复制成 `data/uploads/<uuid>.后缀`。另外 `MAX_FILE_SIZE`（默认 50MB）只定义在 `server/config.py`，上传循环没有使用它。
- **风险。** 同事把历史标书目录扫进知识库后，在界面上点删除，磁盘上的原件会被删掉。持有 24 小时令牌的人也可以把家目录里的 PDF/Word 扫进来，再通过切片接口把正文读走。大文件可以把磁盘写满。
- **建议做法。** 扫描只允许配置好的目录；入库时复制到 `data/uploads`；删除只删除这份副本。给上传加上 `MAX_FILE_SIZE`，超限立刻停止并删掉半截文件。
- **工作量。** 6–10 小时。

### 3. 当前启动方式不能安全地给第二台电脑用

- **问题。** 默认监听 `0.0.0.0:8000`，没有 TLS。`start.sh` 是 Mac/Linux 的一键入口，却带 `--reload`。管理端「重启」调用 `restart_helper.py`：旧进程 `os._exit(0)`，新进程盲等 3 秒再拉起，没有就绪检查。生产前端在非 dev 模式下把 `baseURL` 设为 `VITE_API_URL`，缺省是 `http://localhost:8000`（`web/src/api/index.js`、`web/vite.config.js`）。仓库没有 `web/.env.production`，`web/dist` 不入库，CI 也不构建前端。使用说明要求从 Releases 下载 `Tender.exe`，仓库没有任何 Release，`Tender.spec` 还要求本机已经打好 `web/dist`。
- **风险。** 同事用局域网 IP 打开页面时，浏览器会去请求**他们自己电脑**的 8000 端口。服务若按默认地址暴露在办公室网络上，登录和标书内容走明文，令牌可以被同网段听到。`--reload` 和 `os._exit` 会打断正在生成的标书。没有进程守护时，合上笔记本或进程崩溃后服务不会自己回来。
- **建议做法。** 正式启动去掉 `--reload`，用 launchd（Mac）或同等方式拉起单个 uvicorn 进程，并写明不要加 `--workers`（见下一节的单进程约束）。只给本机用时绑定 `127.0.0.1`。同事要从别的电脑访问时，在前面加本机反向代理并使用 HTTPS，不要把 FastAPI 直接铺到局域网。前端生产包改用相对路径 `/api`，这样和页面同一台主机。发布清单改成：先 `npm run build`，再按 `Tender.spec` 打包，或明确「源码 + venv + 已构建 dist」的启动步骤。使用说明里的 exe/Releases 要么补上真正的发布物，要么改成和实际一致的源码步骤。
- **工作量。** 1–1.5 人天（含一份 Mac launchd 示例和一次用局域网 IP 打开页面的验证）。办公室证书另计约 4 小时。

### 4. CI 工作流文件是坏的，main 上的门禁没有跑过

- **问题。** `.github/workflows/ci.yml` 在「Check coverage threshold」里，`python - <<PY` 的下一行 `import` 顶到了第 1 列。YAML 因此无法解析（在本机用 PyYAML 加载会报 `ScannerError`，行 46–47）。GitHub 上该工作流最近两次 `main` 推送都是立即失败、0 个 job、没有日志：
  - [run 42382805656](https://github.com/cnchaoge/Tender/actions/runs/42382805656)（2026-11-07，PR #9）
  - [run 41962209081](https://github.com/cnchaoge/Tender/actions/runs/41962209081)（2026-11-05，测试/CI 合并）
- **本机对照（2026-11-07，Python 3.12.3，已安装 `requirements.txt`）。** `pytest -q --cov=server`：**88 passed**，约 11.5 秒，行覆盖率 **52%**。`ruff check .`：**68** 个问题（多为未使用导入 F401、导入不在文件顶部 E402）。`mypy server --ignore-missing-imports`：**42** 个错误，集中在 `server/api/bid.py`、`server/api/admin.py`、`server/api/price.py`。流水线顺序是 ruff → mypy → pytest，所以只修缩进之后，Actions 仍会在测试前变红。`requirements-dev.txt` 把 `reportlab` 钉在 3.6.13，这个版本在本环境的 Python 3.12 上无法编过（缺 `ft2build.h`）；PDF 用例改用 reportlab 4 的 wheel 可以通过。CI 矩阵是 3.10 和 3.11，不包含前端构建。
- **风险。** 之后每一次合并都不会被测试拦住。覆盖率门槛 30% 也远低于现在已经达到的 52%，即使将来跑起来，挡不住标书和报价主路径继续没有测试（`server/api/bid.py` 覆盖率约 32%，`server/api/price.py` 约 33%）。
- **建议做法。** 把 heredoc 整段缩进到字面量块内部，让工作流能被解析。短期内把 ruff/mypy 改成只出报告、不让 job 失败，先保证 pytest 在 `main` 上执行；再清掉 68/42，恢复为失败即红。门槛至少保持在当前 52% 附近，而不是 30%。另加一步 `npm run build`，确认 `web/dist` 能生成。
- **工作量。** 让 YAML 可解析并让 pytest 在 Actions 里跑起来：1–2 小时。把 ruff 和 mypy 清到能阻断合并：0.5–1.5 人天。前端构建步骤：1–2 小时。

## P1

P0 之后、正式日常使用之前要补的。

### 5. 登录态撤销不完整，管理员可以被删光

- **问题。** `POST /api/auth/logout` 只返回 `{"message":"ok"}`（`server/api/auth.py`）。改密不更换签名版本，旧 JWT 在过期前仍然有效。创建用户（`POST /api/admin/users`）不检查 8 位最低长度，那条规则只在本人改密时生效。`DELETE /api/admin/users/{id}` 可以删掉最后一个管理员；`bootstrap_admin` 在 `bootstrap_admin_done=1` 之后不会再创建账号。登录没有失败次数限制。
- **风险。** 共用浏览器或泄露的 `localStorage` 令牌，在改密后最长还能用 24 小时。弱密码可以被管理员写进系统。误删唯一管理员后，界面无法自救，只能手工改 `data/tender.db`。服务若暴露在局域网上，登录接口可以被猜密码。
- **建议做法。** 用户表增加令牌版本或「密码变更时间」，校验 JWT 时对照；登出和改密都让旧令牌失效。管理员创建的密码使用和改密相同的规则。禁止删除或降级最后一个管理员。给登录加一个很小的本机失败延迟即可，不必上完整的账号锁定产品。
- **工作量。** 1–1.5 人天。

### 6. SQLite 与 Chroma 会在故障和换模型时分叉

- **问题。** `get_db()` 每次新建连接，`check_same_thread=False`，没有 WAL，没有更长的 `busy_timeout`，也没有打开 `foreign_keys`。知识库写锁只包住切片写入；标书、报价、登录同时写库时不在这把锁里。`server/workers/executor.py` 已说明多进程同时打开 Chroma 持久化客户端和 SQLite 容易损坏，但启动文档没有把「只能一个进程」写成红线。`server/core/glossary.py` 在向量化失败时仍然 `commit`，文档状态保持默认可用，下次启动看到文件名「内置投标术语表」就直接返回，不会重试。`server/db/chromadb.py` 的集合不记录向量维度；更换 `EMBED_PROVIDER` 或模型后，旧向量和新查询混在一起。`MockEmbedder` 每次用随机向量（`server/core/embedder/embedder.py`），设置里可以把 Embedding 切到 `mock`。按文件名去重：同名文件再次上传会返回旧记录，内容变了也不会重新入库（`server/api/kb.py`）。
- **风险。** 两人同时上传并生成标书时，可能出现 `database is locked`，请求失败但用户看不到原因。术语表或某次 Chroma 写入失败后，界面显示文档可用，检索却找不到。换一次 Embedding 模型，历史知识库的相似度结果会错，而且没有重建按钮。误开 mock 后，检索结果没有意义。
- **建议做法。** 打开 WAL，并设置 `busy_timeout`（例如 5–10 秒量级，按本机磁盘再定）。启动时如果检测到第二个进程已打开同一个 `data/`，直接退出并提示。术语表向量失败时把该文档标为 `failed`，下次启动重试。更换 Embedding 模型时清空或重建 `documents` 集合，并记录当前模型名。设置页对 `mock` 标明「不能用于真实检索」。同名再上传改为按内容哈希决定是否重新处理。
- **工作量。** 1.5–2.5 人天。向量重建要先有 P0 的备份。

### 7. `.env` 里的 API Key 权限比 JWT 密钥松

- **问题。** `write_private_text` 用于密钥文件和一次性密码，权限 `0600`。`update_env_many` 用普通 `write_text` 写 `.env`，权限跟随 umask（常见结果是同组或其他用户可读）。模型 Key 明文放在项目根的 `.env`。
- **风险。** 同一台 Mac 上的其他系统账户，或一份被拷走的项目目录，可以读到 DeepSeek/通义密钥。密钥和标书数据的保护级别不一致。
- **建议做法。** 写 `.env` 时沿用 `write_private_text` 的权限。备份说明里把 `.env` 和 `data/.secret_key` 标成机密，不要放进聊天或网盘的公开链接。
- **工作量。** 2–4 小时。

### 8. 日志不够用来排障，健康检查不反映依赖

- **问题。** 业务代码多用 `logging.getLogger`，但没有 `basicConfig`、没有文件、没有按天滚动。启动和错误大量 `print`。`/health` 不打开 SQLite，不看 Chroma，不看 Ollama。没有请求 ID，无法把一次失败的标书生成和日志行对上。
- **风险。** 同事说「生成失败了」，现场只剩一个终端滚动，重启后就没了。进程管理器如果只探活 `/health`，数据库文件损坏时仍会显示正常。
- **建议做法。** 启动时配置一个写到 `data/logs/` 的滚动日志，级别可用环境变量调整。`/health` 增加数据库可打开、Chroma 目录可写；Ollama/云模型单独做一个 `/health` 不调用的「依赖状态」，避免探活打到外部 API。不要在日志里打印密码和 API Key（现在的一次性密码 print 要改成「密码已写入某文件」）。
- **工作量。** 0.5–1 人天。

### 9. 使用说明会把 Mac 用户带去错误的安装路径

- **问题。** `docs/使用说明.md` 和 `docs/manual/01-intro.md` 写操作系统仅 Windows 10/11，交付物是 `Tender.exe`。`docs/manual/05-faq.md` Q6 写 Mac/Linux 不可用、需要虚拟机。README 写支持 Windows 和 Linux、无需 Docker。侧栏锚点仍指向不存在的「clawos-x」。文档更新日期是 2026-05-15，没有备份恢复、换 `SECRET_KEY` 后需要重新登录、单进程、以及「云模型会把正文发出去」这些内容。
- **风险。** 目标用户是在 Mac 上开发的设计初学者。按文档去做会去找一个不存在的 exe，或以为必须装 Windows。出问题后没有步骤可循。
- **建议做法。** 把安装章改成当前真实路径：Python venv、`.env`、`npm run build`、`uvicorn`（不要 `--reload`）、首次密码文件的位置。删掉或更正「仅 Windows」和 Releases 下载，直到真的有 Release。增加一页运行手册：备份、恢复、磁盘满了、唯一管理员被删、Embedding 换模型后如何重建。
- **工作量。** 0.5–1 人天。

### 10. 审计表是空的，云模型数据和文案不一致

- **问题。** `audit_logs(user_id, action, detail, created_at)` 只在建表时出现。没有人记录登录、上传、删除、生成标书、改配置、改报价。README 承诺「文件永不离开」「不上传任何文件到第三方云平台」。默认 `LLM_PROVIDER=ollama` 时这成立；一旦设置里保存了 DeepSeek 或通义，招标文件解析和标书正文会经 `get_generator()` 发到对应云 API。设置页没有把这件事写在保存按钮旁边。
- **风险。** 标书和报价是商业秘密。出了争议无法回答「谁在什么时候生成了哪一版、用的哪个模型」。选了云模型却仍以为数据留在工厂电脑上。
- **建议做法。** 往 `audit_logs` 写入登录成功/失败、文档上传与删除、标书生成（项目名和版本 id）、配置变更（不要写入 API Key 原文）。设置页在选择非 Ollama 提供商时显示「正文会发送到该服务商」。README 改成「默认本地模型时数据留在本机；云模型会发送生成所需文本」。
- **工作量。** 1–2 人天。

### 11. 所有登录用户共用同一套标书和报价

- **问题。** `documents`、`bid_versions`、`price_analyses`、`checklist_items` 都没有 `user_id`。任一登录用户可以列出、下载（`GET /api/bid/download/{filename}`）、删除他人的知识库文件和标书。角色只有 `admin` 和 `user`，`user` 不是「只能看自己的项目」。
- **风险。** 若业务同事各做各的投标，报价和历史标书互相可见、可删。若公司本来就是共用一套资料库，这是可以接受的产品选择，但需要负责人明确写下来，而不是靠「没做隔离」默认成立。
- **建议做法。** 先做产品决定。共用库：在使用说明里写明，并依赖 P1 的审计。按人隔离：给业务表加所有者，列表和下载按当前用户过滤，管理员可看全部。
- **工作量。** 只写明共用策略：1–2 小时。按人隔离：2–3 人天。

## P2

不挡住小团队试用，正式运行稳定后再做。

| 问题 | 风险 | 建议做法 | 工作量 |
|------|------|----------|--------|
| `python-jose==3.3.0` 已停止维护；`chromadb==0.5.5`、`fastapi==0.115.0` 也偏旧。没有依赖漏洞扫描 | 已知漏洞不会在 CI 里出现 | 升级前先有 P0 备份；CI 加 `pip audit` 或同类检查，只报告不阻断也可以 | 0.5–1 人天（升级 Chroma 要回归检索） |
| `/openapi.json` 默认可匿名访问。`spa_fallback` 用 `WEB_DIST / path` 返回文件，没有 `resolve()` 后确认仍在 `web/dist` 内 | 接口形状对外可见；精心构造的路径有机会读到 dist 目录之外的文件 | 生产关闭 OpenAPI，或加上管理员鉴权。静态文件先解析再判断是否仍位于 `WEB_DIST` | 2–4 小时 |
| Ollama Embedding 逐条 HTTP，超时 60 秒（`OllamaEmbedder.embed`） | 大文档入库很慢，看起来像卡死 | 使用 Ollama 的批量输入；界面继续靠现有的状态轮询显示 `processing` | 4–8 小时 |
| 数据库只有 `CREATE TABLE IF NOT EXISTS` 和一次 `ALTER TABLE` 加 `must_change_password` | 下次改表容易漏掉旧库 | 加一个很薄的 `schema_version` 表，每次变更一个函数 | 4–8 小时 |
| `Tender.spec` 仍收集 `sentence_transformers`，而项目里的 `sitecustomize.py` 是为了避免 Chroma 触发该导入 | Windows 单文件包体积大，且和「无 Release」叠加后无人验证能否打出包 | 在一台 Windows 或 CI 上实际打一次包；打不出来就不要在文档里承诺 exe | 0.5–1 人天 |
| 创建用户失败时把异常字符串返回给客户端（`server/api/admin.py`） | 可能把 SQL 细节给到浏览器 | 日志里记详情，接口只返回「创建失败」 | 1 小时 |

## 建议的下一步（只做这三件）

1. **先做能恢复的备份。** 写一个停写后成套复制 `data/`（含 `tender.db`、`chromadb`、`uploads`、`generated`）以及 `.env` 和 `data/.secret_key` 的脚本，并按恢复说明完整走一遍：停进程、换上副本、启动、登录、看到原来的文档。没有这一步，后面的改动都没有退路。
2. **堵住误删和错误的访问方式。** 文件夹扫描改为复制进 `data/uploads`，删除只删副本，并限制可扫描目录。正式进程绑定 `127.0.0.1`（或放在 HTTPS 反代后面），`start.sh` 去掉 `--reload`。生产前端请求相对路径 `/api`，用局域网 IP 打开页面验证接口不是 `localhost`。
3. **让 CI 真的跑测试。** 修正 `.github/workflows/ci.yml` 的 heredoc 缩进。在 ruff/mypy 清零之前让它们不要挡住 pytest。目标是 `main` 上能看到 88 个测试的结果，而不是 0 个 job。本机已经证明这套测试可以通过。

## 附录：本次如何核对

- 阅读了 `server/config.py`、`server/deps.py`、`server/main.py`、`server/db/sqlite.py`、`server/db/chromadb.py`、`server/api/auth.py`、`server/api/admin.py`、`server/api/kb.py`、`server/workers/*`、`start.sh`、`restart_helper.py`、`.env.example`、`.github/workflows/ci.yml`、`docs/manual/*`、`web/src/api/index.js`、`web/vite.config.js`。
- 仓库内没有 Dockerfile、没有 systemd/launchd 单元、没有备份脚本。`gh release list` 为空。
- 测试命令（本机，非 CI）：`pytest -q --cov=server` → 88 passed，行覆盖率 52.00%（4163 条语句中覆盖 2163 条）。CI 工作流未能在 GitHub 上启动任何 job。
