# jqcli 设计文档

聚宽（JoinQuant）策略与回测管理命令行工具。

MVP 目标：在 Windows 和常见命令行环境中稳定运行，并能被 agent/skill 以非交互方式调用。人类友好的表格、确认提示、编辑器集成可以提供，但不能影响自动化主路径。

---

## 一、设计原则

1. 非交互优先：所有命令都必须支持 `--non-interactive --format json`，不能出现等待输入、打开编辑器、弹出系统对话框等卡点。
2. 跨平台优先：路径、换行、编码、配置目录必须兼容 Windows、macOS、Linux。
3. 简单优先：MVP 只实现必要能力；keyring、复杂分页、并发版本控制等放到后续增强。
4. 机器可读优先：给 agent/skill 调用时，stdout 只输出 JSON 结果，stderr 输出错误和诊断信息。
5. 真实 API 优先：聚宽接口形态以调研结果为准，未验证能力不得硬编码。

---

## 二、整体架构

```
jqcli
├── auth        认证管理
├── strategy    策略管理
├── backtest    回测管理
└── community   社区文章
```

### 技术选型

| 层次 | 选型 | 说明 |
|------|------|------|
| CLI 框架 | `click` | 子命令分组、参数解析、帮助生成 |
| HTTP 客户端 | `httpx` | 同步请求，统一超时 |
| 配置存储 | JSON 文件 | 跨平台配置路径 |
| 凭据来源 | 环境变量优先，配置文件兜底 | 避免 keyring 在 agent/CI 中卡住 |
| 输出渲染 | `rich` 可选 | 只用于 table 输出；JSON 输出不用 rich |
| 语言 | Python 3.9+ | |

### 模块边界

- `commands/`：CLI 参数、非交互规则、输出选择。
- `api/`：远端请求、认证注入、响应解析。
- `config.py`：跨平台配置路径和 JSON 读写。
- `errors.py`：统一异常、退出码、错误代码。
- `output.py`：table/json 输出、stderr 错误输出。

---

## 三、跨平台配置与认证

### 配置路径

默认配置文件按平台选择：

| 平台 | 默认路径 |
|------|----------|
| Windows | `%APPDATA%\\jqcli\\config.json` |
| macOS/Linux | `~/.config/jqcli/config.json` |

全局 `--config <path>` 可覆盖默认路径。为兼容旧版本，可以读取 `~/.jqcli/config.json`，但新写入统一使用平台默认路径。

### 配置文件

```json
{
  "api_base": "https://www.joinquant.com",
  "default_format": "table",
  "timeout": 30,
  "username": "example@email.com",
  "token": "optional-token-or-cookie"
}
```

### 凭据优先级

1. `JQCLI_TOKEN`
2. `JQCLI_COOKIE`
3. `--token <token>` 或 `--cookie <cookie>`，仅用于单次命令
4. 配置文件中的 `token`

MVP 不依赖系统 keyring。后续版本可新增 keyring，但必须保持环境变量和配置文件路径可用，避免 agent/CI 卡住。

### 认证命令

```
jqcli auth status
jqcli auth logout
jqcli auth import-token --token <token>
jqcli auth import-cookie --cookie <cookie>
jqcli auth login --username <user> --password-stdin
```

设计约束：

- `auth login` 不直接接收 `--password <text>`，避免密码出现在 shell history。
- `--password-stdin` 只在显式传入时读取 stdin；`--non-interactive` 下未提供凭据必须直接失败。
- `auth import-token` / `auth import-cookie` 是 agent/skill 的首选认证入口。
- `auth logout` 删除配置文件中的 token/cookie，不影响环境变量。
- 所有 debug、错误和测试快照必须脱敏 token、cookie、password、策略源码。

---

## 四、Agent/Skill 调用规范

推荐 skill 固定使用：

```
jqcli --non-interactive --format json <command> ...
```

全局选项：

