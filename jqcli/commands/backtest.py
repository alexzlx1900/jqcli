from __future__ import annotations

import time
from datetime import date
from typing import Any

import click
from rich.console import Console
from rich.table import Table

from jqcli.api.backtest import (
    delete_backtest_record,
    get_backtest,
    get_backtest_logs,
    get_backtest_result,
    get_backtest_stats,
    list_backtests,
    run_backtest,
)
from jqcli.api.client import ApiClient
from jqcli.cli import AppContext
from jqcli.errors import ConfirmationRequiredError, NotAuthenticatedError, TimeoutError
from jqcli.output import write_json


TERMINAL_STATUSES = {"done", "failed", "cancelled"}


@click.group(name="backtest")
def backtest_group() -> None:
    """回测管理。"""


def make_client(app: AppContext) -> ApiClient:
    if not (app.token or app.cookie):
        raise NotAuthenticatedError()
    return ApiClient(app.api_base, token=app.token, cookie=app.cookie, timeout=app.timeout)


def make_optional_client(app: AppContext) -> ApiClient:
    return ApiClient(app.api_base, token=app.token, cookie=app.cookie, timeout=app.timeout)


def close_client(client: object) -> None:
    close = getattr(client, "close", None)
    if callable(close):
        close()


def render_backtest_table(items: list[dict[str, Any]]) -> None:
    table = Table()
    for name in ("ID", "状态", "开始日期", "结束日期", "收益", "提交时间"):
        table.add_column(name)
    for item in items:
        metrics = item.get("metrics") or {}
        table.add_row(
            str(item.get("id", "")),
            str(item.get("status", "")),
            str(item.get("start_date", "")),
            str(item.get("end_date", "")),
            str(metrics.get("annual_return", "")),
            str(item.get("submitted_at", "")),
        )
    Console().print(table)


def has_core_metrics(payload: dict[str, Any]) -> bool:
    metrics = payload.get("metrics")
    return isinstance(metrics, dict) and metrics.get("annual_algo_return") is not None and metrics.get("sharpe") is not None


def wait_for_backtest(client: ApiClient, backtest_id: str, *, timeout: float, poll_interval: float) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    while True:
        payload = get_backtest(client, backtest_id)
        if has_core_metrics(payload):
            return payload
        if time.monotonic() >= deadline:
            raise TimeoutError()
        time.sleep(poll_interval)


@backtest_group.command("run")
@click.argument("strategy_id")
@click.option("--start", "start_date", required=True)
@click.option("--end", "end_date")
@click.option("--capital", type=float)
@click.option("--freq", "frequency", type=click.Choice(["day", "minute"]), default="day")
@click.option("--compile", "compile_only", is_flag=True, help="只做编译运行，不进入正式回测列表")
@click.option("--wait", "wait_result", is_flag=True)
@click.option("--poll-interval", type=float, default=5)
@click.pass_obj
def run(
    app: AppContext,
    strategy_id: str,
    start_date: str,
    end_date: str | None,
    capital: float | None,
    frequency: str,
    compile_only: bool,
    wait_result: bool,
    poll_interval: float,
) -> None:
    if end_date is None:
        end_date = date.today().isoformat()
    client = make_client(app)
    try:
        payload = run_backtest(
            client,
            strategy_id=strategy_id,
            start_date=start_date,
            end_date=end_date,
            capital=capital,
            frequency=frequency,
            compile_only=compile_only,
        )
        if wait_result:
            payload = wait_for_backtest(client, str(payload["id"]), timeout=app.timeout, poll_interval=poll_interval)
    finally:
        close_client(client)
    if app.json_output:
        write_json(payload)
    elif not app.quiet:
        click.echo(f"回测 ID: {payload.get('id', '')}")
        click.echo(f"状态: {payload.get('status', '')}")


@backtest_group.command("ls")
@click.argument("strategy_id")
@click.option("--status", "status_filter", type=click.Choice(["all", "running", "done", "failed"]), default="all")
@click.option("--limit", type=int, default=50)
@click.option("--all", "all_items", is_flag=True)
@click.option("--compile", "compile_only", is_flag=True, help="列出编译运行记录")
@click.pass_obj
def ls(app: AppContext, strategy_id: str, status_filter: str, limit: int, all_items: bool, compile_only: bool) -> None:
    client = make_client(app)
    try:
        payload = list_backtests(
            client,
            strategy_id=strategy_id,
            status=status_filter,
            limit=limit,
            all_items=all_items,
            compile_only=compile_only,
        )
    finally:
        close_client(client)
    if app.json_output:
        write_json(payload)
    else:
        render_backtest_table(list(payload.get("items", [])))


