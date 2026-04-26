from __future__ import annotations

import ast


BEGIN = "# jqcli-standard-backtest-begin"
END = "# jqcli-standard-backtest-end"

STANDARD_BLOCK = f'''{BEGIN}
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
{END}'''


def standardize_code(code: str) -> str:
    cleaned = remove_existing_block(code)
    try:
        tree = ast.parse(cleaned)
    except SyntaxError:
        return append_initialize(cleaned)
    initialize = next((node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "initialize"), None)
    if initialize is None or initialize.end_lineno is None:
        return append_initialize(cleaned)
    lines = cleaned.splitlines()
    indent = function_body_indent(lines, initialize)
    block_lines = [(indent + line if line else "") for line in STANDARD_BLOCK.splitlines()]
    insert_at = initialize.end_lineno
    lines[insert_at:insert_at] = block_lines
    return "\n".join(lines).rstrip() + "\n"


def remove_existing_block(code: str) -> str:
    lines = code.splitlines()
    output: list[str] = []
    skipping = False
    for line in lines:
        if BEGIN in line:
            skipping = True
            continue
        if END in line:
            skipping = False
            continue
        if not skipping:
            output.append(line)
    return "\n".join(output).rstrip() + ("\n" if output else "")


def append_initialize(code: str) -> str:
    prefix = code.rstrip()
    if prefix:
        prefix += "\n\n"
    indented = "\n".join("    " + line if line else "" for line in STANDARD_BLOCK.splitlines())
    return f"{prefix}def initialize(context):\n{indented}\n"


def function_body_indent(lines: list[str], node: ast.FunctionDef) -> str:
    if node.body:
        first = node.body[0]
        if getattr(first, "col_offset", None) is not None:
            return " " * int(first.col_offset)
    line = lines[node.lineno - 1] if 0 <= node.lineno - 1 < len(lines) else ""
    return line[: len(line) - len(line.lstrip())] + "    "
