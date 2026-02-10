# 企业微信指令服务（Python）

这是一个基于 `FastAPI` 的企业微信回调服务：

- 接收企业微信回调消息
- 接收指令执行自定义任务
- 任务执行过程主动推送消息（text/markdown/textcard 等）给用户

## 1. 安装依赖

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## 2. 配置环境变量

```bash
export WECOM_CORP_ID="你的企业ID"
export WECOM_AGENT_ID="应用AgentId"
export WECOM_AGENT_SECRET="应用Secret"
export WECOM_TOKEN="你的Token"
export WECOM_ENCODING_AES_KEY="你的EncodingAESKey"

# 日志目录（可选，默认 logs）
export LOG_DIR="logs"

# 日志级别（可选，默认 INFO，可用: DEBUG/INFO/WARNING/ERROR/CRITICAL）
export LOG_LEVEL="INFO"

# 日志保留天数（可选，默认 30）
export LOG_BACKUP_DAYS="30"

# 企业微信发送消息接口超时秒数（可选，默认 10）
export WECOM_HTTP_TIMEOUT="10"

```
- 获取 `WECOM_CORP_ID`

  企业微信管理后台 -> 我的企业 -> [企业信息](https://work.weixin.qq.com/wework_admin/frame#/profile), 最下方的企业ID就是 CORP_ID

- 获取 `WECOM_AGENT_ID`、`WECOM_AGENT_SECRET`

  企业微信管理后台 -> 应用管理 -> [应用](https://work.weixin.qq.com/wework_admin/frame#/apps) , 创建应用后最上方的 AgentId 和 Secret

- 生成 `WECOM_TOKEN`、`WECOM_ENCODING_AES_KEY`

  企业微信管理后台 -> 应用管理 -> 你的应用 -> 接收消息，配置API接收消息，配置回调URL到你的 `/wecom/callback` 地址，并填写 `Token` 和 `EncodingAESKey`
  
  **注意**: 需要先启动服务再配置，企业微信回调接口需要先验证你的服务

## 3. 启动服务

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

健康检查接口：

```text
GET /health
```

企业微信回调接口：

```text
GET  /wecom/callback   # URL回调验证
POST /wecom/callback   # 接收消息
```

说明： 通过callback收到消息后，异步执行对应任务；任务中可多次推送消息给 `fromUser`。
企业微信可推送消息模板参考：[发送消息](https://developer.work.weixin.qq.com/document/path/94677)

## 4. 已实现指令

- `help`：查看帮助
- `ping`：你还活着吗
- `time`：返回服务器当前时间
- `echo <文本>`：回显输入文本
- `msgtest`：消息测试（支持 text / textcard / markdown 等格式）
- `longtask`：耗时任务测试（会先通知“开始执行”，完成后再通知结果）

说明：任务处理器可在 `CommandRouter` 内通过 `ctx.notify_xxx(...)` 主动分阶段推送消息给用户。

指令分发代码在：`app/command_router.py`

## 5. 扩展新任务

在 `app/command_router.py` `CommandRouter` 中：

1. 新增异步 handler（例如 `async def _handle_xxx`）
2. 在 `CommandRouter` -> `__init__` -> `self._handlers`中注册自定义指令名到你自定义的 `_handle_xxx` 任务处理函数
3. 在 `_handle_xxx` 里执行自定义任务，任务中可随时调用 `ctx.notify_text(...)` / `ctx.notify_markdown(...)` / `ctx.notify_textcard(...)` 推送消息给用户

示例：

```python
self._handlers: dict[str, Handler] = {
    "help": self._handle_help,
    "ping": self._handle_ping,
    "time": self._handle_time,
    "custom": self._handle_xxx,
    ...
}
```

## 6. 注意事项

- 你需要有一个公网地址（最好是静态IP）
- 企业微信服务器必须能访问你的公网地址
- 回调 URL 与企业微信后台配置应一致
- `Token / EncodingAESKey / CorpId` 必须和后台配置一致
- 你需要在 企业微信管理后台 -> 应用管理 -> 你的应用 -> 企业可信IP 中配置你的公网IP后才可以发送消息
