# 聚宽精选策略帖子本地管理网站设计文档

## 1. 目标

建设一个本地 Flask 网站，用来管理已经筛选出的聚宽精选策略帖子。网站以本地归档数据为主，复用现有 `jqcli` 的社区抓取、策略管理和回测接口，提供帖子浏览、策略下载、本地存档、标准化回测、回测结果记录、原创/水贴标签过滤和全局增量刷新能力。

首版重点是可用、可恢复、避免重复请求聚宽接口。所有远端操作都落到本地状态表，页面只展示本地状态，不依赖每次打开页面实时访问聚宽。

## 2. 数据来源

首版使用以下已有数据作为初始数据源：

- `data/community_posts_archive.jsonl`
  - 全量社区帖子归档。
  - 包含列表、详情、回测基础信息和回测核心统计字段。
- `data/original_strategy_candidates.csv`
  - 按“原创策略帖子”规则筛选后的候选集。
- `data/original_strategy_candidates_period_gt_1y.csv`
  - 在原创候选集基础上增加“回测大于 1 年”的候选集。

网站默认展示 `original_strategy_candidates_period_gt_1y.csv`，同时支持切换到全部归档帖子。归档文件继续由 `scripts/archive_community_posts.py --phase sync` 增量维护。

## 3. 功能范围

### 3.1 帖子列表

列表按发布时间倒序展示全部帖子，核心字段：

- 发布时间
- 标题
- 聚宽帖子链接
- 回测周期
- 年化收益
- 夏普
- 克隆次数
- 点赞数
- 回复数
- 本地下载状态
- 本地回测状态
- 水贴/原创分析标签

列表支持：

- 关键词搜索标题和正文摘要。
- 按发布时间范围过滤。
- 按回测周期过滤，例如 `>1 年`、`>3 年`。
- 按夏普、年化收益范围过滤。
- 按是否已下载、是否已回测过滤。
- 按水贴分析标签过滤。

### 3.2 策略下载

下载按钮的业务含义不是直接下载帖子附件，而是：

1. 根据帖子里的 `backtest_id` 或策略卡片信息定位源策略。
2. 先执行克隆操作，把社区策略克隆到当前登录账号的策略列表。
3. 使用本地策略 API 读取克隆后的策略源码。
4. 将源码和元数据保存到本地归档目录。
5. 更新本地数据库状态。

如果本地已经存在归档：

- 不重复克隆。
- 按钮显示为“已下载”。
- 允许用户手动执行“重新下载”，但需要二次确认，避免覆盖本地修改。

### 3.3 标准化回测

回测按钮执行前先生成标准化源码，不直接提交原始源码。

默认回测参数：

- 开始日期：`2021-01-01`
- 结束日期：`2025-12-12`
- 初始资金：`500000`
- 频率：`day`

点击回测时弹窗确认，用户可以修改：

- 开始日期
- 结束日期
- 初始资金
- 回测频率
- 是否覆盖已有标准化脚本
- 是否保存标准化脚本快照

本地已有回测结果时：

- 列表直接展示上次回测的周期、年化收益、夏普、最大回撤和状态。
- 按钮显示“再次回测”。
- 再次回测会生成新的回测任务记录，不覆盖历史记录，只更新帖子上的“最近一次回测”指针。

### 3.4 滑点和交易成本标准化

标准化逻辑在源码的 `initialize(context)` 函数尾部注入以下代码：

```python
set_slippage(FixedSlippage(0.002), type="fund")
# 股票交易总成本0.3%(含固定滑点0.02)
set_slippage(FixedSlippage(0.02), type="stock")
set_order_cost(
    OrderCost(
        open_tax=0,
        close_tax=0.001,
        open_commission=0.0003,
        close_commission=0.0003,
        close_today_commission=0,
        min_commission=5,
    ),
    type="stock",
)
# 设置货币ETF交易佣金0
set_order_cost(
    OrderCost(
        open_tax=0,
        close_tax=0,
        open_commission=0,
        close_commission=0,
        close_today_commission=0,
        min_commission=0,
    ),
    type="mmf",
)
```

注入规则：

- 优先使用 Python `ast` 定位 `initialize` 函数。
- 如果没有 `initialize(context)`，自动新增一个。
- 如果已经存在同样的标准化标记，则不重复注入。
- 注入代码带本地标记注释，便于后续识别和替换。
- 原始源码永远保留，标准化源码另存。

建议注入后的代码块包裹为：

```python
# jqcli-standard-backtest-begin
...
# jqcli-standard-backtest-end
```