```
jqcli [--config <path>]
      [--api-base <url>]
      [--token <token> | --cookie <cookie>]
      [--format {table,json}]
      [--non-interactive]
      [--quiet]
      [--debug]
      [--timeout <seconds>]
      <command> ...
```

规则：

- `--format json` 为全局选项，命令无需重复定义。
- `--non-interactive` 禁止 prompt、确认、打开编辑器、隐式读取 stdin。
- `--quiet` 在成功时只输出核心结果；错误仍输出到 stderr。
- 需要破坏性操作时，非交互模式必须显式传 `--yes`，否则返回 `confirmation_required`。
- 需要读取 stdin 的命令必须显式声明，例如 `--password-stdin`、`--code-stdin`。
- 正常结果输出到 stdout；错误、警告、debug 输出到 stderr。
- JSON 模式下 stdout 必须是合法 JSON，不能混入进度条或说明文字。

JSON 错误格式：

```json
{
  "error": {
    "code": "not_found",
    "message": "策略 abc123 不存在",
    "details": {}
  }
}
```

---

## 五、API 契约

实现 `api/` 前必须先记录真实接口样本，并用 mock 测试固化：

- 登录、token/cookie 校验方式。
- 策略列表、新建、读取、更新、删除接口。
- 回测提交、列表、详情接口。
- 认证失败、资源不存在、限流、服务端错误的响应格式。

MVP 不强制抽象完整领域模型，只要求内部字段稳定映射到 JSON 输出。策略和回测至少包含以下字段：

### Strategy

```json
{
  "id": "abc123",
  "name": "双均线策略",
  "type": "stock",
  "created_at": "2024-01-10T09:00:00+08:00",
  "updated_at": "2024-03-15T14:22:00+08:00"
}
```

### Backtest

```json
{
  "id": "bt-789xyz",
  "strategy_id": "abc123",
  "status": "running",
  "start_date": "2023-01-01",
  "end_date": "2023-12-31",
  "capital": 1000000,
  "frequency": "day",
  "metrics": {}
}
```

时间使用 ISO 8601；CLI 日期输入使用 `YYYY-MM-DD`；百分比在 JSON 中使用小数值，例如 `0.1832`。

---

## 六、命令设计

### `jqcli strategy ls`

列出当前账号下的策略。

```
jqcli strategy ls [--sort {name,created,updated}] [--limit <n>] [--all]
```

- 默认返回最近 50 条。
- `--all` 拉取所有可用数据；是否分页由 API 层内部处理。
- JSON 输出为 `{"items": [...]}`，如果远端返回分页信息，可附带 `has_more`。

### `jqcli strategy new`

新建策略。

```
jqcli strategy new <name> [--file <path> | --code-stdin] [--type {stock,futures}]
```

- `--file` 读取 UTF-8 Python 文件。
- `--code-stdin` 显式从 stdin 读取源码，适合 agent 生成后直接传入。
- 省略源码时创建最小可运行模板。
- `--file` 与 `--code-stdin` 互斥。

### `jqcli strategy edit`

更新策略代码或名称。

```
jqcli strategy edit <strategy_id> [--file <path> | --code-stdin] [--name <name>]
```

- MVP 主路径只支持 `--file` 和 `--code-stdin`。
- `--editor` 不进入 MVP；后续可作为人工便利功能添加。
- 未提供 `--file`、`--code-stdin`、`--name` 时返回参数错误。
- 若远端能提供版本字段，后续再加入冲突检测；MVP 不做复杂并发控制。

### `jqcli strategy show`

查看策略详情与源代码。

```
jqcli strategy show <strategy_id> [--code] [--output <path>] [--force]
```

- `--output` 隐含 `--code`。
- 输出文件存在时默认失败；`--force` 覆盖。
- Windows 路径必须正常支持，例如 `C:\\Users\\me\\strategy.py`。

### `jqcli strategy rm`

删除策略。

```
jqcli strategy rm <strategy_id> [--yes]
```

