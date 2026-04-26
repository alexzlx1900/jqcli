from __future__ import annotations

from pathlib import Path
from typing import Any

from flask import Blueprint, current_app, jsonify, redirect, render_template, request, url_for

from jqcli.api.client import ApiClient
from jqcli.web.db import connect, row_to_dict, rows_to_dicts

from .services.archive_sync import refresh_archive
from .services.backtest_runner import submit_standardized_backtest
from .services.jobs import get_job, start_job
from .services.posts import get_post, import_posts, list_posts
from .services.strategy_download import download_strategy_for_post

bp = Blueprint("web", __name__)


@bp.get("/")
def index():
    return redirect(url_for("web.posts_page"))


@bp.get("/posts")
def posts_page():
    return render_template("posts.html")


@bp.get("/posts/<post_id>")
def post_detail_page(post_id: str):
    return render_template("post_detail.html", post_id=post_id)


@bp.get("/api/posts")
def api_posts():
    return jsonify(list_posts(db_path(), dict(request.args)))


@bp.post("/api/posts/reindex")
def api_reindex():
    payload = import_posts(db_path(), archive_path(), candidates_path())
    return jsonify(payload)


@bp.get("/api/posts/<post_id>")
def api_post(post_id: str):
    post = get_post(db_path(), post_id)
    if not post:
        return jsonify({"error": "not found"}), 404
    return jsonify(post)


@bp.post("/api/posts/<post_id>/download")
def api_download(post_id: str):
    db = db_path()
    mgr = manager_dir()
    client_config = client_settings()

    def run(job_id: str) -> dict[str, Any]:
        with make_client(client_config) as client:
            return download_strategy_for_post(db, mgr, client, post_id)

    return jsonify({"job_id": start_job(db, "download", run, "正在下载策略")})


@bp.post("/api/posts/<post_id>/standardize")
def api_standardize(post_id: str):
    from .services.code_standardizer import standardize_code

    with connect(db_path()) as conn:
        archive = row_to_dict(conn.execute("SELECT * FROM strategy_archives WHERE post_id=?", (post_id,)).fetchone())
        if not archive:
            return jsonify({"error": "strategy not downloaded"}), 400
        original_path = Path(str(archive.get("original_code_path") or ""))
        if not original_path.exists():
            return jsonify({"error": "original code missing"}), 400
        target = manager_dir() / "strategies" / post_id / "standardized.py"
        target.write_text(standardize_code(original_path.read_text(encoding="utf-8")), encoding="utf-8")
        conn.execute("UPDATE strategy_archives SET standardized_code_path=? WHERE post_id=?", (str(target), post_id))
        conn.commit()
    return jsonify({"standardized_code_path": str(target)})


@bp.post("/api/posts/<post_id>/backtests")
def api_submit_backtest(post_id: str):
    payload = request.get_json(silent=True) or {}
    start_date = str(payload.get("start_date") or current_app.config["JQCLI_BACKTEST_START"])
    end_date = str(payload.get("end_date") or current_app.config["JQCLI_BACKTEST_END"])
    capital = float(payload.get("capital") or current_app.config["JQCLI_BACKTEST_CAPITAL"])
    frequency = str(payload.get("frequency") or current_app.config["JQCLI_BACKTEST_FREQUENCY"])
    db = db_path()
    mgr = manager_dir()
    client_config = client_settings()

    def run(job_id: str) -> dict[str, Any]:
        with make_client(client_config) as client:
            return submit_standardized_backtest(
                db,
                mgr,
                client,
                post_id,
                start_date=start_date,
                end_date=end_date,
                capital=capital,
                frequency=frequency,
            )

    return jsonify({"job_id": start_job(db, "backtest", run, "正在提交回测")})


@bp.get("/api/posts/<post_id>/backtests")
def api_backtests(post_id: str):
    with connect(db_path()) as conn:
        rows = conn.execute("SELECT * FROM backtest_runs WHERE post_id = ? ORDER BY id DESC", (post_id,)).fetchall()
    return jsonify({"items": rows_to_dicts(rows)})


@bp.get("/api/backtests/<int:run_id>")
def api_backtest_run(run_id: int):
    with connect(db_path()) as conn:
        row = row_to_dict(conn.execute("SELECT * FROM backtest_runs WHERE id = ?", (run_id,)).fetchone())
    if not row:
        return jsonify({"error": "not found"}), 404
    return jsonify(row)


@bp.post("/api/refresh")
def api_refresh():
    db = db_path()
    root = root_dir()
    archive = archive_path()
    candidates = candidates_path()

    def run(job_id: str) -> dict[str, Any]:
        return refresh_archive(db, root, archive, candidates, job_id=job_id)

    return jsonify({"job_id": start_job(db, "refresh", run, "准备刷新数据")})


@bp.get("/api/jobs/<job_id>")
def api_job(job_id: str):
    job = get_job(db_path(), job_id)
    if not job:
        return jsonify({"error": "not found"}), 404
    return jsonify(job)


def db_path() -> Path:
    return Path(current_app.config["JQCLI_DB_PATH"])


def manager_dir() -> Path:
    return Path(current_app.config["JQCLI_MANAGER_DIR"])


def root_dir() -> Path:
    return Path(current_app.config["JQCLI_ROOT"])


def archive_path() -> Path:
    return Path(current_app.config["JQCLI_ARCHIVE_PATH"])


def candidates_path() -> Path:
    return Path(current_app.config["JQCLI_CANDIDATES_PATH"])


def client_settings() -> dict[str, Any]:
    return {
        "api_base": str(current_app.config["JQCLI_API_BASE"]),
        "token": current_app.config.get("JQCLI_TOKEN"),
        "cookie": current_app.config.get("JQCLI_COOKIE"),
        "timeout": float(current_app.config["JQCLI_TIMEOUT"]),
    }


def make_client(settings: dict[str, Any] | None = None) -> ApiClient:
    settings = settings or client_settings()
    return ApiClient(
        settings["api_base"],
        token=settings.get("token"),
        cookie=settings.get("cookie"),
        timeout=float(settings["timeout"]),
    )
