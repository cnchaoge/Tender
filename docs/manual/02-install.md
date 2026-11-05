# 二、安装与启动

## 获取程序

从 GitHub 下载最新版本：

👉 [https://github.com/cnchaoge/tender/releases](https://github.com/cnchaoge/tender/releases)

下载 `Tender.exe`（Windows 单文件版）

---

## 首次启动

**步骤 1：** 双击运行 `Tender.exe`

**步骤 2：** 全新安装会在服务日志中打印一次性管理员密码，并写入程序目录下的 `data/initial_admin_password.txt`

**步骤 3：** 浏览器打开 `http://localhost:8000`，使用用户名 `admin` 和该一次性密码登录

**步骤 4：** 系统要求立即设置新密码。完成后删除 `data/initial_admin_password.txt`

生产环境请在启动前设置环境变量 `SECRET_KEY`（`DEBUG=false` 或 `APP_ENV=production` 时不设置将无法启动）。本地开发未设置时，会在 `data/.secret_key` 生成并复用一个密钥。

---

## 配置 AI API Key

> Tender 需要连接 AI 模型服务才能正常工作。

**步骤 1：** 登录后进入 **系统设置** 页面

**步骤 2：** 在「AI 模型配置」中填入 DeepSeek API Key

**步骤 3：** 保存后即可开始使用

### 如何获取 API Key

| 模型 | 获取地址 |
|------|----------|
| **DeepSeek** | [platform.deepseek.com](https://platform.deepseek.com) 注册后创建 API Key |
| **通义千问** | 阿里云百炼平台 |

---

## 开发模式运行（可选）

如需修改代码或调试，可从源码启动：

```bash
# 前端（开发模式，热更新）
cd tender/web
npm install
npm run dev     # 访问 http://localhost:5173

# 后端（另一个终端）
cd tender
./start.sh      # 访问 http://localhost:8000
```