- 交互终端且未传 `--non-interactive` 时，可以提示用户确认。
- 非交互模式必须传 `--yes`，否则失败并返回 `confirmation_required`。
- 删除是否级联回测记录以远端接口为准，CLI 不做本地假设。

### `jqcli backtest run`

发起回测。

```
jqcli backtest run <strategy_id>
                   --start <YYYY-MM-DD>
                   [--end <YYYY-MM-DD>]
                   [--capital <amount>]
                   [--freq {day,minute}]
                   [--compile]
                   [--wait]
                   [--poll-interval <seconds>]
```

- `--end` 默认今日，按本地日期计算。
- 默认发起正式回测，提交 `backtest[type]=0`，记录进入 `/algorithm/backtest/list`。
- `--compile` 保留聚宽编译运行路径，提交 `backtest[type]=1`，记录进入 `/algorithm/backtest/buildList`。
- 两种方式都 POST `/algorithm/index/build`，差异由 `backtest[type]` 决定。
- 默认异步提交并返回详情 ID 和列表 ID。
- `--wait` 轮询直到完成、失败或全局 `--timeout` 到期。
- Ctrl-C 只停止本地等待，不取消远端回测。

### `jqcli backtest ls`

列出某策略下的回测记录。

```
jqcli backtest ls <strategy_id> [--status {all,running,done,failed}] [--limit <n>] [--all] [--compile]
```

- 默认返回最近 50 条。
- `--all` 拉取所有可用数据。
- 默认请求正式回测列表 `/algorithm/backtest/list`。
- `--compile` 请求编译运行列表 `/algorithm/backtest/buildList`。
- 状态枚举按真实 API 校准，内部至少归一为 `running`、`done`、`failed`。

### `jqcli backtest show`

查看回测详情。

```
jqcli backtest show <backtest_id>
```

- `running`：展示状态、策略 ID、提交时间等可用信息。
- `failed`：展示失败原因。
- `done`：展示收益、风险、交易统计等可用指标。
- JSON 输出保留远端可用指标，不强制做复杂归一化。

### `jqcli backtest rm`

删除回测记录。

```
jqcli backtest rm <backtest_id> [--yes] [--compile]
```

- 默认请求 `/algorithm/backtest/del?type=0` 删除正式回测。
- `--compile` 请求 `/algorithm/backtest/del?type=1` 删除编译运行记录。
- 建议传 `backtest ls` 返回的 `list_id`。
- 非交互模式必须传 `--yes`。

### `jqcli community latest`

读取聚宽社区最新发帖列表。

```
jqcli community latest
                       [--page-size <n>]
                       [--max-pages <n>]
                       [--until <YYYY-MM-DD|YYYY-MM-DD HH:MM:SS>]
                       [--list-type <n>]
                       [--tags <ids>]
```

- 默认请求 `/community/post/listV2`，参数为 `limit=50&page=1&type=isNewPublish&cate=3&tags=`。
- `listType=1` 为文章分类，聚宽前端通过 `/community/post/tagList` 将其映射到 `cate=3`。
- 未传 `--max-pages` 且未传 `--until` 时只读取 1 页。
- 传 `--max-pages` 时最多读取指定页数。
- 传 `--until` 时按文章发布时间 `addTime` 截止；日期格式按当天 `00:00:00` 处理。
- 聚宽会把置顶帖放在最新列表前面。截止判断中，早于截止时间的置顶帖会被跳过但不会触发停止；早于截止时间的非置顶文章才触发停止翻页。
- JSON 输出包含 `items`、`page_size`、`pages_read`、`max_pages`、`until`、`stopped_by_until`、`total_count` 和 `curr_time`。

### `jqcli community detail`

读取聚宽社区文章详情、文章内策略信息和讨论区。

```
jqcli community detail <post_id>
                        [--reply-page <n>]
                        [--reply-pages <n>]
                        [--all-replies]
```

