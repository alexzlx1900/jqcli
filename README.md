# jqcli

聚宽（JoinQuant）策略与回测管理命令行工具。

当前项目处于 MVP 实现阶段，接口行为以真实聚宽 API 调研结果为准。

## 环境变量配置

默认会读取当前目录 `.env`，也可以用 `--env-file <path>` 指定路径。

示例：

```dotenv
JQCLI_USERNAME=your_username
JQCLI_PASSWORD=your_password
JQCLI_TOKEN=your_token
JQCLI_COOKIE=your_cookie
```

常用命令：

```bash
jqcli --env-file .env --format json auth status
jqcli --env-file .env --format json auth login
```

`.env` 已加入 `.gitignore`，不要提交真实账号密码。
