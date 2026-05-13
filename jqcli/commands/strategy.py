from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import click
from rich.console import Console
from rich.table import Table

from jqcli.api.client import ApiClient
from jqcli.api.strategy import (
    build_strategy_folder_sync_plan,
    create_strategy_folder,
    create_strategy,
    delete_strategy,
    get_strategy,
    list_strategies,
    list_strategy_folders,
    load_strategy_index_rows,
    move_strategies_to_folder,
    update_strategy,
)
from jqcli.cli import AppContext
from jqcli.errors import ConfirmationRequiredError, FileError, NotAuthenticatedError, UsageError
from jqcli.output import write_json


TEMPLATE = """def initialize(context):
    pass


def handle_data(context, data):
    pass
"""


@click.group(name="strategy")
def strategy_group() -> None:
    """策略管理。"""


def make_client(app: AppContext) -> ApiClient:
    if not (app.token or app.cookie):
        raise NotAuthenticatedError()
    return ApiClient(app.api_base, token=app.token, cookie=app.cookie, timeout=app.timeout)


def close_client(client: object) -> None:
    close = getattr(client, "close", None)
    if callable(close):
        close()


def read_code(file_path: str | None, code_stdin: bool) -> str | None:
    if file_path and code_stdin:
        raise UsageError("--file 与 --code-stdin 不可同时使用")
    if file_path:
        path = Path(file_path)
        try:
            code = path.read_text(encoding="utf-8")
        except OSError as exc:
            raise FileError(f"无法读取文件 {file_path}") from exc
        if not code.strip():
            raise FileError(f"文件 {file_path} 为空")
        return code
    if code_stdin:
        code = sys.stdin.read()
        if not code.strip():
            raise UsageError("stdin 中没有策略源码")
        return code
    return None


def render_strategy_table(items: list[dict[str, Any]]) -> None:
    table = Table()
    for name in ("ID", "名称", "类型", "创建时间", "最近修改"):
        table.add_column(name)
    for item in items:
        table.add_row(
            str(item.get("id", "")),
            str(item.get("name", "")),
            str(item.get("type", "")),
            str(item.get("created_at", "")),
            str(item.get("updated_at", "")),
        )
    Console().print(table)


@strategy_group.command("ls")
@click.option("--sort", "sort_by", type=click.Choice(["name", "created", "updated"]), default="updated")
@click.option("--limit", type=int, default=50)
@click.option("--all", "all_items", is_flag=True)
@click.pass_obj
def ls(app: AppContext, sort_by: str, limit: int, all_items: bool) -> None:
    client = make_client(app)
    try:
        payload = list_strategies(client, sort=sort_by, limit=limit, all_items=all_items)
    finally:
        close_client(client)
    if app.json_output:
        write_json(payload)
    else:
        render_strategy_table(list(payload.get("items", [])))


@strategy_group.command("show")
@click.argument("strategy_id")
@click.option("--code", "show_code", is_flag=True)
@click.option("--output", "-o", type=click.Path(dir_okay=False, path_type=str))
@click.option("--force", is_flag=True)
@click.pass_obj
def show(app: AppContext, strategy_id: str, show_code: bool, output: str | None, force: bool) -> None:
    include_code = show_code or bool(output)
    client = make_client(app)
    try:
        payload = get_strategy(client, strategy_id, include_code=include_code)
    finally:
        close_client(client)
    if output:
        path = Path(output)
        if path.exists() and not force:
            raise FileError(f"输出文件已存在：{output}")
        code = payload.get("code")
        if code is None:
            raise FileError("远端响应未包含策略源码")
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(str(code), encoding="utf-8")
        except OSError as exc:
            raise FileError(f"无法写入文件 {output}") from exc
    if app.json_output:
        write_json(payload)
    else:
        click.echo(f"ID: {payload.get('id', '')}")
        click.echo(f"名称: {payload.get('name', '')}")
        if include_code and payload.get("code") is not None and not output:
            click.echo(str(payload["code"]))


@strategy_group.command("new")
@click.argument("name")
@click.option("--file", "-f", "file_path", type=click.Path(dir_okay=False, path_type=str))
@click.option("--code-stdin", is_flag=True)
@click.option("--type", "strategy_type", type=click.Choice(["stock", "futures"]), default="stock")
@click.pass_obj
def new(app: AppContext, name: str, file_path: str | None, code_stdin: bool, strategy_type: str) -> None:
    code = read_code(file_path, code_stdin)
    if code is None:
        code = TEMPLATE
    client = make_client(app)
    try:
        payload = create_strategy(client, name=name, code=code, strategy_type=strategy_type)
    finally:
        close_client(client)
    if app.json_output:
        write_json(payload)
    elif not app.quiet:
        click.echo(f"策略已创建：{payload.get('id', '')}")


@strategy_group.command("edit")
@click.argument("strategy_id")
@click.option("--file", "-f", "file_path", type=click.Path(dir_okay=False, path_type=str))
@click.option("--code-stdin", is_flag=True)
@click.option("--name")
@click.pass_obj
def edit(app: AppContext, strategy_id: str, file_path: str | None, code_stdin: bool, name: str | None) -> None:
    code = read_code(file_path, code_stdin)
    if code is None and name is None:
        raise UsageError("请提供 --file、--code-stdin 或 --name")
    client = make_client(app)
    try:
        payload = update_strategy(client, strategy_id, name=name, code=code)
    finally:
        close_client(client)
    if app.json_output:
        write_json(payload)
    elif not app.quiet:
        click.echo(f"策略已更新：{payload.get('id', strategy_id)}")


