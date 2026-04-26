# jqcli

聚宽（JoinQuant）策略与回测管理命令行工具。

`jqcli` 面向自动化调用和真实聚宽网页接口封装，支持认证、策略管理、正式回测、编译运行记录查询与删除、社区最新文章列表。所有命令都可以使用 `--non-interactive --format json` 作为机器可读主路径。

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

注意：聚宽列表页初始 HTML 中指标可能是 `--`，完整指标以 `backtest stats` 调用统计接口为准。

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

### backtest stats

读取回测收益和风险指标。公开社区回测可不传登录态；私有回测仍需 `--env-file .env`。

```bash
jqcli --format json backtest stats <backtest_id>
```

真实接口：

- `GET /algorithm/backtest/stats?backtestId=<backtest_id>`

主要字段：

- `algorithm_return`：策略收益
- `benchmark_return`：基准收益
- `annual_algo_return`：年化收益
- `annual_bm_return`：基准年化收益
- `max_drawdown`：最大回撤
- `sharpe`、`sortino`、`information`、`alpha`、`beta`
- `win_ratio`、`profit_loss_ratio`、`turnover_rate`

### backtest result

读取回测收益曲线数据。

```bash
jqcli --format json backtest result <backtest_id>
jqcli --format json backtest result <backtest_id> --offset 0 --user-record-offset 0
```

真实接口：

- `GET /algorithm/backtest/result?backtestId=<backtest_id>&offset=<offset>&userRecordOffset=<user_record_offset>`

返回 `data.result.overallReturn`、`data.result.benchmark` 和可选 `data.userRecord`，用于绘制策略收益曲线、基准曲线和用户记录曲线。

### backtest logs

读取回测运行日志或错误日志，供自动调优流程定位编译错误、运行异常和策略输出。

```bash
jqcli --env-file .env --format json backtest logs <backtest_id>
jqcli --env-file .env --format json backtest logs <backtest_id> --offset 100
jqcli --env-file .env --format json backtest logs <backtest_id> --all
jqcli --env-file .env --format json backtest logs <backtest_id> --error
```

真实接口：

- 普通日志：`GET /algorithm/backtest/log?backtestId=<backtest_id>&offset=<offset>`
- 错误日志：`GET /algorithm/backtest/error?backtestId=<backtest_id>`

主要字段：

- `logs`：日志行数组
- `state`：回测状态
- `next_offset`：下一页普通日志 offset
- `max`：页面提示需导出完整日志时为 `true`

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

## Community API

社区最新文章列表基于用户可访问的聚宽社区页面实现。

页面入口：

```text
https://www.joinquant.com/view/community/list?listType=1&type=isNewPublish&tags=
```

真实接口：

```text
GET /community/post/listV2
GET /community/post/detailV2
GET /community/post/replyList
POST /community/post/checkBacktestView
POST /community/post/dealCreditsHander
```

默认参数：

```text
limit=50
page=1
type=isNewPublish
cate=3
tags=
```

分类说明：

- `listType=1` 为“文章”
- 前端先请求 `/community/post/tagList`，其中 `type=1` 对应 `tagId=3`
- 因此文章列表实际提交 `cate=3`

### community latest

读取社区最新发帖列表。默认读取 1 页，每页 50 条。

```bash
jqcli --format json community latest
```

指定页数：

```bash
jqcli --format json community latest --max-pages 3
```

指定截止时间或日期：

```bash
jqcli --format json community latest --until 2026-04-25
jqcli --format json community latest --until "2026-04-25 12:00:00"
```

长时间拉取时逐条输出 NDJSON：

```bash
jqcli community latest --until 2026-04-25 --stream
jqcli community latest --since-id <last_seen_post_id> --stream
```

参数：

- `--page-size <n>`：每页条数，默认 `50`
- `--max-pages <n>`：最多读取页数；不传且未设置 `--until` 时默认 1 页
- `--until <date|datetime>`：读取到该发布时间为止，支持 `YYYY-MM-DD` 或 `YYYY-MM-DD HH:MM:SS`
- `--list-type <n>`：默认 `1`，当前用于文章分类
- `--tags <ids>`：标签 ID，多个用逗号分隔
- `--since-id <post_id>`：遇到指定文章 ID 后停止，适合外部保存上次处理到的游标
- `--stream`：逐条输出 NDJSON；不传时仍保持兼容，一次性返回包含 `items` 的 JSON 或表格

置顶帖处理：

- 聚宽最新发帖接口会把置顶帖放在列表前面，即使置顶帖的发布时间很早。
- 使用 `--until` 时，`jqcli` 会跳过早于截止时间的置顶帖，但不会因为置顶帖而停止翻页。
- 只有遇到早于截止时间的非置顶文章时，才认为已经读取到截止位置并停止。