@backtest_group.command("show")
@click.argument("backtest_id")
@click.pass_obj
def show(app: AppContext, backtest_id: str) -> None:
    client = make_client(app)
    try:
        payload = get_backtest(client, backtest_id)
    finally:
        close_client(client)
    if app.json_output:
        write_json(payload)
    else:
        click.echo(f"回测 ID: {payload.get('id', '')}")
        click.echo(f"状态: {payload.get('status', '')}")
        if payload.get("error"):
            click.echo(f"错误: {payload['error']}")


@backtest_group.command("stats")
@click.argument("backtest_id")
@click.pass_obj
def stats(app: AppContext, backtest_id: str) -> None:
    client = make_optional_client(app)
    try:
        payload = get_backtest_stats(client, backtest_id)
    finally:
        close_client(client)
    if app.json_output:
        write_json(payload)
    else:
        metrics = payload.get("metrics") if isinstance(payload.get("metrics"), dict) else {}
        click.echo(f"回测 ID: {payload.get('id', '')}")
        click.echo(f"策略收益: {metrics.get('algorithm_return', '')}")
        click.echo(f"年化收益: {metrics.get('annual_algo_return', '')}")
        click.echo(f"最大回撤: {metrics.get('max_drawdown', '')}")
        click.echo(f"Sharpe: {metrics.get('sharpe', '')}")


@backtest_group.command("result")
@click.argument("backtest_id")
@click.option("--offset", type=int, default=0, show_default=True)
@click.option("--user-record-offset", type=int, default=0, show_default=True)
@click.pass_obj
def result(app: AppContext, backtest_id: str, offset: int, user_record_offset: int) -> None:
    client = make_optional_client(app)
    try:
        payload = get_backtest_result(
            client,
            backtest_id,
            offset=offset,
            user_record_offset=user_record_offset,
        )
    finally:
        close_client(client)
    if app.json_output:
        write_json(payload)
    else:
        data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
        state = data.get("state", "")
        result_data = data.get("result") if isinstance(data.get("result"), dict) else {}
        count = result_data.get("count", "")
        click.echo(f"回测 ID: {payload.get('id', '')}")
        click.echo(f"状态: {state}")
        click.echo(f"数据点: {count}")


@backtest_group.command("logs")
@click.argument("backtest_id")
@click.option("--offset", type=int, default=0, show_default=True)
@click.option("--error", "error_logs", is_flag=True, help="获取错误日志，而不是普通日志")
@click.option("--all", "all_items", is_flag=True, help="自动分页拉取全部普通日志")
@click.option("--max-pages", type=int, default=50, show_default=True)
@click.pass_obj
def logs(app: AppContext, backtest_id: str, offset: int, error_logs: bool, all_items: bool, max_pages: int) -> None:
    client = make_optional_client(app)
    try:
        payload = get_backtest_logs(
            client,
            backtest_id,
            offset=offset,
            error=error_logs,
            all_items=all_items,
            max_pages=max_pages,
        )
    finally:
        close_client(client)
    if app.json_output:
        write_json(payload)
    else:
        for line in payload.get("logs", []):
            click.echo(str(line))


@backtest_group.command("rm")
@click.argument("backtest_id")
@click.option("--yes", "-y", is_flag=True)
@click.option("--compile", "compile_only", is_flag=True, help="删除编译运行记录")
@click.pass_obj
def rm(app: AppContext, backtest_id: str, yes: bool, compile_only: bool) -> None:
    if app.non_interactive and not yes:
        raise ConfirmationRequiredError()
    if not app.non_interactive and not yes:
        click.confirm(f"确认删除回测 {backtest_id}？", abort=True)
    client = make_client(app)
    try:
        payload = delete_backtest_record(client, backtest_id, compile_only=compile_only) or {"ok": True, "id": backtest_id}
    finally:
        close_client(client)
    if app.json_output:
        write_json(payload)
    elif not app.quiet:
        click.echo(f"回测已删除：{backtest_id}")
