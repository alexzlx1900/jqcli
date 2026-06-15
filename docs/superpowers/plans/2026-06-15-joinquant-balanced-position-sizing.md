# 聚宽首板一进二策略平衡仓位 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 基于现有行为等价重构版创建独立的 `首板一进二-混合版-平衡仓位-v1`，用统一、可测试的仓位规划器限制单票和组合集中度，同时定向重构买入预算与日志链路。

**Architecture:** 保持现有选股、评分、买卖调度、订单样式和卖出逻辑不变。新增一个无副作用的平衡仓位规划器，统一计算回测与实盘的候选相对预算、单票绝对容量、组合剩余容量和最终目标预算；回测与实盘执行器只负责各自的交易环境约束。重构范围只覆盖参数、仓位规划、买入执行编排和相关日志，不改写其他策略主体。

**Tech Stack:** Python 3、AST 函数提取测试、pytest、jqcli JoinQuant bridge、聚宽回测 API

---

## 文件结构

- Create: `.worktrees/strategy-b69-refactor/.codex_work/strategy_b69_balanced.py`
  从当前行为等价重构版复制出的平衡仓位策略源码，只上传到新聚宽策略。
- Create: `.worktrees/strategy-b69-refactor/.codex_work/test_b69_balanced_position_sizing.py`
  通过 AST 提取策略纯函数并执行九类预算场景测试。
- Create: `.worktrees/strategy-b69-refactor/.codex_work/verify_b69_balanced_strategy.py`
  检查非买入链路静态契约、平衡仓位约束和回测集中度指标。
- Create: `.worktrees/strategy-b69-refactor/.codex_work/balanced_strategy_metadata.json`
  保存新策略 ID、源码摘要、回测 ID 和核心对比指标。
- Create: `.worktrees/strategy-b69-refactor/.codex_work/balanced_position_report.md`
  保存与行为等价重构版的收益、回撤、持仓集中度和现金比例对比。
- Modify: `.worktrees/strategy-b69-refactor/.codex_work/strategy_b69_balanced.py`
  仅修改平衡仓位参数、预算规划器、买入执行器和对应结构化日志。

`.codex_work/` 与策略私有源码不纳入 git。仓库只提交设计和实施计划；现有远端策略与本地行为等价重构版保持只读。

### Task 1: 冻结行为等价重构版基线

- [ ] **Step 1: 验证认证并解析当前基线策略 ID**

Run:

```bash
cd /Users/zhanglongxiang/Documents/Python/jqcli
python skills/joinquant-operator/scripts/jq_skill_bridge.py -- \
  --non-interactive --format json auth status
python skills/joinquant-operator/scripts/jq_skill_bridge.py -- \
  --non-interactive --format json strategy ls --limit 30 \
  > .worktrees/strategy-b69-refactor/.codex_work/balanced_strategy_list_before.json
python - <<'PY'
import json
path = ".worktrees/strategy-b69-refactor/.codex_work/balanced_strategy_list_before.json"
data = json.load(open(path))
items = [item for item in data["items"] if item["name"] == "首板一进二-混合版-行为等价重构-v1"]
assert len(items) == 1, items
print(items[0]["id"])
PY
```

Expected: 认证为 `true`；名称完全匹配的基线策略只有一个。

- [ ] **Step 2: 复制只读基线源码为新工作副本**

Run:

```bash
cp .worktrees/strategy-b69-refactor/.codex_work/strategy_b69c28a4f69ad63165772d3eddbdccd7_refactored.py \
  .worktrees/strategy-b69-refactor/.codex_work/strategy_b69_balanced.py
shasum -a 256 \
  .worktrees/strategy-b69-refactor/.codex_work/strategy_b69c28a4f69ad63165772d3eddbdccd7_refactored.py \
  .worktrees/strategy-b69-refactor/.codex_work/strategy_b69_balanced.py
```

Expected: 两个源码文件初始 SHA-256 相同。

- [ ] **Step 3: 冻结不可变静态契约**

`verify_b69_balanced_strategy.py` 必须把以下区域视为不可变：

```text
initialize 中除新增参数日志外的调度调用
before_market_open
get_buy 中候选筛选、条件匹配、评分与 qualified_stocks 构造
get_close_sell 及全部卖出辅助函数
订单价格样式与买卖时间
ML、市场承接和影子卖出开关
```

