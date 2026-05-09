from __future__ import annotations

from pathlib import Path

import click

from jqcli.cli import AppContext
from jqcli.web import create_app


@click.group(name="web")
def web_group() -> None:
    """本地策略帖子管理网站。"""


@web_group.command("run")
@click.option("--host", default="127.0.0.1")
@click.option("--port", default=5050, type=int)
@click.option("--debug", "debug_server", is_flag=True)
@click.option("--allow-public", is_flag=True, help="允许监听非本机地址")
@click.option("--db", "db_path", type=click.Path(dir_okay=False, path_type=str))
@click.pass_obj
def run(app_ctx: AppContext, host: str, port: int, debug_server: bool, allow_public: bool, db_path: str | None) -> None:
    local_hosts = {"127.0.0.1", "localhost", "::1"}
    if host not in local_hosts and not allow_public:
        raise click.ClickException("web run 默认只允许监听本机地址；如确认需要公开访问，请显式传入 --allow-public")
    if debug_server and host not in local_hosts:
        raise click.ClickException("debug 模式不能监听公开地址")
    config = {
        "JQCLI_API_BASE": app_ctx.api_base,
        "JQCLI_TOKEN": app_ctx.token,
        "JQCLI_COOKIE": app_ctx.cookie,
        "JQCLI_TIMEOUT": app_ctx.timeout,
    }
    if db_path:
        config["JQCLI_DB_PATH"] = Path(db_path)
    app = create_app(config)
    click.echo(f"本地网站: http://{host}:{port}")
    app.run(host=host, port=port, debug=debug_server)
