# jqcli

聚宽（JoinQuant）策略与回测管理命令行工具。

`jqcli` 面向自动化调用和真实聚宽网页接口封装，支持认证、策略管理、正式回测、编译运行记录查询与删除。所有命令都可以使用 `--non-interactive --format json` 作为机器可读主路径。

## 安装与运行

项目使用 Python 3.9+。

```bash
python -m venv .venv
.venv/bin/pip install -e ".[dev]"
.venv/bin/jqcli --help
```

本仓库中的示例默认使用本地可执行文件：

```bash
.venv/bin/jqcli --env-file .env --format json auth status
```

## 配置与认证

默认会读取当前目录 `.env`，也可以用 `--env-file <path>` 指定。

```dotenv
JQCLI_USERNAME=your_username
JQCLI_PASSWORD=your_password
JQCLI_TOKEN=your_token
JQCLI_COOKIE=your_cookie
```

`.env` 已加入 `.gitignore`，不要提交真实账号、密码、cookie 或 token。

凭据优先级：

1. 命令行 `--token` / `--cookie`
2. 环境变量 `JQCLI_TOKEN` / `JQCLI_COOKIE`
3. 本地配置文件中保存的 `token` / `cookie`
4. `auth login` 使用 `JQCLI_USERNAME` / `JQCLI_PASSWORD` 或 stdin 密码登录后保存 cookie

默认配置文件路径：

```text
macOS/Linux: ~/.config/jqcli/config.json
Windows:     %APPDATA%\jqcli\config.json
```

## 全局选项

```bash
jqcli [--config <path>]
      [--env-file <path>]
      [--api-base <url>]
      [--token <token> | --cookie <cookie>]
      [--format table|json]
      [--non-interactive]
      [--quiet]
      [--debug]
      [--timeout <seconds>]
      <command>
```

常用自动化格式：

```bash
jqcli --env-file .env --non-interactive --format json <command>
```

JSON 模式下成功结果输出到 stdout；错误输出到 stderr，格式为：

```json
{
  "error": {
    "code": "not_authenticated",
    "message": "未登录，请先配置 token/cookie",
    "details": {}
  }
}
```

## Auth API

### auth status

检查本地是否已有可用凭据。该命令只检查配置/环境变量，不会远程校验 cookie 是否过期。

```bash
jqcli --format json auth status
```

输出：

```json
{
  "authenticated": true,
  "api_base": "https://www.joinquant.com",
  "credential_source": "cookie",
  "username": "user@example.com"
}
```

### auth login

使用真实聚宽登录接口登录并保存 cookie。

```bash
jqcli --env-file .env --format json auth login
printf '%s' "$JQ_PASSWORD" | jqcli --format json auth login --username user@example.com --password-stdin
```

真实接口：

- 登录页：`GET /user/login/index`
- 登录提交：`POST /user/login/doLogin`
- 登录 token：从登录页 `window.tokenData.value` 提取

输出：

```json
{
  "ok": true,
  "username": "user@example.com",
  "credential": "cookie"
}
```

### auth import-token

保存 token 到本地配置。

```bash
jqcli --format json auth import-token --token <token>
```

输出：

```json
{
  "ok": true,
  "credential": "token"
}
```

### auth import-cookie

保存 cookie 到本地配置。

```bash
jqcli --format json auth import-cookie --cookie '<cookie>'
```

输出：

```json
{
  "ok": true,
  "credential": "cookie"
}
```

### auth logout

删除本地配置中保存的 token、cookie、username，不影响环境变量。

```bash
jqcli --format json auth logout
```

输出：

```json
{
  "ok": true
}
```

## Strategy API

策略接口基于聚宽服务端渲染页面和表单提交实现。

真实接口：

- 列表：`GET /algorithm/index/list`
- 详情/编辑页：`GET /algorithm/index/edit?algorithmId=<id>`
- 新建入口：`GET /algorithm/index/new`
- 保存：`POST /algorithm/index/save`
- 删除：`POST /algorithm/index/del`

注意：聚宽列表页中的 `algorithmId` 可能随请求变化。`jqcli` 会优先使用列表/编辑页当前可用 ID，并在删除等场景按名称回查当前列表项。

### strategy ls

列出当前账号策略。

```bash
jqcli --env-file .env --format json strategy ls
jqcli --env-file .env --format json strategy ls --limit 10
jqcli --env-file .env --format json strategy ls --all
```

参数：

- `--sort name|created|updated`：本地排序参数，默认 `updated`
- `--limit <n>`：默认 `50`
- `--all`：不按 limit 截断

输出：

```json
{
  "items": [
    {
      "id": "7ee9a660be05973fd75e78ad0d976250",
      "internal_id": "1b2162d3e756996fd98e62e027ef53e3",
      "name": "全天候ETF",
      "type": "Code",
      "created_at": "",
      "updated_at": "2026-04-25 20:44:41",
      "run_count": 0,
      "backtest_count": 6
    }
  ]
}
```

字段说明：

- `id`：编辑链接中的当前 `algorithmId`，用于 `strategy show/edit/rm` 和 `backtest run/ls`
- `internal_id`：列表行 `_algorithmId`
- `folder_id`：如果策略在文件夹中，可能返回该字段
- `created_at`：当前列表页未稳定提供，通常为空字符串

