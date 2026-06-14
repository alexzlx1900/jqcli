# 聚宽首板一进二策略行为等价重构 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 创建一个全新的聚宽策略，在严格保持原策略交易行为和结构化记录一致的前提下，改善单文件代码组织、注释与人工日志可读性。

**Architecture:** 原策略保持只读，并作为远端黄金基线。重构工作在 `.codex_work/` 的本地副本完成，使用静态契约脚本锁定参数、调度、订单调用和关键函数语义，再上传到新策略执行 compile、短区间和完整区间回测。日志重构通过无副作用辅助函数完成，交易计算与结构化记录路径不改变。

**Tech Stack:** Python 3、AST、pytest、jqcli JoinQuant bridge、聚宽回测 API

---

## 文件结构

- Create: `.codex_work/strategy_b69c28a4f69ad63165772d3eddbdccd7_original.py`  
  从远端重新拉取的原策略只读快照。
- Create: `.codex_work/strategy_b69c28a4f69ad63165772d3eddbdccd7_refactored.py`  
  上传到新聚宽策略的行为等价重构版本。
- Create: `.codex_work/strategy_b69c28a4f69ad63165772d3eddbdccd7_baseline.json`  
  原策略元数据、源码摘要、回测 ID 和核心结果摘要。
- Create: `.codex_work/strategy_b69c28a4f69ad63165772d3eddbdccd7_refactored.json`  
  新策略 ID、源码摘要和验证回测 ID。
- Create: `.codex_work/verify_b69_strategy_equivalence.py`  
  本次任务专用的静态与回测结果等价检查器。
- Create: `.codex_work/test_b69_strategy_equivalence.py`  
  等价检查器和日志格式辅助函数的测试。

`.codex_work/` 已用于本仓库的策略工作副本，不纳入 git 提交。仓库只提交设计与实施计划，不提交私有策略源码和回测结果。

### Task 1: 冻结远端黄金基线

- [ ] **Step 1: 验证认证与原策略身份**

Run:

```bash
python skills/joinquant-operator/scripts/jq_skill_bridge.py -- \
  --non-interactive --format json auth status
python skills/joinquant-operator/scripts/jq_skill_bridge.py -- \
  --non-interactive --format json strategy show b69c28a4f69ad63165772d3eddbdccd7
```

Expected: 认证为 `true`；策略名称为 `首板一进二-混合版-增加主题热点和集合竞价因子评分等多处改进`。

- [ ] **Step 2: 重新下载原策略源码**

Run:

```bash
python skills/joinquant-operator/scripts/jq_skill_bridge.py -- \
  strategy show b69c28a4f69ad63165772d3eddbdccd7 \
  --output .codex_work/strategy_b69c28a4f69ad63165772d3eddbdccd7_original.py --force
cp .codex_work/strategy_b69c28a4f69ad63165772d3eddbdccd7_original.py \
  .codex_work/strategy_b69c28a4f69ad63165772d3eddbdccd7_refactored.py
```

Expected: 两个文件初始 SHA-256 一致。

- [ ] **Step 3: 保存原策略正式回测证据**

Run:

```bash
python skills/joinquant-operator/scripts/jq_skill_bridge.py -- \
  --non-interactive --format json backtest ls b69c28a4f69ad63165772d3eddbdccd7 --limit 10
python skills/joinquant-operator/scripts/jq_skill_bridge.py -- \
  --non-interactive --format json backtest stats be8b46b9afa77434edb7067582e46856
python skills/joinquant-operator/scripts/jq_skill_bridge.py -- \
  --non-interactive --format json backtest result be8b46b9afa77434edb7067582e46856
```

Expected: 基线区间为 `2026-01-01` 至 `2026-06-13`，本金 `2,000,000`，收益约 `182.325%`，交易数 `42`。

- [ ] **Step 4: 生成基线 JSON**

保存以下字段到 `.codex_work/strategy_b69c28a4f69ad63165772d3eddbdccd7_baseline.json`：