这样再次标准化时可以先替换旧块，避免重复插入。

### 3.5 水贴分析标签

帖子详情下载完成后，为每篇帖子生成标签，便于过滤。

标签来源包括：

- 正文长度。
- 是否包含策略思想、选股逻辑、择时逻辑、风控、调仓、参数解释等描述。
- 是否只是简单参数调整。
- 是否只是多个公开策略的简单组合。
- 是否存在代码但缺少解释。
- 回复里的负面评价比例。
- 回测周期、夏普和年化收益是否异常，需要提示可能过拟合。

首版标签建议：

- `原创候选`
- `详细思路`
- `简单调参`
- `简单组合`
- `代码为主`
- `回复争议`
- `回测大于1年`
- `回测大于3年`
- `夏普偏高`
- `疑似过拟合`
- `信息不足`

标签不作为最终结论，只作为筛选辅助。判断分数和命中原因需要保存，页面可展开查看。

### 3.6 全局刷新

页面右上角提供“刷新数据”按钮，执行完整增量流程：

1. 调用 `scripts/archive_community_posts.py --phase sync`。
2. 从当前归档中的最新发布时间向前抓取。
3. 已存在帖子不重复抓取。
4. 缺失详情的帖子补详情。
5. 缺失回测统计的帖子补回测信息。
6. 重新生成本地索引和水贴标签。
7. 页面显示任务进度和刷新结果。

刷新过程作为后台任务运行，避免阻塞 Flask 请求。页面通过轮询任务状态接口更新进度。

## 4. 系统架构

```text
Flask Web UI
  |
  |-- routes: 页面和 JSON API
  |-- services: 下载、回测、刷新、标签分析
  |-- repositories: SQLite 读写
  |
SQLite 本地数据库
  |
本地文件归档
  |-- data/community_posts_archive.jsonl
  |-- data/strategy_manager/strategies/
  |-- data/strategy_manager/backtests/
  |-- data/strategy_manager/jobs/
  |
jqcli API
  |-- community sync
  |-- strategy clone/create/update/show
  |-- backtest run/stats/result
```

建议新增模块：

```text
jqcli/web/
  __init__.py
  app.py
  db.py
  routes.py
  models.py
  services/
    posts.py
    archive_sync.py
    strategy_download.py
    code_standardizer.py
    backtest_runner.py
    post_labels.py
  templates/
    base.html
    posts.html
    post_detail.html
  static/
    app.css
    app.js
```

## 5. 本地存储设计

### 5.1 SQLite

数据库路径：

```text
data/strategy_manager/manager.sqlite3
```

### 5.2 表结构

#### posts

保存帖子和回测卡片的核心展示字段。

```sql
CREATE TABLE posts (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    url TEXT NOT NULL,
    published_at TEXT,
    updated_at TEXT,
    author_name TEXT,
    content TEXT,
    content_preview TEXT,
    view_count INTEGER,
    like_count INTEGER,
    reply_count INTEGER,
    backtest_id TEXT,
    backtest_name TEXT,
    trading_days INTEGER,
    period_years REAL,
    annual_return REAL,
    sharpe REAL,
    max_drawdown REAL,
    clone_count INTEGER,
    is_original_candidate INTEGER DEFAULT 0,
    source TEXT,
    raw_json TEXT,
    created_at TEXT NOT NULL,
    refreshed_at TEXT NOT NULL
);
```

#### post_labels

保存水贴分析标签和命中原因。

```sql
CREATE TABLE post_labels (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    post_id TEXT NOT NULL,
    label TEXT NOT NULL,
    score REAL,
    reason TEXT,
    created_at TEXT NOT NULL,
    UNIQUE(post_id, label)
);
```

#### strategy_archives

保存策略下载状态。

```sql
CREATE TABLE strategy_archives (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    post_id TEXT NOT NULL UNIQUE,
    source_backtest_id TEXT,
    cloned_strategy_id TEXT,
    cloned_strategy_name TEXT,
    original_code_path TEXT,
    standardized_code_path TEXT,
    metadata_path TEXT,
    status TEXT NOT NULL,
    error TEXT,
    downloaded_at TEXT,
    updated_at TEXT NOT NULL
);
```

状态枚举：

- `missing`
- `cloning`
- `downloaded`
- `failed`

#### backtest_runs

保存本地发起的标准化回测记录。