输出模式：

- 默认模式：逐页拉取后在内存中聚合为 `items`，命令结束时一次性输出完整 JSON 或表格。
- `--stream` 模式：每行输出一个 JSON 对象并立即 flush，包含 `post`、`progress` 和 `done` 事件，适合重定向到 `.jsonl` 文件或管道消费。

输出：

```json
{
  "items": [
    {
      "id": "990cd272a9801944845af14b1632b9ad",
      "title": "红利低波ETF RSI择时策略-年化21回撤13",
      "url": "https://www.joinquant.com/view/community/detail/990cd272a9801944845af14b1632b9ad",
      "author": {
        "id": "e7ce9f37b2a20675e30527d3f81e5059",
        "name": "凌空飞影"
      },
      "published_at": "2026-04-25 21:05:05",
      "updated_at": "2026-04-25 21:05:05",
      "last_active_at": "2026-04-25 21:05:05",
      "last_reply_at": "",
      "reply_count": 0,
      "view_count": 66,
      "like_count": 1,
      "collection_count": 2,
      "is_top": false,
      "is_best": false,
      "backtest": {
        "id": "947c5c8b3fa520bfdb1fe86d32e2d67f",
        "clone_count": 3,
        "pic_url": ""
      },
      "research": {
        "notebook_path": "",
        "notebook_report": "",
        "notebook_clone_count": 0
      },
      "file": {
        "key": "",
        "name": "",
        "type": "",
        "download_count": 0
      },
      "tags": [
        {
          "id": "1395",
          "name": "本地数据JQData"
        }
      ],
      "content_preview": "---\n## 策略简介\n..."
    }
  ],
  "page_size": 50,
  "pages_read": 1,
  "max_pages": 1,
  "until": null,
  "since_id": "",
  "stopped_by_until": false,
  "stopped_by_since_id": false,
  "total_count": 33894,
  "curr_time": "2026-04-25 21:39:18"
}
```

`--stream` 输出示例：

```jsonl
{"type":"post","page":1,"item":{"id":"990cd272a9801944845af14b1632b9ad","title":"红利低波ETF RSI择时策略-年化21回撤13"}}
{"type":"progress","page":1,"page_items":50,"items_seen":50,"total_count":33894,"curr_time":"2026-04-25 21:39:18"}
{"type":"done","page_size":50,"pages_read":1,"max_pages":1,"until":null,"since_id":"","stopped_by_until":false,"stopped_by_since_id":false,"total_count":33894,"curr_time":"2026-04-25 21:39:18","items_seen":50}
```

文章附加信息字段：

- `backtest.id`：文章关联回测 ID
- `backtest.clone_count`：回测克隆次数
- `backtest.pic_url`：回测图片 URL，接口有值时返回
- `research.notebook_path`：研究/Notebook 路径
- `research.notebook_report`：研究报告 HTML 路径
- `research.notebook_clone_count`：研究克隆次数
- `file.*`：文章附件 key、文件名、类型和下载次数

### archive community posts

批量归档聚宽社区帖子，支持统一增量同步，也保留旧的列表/回测两阶段模式。

推荐使用统一增量归档：

```bash
.venv/bin/python scripts/archive_community_posts.py \
  --phase sync \
  --store data/community_posts_archive.jsonl \
  --state data/community_posts_archive.state.json
```

`sync` 模式会把列表、详情和回测信息合并到同一个 canonical JSONL。每次运行时：

1. 先读取已有 `--store`。
2. 如指定 `--seed`，或发现旧输出文件，会先把旧数据一次性导入并去重。
3. 从社区列表第一页开始增量抓取，直到遇到本地已有数据的最新发布时间。
4. 对缺失详情的帖子调用 `/community/post/detailV2` 补齐正文和详情字段。
5. 对缺失 `backtest.stats` 的帖子调用 `/algorithm/backtest/stats` 补齐核心回测指标。

复用旧脚本已抓取数据：

```bash
.venv/bin/python scripts/archive_community_posts.py \
  --phase sync \
  --store data/community_posts_archive.jsonl \
  --seed data/community_posts_until_20200101.enriched.jsonl
```

限制单次补齐量，适合试跑或分批补详情：

```bash
.venv/bin/python scripts/archive_community_posts.py \
  --phase sync \
  --store data/community_posts_archive.jsonl \
  --max-detail 500 \
  --max-backtest 500
```

统一归档每行是一篇帖子，去掉 `post/detail/strategy` 这类重复嵌套，保留完整非重复信息：