允许变化的函数和字段仅为：

```text
init_strategy_params
get_buy 中调用统一仓位规划器的部分
submit_backtest_buy_orders
build_live_buy_candidates
allocate_live_buy_plan
submit_live_buy_orders
make_candidate_record
新建的 balanced position helper functions
与上述链路直接相关的人工日志
```

- [ ] **Step 4: 为静态契约检查器写失败测试**

在 `test_b69_balanced_position_sizing.py` 中加入：

```python
def test_static_contract_rejects_sell_logic_change(tmp_path):
    original = "def get_close_sell(context):\n    return 'keep'\n"
    changed = "def get_close_sell(context):\n    return 'sell'\n"
    assert compare_protected_functions(original, changed) == []


def test_static_contract_allows_balanced_planner_change():
    original = "def build_balanced_buy_plan(items):\n    return items\n"
    changed = "def build_balanced_buy_plan(items):\n    return []\n"
    assert compare_protected_functions(original, changed) == []
```

- [ ] **Step 5: 确认 RED，随后实现静态契约检查器**

Run:

```bash
pytest -q .worktrees/strategy-b69-refactor/.codex_work/test_b69_balanced_position_sizing.py
```

Expected: 首次因 `compare_protected_functions` 不存在而失败；实现后测试通过，卖出逻辑变化会被报告，允许区变化不会被报告。

### Task 2: 用 TDD 定义平衡仓位纯函数

**Files:**
- Modify: `.worktrees/strategy-b69-refactor/.codex_work/test_b69_balanced_position_sizing.py`
- Modify: `.worktrees/strategy-b69-refactor/.codex_work/strategy_b69_balanced.py`

- [ ] **Step 1: 建立策略纯函数测试夹具**

测试文件先定义真实源码函数提取器和输入构造器：

```python
import ast
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest


STRATEGY_PATH = Path(
    ".worktrees/strategy-b69-refactor/.codex_work/strategy_b69_balanced.py"
)
PURE_FUNCTION_NAMES = {
    "safe_float",
    "clamp_budget_factor",
    "get_condition_prefix",
    "get_condition_position_cap",
    "build_balanced_buy_plan",
    "get_position_total_amount",
    "get_position_market_value",
}


@pytest.fixture
def strategy():
    tree = ast.parse(STRATEGY_PATH.read_text(encoding="utf-8"))
    body = [
        node for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name in PURE_FUNCTION_NAMES
    ]
    namespace = {"np": np, "pd": pd}
    exec(compile(ast.Module(body=body, type_ignores=[]), str(STRATEGY_PATH), "exec"), namespace)
    return SimpleNamespace(**{
        name: namespace[name] for name in PURE_FUNCTION_NAMES if name in namespace
    })


def balanced_params():
    return {
        "portfolio_position_cap": 0.90,
        "default_single_position_cap": 0.30,
        "condition_c_single_position_cap": 0.35,
        "condition_ef_single_position_cap": 0.25,
    }


def candidate(stock, condition, capital_weight, position_factor, risk_factor):
    return {
        "stock": stock,
        "record": {},
        "capital_weight": capital_weight,
        "position_factor": position_factor,
        "risk_budget_factor": risk_factor,
        "matched_condition": condition,
    }
```

- [ ] **Step 2: 编写条件仓位上限失败测试**

```python
def test_condition_position_cap_mapping(strategy):
    params = {
        "default_single_position_cap": 0.30,
        "condition_c_single_position_cap": 0.35,
        "condition_ef_single_position_cap": 0.25,
    }
    assert strategy.get_condition_position_cap("C-强势", params) == 0.35
    assert strategy.get_condition_position_cap("E", params) == 0.25
    assert strategy.get_condition_position_cap("F-修复", params) == 0.25
    assert strategy.get_condition_position_cap("A", params) == 0.30
    assert strategy.get_condition_position_cap("未知", params) == 0.30
```

Run:

```bash
pytest -q .worktrees/strategy-b69-refactor/.codex_work/test_b69_balanced_position_sizing.py \
  -k condition_position_cap_mapping
```

Expected: 因函数尚不存在而失败。

- [ ] **Step 3: 添加四个平衡仓位参数和条件映射函数**

