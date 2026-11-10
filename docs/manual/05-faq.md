# 五、常见问题

## Q1：登录失败，提示"认证失败"

可能原因：
- 账号密码输入错误
- 全新安装时使用了错误的一次性密码（见服务日志或 `data/initial_admin_password.txt`）
- Token 过期，或服务已更换 `SECRET_KEY`（需要重新登录）

**解决方法：** 使用当前密码重新登录。首次登录若被要求修改密码，设置新密码后再继续。忘记密码请联系管理员重置。

---

## Q2：标书解析失败，显示"解析失败"

可能原因：
- 文件不是文字版（扫描件图片），建议使用文字版 PDF
- 文件格式不支持，换成 PDF 或 DOCX 格式
- 网络异常，AI 模型调用超时

**解决方法：** 确认文件是文字版 PDF 或 Word，可先复制文字内容保存为 Markdown 再试。

---

## Q3：生成标书时报错"DashScope API Key 无效"

Embedding 模型 API Key 配置错误。

**解决方法：** 进入「系统设置」→「Embedding 配置」修正 API Key，或暂时切换为 Mock Embedder（不调 API，但无法做向量检索）。

---

## Q4：生成的内容与招标文件不符

可能原因：
- 解析结果中的「项目名称」「工期」等字段有误
- 招标文件格式特殊，解析不完整

**解决方法：** 检查解析结果，手动修正后再生成。可补充行业关键词提升解析准确率。

---

## Q5：如何更新到新版本？

仓库没有可下载的 `Tender.exe`。更新的是这份源码。

1. 停掉唯一的 Tender 进程。
2. 按 [备份与恢复](/ops/backup-and-recovery) 把 SQLite、Chroma、`data/library/`、`.env` 和 `data/.secret_key` 作为同一套拷走。
3. 更新代码后，在 `web/` 执行 `npm run build`，再用 `bash start.sh` 启动一个进程。

不要只拷走 `tender.db`。SQLite 和 Chroma 必须来自同一次备份，而且备份目录和正在使用的 `data/` 不能被两个进程同时打开。

---

## Q6：Mac / Linux 可以用吗？

可以。Mac、Linux 和 Windows 都用 [安装与启动](/manual/02-install) 里的虚拟环境、`.env`、`npm run build` 和 `start.sh` / `run.bat`。不需要为了运行而安装 Windows 虚拟机。