- 文章详情请求 `/community/post/detailV2?postId=<post_id>`。
- 讨论区请求 `/community/post/replyList?postId=<post_id>&page=<page>`。
- 默认读取讨论区第 1 页；`--reply-pages` 读取多页；`--all-replies` 按 `totalCount` 读取全部页。
- 输出顶层为 `post`、`strategy` 和 `discussion`。
- `post.backtest`、`post.research`、`post.file` 为文章内策略/研究/附件信息；`strategy` 顶层重复这些字段，便于调用方直接读取。
- `discussion.items[*].backtest` 表示回复中附带的回测信息；`sub_replies` 表示接口随主回复返回的子回复，`sub_reply_remaining_count` 表示仍需展开的子回复数量。

### `jqcli community clone-strategy`

检查或执行文章内回测策略克隆。

```
jqcli community clone-strategy <post_id>
                               [--backtest-id <id>]
                               [--reply-id <id>]
                               [--yes]
```

- 该命令需要登录态。
- 默认只请求 `/community/post/checkBacktestView`，参数为 `postId`、`backId`、`ruleKey=clone_algorithm`，不会扣积分。
- `--backtest-id` 不传时，先调用 `community detail` 的详情接口解析 `strategy.backtest.id`。
- 传 `--yes` 时，先调用检查接口，再把检查接口返回的 `secret`、`random`、`reason` 等字段提交给 `/community/post/dealCreditsHander` 执行克隆。
- JSON 检查输出会隐藏 `secret`，只返回 `secret_present` 和 `random_present`。
- 回复中附带回测时可传 `--reply-id`。

---

## 七、错误处理

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

click 参数错误保持 click 默认格式；JSON 模式下也需要保证 stderr 中输出 JSON 错误对象。

---

## 八、项目结构

```
jqcli/
├── jqcli/
│   ├── __init__.py
│   ├── cli.py
│   ├── api/
│   │   ├── __init__.py
│   │   ├── client.py
│   │   ├── auth.py
│   │   ├── strategy.py
│   │   ├── backtest.py
│   │   └── community.py
│   ├── commands/
│   │   ├── __init__.py
│   │   ├── auth.py
│   │   ├── strategy.py
│   │   ├── backtest.py
│   │   └── community.py
│   ├── config.py
│   ├── errors.py
│   └── output.py
├── tests/
│   ├── test_api/
│   ├── test_commands/
│   ├── test_config.py
│   └── test_output.py
├── pyproject.toml
└── README.md
```

后续增强再考虑：

- `credentials.py` / keyring 集成。
- `models.py` 中的完整领域模型。
- `--editor` 人工编辑模式。
- 更细的分页参数 `--page`。
- 远端版本冲突检测。

---

## 九、测试策略

- Windows 路径测试：配置路径、`--file`、`--output` 覆盖 Windows 风格路径。
- 非交互测试：所有破坏性命令在 `--non-interactive` 且无 `--yes` 时必须失败。
- JSON 测试：`--format json` 下 stdout 必须可被 `json.loads` 解析。
- stdin 测试：只有显式 `--password-stdin`、`--code-stdin` 时才读取 stdin。
- API 测试：使用 `pytest-httpx` 或 `respx` mock 聚宽响应，不访问真实服务。
- 回归测试：每个 MVP 命令至少覆盖一个成功路径和一个错误路径。

---

## 十、实现顺序

1. 项目脚手架和测试配置。
2. 全局选项：`--format`、`--non-interactive`、`--config`、`--timeout`。
3. 跨平台配置路径和环境变量凭据读取。
4. 统一错误、JSON 输出、stdout/stderr 分离。
5. HTTP 客户端和 API mock 样本。
6. `auth status / logout / import-token / import-cookie`。
7. `strategy ls / show`。
8. `strategy new / edit`，支持 `--file` 和 `--code-stdin`。
9. `backtest run / show / ls`。
10. `strategy rm` 和可用时的 `backtest rm`，强制非交互确认规则。
11. 真实账号手工验收，并更新 README 的接口风险说明。