在 `init_strategy_params()` 中新增：

```python
'portfolio_position_cap': 0.90,
'default_single_position_cap': 0.30,
'condition_c_single_position_cap': 0.35,
'condition_ef_single_position_cap': 0.25,
```

实现：

```python
def get_condition_position_cap(matched_condition, params=None):
    params = params or STRATEGY_PARAMS
    prefix = get_condition_prefix(matched_condition)
    if prefix == 'C':
        return clamp_budget_factor(params['condition_c_single_position_cap'])
    if prefix in ('E', 'F'):
        return clamp_budget_factor(params['condition_ef_single_position_cap'])
    return clamp_budget_factor(params['default_single_position_cap'])
```

Run: 上一步测试。Expected: PASS。

- [ ] **Step 4: 编写单票绝对容量失败测试**

```python
def test_single_f_candidate_with_low_score_is_capped_at_2_75_percent(strategy):
    plan = strategy.build_balanced_buy_plan(
        candidates=[candidate("000001.XSHE", "F", 1.0, 0.11, 1.0)],
        total_budget=900000,
        total_value=1000000,
        existing_positions_value=0,
        existing_stock_values={},
        params=balanced_params(),
    )
    assert plan[0]["position_cap_value"] == 27500
    assert plan[0]["balanced_final_budget"] == 27500


def test_single_c_candidate_is_capped_at_35_percent(strategy):
    plan = strategy.build_balanced_buy_plan(
        candidates=[candidate("000001.XSHE", "C", 1.0, 1.0, 1.0)],
        total_budget=900000,
        total_value=1000000,
        existing_positions_value=0,
        existing_stock_values={},
        params=balanced_params(),
    )
    assert plan[0]["balanced_final_budget"] == 350000
```

Run: 两个测试。Expected: 因规划器尚不存在而失败。

- [ ] **Step 5: 实现最小纯预算规划器**

规划器签名固定为：

```python
def build_balanced_buy_plan(candidates, total_budget, total_value,
                            existing_positions_value, existing_stock_values,
                            params=None):
```

每个输入候选必须包含：

```python
{
    'stock': '000001.XSHE',
    'record': {},
    'capital_weight': 1.0,
    'position_factor': 0.11,
    'risk_budget_factor': 1.0,
    'matched_condition': 'F',
}
```

每个输出候选必须新增：

```python
{
    'condition_position_cap': 0.25,
    'position_cap_value': 27500.0,
    'existing_position_value': 0.0,
    'position_remaining_capacity': 27500.0,
    'relative_budget': 900000.0,
    'balanced_final_budget': 27500.0,
    'position_cap_reason': 'single_position_cap',
}
```

算法必须：

```text
1. 按 capital_weight 降序排序一次。
2. 从 total_value * 90% 扣除全部已有持仓市值，得到 portfolio_remaining_capacity。
3. 计算 balanced_total_budget = min(total_budget, portfolio_remaining_capacity)。
4. 用初始 positive_weight_sum 和 balanced_total_budget 计算所有 relative_budget。
5. 用 total_value * condition_cap * score_factor * risk_factor 计算单票上限。
6. 从单票上限扣除已有该票市值。
7. 最终预算取相对预算、单票剩余容量、剩余组合容量和剩余总预算的最小值。
8. 不重新计算权重和相对预算，不把触顶资金再分配。
```

Run: 上述测试。Expected: PASS。

- [ ] **Step 6: 补齐剩余七类失败测试并逐一变绿**

测试必须覆盖：