### strategy show

查看策略详情。

```bash
jqcli --env-file .env --format json strategy show <strategy_id>
jqcli --env-file .env --format json strategy show <strategy_id> --code
jqcli --env-file .env strategy show <strategy_id> --output strategy.py --force
```

参数：

- `--code`：输出策略源码
- `--output <path>`：将源码写入文件，隐含 `--code`
- `--force`：覆盖已存在输出文件

输出：

```json
{
  "id": "7ee9a660be05973fd75e78ad0d976250",
  "save_id": "2b579058c142e5ecb58627a128ae2645",
  "backtest_id": "34df343239d1055d091782e071fb7e93",
  "name": "全天候ETF",
  "type": "Code",
  "code": "def initialize(context):\n    pass\n"
}
```

### strategy new

新建策略。

```bash
jqcli --env-file .env --format json strategy new "新策略"
jqcli --env-file .env --format json strategy new "新策略" --file strategy.py
printf 'def initialize(context):\n    pass\n' | jqcli --env-file .env --format json strategy new "新策略" --code-stdin
```

参数：

- `--file <path>`：读取 UTF-8 源码文件
- `--code-stdin`：从 stdin 读取源码
- `--type stock|futures`：默认 `stock`

如果不传源码，会创建最小可运行模板。

输出：

```json
{
  "id": "current-list-algorithm-id",
  "save_id": "save-form-algorithm-id",
  "name": "新策略",
  "type": "stock"
}
```

### strategy edit

修改策略名称或源码。

```bash
jqcli --env-file .env --format json strategy edit <strategy_id> --name "新名称"
jqcli --env-file .env --format json strategy edit <strategy_id> --file strategy.py
printf 'def initialize(context):\n    pass\n' | jqcli --env-file .env --format json strategy edit <strategy_id> --code-stdin
```

参数：

- `--name <name>`：修改策略名称
- `--file <path>`：用文件内容替换源码
- `--code-stdin`：用 stdin 内容替换源码

`--file` 和 `--code-stdin` 互斥；未提供 `--name`、`--file`、`--code-stdin` 时返回参数错误。

输出：

```json
{
  "id": "current-list-algorithm-id",
  "save_id": "save-form-algorithm-id",
  "name": "新名称",
  "ok": true
}
```

### strategy rm

删除策略。

```bash
jqcli --env-file .env --non-interactive --format json strategy rm <strategy_id> --yes
```

参数：

- `--yes` / `-y`：确认删除

非交互模式下不传 `--yes` 会失败并返回 `confirmation_required`。

输出：

```json
{
  "ok": true,
  "id": "strategy_id",
  "response": {
    "code": "00000"
  }
}
```

## Backtest API

回测接口保留两种聚宽服务端路径：

- 正式回测：默认模式，进入聚宽正式回测列表
- 编译运行：`--compile` 模式，只做编译运行，进入 build list

两种模式都提交到：

```text
POST /algorithm/index/build
```

关键差异：

| 模式 | CLI 参数 | `backtest[type]` | 列表接口 | 删除接口 |
|------|----------|------------------|----------|----------|
| 正式回测 | 默认 | `0` | `/algorithm/backtest/list` | `/algorithm/backtest/del?type=0` |
| 编译运行 | `--compile` | `1` | `/algorithm/backtest/buildList` | `/algorithm/backtest/del?type=1` |

### backtest run

发起正式回测，默认不等待完成。

```bash
jqcli --env-file .env --format json --non-interactive backtest run <strategy_id> --start 2024-01-02 --end 2024-01-10 --capital 1000000
```

发起编译运行：

```bash
jqcli --env-file .env --format json --non-interactive backtest run <strategy_id> --start 2024-01-02 --end 2024-01-10 --compile
```

参数：

- `--start <YYYY-MM-DD>`：必填
- `--end <YYYY-MM-DD>`：可选，默认本地今日
- `--capital <amount>`：初始资金
- `--freq day|minute`：默认 `day`
- `--compile`：使用编译运行模式
- `--wait`：轮询详情直到终态或超时
- `--poll-interval <seconds>`：默认 `5`

正式回测输出：

```json
{
  "id": "55544646",
  "list_id": "34df343239d1055d091782e071fb7e93",
  "strategy_id": "7ee9a660be05973fd75e78ad0d976250",
  "mode": "backtest",
  "status": "running",
  "response": {
    "data": {
      "algorithmId": "2b579058c142e5ecb58627a128ae2645",
      "backtestId": "34df343239d1055d091782e071fb7e93",
      "backtestId_": "55544646",
      "tradeDays": [1704124800]
    },
    "status": "0",
    "code": "00000",
    "msg": ""
  }
}
```

字段说明：

- `id`：详情 ID，传给 `backtest show`
- `list_id`：列表记录 ID，建议传给 `backtest rm`
- `mode`：`backtest` 或 `compile`
- `response`：聚宽原始响应，保留用于排查

### backtest ls

列出正式回测记录。

