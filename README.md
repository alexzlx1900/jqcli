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

参数：

- `--page-size <n>`：每页条数，默认 `50`
- `--max-pages <n>`：最多读取页数；不传且未设置 `--until` 时默认 1 页
- `--until <date|datetime>`：读取到该发布时间为止，支持 `YYYY-MM-DD` 或 `YYYY-MM-DD HH:MM:SS`
- `--list-type <n>`：默认 `1`，当前用于文章分类
- `--tags <ids>`：标签 ID，多个用逗号分隔

置顶帖处理：

- 聚宽最新发帖接口会把置顶帖放在列表前面，即使置顶帖的发布时间很早。
- 使用 `--until` 时，`jqcli` 会跳过早于截止时间的置顶帖，但不会因为置顶帖而停止翻页。
- 只有遇到早于截止时间的非置顶文章时，才认为已经读取到截止位置并停止。

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
  "stopped_by_until": false,
  "total_count": 33894,
  "curr_time": "2026-04-25 21:39:18"
}
```

文章附加信息字段：

- `backtest.id`：文章关联回测 ID
- `backtest.clone_count`：回测克隆次数
- `backtest.pic_url`：回测图片 URL，接口有值时返回
- `research.notebook_path`：研究/Notebook 路径
- `research.notebook_report`：研究报告 HTML 路径
- `research.notebook_clone_count`：研究克隆次数
- `file.*`：文章附件 key、文件名、类型和下载次数

### community detail

读取文章详情，包含文章正文、文章内策略信息和讨论区。

```bash
jqcli --format json community detail <post_id>
```

读取多页讨论区：

```bash
jqcli --format json community detail <post_id> --reply-pages 3
jqcli --format json community detail <post_id> --all-replies
```

参数：

- `post_id`：文章 ID，通常来自 `community latest` 输出的 `id`
- `--reply-page <n>`：讨论区起始页，默认 `1`
- `--reply-pages <n>`：读取讨论区页数，默认 `1`
- `--all-replies`：读取全部讨论区页；聚宽讨论区每页 20 条

真实接口：

- 文章详情：`GET /community/post/detailV2?postId=<post_id>`
- 讨论区：`GET /community/post/replyList?postId=<post_id>&page=<page>`
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