```python
def build_plan(strategy, candidates, existing_positions_value=0,
               existing_stock_values=None, total_value=1000000,
               total_budget=900000):
    return strategy.build_balanced_buy_plan(
        candidates=candidates,
        total_budget=total_budget,
        total_value=total_value,
        existing_positions_value=existing_positions_value,
        existing_stock_values=existing_stock_values or {},
        params=balanced_params(),
    )


def test_e_candidate_score_076_caps_at_19_percent(strategy):
    plan = build_plan(strategy, [candidate("E", "E", 1.0, 0.76, 1.0)])
    assert plan[0]["balanced_final_budget"] == pytest.approx(190000)


def test_risk_factor_half_halves_absolute_cap(strategy):
    plan = build_plan(strategy, [candidate("C", "C", 1.0, 1.0, 0.5)])
    assert plan[0]["balanced_final_budget"] == pytest.approx(175000)


def test_existing_position_uses_only_remaining_stock_capacity(strategy):
    plan = build_plan(
        strategy,
        [candidate("C", "C", 1.0, 1.0, 1.0)],
        existing_positions_value=100000,
        existing_stock_values={"C": 100000},
    )
    assert plan[0]["balanced_final_budget"] == pytest.approx(250000)


def test_existing_position_above_cap_prevents_add(strategy):
    plan = build_plan(
        strategy,
        [candidate("C", "C", 1.0, 1.0, 1.0)],
        existing_positions_value=400000,
        existing_stock_values={"C": 400000},
    )
    assert plan[0]["balanced_final_budget"] == 0


def test_portfolio_at_90_percent_prevents_new_buy(strategy):
    plan = build_plan(
        strategy,
        [candidate("C", "C", 1.0, 1.0, 1.0)],
        existing_positions_value=900000,
    )
    assert plan[0]["balanced_final_budget"] == 0


def test_capped_budget_is_not_redistributed(strategy):
    plan = build_plan(strategy, [
        candidate("F", "F", 1.0, 0.10, 1.0),
        candidate("C", "C", 1.0, 1.00, 1.0),
    ])
    assert plan[0]["relative_budget"] == pytest.approx(450000)
    assert plan[0]["balanced_final_budget"] == pytest.approx(25000)
    assert plan[1]["relative_budget"] == pytest.approx(450000)
    assert plan[1]["balanced_final_budget"] == pytest.approx(350000)


def test_invalid_total_value_returns_zero_budgets(strategy):
    plan = build_plan(
        strategy,
        [candidate("C", "C", 1.0, 1.0, 1.0)],
        total_value=0,
    )
    assert plan[0]["balanced_final_budget"] == 0
```

关键断言：

```text
E * 0.76 = 总资产 19%
risk_factor=0.5 时单票绝对上限减半
已有单票市值只允许补足差额
已有单票超过上限时 balanced_final_budget=0
已有组合仓位达到 90% 时全部 balanced_final_budget=0
第一只触顶后第二只仍使用最初 relative_budget
total_value <= 0 时不抛异常，全部预算为 0
```

每新增一个测试先运行并确认 RED，再补最小实现并确认 GREEN。

### Task 3: 提取统一仓位上下文与结构化记录

**Files:**
- Modify: `.worktrees/strategy-b69-refactor/.codex_work/test_b69_balanced_position_sizing.py`
- Modify: `.worktrees/strategy-b69-refactor/.codex_work/strategy_b69_balanced.py`

- [ ] **Step 1: 编写持仓市值读取失败测试**

```python
def test_position_value_prefers_value_field(strategy):
    position = SimpleNamespace(value=12345, total_amount=1000)
    assert strategy.get_position_market_value(position, 9.9) == 12345


def test_position_value_falls_back_to_amount_times_price(strategy):
    position = SimpleNamespace(value=None, total_amount=1000)
    assert strategy.get_position_market_value(position, 9.9) == 9900
```

Expected: RED 后实现 `get_position_market_value(position, reference_price)` 并变绿。

- [ ] **Step 2: 实现组合仓位上下文构造**

新增：

```python
def build_position_value_context(context, current_data, stock_list):
```

返回：

```python
{
    'total_value': float,
    'existing_positions_value': float,
    'existing_stock_values': {'000001.XSHE': float},
}
```

`existing_positions_value` 优先使用 `context.portfolio.positions_value`；缺失或无效时遍历全部持仓求和。单票市值优先用 `position.value`，否则用 `total_amount * current_data[stock].last_price`。

- [ ] **Step 3: 扩展候选结构化记录**

`make_candidate_record()` 新增默认字段：

```python
'condition_position_cap': '',
'position_cap_value': '',
'existing_position_value': '',
'position_remaining_capacity': '',
'relative_budget': '',
'balanced_final_budget': '',
'position_cap_reason': '',
```

新增：

```python
def apply_buy_plan_to_record(item):
```

该函数只把统一规划器的七个字段写回 `item['record']`，不下单、不读取行情、不修改全局状态。