@strategy_group.command("rm")
@click.argument("strategy_id")
@click.option("--yes", "-y", is_flag=True)
@click.pass_obj
def rm(app: AppContext, strategy_id: str, yes: bool) -> None:
    if app.non_interactive and not yes:
        raise ConfirmationRequiredError()
    if not app.non_interactive and not yes:
        click.confirm(f"确认删除策略 {strategy_id}？", abort=True)
    client = make_client(app)
    try:
        payload = delete_strategy(client, strategy_id) or {"ok": True, "id": strategy_id}
    finally:
        close_client(client)
    if app.json_output:
        write_json(payload)
    elif not app.quiet:
        click.echo(f"策略已删除：{strategy_id}")


CATEGORY_FOLDER_NAMES = {
    "small_micro_cap": "01_小市值微盘",
    "etf_fund_rotation": "02_ETF基金轮动",
    "ml_ai": "03_机器学习AI",
    "short_term_breakout": "04_短线打板突破",
    "factor_value_quality": "05_因子价值质量",
    "timing_technical": "06_择时技术指标",
    "multi_strategy_portfolio": "07_多策略组合配置",
    "futures_convertible_arbitrage": "08_期货转债套利",
    "grid_intraday": "09_网格日内交易",
    "live_trading_ops": "10_实盘交易对接",
    "research_template_tooling": "11_研究模板工具",
    "uncategorized": "99_未分类",
}


def _folders_by_name(client: ApiClient, parent_id: str) -> dict[str, dict[str, Any]]:
    payload = list_strategy_folders(client, parent_id=parent_id)
    return {str(item["name"]): item for item in payload.get("items", [])}


@strategy_group.command("folder-sync")
@click.option("--from-index", "index_path", required=True, type=click.Path(dir_okay=False, path_type=str))
@click.option("--root-folder", default="Codex策略分类", show_default=True)
@click.option("--dry-run/--no-dry-run", default=True, show_default=True)
@click.option("--yes", "-y", is_flag=True, help="真正创建文件夹并移动根目录策略")
@click.option("--batch-size", type=int, default=50, show_default=True)
@click.pass_obj
def folder_sync(app: AppContext, index_path: str, root_folder: str, dry_run: bool, yes: bool, batch_size: int) -> None:
    if batch_size <= 0:
        raise UsageError("--batch-size 必须大于 0")
    if app.non_interactive and not dry_run and not yes:
        raise ConfirmationRequiredError()
    if not dry_run and not yes:
        click.confirm("确认在聚宽远端创建分类文件夹并移动根目录策略？", abort=True)
    index_rows = load_strategy_index_rows(index_path)
    client = make_client(app)
    try:
        remote_items = list_strategies(client, all_items=True).get("items", [])
        plan = build_strategy_folder_sync_plan(
            list(remote_items),
            index_rows,
            root_folder_name=root_folder,
            category_names=CATEGORY_FOLDER_NAMES,
        )
        plan["dry_run"] = dry_run
        plan["existing_remote_count"] = len(remote_items)
        plan["index_count"] = len(index_rows)
        if not dry_run:
            root_folders = _folders_by_name(client, "0")
            root = root_folders.get(root_folder)
            if root:
                root_id = str(root["id"])
                created_root = False
            else:
                created = create_strategy_folder(client, root_folder, parent_id="0")
                root_id = str(created.get("id") or "")
                created_root = True
            if not root_id:
                raise UsageError("无法获取或创建目标根文件夹")
            child_folders = _folders_by_name(client, root_id)
            created_folders: list[dict[str, Any]] = []
            moved: list[dict[str, Any]] = []
            for category, bucket in plan["categories"].items():
                folder_name = str(bucket["folder_name"])
                folder = child_folders.get(folder_name)
                if folder:
                    target_id = str(folder["id"])
                else:
                    created = create_strategy_folder(client, folder_name, parent_id=root_id)
                    target_id = str(created.get("id") or "")
                    created_folders.append({"category": category, "folder_name": folder_name, "folder_id": target_id})
                if not target_id:
                    raise UsageError(f"无法获取或创建分类文件夹：{folder_name}")
                internal_ids = [str(item["internal_id"]) for item in bucket["items"]]
                for start in range(0, len(internal_ids), batch_size):
                    batch = internal_ids[start : start + batch_size]
                    result = move_strategies_to_folder(client, batch, target_id)
                    moved.append({"category": category, "folder_id": target_id, "count": len(batch), "ok": result.get("ok")})
            plan["executed"] = {
                "root_folder_id": root_id,
                "created_root": created_root,
                "created_folders": created_folders,
                "move_batches": moved,
                "moved_count": sum(int(item["count"]) for item in moved),
            }
    finally:
        close_client(client)
    if app.json_output:
        write_json(plan)
    else:
        click.echo(f"索引策略数: {plan['index_count']}")
        click.echo(f"远端策略数: {plan['existing_remote_count']}")
        click.echo(f"计划移动根目录策略: {plan['planned_move_count']}")
        click.echo(f"跳过已有文件夹策略: {plan['skipped_existing_folder_count']}")
        click.echo(f"未匹配策略: {plan['unmatched_count']}")