```json
{
  "strategy_id": "b69c28a4f69ad63165772d3eddbdccd7",
  "strategy_name": "首板一进二-混合版-增加主题热点和集合竞价因子评分等多处改进",
  "source_sha256": "<sha256>",
  "backtest_id": "be8b46b9afa77434edb7067582e46856",
  "start_date": "2026-01-01",
  "end_date": "2026-06-13",
  "capital": 2000000,
  "frequency": "day"
}
```

### Task 2: 建立等价检查器

**Files:**
- Create: `.codex_work/test_b69_strategy_equivalence.py`
- Create: `.codex_work/verify_b69_strategy_equivalence.py`

- [ ] **Step 1: 编写失败的静态契约测试**

测试必须覆盖：

```python
def test_contract_rejects_changed_schedule():
    original = "run_daily(get_buy, time='09:26')"
    changed = "run_daily(get_buy, time='09:27')"
    assert compare_static_contracts(original, changed) == []


def test_contract_rejects_changed_order_style():
    original = "order_value(s, value, MarketOrderStyle(data[s].day_open))"
    changed = "order_value(s, value)"
    assert compare_static_contracts(original, changed) == []


def test_contract_allows_log_text_change():
    original = "log.info('旧日志')"
    changed = "log.info('[盘前摘要] 新日志')"
    assert compare_static_contracts(original, changed) == []
```

前两个测试应因返回差异而失败，第三个测试应通过。

- [ ] **Step 2: 运行测试并确认 RED**

Run:

```bash
pytest -q .codex_work/test_b69_strategy_equivalence.py
```

Expected: 因 `compare_static_contracts` 尚不存在而失败。

- [ ] **Step 3: 实现静态契约提取**

`verify_b69_strategy_equivalence.py` 使用 Python AST 提取并比较：

- `STRATEGY_PARAMS` 中全部字面量
- `run_daily` 调用及顺序
- `order`、`order_value`、`order_target_value` 的调用表达式
- 所有 `if`、`elif`、`return` 的非日志表达式
- 全局状态赋值与结构化记录字段

比较时仅忽略：

- `log.info`、`log.warn`、`log.error` 调用
- 注释、空行、章节标题和文档字符串
- 已明确登记的纯日志辅助函数

- [ ] **Step 4: 实现回测结果比较**

提供以下命令：

```bash
python .codex_work/verify_b69_strategy_equivalence.py static \
  .codex_work/strategy_b69c28a4f69ad63165772d3eddbdccd7_original.py \
  .codex_work/strategy_b69c28a4f69ad63165772d3eddbdccd7_refactored.py

python .codex_work/verify_b69_strategy_equivalence.py result \
  .codex_work/original_result.json \
  .codex_work/refactored_result.json
```

结果比较器逐字段比较订单、交易、收益曲线和核心指标；发现差异时输出首个不同日期、字段和新旧值。

- [ ] **Step 5: 运行测试并确认 GREEN**

Run:

```bash
pytest -q .codex_work/test_b69_strategy_equivalence.py
```

Expected: 全部通过。

### Task 3: 创建隔离的新聚宽策略

- [ ] **Step 1: 使用原始源码创建新策略**

Run:

```bash
python skills/joinquant-operator/scripts/jq_skill_bridge.py -- \
  --non-interactive --format json strategy new \
  "首板一进二-混合版-行为等价重构-v1" \
  --file .codex_work/strategy_b69c28a4f69ad63165772d3eddbdccd7_original.py
```

Expected: 返回一个与 `b69c28a4f69ad63165772d3eddbdccd7` 不同的新策略 ID。

- [ ] **Step 2: 读取新旧策略并验证隔离**

Run:

```bash
python skills/joinquant-operator/scripts/jq_skill_bridge.py -- \
  --non-interactive --format json strategy show b69c28a4f69ad63165772d3eddbdccd7
python skills/joinquant-operator/scripts/jq_skill_bridge.py -- \
  --non-interactive --format json strategy show <new_strategy_id>
```

Expected: 新旧名称和 ID 不同；原策略源码摘要仍与基线一致。

- [ ] **Step 3: 对未重构新策略执行 compile**