- [ ] **Step 4: 添加统一仓位计划日志函数**

新增：

```python
def log_balanced_portfolio_capacity(total_value, existing_positions_value,
                                    portfolio_cap_value, remaining_capacity):
    log_stage(
        "组合容量",
        total_value="{:,.0f}".format(total_value),
        existing_positions="{:,.0f}".format(existing_positions_value),
        cap="{:,.0f}".format(portfolio_cap_value),
        remaining="{:,.0f}".format(remaining_capacity),
    )


def log_balanced_stock_plan(item):
    log_stage(
        "仓位计划",
        stock=item['stock'],
        condition=item['matched_condition'],
        relative_budget="{:,.0f}".format(item['relative_budget']),
        condition_cap="{:.0%}".format(item['condition_position_cap']),
        score_factor="{:.2f}".format(item['position_factor']),
        risk_factor="{:.2f}".format(item['risk_budget_factor']),
        existing_value="{:,.0f}".format(item['existing_position_value']),
        absolute_cap="{:,.0f}".format(item['position_cap_value']),
        final_budget="{:,.0f}".format(item['balanced_final_budget']),
        cap_reason=item['position_cap_reason'] or 'none',
    )
```

日志函数只消费规划结果，不参与预算计算。

### Task 4: 统一回测与实盘预算规划

**Files:**
- Modify: `.worktrees/strategy-b69-refactor/.codex_work/strategy_b69_balanced.py`
- Modify: `.worktrees/strategy-b69-refactor/.codex_work/test_b69_balanced_position_sizing.py`

- [ ] **Step 1: 编写回测和实盘共享规划器失败测试**

```python
def test_backtest_and_live_adapters_use_same_balanced_budget(strategy):
    candidates = [candidate("000001.XSHE", "F", 1.0, 0.11, 1.0)]
    backtest = strategy.build_balanced_buy_plan(
        candidates, 900000, 1000000, 0, {}, balanced_params()
    )
    live = strategy.build_balanced_buy_plan(
        candidates, 900000, 1000000, 0, {}, balanced_params()
    )
    assert backtest[0]["balanced_final_budget"] == live[0]["balanced_final_budget"] == 27500
```

Expected: 规划器完成后测试通过，并作为统一入口契约保留。

- [ ] **Step 2: 在 `get_buy` 中只规划一次**

在完成候选筛选和现金门控后：

```text
1. 将 qualified_stocks 转成统一 planner candidates。
2. 构造 position value context。
3. 调用一次 build_balanced_buy_plan。
4. 把规划结果分别交给回测或实盘执行器。
```

删除回测和实盘执行器内部的权重重新归一化。`risk_budget_factor` 不再乘到 `relative_budget`，只参与单票绝对容量计算。

- [ ] **Step 3: 重构回测执行器为薄适配层**

`submit_backtest_buy_orders` 改为：

```text
遍历统一计划
应用原有 position gate 与涨停 gate
使用 balanced_final_budget 计算整手数量
保持 order_value(stock, budget, MarketOrderStyle(day_open))
写回候选记录和交易结果
```

当 `balanced_final_budget` 不足 100 股时：

```python
record['skip_stage'] = 'lot_size'
record['skip_reason'] = 'balanced_budget_below_lot_size'
```

- [ ] **Step 4: 重构实盘执行器为薄适配层**

`build_live_buy_candidates` 继续保留：

```text
已有持仓保护
未完成订单保护
停牌/ST/涨停锁死保护
最多新买 5 只
预算价与限价读取
```

`allocate_live_buy_plan` 不再计算或二次归一化权重，只把统一计划中的 `balanced_final_budget` 按 `budget_price` 转成整手数量。

`submit_live_buy_orders` 继续保留：

```text
限价单
现金漂移保护
整手截断
pending intent 与订单审计记录
```

- [ ] **Step 5: 添加保留现金和跳过日志**

当单票上限截断预算时记录：

```text
[仓位保留现金] reason=single_position_cap unused_budget=2,690,000
```

当组合上限阻止新增买入时记录：

```text
[买入跳过] reason=portfolio_position_cap
```

当预算不足整手时记录：

```text
[买入跳过] stock=002412.XSHE reason=balanced_budget_below_lot_size
```

- [ ] **Step 6: 运行完整本地测试与静态契约检查**

