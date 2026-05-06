# ClawOS X 待办

## 飞书云端中继（cloud relay）

- [ ] relay.clawosx.cn 域名备案完成后 DNS A 记录指向 82.156.229.67
- [ ] 飞书开放平台配置 webhook URL 为 http://relay.clawosx.cn/feishu/webhook
- [ ] 客户机 WebSocket 长连接连到 ws://relay.clawosx.cn/ws/relay
- [ ] 客户机本地 RAG 处理飞书消息，发送回复
- [ ] 完善 relay_server.py 的签名验证（可选）

## 客户端连接器（客户机侧）

- [ ] ClawOS X 客户端自动连接云端 relay
- [ ] 断线自动重连
- [ ] 开机自启（Windows 服务或计划任务）
- [ ] 按 machine_name 路由消息到对应客户机

## 产品化

- [ ] PyInstaller 打包 ClawOS X 为 Windows 单文件 exe
- [ ] 安装程序（NSIS/Inno Setup）带配置向导
- [ ] 飞书应用权限：订阅 im.message.receive_v1 事件
- [ ] 客户机首次启动引导（填飞书 bot token/设置）

## RAG 完善

- [ ] 换真实 DASHSCOPE_API_KEY
- [ ] 文件夹扫描排除 node_modules
- [ ] 文档上传去重（同名文件）
- [ ] 支持更多文件类型（PDF、Word）

## 已完成

- [x] relay_server.py 轻量云端转发服务（端口 18001）
- [x] nginx 配置 relay.clawosx.cn 路由（待域名生效）
- [x] 飞书 webhook 接收 + 广播给已连接客户机
- [x] 客户机回复回传飞书