```sql
CREATE TABLE backtest_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    post_id TEXT NOT NULL,
    strategy_archive_id INTEGER,
    remote_strategy_id TEXT,
    remote_backtest_id TEXT,
    start_date TEXT NOT NULL,
    end_date TEXT NOT NULL,
    capital REAL NOT NULL,
    frequency TEXT NOT NULL,
    status TEXT NOT NULL,
    annual_return REAL,
    sharpe REAL,
    max_drawdown REAL,
    trading_days INTEGER,
    metrics_json TEXT,
    result_json_path TEXT,
    submitted_at TEXT,
    completed_at TEXT,
    error TEXT
);
```

状态枚举：

- `pending`
- `submitted`
- `running`
- `done`
- `failed`

#### jobs

保存后台任务状态。

```sql
CREATE TABLE jobs (
    id TEXT PRIMARY KEY,
    type TEXT NOT NULL,
    status TEXT NOT NULL,
    progress_current INTEGER DEFAULT 0,
    progress_total INTEGER,
    message TEXT,
    result_json TEXT,
    error TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    finished_at TEXT
);
```

## 6. 文件归档设计

策略归档目录：

```text
data/strategy_manager/
  manager.sqlite3
  strategies/
    <post_id>/
      original.py
      standardized.py
      metadata.json
  backtests/
    <post_id>/
      <remote_backtest_id>.json
      <remote_backtest_id>.result.json
  jobs/
    <job_id>.log
```

`metadata.json` 保存：

- 帖子 ID 和链接。
- 源回测 ID。
- 克隆后的策略 ID。
- 下载时间。
- 源码哈希。
- 标准化源码哈希。
- 使用的标准化规则版本。

## 7. 后端接口设计

### 页面路由

```text
GET /                     -> 重定向到 /posts
GET /posts                -> 帖子列表页面
GET /posts/<post_id>      -> 帖子详情页面
```

### JSON API

```text
GET  /api/posts
POST /api/posts/reindex
GET  /api/posts/<post_id>
POST /api/posts/<post_id>/download
POST /api/posts/<post_id>/standardize
POST /api/posts/<post_id>/backtests
GET  /api/posts/<post_id>/backtests
GET  /api/backtests/<run_id>
POST /api/refresh
GET  /api/jobs/<job_id>
```

`GET /api/posts` 参数：

- `q`
- `page`
- `page_size`
- `published_from`
- `published_to`
- `min_period_years`
- `min_sharpe`
- `max_sharpe`
- `downloaded`
- `backtested`
- `label`
- `sort`

`POST /api/posts/<post_id>/backtests` 请求体：

```json
{
  "start_date": "2021-01-01",
  "end_date": "2025-12-12",
  "capital": 500000,
  "frequency": "day",
  "force_standardize": true
}
```

## 8. 核心流程

### 8.1 初始化索引

首次启动时：

1. 创建 SQLite 表。
2. 读取 `community_posts_archive.jsonl`。
3. 合并 `original_strategy_candidates_period_gt_1y.csv` 的候选标记。
4. 写入 `posts`。
5. 对缺失标签的帖子运行标签分析。

后续启动只做轻量检查，不重复全量导入。用户点击“重建索引”时才重新导入。

### 8.2 下载策略

```text
用户点击下载
  -> 检查 strategy_archives 是否已有 downloaded
  -> 没有则创建 download job
  -> 根据 post.backtest_id 克隆策略
  -> 获取克隆后 strategy_id
  -> 读取策略源码
  -> 写 original.py 和 metadata.json
  -> 更新 strategy_archives
```

需要补充或确认的底层接口：

- 社区策略克隆接口。
- 克隆后策略 ID 的可靠定位方式。

如果克隆接口返回值不稳定，兜底策略：

1. 克隆前记录当前策略列表。
2. 执行克隆。
3. 克隆后拉取策略列表。
4. 用新增项、更新时间和名称匹配克隆结果。

### 8.3 标准化脚本

```text
读取 original.py
  -> AST 定位 initialize
  -> 移除旧 jqcli-standard-backtest 块
  -> 在 initialize 尾部插入滑点和交易成本代码
  -> 写 standardized.py
  -> 更新 metadata.json
```

标准化失败时不提交回测，页面展示错误原因。

### 8.4 提交回测

```text
用户确认参数
  -> 确保策略已下载
  -> 生成 standardized.py
  -> 更新克隆策略源码
  -> 调用 run_backtest
  -> 写 backtest_runs submitted
  -> 后台轮询 stats/result
  -> 完成后写 metrics 和结果文件
```

回测结果获取：