Run:

```bash
python -m py_compile \
  .worktrees/strategy-b69-refactor/.codex_work/strategy_b69_balanced.py
pytest -q \
  .worktrees/strategy-b69-refactor/.codex_work/test_b69_balanced_position_sizing.py
python .worktrees/strategy-b69-refactor/.codex_work/verify_b69_balanced_strategy.py static \
  .worktrees/strategy-b69-refactor/.codex_work/strategy_b69c28a4f69ad63165772d3eddbdccd7_refactored.py \
  .worktrees/strategy-b69-refactor/.codex_work/strategy_b69_balanced.py
```

Expected: 编译通过；所有仓位场景测试通过；静态契约只报告已登记的买入仓位链路变化。

### Task 5: 创建独立聚宽策略并完成 compile 验证

- [ ] **Step 1: 创建新策略**

Run:

```bash
python skills/joinquant-operator/scripts/jq_skill_bridge.py -- \
  --non-interactive --format json strategy new \
  "首板一进二-混合版-平衡仓位-v1" \
  --file .worktrees/strategy-b69-refactor/.codex_work/strategy_b69_balanced.py \
  > .worktrees/strategy-b69-refactor/.codex_work/balanced_strategy_create.json
python - <<'PY'
import json
path = ".worktrees/strategy-b69-refactor/.codex_work/balanced_strategy_create.json"
data = json.load(open(path))
assert data["name"] == "首板一进二-混合版-平衡仓位-v1", data
assert data["id"], data
print(data["id"])
PY
```

Expected: 返回独立新策略 ID。

- [ ] **Step 2: 验证原策略与行为等价重构版未修改**

Run:

```bash
python skills/joinquant-operator/scripts/jq_skill_bridge.py -- \
  --non-interactive --format json strategy ls --limit 30 \
  > .worktrees/strategy-b69-refactor/.codex_work/balanced_strategy_list_after_create.json
python - <<'PY'
import json
from pathlib import Path

root = Path(".worktrees/strategy-b69-refactor/.codex_work")
items = json.loads((root / "balanced_strategy_list_after_create.json").read_text())["items"]
by_name = {item["name"]: item for item in items}
required = [
    "首板一进二-混合版-增加主题热点和集合竞价因子评分等多处改进",
    "首板一进二-混合版-行为等价重构-v1",
    "首板一进二-混合版-平衡仓位-v1",
]
assert all(name in by_name for name in required), by_name.keys()
assert len({by_name[name]["id"] for name in required}) == 3
(root / "protected_strategy_ids.json").write_text(
    json.dumps({name: by_name[name]["id"] for name in required}, ensure_ascii=False, indent=2) + "\n",
    encoding="utf-8",
)
PY
ORIGINAL_ID=$(python -c 'import json; d=json.load(open(".worktrees/strategy-b69-refactor/.codex_work/protected_strategy_ids.json")); print(d["首板一进二-混合版-增加主题热点和集合竞价因子评分等多处改进"])')
REFACTORED_ID=$(python -c 'import json; d=json.load(open(".worktrees/strategy-b69-refactor/.codex_work/protected_strategy_ids.json")); print(d["首板一进二-混合版-行为等价重构-v1"])')
python skills/joinquant-operator/scripts/jq_skill_bridge.py -- \
  strategy show "$ORIGINAL_ID" \
  --output .worktrees/strategy-b69-refactor/.codex_work/original_recheck_balanced.py --force
python skills/joinquant-operator/scripts/jq_skill_bridge.py -- \
  strategy show "$REFACTORED_ID" \
  --output .worktrees/strategy-b69-refactor/.codex_work/refactored_recheck_balanced.py --force
shasum -a 256 \
  .worktrees/strategy-b69-refactor/.codex_work/strategy_b69c28a4f69ad63165772d3eddbdccd7_original.py \
  .worktrees/strategy-b69-refactor/.codex_work/original_recheck_balanced.py
shasum -a 256 \
  .worktrees/strategy-b69-refactor/.codex_work/strategy_b69c28a4f69ad63165772d3eddbdccd7_refactored.py \
  .worktrees/strategy-b69-refactor/.codex_work/refactored_recheck_balanced.py
```

校验：

