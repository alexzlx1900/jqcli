# 聚宽首板一进二策略平衡仓位设计

## 目标

基于聚宽策略 `首板一进二-混合版-行为等价重构-v1` 创建独立新策略：

`首板一进二-混合版-平衡仓位-v1`

新策略保留现有选股条件、评分因子、买卖调度、订单价格、卖出逻辑和实盘订单保护，只修改买入预算分配，解决单一候选经权重归一化后获得接近全部可用现金的问题。

现有行为等价重构版不得修改。

## 当前问题

当前策略先计算：

```text
capital_weight = final_position_factor * capital_priority
```

再按照所有合格候选的相对权重分配总预算：

```text
relative_budget = total_budget * capital_weight / positive_weight_sum
```

当只有一只候选时，`capital_weight / positive_weight_sum = 1`。因此，即使 `position_factor` 很低，该候选仍可能获得全部可用预算。现有回测中出现过 `position_factor=0.11` 但目标金额等于全部当日预算的情况。

## 范围

### 允许变更

- 新增平衡仓位参数。
- 新增单票绝对仓位上限与组合总仓位上限计算。
- 修改回测和实盘买入金额分配。
- 新增仓位计划、触顶和保留现金日志。
- 新增结构化仓位计划记录字段。

### 保持不变

- 不修改盘前股票池、A-F 条件、硬过滤和评分公式。
- 不修改候选排序、买入时间和订单价格样式。
- 不修改卖出条件、判断优先级和卖出时间。
- 不修改当前关闭的 ML、市场承接和影子卖出开关。
- 不强制凑够持股数量，不放宽条件买入低质量股票。
- 不自动卖出或减仓已有持仓，即使已有持仓超过新上限。

## 仓位参数

```python
'portfolio_position_cap': 0.90,
'default_single_position_cap': 0.30,
'condition_c_single_position_cap': 0.35,
'condition_ef_single_position_cap': 0.25,
```

条件上限映射：

| 条件 | 单票基础上限 |
|---|---:|
| C | 35% |
| E、F | 25% |
| A、B、D 及未知条件 | 30% |

所有比例均按当前 `context.portfolio.total_value` 计算。

## 预算公式

### 组合剩余容量

```text
existing_positions_value = 当前全部已有持仓市值
portfolio_cap_value = 当前总资产 * 90%
portfolio_remaining_capacity = max(portfolio_cap_value - existing_positions_value, 0)
```

当已有持仓市值超过组合上限时：

- 新买入预算为 0。
- 保留现有持仓。
- 不触发自动卖出、撤单或减仓。

### 当日总买入预算

```text
balanced_total_budget = min(
    现有策略计算出的 total_budget,
    portfolio_remaining_capacity
)
```

现有策略的回撤减仓、ML 系数和 97% 现金安全垫继续生效。

### 单票绝对上限

```text
condition_cap = 按 A-F 条件映射得到的单票基础上限
score_factor = min(max(final_position_factor, 0), 1)
risk_factor = min(max(risk_budget_factor, 0), 1)

stock_position_cap_value = (
    当前总资产
    * condition_cap
    * score_factor
    * risk_factor
)
```

### 包含已有持仓

```text
existing_stock_value = 该股票已有持仓市值
stock_remaining_capacity = max(
    stock_position_cap_value - existing_stock_value,
    0
)
```

已有持仓市值优先使用持仓对象的 `value`；若运行环境未提供，则使用 `total_amount * 当前参考价`。

### 最终买入金额

先保留原相对权重预算：

```text
relative_budget = (
    balanced_total_budget
    * capital_weight
    / positive_weight_sum
)
```

然后应用绝对上限：

```text
final_buy_budget = min(
    relative_budget,
    stock_remaining_capacity,
    当时剩余组合容量,
    当时剩余可用预算
)
```

`risk_budget_factor` 只在单票绝对上限中使用，不再额外乘到 `relative_budget`，避免风险预算系数被重复应用。

## 资金再分配规则