- 优先 `get_backtest_stats(backtest_id)` 获取核心指标。
- 必要时调用 `get_backtest_result(backtest_id)` 保存完整结果。
- 如果结果还未完成，后台任务按间隔轮询，直到完成、失败或超时。

### 8.5 全局刷新

```text
用户点击刷新
  -> 创建 refresh job
  -> 执行 archive sync
  -> 导入新增/补齐后的 JSONL
  -> 更新 posts
  -> 对新增或正文变化帖子重新生成标签
  -> 返回统计：新增、更新、补详情、补回测、失败数
```

刷新任务需要互斥。同一时间只允许一个 refresh job 运行。

## 9. 前端设计

页面风格以本地管理工具为主，信息密度高、操作明确，不做营销式页面。

### 9.1 列表页

顶部：

- 搜索框。
- 发布时间范围。
- 回测周期筛选。
- 夏普筛选。
- 标签筛选。
- 已下载/已回测筛选。
- 全局刷新按钮。

表格列：

- 发布时间
- 标题
- 回测周期
- 年化
- 夏普
- 标签
- 下载状态
- 最近本地回测
- 操作

操作按钮：

- 打开原帖。
- 下载。
- 回测。
- 查看详情。

### 9.2 回测确认弹窗

字段：

- 开始日期。
- 结束日期。
- 初始资金。
- 频率。
- 是否重新标准化。

弹窗同时展示：

- 本地上次回测参数和结果。
- 本次将使用的克隆策略 ID。
- 标准化脚本路径。

### 9.3 详情页

展示：

- 帖子正文。
- 原始策略卡片回测指标。
- 标签和命中原因。
- 下载归档状态。
- 本地回测历史。
- 原始脚本和标准化脚本路径。

## 10. 安全和幂等

- 所有远端写操作必须依赖本地登录凭据 `.env` 或配置文件。
- 下载和回测动作都写入 job 和状态表，可恢复。
- 本地已有源码不自动覆盖，除非用户确认。
- 标准化脚本与原始脚本分开保存。
- 回测历史不覆盖，只更新最近结果指针。
- 刷新归档只做增量抓取，已有帖子按 ID 合并。

## 11. 依赖

建议新增依赖：

```toml
Flask >= 3.0
```

可选依赖：

```toml
APScheduler >= 3.10
```

首版可以不用 APScheduler，使用 `threading.Thread` 和 SQLite job 表实现后台任务。等任务数量和调度需求变复杂后再引入任务队列。

## 12. 实施步骤

### 第一阶段：只读管理网站

1. 新增 Flask app 骨架。
2. 新增 SQLite 初始化和 JSONL/CSV 导入逻辑。
3. 完成帖子列表、过滤、详情页。
4. 显示已有策略卡片回测指标和原创/水贴标签。

### 第二阶段：策略下载

1. 补充社区策略克隆 API。
2. 实现下载 job。
3. 保存 `original.py` 和 `metadata.json`。
4. 页面展示下载状态。

### 第三阶段：标准化和回测

1. 实现源码标准化模块。
2. 实现回测确认弹窗和提交接口。
3. 实现回测结果轮询和本地保存。
4. 页面展示最近回测和历史回测。

### 第四阶段：全局刷新

1. 接入 `archive_community_posts.py --phase sync`。
2. 实现 refresh job 和进度展示。
3. 刷新后自动更新 SQLite 索引和标签。

## 13. 风险点

- 聚宽克隆接口可能需要从页面 JS 或网络请求继续确认。
- 克隆后策略 ID 返回不稳定时，需要通过策略列表差异定位。
- 部分社区策略可能不可克隆或源码不可读，需要记录失败原因。
- 回测任务耗时较长，必须后台执行并轮询。
- 标准化源码可能遇到非标准 Python 代码，AST 失败时需要保留错误并支持人工处理。
- 聚宽接口可能限流，刷新和回测轮询需要控制并发。

## 14. 首版验收标准

- 本地启动 Flask 后可以打开帖子列表。
- 列表按发布时间倒序展示时间、标题、回测周期、年化、夏普。
- 能按“回测大于 1 年”和水贴标签过滤。
- 已有归档数据不会重复导入。
- 下载按钮能识别本地已下载状态。
- 回测按钮能弹窗确认默认参数。
- 标准化脚本能正确注入滑点和交易成本代码。
- 回测完成后本地保存结果，并在列表展示最近回测周期、年化和夏普。
- 全局刷新能增量拉取最新帖子并补齐缺失详情、回测信息。