Run:

```bash
python skills/joinquant-operator/scripts/jq_skill_bridge.py -- \
  --non-interactive --format json backtest run <new_strategy_id> \
  --start 2026-06-01 --end 2026-06-05 --capital 2000000 --freq day --compile --wait
```

Expected: 未重构副本能够编译运行，证明新策略创建链路正常。

### Task 4: 低风险整理代码结构

**Files:**
- Modify: `.codex_work/strategy_b69c28a4f69ad63165772d3eddbdccd7_refactored.py`

- [ ] **Step 1: 添加九个职责章节标题与文件级说明**

只添加注释和章节分隔，不移动可执行语句。运行：

```bash
python -m py_compile .codex_work/strategy_b69c28a4f69ad63165772d3eddbdccd7_refactored.py
python .codex_work/verify_b69_strategy_equivalence.py static \
  .codex_work/strategy_b69c28a4f69ad63165772d3eddbdccd7_original.py \
  .codex_work/strategy_b69c28a4f69ad63165772d3eddbdccd7_refactored.py
```

Expected: 编译通过；静态契约无差异。

- [ ] **Step 2: 补充关键流程注释和函数文档**

仅为以下入口补充职责、输入和副作用说明：

```text
initialize
before_market_open
get_buy
submit_backtest_buy_orders
get_close_sell
submit_live_buy_orders
submit_live_sell_order
eod_stats
on_strategy_end
```

Expected: 静态契约无差异。

- [ ] **Step 3: 整理局部命名与重复表达式**

仅在静态契约检查器能够证明非日志语义一致的范围内进行；每处理一个函数就运行静态契约检查。若检查器无法证明等价，则保留原实现。

Expected: 参数、调用顺序、条件表达式和结构化记录完全一致。

### Task 5: 重构人工日志

**Files:**
- Modify: `.codex_work/strategy_b69c28a4f69ad63165772d3eddbdccd7_refactored.py`

- [ ] **Step 1: 为日志辅助函数编写失败测试**

测试期望：

```python
def test_format_stage_log_uses_stable_field_order():
    assert format_stage_log("盘前摘要", initial=3048, strong=89) == (
        "[盘前摘要] initial=3048 strong=89"
    )


def test_format_exception_log_explains_fallback():
    assert format_exception_log("市场观察", "保留默认值", "boom") == (
        "[数据异常] 模块=市场观察 动作=保留默认值 交易继续=true 错误=boom"
    )
```

- [ ] **Step 2: 确认 RED 后实现纯日志辅助函数**

辅助函数只拼接字符串，不读取或修改 `g`、`context`、订单和行情数据：

```python
def format_stage_log(stage, **fields):
    details = " ".join("{}={}".format(key, value) for key, value in fields.items())
    return "[{}] {}".format(stage, details)


def format_exception_log(module, action, error):
    return "[数据异常] 模块={} 动作={} 交易继续=true 错误={}".format(
        module, action, error
    )
```

- [ ] **Step 3: 分阶段替换日志**

按以下顺序逐批替换并在每批后运行静态契约检查：

1. 初始化与策略配置
2. 盘前筛选与市场观察
3. 竞价观察与候选决策
4. 回测和实盘买入提交
5. 卖出决策与提交
6. 收盘统计、导出和异常日志

日志必须复用已有变量，不允许为了展示日志额外调用行情、因子或订单 API。

- [ ] **Step 4: 添加摘要日志**

摘要只使用当前函数已经计算出的数量和状态：

```text
[盘前摘要]
[竞价摘要]
[买入决策]
[买入提交]
[卖出决策]
[收盘摘要]
[数据异常]
```

Expected: 静态契约无差异，日志能够解释阶段、原因和资金影响。

### Task 6: 上传新策略并执行快速验证

- [ ] **Step 1: 最终本地静态检查**

Run:

```bash
python -m py_compile .codex_work/strategy_b69c28a4f69ad63165772d3eddbdccd7_refactored.py
pytest -q .codex_work/test_b69_strategy_equivalence.py
python .codex_work/verify_b69_strategy_equivalence.py static \
  .codex_work/strategy_b69c28a4f69ad63165772d3eddbdccd7_original.py \
  .codex_work/strategy_b69c28a4f69ad63165772d3eddbdccd7_refactored.py
```

Expected: 全部通过。

- [ ] **Step 2: 再次确认目标是新策略**

Run:

```bash
python skills/joinquant-operator/scripts/jq_skill_bridge.py -- \
  --non-interactive --format json strategy show <new_strategy_id>
```

Expected: 名称为 `首板一进二-混合版-行为等价重构-v1`。

- [ ] **Step 3: 上传重构源码**

Run:

```bash
python skills/joinquant-operator/scripts/jq_skill_bridge.py -- \
  --non-interactive --format json strategy edit <new_strategy_id> \
  --file .codex_work/strategy_b69c28a4f69ad63165772d3eddbdccd7_refactored.py
```

- [ ] **Step 4: 执行 compile 回测并检查错误日志**

Run:

```bash
python skills/joinquant-operator/scripts/jq_skill_bridge.py -- \
  --non-interactive --format json backtest run <new_strategy_id> \
  --start 2026-06-01 --end 2026-06-05 --capital 2000000 --freq day --compile --wait
```

Expected: 状态成功；若失败，先运行 `backtest logs <id> --error`。

- [ ] **Step 5: 执行短区间正式回测**

Run:

```bash
python skills/joinquant-operator/scripts/jq_skill_bridge.py -- \
  --non-interactive --format json backtest run <new_strategy_id> \
  --start 2026-01-01 --end 2026-03-11 --capital 2000000 --freq day --wait
```

Expected: 与原策略同期订单、交易和收益曲线一致，且日志前缀更清晰。

### Task 7: 执行完整行为等价验证

- [ ] **Step 1: 执行完整正式回测**

Run:

```bash
python skills/joinquant-operator/scripts/jq_skill_bridge.py -- \
  --non-interactive --format json backtest run <new_strategy_id> \
  --start 2026-01-01 --end 2026-06-13 --capital 2000000 --freq day --wait
```

- [ ] **Step 2: 下载新策略回测结果**

Run:

```bash
python skills/joinquant-operator/scripts/jq_skill_bridge.py -- \
  --non-interactive --format json backtest stats <new_backtest_id>
python skills/joinquant-operator/scripts/jq_skill_bridge.py -- \
  --non-interactive --format json backtest result <new_backtest_id>
python skills/joinquant-operator/scripts/jq_skill_bridge.py -- \
  --non-interactive --format json backtest logs <new_backtest_id> --all
```

- [ ] **Step 3: 逐字段比较**

Run:

```bash
python .codex_work/verify_b69_strategy_equivalence.py result \
  .codex_work/original_result.json \
  .codex_work/refactored_result.json
```

Expected:

```text
orders: identical
trades: identical
daily_curve: identical
core_stats: identical
```

- [ ] **Step 4: 验证原策略未被修改**

重新下载原策略源码并比较 SHA-256。Expected: 与 Task 1 基线摘要一致。

- [ ] **Step 5: 输出验证摘要**

保存新策略 ID、compile ID、短区间回测 ID、完整回测 ID、源码摘要和等价比较结果到：

`.codex_work/strategy_b69c28a4f69ad63165772d3eddbdccd7_refactored.json`

## 最终验收命令

```bash
python -m py_compile .codex_work/strategy_b69c28a4f69ad63165772d3eddbdccd7_refactored.py
pytest -q .codex_work/test_b69_strategy_equivalence.py
python .codex_work/verify_b69_strategy_equivalence.py static \
  .codex_work/strategy_b69c28a4f69ad63165772d3eddbdccd7_original.py \
  .codex_work/strategy_b69c28a4f69ad63165772d3eddbdccd7_refactored.py
git diff --check
git status --short
```

只有上述本地检查通过、聚宽 compile 成功、完整正式回测逐字段一致且原策略源码摘要不变，才能宣称行为等价重构完成。