- 基础字段：`id`、`internal_post_id`、`title`、`url`
- 正文：`content`，以及列表摘要 `content_preview`
- 作者：`author`
- 时间：`published_at`、`updated_at`、`last_active_at`、`last_reply_at`、`last_reply_id`
- 计数和状态：`reply_count`、`view_count`、`like_count`、`dislike_count`、`collection_count`、`is_top`、`is_best`、`is_rich`、`is_worth`
- 分类和元信息：`tags`、`type`、`status`、`ip_address`、`bounty`
- 策略回测：`backtest.id`、`backtest.name`、`backtest.clone_count`、`backtest.pic_url`、`backtest.stats`
- 研究和附件：`research.*`、`file.*`
- 抓取元信息：`list_fetched_at`、`detail_fetched_at`

旧的两阶段模式仍可使用：

```bash
# 1. 只抓列表信息，持续翻页直到空页、--until 或 --max-pages
.venv/bin/python scripts/archive_community_posts.py \
  --phase list \
  --list-out data/community_posts.list.jsonl \
  --until 2020-01-01

# 2. 从列表 JSONL 读取帖子，再补全 backtest.stats
.venv/bin/python scripts/archive_community_posts.py \
  --phase enrich \
  --list-out data/community_posts.list.jsonl \
  --enriched-out data/community_posts.enriched.jsonl \
  --backtest-workers 4
```

默认 `--phase all` 会先抓列表，再补全回测信息。列表阶段只使用 `/community/post/listV2`，不会抓正文详情和回复；补全阶段只对有 `backtest.id` 的帖子调用 `/algorithm/backtest/stats`。

列表 JSONL 每行是一篇帖子，保留核心字段：

- `id`、`title`、`url`
- `author`
- `published_at`、`updated_at`、`last_active_at`、`last_reply_at`
- `reply_count`、`view_count`、`like_count`、`collection_count`
- `tags`、`content_preview`
- `backtest.id`、`backtest.clone_count`、`backtest.pic_url`
- `research.*`、`file.*`

补全后的 JSONL 会在 `backtest.stats` 下追加核心指标：

- `algorithm_return`、`benchmark_return`
- `annual_algo_return`、`annual_bm_return`
- `max_drawdown`、`max_drawdown_period`
- `sharpe`、`sortino`、`information`
- `alpha`、`beta`
- `algorithm_volatility`、`benchmark_volatility`
- `win_ratio`、`profit_loss_ratio`、`turnover_rate`、`trading_days`

断点和去重：

- 默认开启 `--resume`。
- 列表阶段会读取已存在的 list JSONL，跳过已写入的 `id`。
- 状态文件记录 `last_page`，续跑时从下一页继续。
- 补全阶段会读取已存在的 enriched JSONL，跳过已补全的 `id`。
- 传 `--force` 会删除本阶段输出文件后重跑。

常用参数：

- `--store <path>`：统一归档 JSONL，默认 `data/community_posts_archive.jsonl`
- `--seed <path>`：导入旧 JSONL，可传多次
- `--page-size <n>`：列表接口每页条数，默认 `50`
- `--until <date|datetime>`：抓到该发布时间以前停止
- `--max-pages <n>`：最多抓到指定页
- `--page-sleep <seconds>`：列表翻页间隔
- `--backtest-workers <n>`：回测 stats 并发数，默认 `4`
- `--detail-workers <n>`：文章详情并发数，默认 `4`
- `--skip-detail`：不补文章详情
- `--skip-backtest`：不补回测 stats
- `--max-detail <n>`：本次最多补齐多少条详情
- `--max-backtest <n>`：本次最多补齐多少条回测 stats
- `--retries <n>`：stats 请求失败重试次数，默认 `2`

### community detail

读取文章详情，包含文章正文、文章内策略信息和讨论区。

```bash
jqcli --format json community detail <post_id>
```

读取多页讨论区：

```bash
jqcli --format json community detail <post_id> --reply-pages 3
jqcli --format json community detail <post_id> --all-replies
jqcli --format json community detail <post_id> --with-backtest-stats
```

参数：

- `post_id`：文章 ID，通常来自 `community latest` 输出的 `id`
- `--reply-page <n>`：讨论区起始页，默认 `1`
- `--reply-pages <n>`：读取讨论区页数，默认 `1`
- `--all-replies`：读取全部讨论区页；聚宽讨论区每页 20 条
- `--with-backtest-stats`：文章带策略回测时，额外读取收益/风险指标并放入 `strategy.backtest.stats`

真实接口：

- 文章详情：`GET /community/post/detailV2?postId=<post_id>`
- 讨论区：`GET /community/post/replyList?postId=<post_id>&page=<page>`
- 回测指标：`GET /algorithm/backtest/stats?backtestId=<backtest_id>`，仅传 `--with-backtest-stats` 时请求
- 展开子回复时，聚宽前端同样使用 `replyList`，参数增加 `oReplyId=<reply_id>`；当前详情输出包含接口已随主回复返回的子回复和剩余数量。