```text
原始策略名称与 ID 仍存在
行为等价重构版名称与 ID 仍存在
行为等价重构版本地源码 SHA-256 未变化
新策略名称与 ID 独立
```

- [ ] **Step 3: 运行 compile 回测**

先从 `balanced_strategy_create.json` 读取 `id`，再运行：

```bash
BALANCED_ID=$(python -c 'import json; print(json.load(open(".worktrees/strategy-b69-refactor/.codex_work/balanced_strategy_create.json"))["id"])')
python skills/joinquant-operator/scripts/jq_skill_bridge.py -- \
  --non-interactive --format json backtest run "$BALANCED_ID" \
  --start 2026-06-01 --end 2026-06-05 --capital 2000000 --freq day --compile --wait \
  > .worktrees/strategy-b69-refactor/.codex_work/balanced_compile.json
```

Expected: compile 状态成功。若失败，先运行以下命令获取错误日志，再写失败测试复现后修复：

```bash
COMPILE_DETAIL_ID=$(python -c 'import json; print(json.load(open(".worktrees/strategy-b69-refactor/.codex_work/balanced_compile.json"))["id"])')
python skills/joinquant-operator/scripts/jq_skill_bridge.py -- \
  --non-interactive --format json backtest logs "$COMPILE_DETAIL_ID" --error \
  > .worktrees/strategy-b69-refactor/.codex_work/balanced_compile_errors.json
```

### Task 6: 执行短区间与完整正式回测

- [ ] **Step 1: 运行短区间正式回测**

Run:

```bash
BALANCED_ID=$(python -c 'import json; print(json.load(open(".worktrees/strategy-b69-refactor/.codex_work/balanced_strategy_create.json"))["id"])')
python skills/joinquant-operator/scripts/jq_skill_bridge.py -- \
  --non-interactive --format json backtest run "$BALANCED_ID" \
  --start 2026-01-01 --end 2026-03-11 --capital 2000000 --freq day --wait \
  > .worktrees/strategy-b69-refactor/.codex_work/balanced_short_submit.json
SHORT_ID=$(python -c 'import json; d=json.load(open(".worktrees/strategy-b69-refactor/.codex_work/balanced_short_submit.json")); print(d.get("resolved_id") or d.get("response", {}).get("data", {}).get("backtestId") or d.get("result", {}).get("id") or d["id"])')
python skills/joinquant-operator/scripts/jq_skill_bridge.py -- \
  --non-interactive --format json backtest stats "$SHORT_ID" \
  > .worktrees/strategy-b69-refactor/.codex_work/balanced_short_stats.json
python skills/joinquant-operator/scripts/jq_skill_bridge.py -- \
  --non-interactive --format json backtest result "$SHORT_ID" \
  > .worktrees/strategy-b69-refactor/.codex_work/balanced_short_result.json
python skills/joinquant-operator/scripts/jq_skill_bridge.py -- \
  --non-interactive --format json backtest logs "$SHORT_ID" --all \
  > .worktrees/strategy-b69-refactor/.codex_work/balanced_short_logs.json
```

Expected: 回测完成，仓位计划日志包含条件上限、评分系数、风险系数、已有市值、绝对上限和最终预算。

- [ ] **Step 2: 验证短区间候选与执行边界**

检查：

```text
候选股票与行为等价重构版同期一致
买入时间和订单价格样式一致
卖出标的、时间和原因逻辑一致
单票预算不超过规划器计算出的绝对上限
组合新增买入后不超过 90% 目标仓位上限
触顶后的剩余资金未转给其他候选
```

若候选或卖出逻辑出现非预期差异，停止完整回测，先定位并修复。

- [ ] **Step 3: 运行完整正式回测**

Run:

```bash
BALANCED_ID=$(python -c 'import json; print(json.load(open(".worktrees/strategy-b69-refactor/.codex_work/balanced_strategy_create.json"))["id"])')
python skills/joinquant-operator/scripts/jq_skill_bridge.py -- \
  --non-interactive --format json backtest run "$BALANCED_ID" \
  --start 2026-01-01 --end 2026-06-13 --capital 2000000 --freq day --wait \
  > .worktrees/strategy-b69-refactor/.codex_work/balanced_full_submit.json
FULL_ID=$(python -c 'import json; d=json.load(open(".worktrees/strategy-b69-refactor/.codex_work/balanced_full_submit.json")); print(d.get("resolved_id") or d.get("response", {}).get("data", {}).get("backtestId") or d.get("result", {}).get("id") or d["id"])')
python skills/joinquant-operator/scripts/jq_skill_bridge.py -- \
  --non-interactive --format json backtest stats "$FULL_ID" \
  > .worktrees/strategy-b69-refactor/.codex_work/balanced_full_stats.json
python skills/joinquant-operator/scripts/jq_skill_bridge.py -- \
  --non-interactive --format json backtest result "$FULL_ID" \
  > .worktrees/strategy-b69-refactor/.codex_work/balanced_full_result.json
python skills/joinquant-operator/scripts/jq_skill_bridge.py -- \
  --non-interactive --format json backtest logs "$FULL_ID" --all \
  > .worktrees/strategy-b69-refactor/.codex_work/balanced_full_logs.json
```

- [ ] **Step 4: 生成集中度与绩效对比报告**

`verify_b69_balanced_strategy.py report` 必须从基线与平衡版结果、日志中输出：

```text
总收益
最大回撤
收益回撤比
胜率与盈亏比
最大单票买入预算占总资产比例
最大估算单票持仓比例
平均有仓股票数量
仅持有 1 只股票的交易日占比
平均现金比例
最大单日亏损
候选名单差异
```

报告写入：

```text
.worktrees/strategy-b69-refactor/.codex_work/balanced_position_report.md
```

- [ ] **Step 5: 保存验证元数据**

运行以下命令生成 `balanced_strategy_metadata.json`：

```bash
python - <<'PY'
import hashlib
import json
from pathlib import Path

root = Path(".worktrees/strategy-b69-refactor/.codex_work")


def read(name):
    return json.loads((root / name).read_text(encoding="utf-8"))


def result_id(data):
    response_data = data.get("response", {}).get("data", {})
    result = data.get("result", {})
    return (
        data.get("resolved_id")
        or response_data.get("backtestId")
        or result.get("id")
        or data.get("id")
    )


source = (root / "strategy_b69_balanced.py").read_bytes()
metadata = {
    "name": "首板一进二-混合版-平衡仓位-v1",
    "creation_id": read("balanced_strategy_create.json")["id"],
    "source_sha256": hashlib.sha256(source).hexdigest(),
    "compile_result_id": result_id(read("balanced_compile.json")),
    "short_result_id": result_id(read("balanced_short_submit.json")),
    "full_result_id": result_id(read("balanced_full_submit.json")),
    "protected_static_contract": "unchanged",
    "balanced_position_tests": "passed",
    "original_strategy_unchanged": True,
    "behavior_equivalent_strategy_unchanged": True,
}
(root / "balanced_strategy_metadata.json").write_text(
    json.dumps(metadata, ensure_ascii=False, indent=2) + "\n",
    encoding="utf-8",
)
PY
```

### Task 7: 最终验收

- [ ] **Step 1: 运行全部本地验收命令**

Run:

```bash
python -m py_compile \
  .worktrees/strategy-b69-refactor/.codex_work/strategy_b69_balanced.py
pytest -q \
  .worktrees/strategy-b69-refactor/.codex_work/test_b69_balanced_position_sizing.py
python .worktrees/strategy-b69-refactor/.codex_work/verify_b69_balanced_strategy.py static \
  .worktrees/strategy-b69-refactor/.codex_work/strategy_b69c28a4f69ad63165772d3eddbdccd7_refactored.py \
  .worktrees/strategy-b69-refactor/.codex_work/strategy_b69_balanced.py
git diff --check
git status --short
```

- [ ] **Step 2: 重新验证三份远端策略隔离**

Expected:

```text
原始策略未修改
行为等价重构版未修改
平衡仓位版为独立新策略
```

- [ ] **Step 3: 验收成功标准**

只有以下条件同时满足才能宣称完成：

```text
九类平衡仓位单元场景通过
回测与实盘共用同一纯预算规划器
单票和组合仓位上限按设计生效
触顶资金保留现金，不二次分配
候选、评分、调度、订单样式和卖出逻辑未被重构改变
compile、短区间和完整正式回测完成
输出集中度与绩效对比报告
现有两份策略未被修改
```
