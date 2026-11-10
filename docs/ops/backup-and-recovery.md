# 备份与恢复

停掉 Tender 之后，用项目里的 `scripts/backup_tender.py` 把**同一时刻**的这一套文件拷走：

| 路径 | 内容 |
|------|------|
| `data/tender.db` | 用户、文档、项目、标书版本、报价、清单。若旁边有 `tender.db-wal` / `tender.db-shm`，一并拷贝 |
| `data/chromadb/` | 向量索引 |
| `data/library/` | 当前受管原件（`data/library/{id}/`） |
| `data/uploads/` | 仅当目录还在时拷贝。这是旧布局，不是现在的唯一存储 |
| `data/generated/` | 导出的 Word |
| `.env` | 配置，含模型 API Key。**机密** |
| `data/.secret_key` | 本机 JWT 签名密钥。**机密** |

SQLite 和 Chroma 必须来自同一次备份。只换 `tender.db`、或只换 `chromadb/`，检索和文档列表会对不上。脚本在拷贝前会独占打开数据库，把残留的 WAL 折进 `tender.db`。干净退出后备份里往往没有 `-wal` / `-shm`；若折进之后文件还在，会和这次的 `tender.db` 一起拷走。

备份目录和正在使用的 `data/` **不能被两个进程同时打开**。不要一边用原目录跑服务，一边让另一个进程打开备份里的数据库。

`.env` 和 `data/.secret_key` 是机密。不要贴进聊天，也不要放到网盘的公开链接里。

## 备份

1. 停掉唯一的 Tender 进程（不要留着 `--reload` 拉起的第二个进程）。
2. 在项目根目录先看将要拷贝的路径，这一步不写文件：

```bash
python scripts/backup_tender.py --dry-run
```

3. 把副本写到**项目目录之外**。脚本发现数据库仍被占用时会停下：

```bash
python scripts/backup_tender.py --dest /绝对路径/备份父目录
```

生成 `tender-backup-<时间>/`，里面有 `MANIFEST.txt`。`.env` 和 `data/.secret_key` 在副本里的权限是 `0600`。

## 恢复

在一台已经停掉 Tender 的机器上，用**同一次**备份整套换回去。下面把备份目录写成 `$BACKUP`。

1. 确认没有进程打开当前 `data/`，也没有进程打开 `$BACKUP`。
2. 把现用数据改名留底，不要直接删：

```bash
mv data "data.before-restore-$(date +%Y%m%d%H%M%S)"
mv .env .env.before-restore
```

3. 只从这一份备份恢复。有 WAL 旁路文件时一起拷回：

```bash
mkdir -p data
cp -a "$BACKUP/data/tender.db" data/
if [ -f "$BACKUP/data/tender.db-wal" ]; then cp -a "$BACKUP/data/tender.db-wal" data/; fi
if [ -f "$BACKUP/data/tender.db-shm" ]; then cp -a "$BACKUP/data/tender.db-shm" data/; fi
cp -a "$BACKUP/data/chromadb" data/
cp -a "$BACKUP/data/library" data/
if [ -d "$BACKUP/data/uploads" ]; then cp -a "$BACKUP/data/uploads" data/; fi
cp -a "$BACKUP/data/generated" data/
cp -a "$BACKUP/.env" .env
cp -a "$BACKUP/data/.secret_key" data/.secret_key
chmod 600 .env data/.secret_key
```

4. 用官方方式启动**一个**进程（不要加 `--reload`，不要加 `--workers`）：

```bash
bash start.sh
```

5. 浏览器打开 `http://127.0.0.1:8000`，用恢复出来的账号登录。知识库文档和项目（标书版本、报价）应能在页面上看到。看不到时，先确认第 3 步的 SQLite 和 `chromadb/` 来自同一个 `$BACKUP`，并且没有第二个进程还开着旧目录。

这次仓库里的检查只验证脚本会拷到上表这些路径。在使用者的 Mac 上按上面 1–5 步走一遍，才是一次完整演练。不要把演练用的 `.env` 或 `data/.secret_key` 发给别人。
