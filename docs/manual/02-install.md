# 二、安装与启动

## 获取程序

从 GitHub 下载最新版本：

👉 [https://github.com/cnchaoge/clawosx/releases](https://github.com/cnchaoge/clawosx/releases)

下载 `ClawOSX.exe`（Windows 单文件版）

---

## 首次启动

**步骤 1：** 双击运行 `ClawOSX.exe`

**步骤 2：** 首次运行会提示设置管理员密码

**步骤 3：** 设置密码后，浏览器自动打开 `http://localhost:8000`

**步骤 4：** 使用账号 `admin` 和刚才设置的密码登录

---

## 配置 AI API Key

> ClawOS X 需要连接 AI 模型服务才能正常工作。

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
cd clawosx/web
npm install
npm run dev     # 访问 http://localhost:5173

# 后端（另一个终端）
cd clawosx
./start.sh      # 访问 http://localhost:8000
```