```bash
jqcli --env-file .env --format json backtest ls <strategy_id>
jqcli --env-file .env --format json backtest ls <strategy_id> --limit 10
```

列出编译运行记录：

```bash
jqcli --env-file .env --format json backtest ls <strategy_id> --compile
```

参数：

- `--status all|running|done|failed`：默认 `all`
- `--limit <n>`：默认 `50`
- `--all`：不按 limit 截断
- `--compile`：读取编译运行列表

输出：

```json
{
  "items": [
    {
      "id": "b1c8059fddb8cc515b825fa9500271f6",
      "list_id": "9d0018152c49f2a9023c26473610ba7a",
      "source_id": "eff29de3bc4308d804671fbfa305ee09",
      "strategy_id": "7ee9a660be05973fd75e78ad0d976250",
      "name": "全天候ETF",
      "status": "done",
      "start_date": "2024-01-02",
      "end_date": "2024-01-10",
      "capital": 1000000.0,
      "frequency": "每天",
      "metrics": {
        "algorithm_return": "--",
        "benchmark_return": "--",
        "max_drawdown": "--"
      },
      "submitted_at": "2026-04-25 20:51:26"
    }
  ]
}
```

注意：聚宽列表页初始 HTML 中指标可能是 `--`，完整指标以 `backtest show` 调用详情统计接口为准。

### backtest show

查看回测详情、源码和统计指标。

```bash
jqcli --env-file .env --format json backtest show <backtest_id>
```

真实接口：

- 详情页：`GET /algorithm/backtest/detail?backtestId=<id>`
- 源码：`GET /algorithm/backtest/source?backtestId=<source_id>`
- 指标：`GET /algorithm/backtest/stats?backtestId=<source_id>`

输出：

```json
{
  "id": "55544646",
  "list_id": "",
  "strategy_id": "",
  "status": "done",
  "start_date": "",
  "code": "from jqdata import *\n...",
  "metrics": {
    "trading_days": 7,
    "algorithm_return": 0.0053687416399999,
    "benchmark_return": 0.00328947368421,
    "annual_algo_return": 0.21073535248402,
    "annual_bm_return": 0.12444367253539,
    "sharpe": 3.7356032973192,
    "sortino": 7.6674135266037,
    "max_drawdown": 0.0035792419084949,
    "max_drawdown_period": ["2024-01-02", "2024-01-04"],
    "turnover_rate": 0.10606310253703
  }
}
```

### backtest rm

删除正式回测记录。

```bash
jqcli --env-file .env --non-interactive --format json backtest rm <list_id> --yes
```

删除编译运行记录：

```bash
jqcli --env-file .env --non-interactive --format json backtest rm <list_id> --yes --compile
```

参数：

- `--yes` / `-y`：确认删除
- `--compile`：删除编译运行记录，否则删除正式回测记录

建议传 `backtest ls` 返回的 `list_id`。非交互模式下不传 `--yes` 会失败并返回 `confirmation_required`。

输出：

```json
{
  "ok": true,
  "id": "9d0018152c49f2a9023c26473610ba7a",
  "mode": "backtest",
  "response": {
    "data": [],
    "status": "0",
    "code": "00000",
    "msg": ""
  }
}
```

## 状态与错误码

回测列表状态映射：

| 聚宽状态 | jqcli 状态 |
|----------|------------|
| `0` | `running` |
| `1` | `failed` |
| `2` | `done` |
| `3` | `cancelled` |

其他未知状态会原样返回，例如聚宽列表中可能出现 `"4"`。

错误码：

| 场景 | 退出码 | 错误代码 |
|------|--------|----------|
| 未登录/认证过期 | 1 | `not_authenticated` |
| 资源不存在 | 2 | `not_found` |
| 参数错误 | 3 | `usage_error` |
| API 请求失败 | 4 | `api_error` |
| 网络错误 | 5 | `network_error` |
| 文件读写失败 | 6 | `file_error` |
| 需要确认但处于非交互模式 | 7 | `confirmation_required` |
| 等待超时 | 8 | `timeout` |

## 真实测试记录

截至 2026-04-25，已用真实聚宽账号验证：

- `auth login/status/logout/import-cookie`
- `strategy ls/show/new/edit/rm`
- `backtest run/ls/show/rm`
- 默认正式回测进入 `/algorithm/backtest/list`
- `--compile` 编译运行使用 `/algorithm/backtest/buildList`

最近一次保留在服务器上的正式回测：

```json
{
  "strategy_name": "全天候ETF",
  "strategy_id": "7ee9a660be05973fd75e78ad0d976250",
  "backtest_detail_id": "55544646",
  "submitted_at": "2026-04-25 20:51:26",
  "start_date": "2024-01-02",
  "end_date": "2024-01-10",
  "capital": 1000000,
  "algorithm_return": 0.0053687416399999,
  "benchmark_return": 0.00328947368421,
  "sharpe": 3.7356032973192,
  "max_drawdown": 0.0035792419084949
}
```

## 开发与测试

运行测试：

```bash
.venv/bin/python -m pytest
```

当前测试覆盖 API 解析、CLI 参数、非交互确认、JSON 输出和配置读取。