V1 不对因单票上限截断而剩余的资金进行二次权重归一化。

执行规则：

1. 按现有 `capital_weight` 从高到低遍历候选。
2. 每只股票以初始相对权重预算为起点，并受单票剩余容量约束。
3. 单票触顶后的剩余资金保留为现金。
4. 后续股票仍使用基于初始总预算计算的原始相对预算，不承接前面股票未使用的预算。

该规则防止剩余资金继续流向其他候选并形成新的集中风险。

## 回测与实盘一致性

回测和实盘必须调用同一套纯预算规划函数，输出统一的每只股票目标金额。

允许保留的执行差异：

- 回测继续使用当前 `order_value` 和 `MarketOrderStyle(day_open)`。
- 实盘继续使用限价单、整手数量、现金漂移保护和最多新买 5 只限制。

除订单执行层固有差异外，回测与实盘的条件仓位上限、评分系数、风险系数、已有持仓扣减和组合总仓位上限必须一致。

## 日志与记录

新增阶段日志：

```text
[组合容量] total_value=4,000,000 existing_positions=800,000 cap=3,600,000 remaining=2,800,000
[仓位计划] stock=002412.XSHE condition=F relative_budget=2,800,000 condition_cap=25% score_factor=0.11 risk_factor=1.00 existing_value=0 absolute_cap=110,000 final_budget=110,000
[仓位保留现金] reason=single_position_cap unused_budget=2,690,000
[买入跳过] stock=002412.XSHE reason=balanced_budget_below_lot_size
```

结构化候选记录新增：

- `condition_position_cap`
- `position_cap_value`
- `existing_position_value`
- `position_remaining_capacity`
- `relative_budget`
- `balanced_final_budget`
- `position_cap_reason`

## 边界处理

- `total_value <= 0`：停止新增买入并记录异常。
- `position_factor <= 0`：保持现有 position gate 行为。
- `risk_budget_factor <= 0`：最终预算为 0。
- 单票剩余容量不足 100 股：不下单，记录 `balanced_budget_below_lot_size`。
- 已有持仓超过单票上限：不追加买入，不自动减仓。
- 已有组合持仓超过 90%：不新增买入，不自动减仓。
- 候选为空：保持现有行为。

## 验证方案

### 单元验证

覆盖以下预算场景：

1. 单一 F 类候选，`position_factor=0.11`，最终上限为总资产的 2.75%。
2. 单一 C 类候选，`position_factor=1.0`，最终上限为总资产的 35%。
3. E 类候选，`position_factor=0.76`，最终上限为总资产的 19%。
4. `risk_budget_factor=0.5` 时绝对上限减半。
5. 已有持仓占用部分单票容量时，只允许补足差额。
6. 已有持仓超过单票容量时，不追加买入。
7. 组合已有持仓达到或超过 90% 时，不新增买入。
8. 多候选触顶后的剩余资金不二次分配。
9. 回测与实盘预算规划结果一致。

### 聚宽验证

创建新策略后依次运行：

1. compile 回测。
2. 2026-01-01 至 2026-03-11 短区间回测。
3. 2026-01-01 至 2026-06-13 完整正式回测。

与行为等价重构版对比：

- 最大单票买入预算占总资产比例。
- 最大估算单票持仓比例。
- 平均持仓数量和有持仓交易日占比。
- 平均现金比例和资金利用率。
- 总收益、最大回撤、收益回撤比和单日最大亏损。
- 交易标的与候选名单是否保持一致。

## 成功标准

- 创建独立新策略，现有行为等价重构版未被修改。
- 选股候选、买卖时间和卖出逻辑保持不变。
- 单票最终预算符合 C 35%、E/F 25%、其他 30% 的基础上限，并受评分、风险和已有持仓进一步约束。
- 组合新增买入后不突破 90% 目标仓位上限。
- 单票触顶后的剩余资金保留为现金。
- 回测与实盘使用同一预算规划规则。
- 输出完整回测对比和仓位集中度变化说明。