输出：

```json
{
  "post": {
    "id": "19e1885a8221879759080258c9c84061",
    "requested_id": "10e87b3f20c7d720419299d3a2d4d219",
    "title": "红利低波ETF RSI择时策略-年化21回撤13",
    "url": "https://www.joinquant.com/view/community/detail/10e87b3f20c7d720419299d3a2d4d219",
    "content": "---\n## 策略简介\n...",
    "author": {
      "id": "dbb53ca26723ebef4df12fc3b4bed219",
      "name": "凌空飞影",
      "head_img_key": "",
      "vip_type": ""
    },
    "published_at": "2026-04-25 21:05:05",
    "updated_at": "2026-04-25 21:05:05",
    "reply_count": 1,
    "view_count": 101,
    "like_count": 2,
    "collection_count": 2,
    "backtest": {
      "id": "5b080ec242d8ab0755d446f2068eba4e",
      "name": "红利低波ETF_RSI择时策略",
      "clone_count": 5
    },
    "research": {
      "notebook_path": "",
      "notebook_report": "",
      "notebook_clone_count": 0
    },
    "file": {
      "key": "",
      "name": "",
      "type": "",
      "size": 0,
      "download_count": 0
    },
    "tags": [
      {
        "id": "1",
        "name": "策略"
      }
    ]
  },
  "strategy": {
    "backtest": {
      "id": "5b080ec242d8ab0755d446f2068eba4e",
      "name": "红利低波ETF_RSI择时策略",
      "clone_count": 5
    },
    "research": {
      "notebook_path": "",
      "notebook_report": "",
      "notebook_clone_count": 0
    },
    "file": {
      "key": "",
      "name": "",
      "type": "",
      "size": 0,
      "download_count": 0
    }
  },
  "discussion": {
    "items": [
      {
        "id": "ceaa7f36920ad9d435d6478a3de3f1d6",
        "content": "红利低波plus策略, 回测对比仅买入持有收益明显增强.",
        "author": {
          "id": "8f3116afba34e0a6ba9dc02bb0ce7574",
          "name": "K998800"
        },
        "published_at": "2026-04-25 21:55:52",
        "backtest": {
          "id": "",
          "name": "",
          "overall_return": null
        },
        "sub_replies": [],
        "sub_reply_remaining_count": 0
      }
    ],
    "bounty_items": [],
    "start_page": 1,
    "pages_read": 1,
    "max_pages": null,
    "total_count": 1,
    "can_choose_best": false,
    "is_faq": false,
    "curr_time": "2026-04-25 22:18:23"
  }
}
```

### community clone-strategy

读取文章中回测策略的克隆检查信息，或确认后执行克隆。

默认只调用检查接口，不会扣积分：

```bash
jqcli --env-file .env --format json community clone-strategy <post_id> --backtest-id <backtest_id>
```

确认执行克隆：

```bash
jqcli --env-file .env --format json community clone-strategy <post_id> --backtest-id <backtest_id> --yes
```

参数：

- `post_id`：文章 ID，可使用 `community detail` 或 `community latest` 输出的文章 ID
- `--backtest-id <id>`：文章内回测 ID；不传时会先读取文章详情中的 `strategy.backtest.id`
- `--reply-id <id>`：如果克隆的是讨论区回复中附带的回测，传对应回复 ID
- `--yes`：确认执行克隆；不传时只调用检查接口

真实接口流程：

1. `POST /community/post/checkBacktestView`
   - `postId=<post_id>`
   - `backId=<backtest_id>`
   - `ruleKey=clone_algorithm`
   - 可选 `replyId=<reply_id>`
2. `POST /community/post/dealCreditsHander`
   - 仅传 `--yes` 时调用
   - 提交检查接口返回的 `secret`、`random`、`reason` 等字段

检查输出示例：

```json
{
  "post_id": "10e87b3f20c7d720419299d3a2d4d219",
  "backtest_id": "5b080ec242d8ab0755d446f2068eba4e",
  "reply_id": "",
  "rule_key": "clone_algorithm",
  "can_clone": true,
  "reason": "more",
  "amount": 48,
  "reduce": 10,
  "usable": 2,
  "is_view": true,
  "secret_present": true,
  "random_present": true,
  "url": "",
  "redirect": "",
  "execute": false,
  "hint": "传 --yes 才会执行克隆并可能扣除积分"
}
```

说明：

- `amount`：当前可用积分
- `reduce`：本次克隆预计扣除积分
- `reason=more`：积分充足，可执行克隆
- `reason=deny`：积分不足或无权限
- `secret` 不会输出，只返回 `secret_present`

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
