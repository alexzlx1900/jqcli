from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from jqcli.api.backtest import get_backtest_stats, run_backtest
from jqcli.api.client import ApiClient
from jqcli.api.strategy import update_strategy
from jqcli.web.db import connect, row_to_dict

from .code_standardizer import standardize_code


def now_text() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def submit_standardized_backtest(
    db_path: Path,
    manager_dir: Path,
    client: ApiClient,
    post_id: str,
    *,
    start_date: str,
    end_date: str,
    capital: float,
    frequency: str,
) -> dict[str, Any]:
    with connect(db_path) as conn:
        archive = row_to_dict(conn.execute("SELECT * FROM strategy_archives WHERE post_id = ?", (post_id,)).fetchone())
    if not archive or archive.get("status") != "downloaded":
        raise ValueError("请先下载策略")
    original_path = Path(str(archive.get("original_code_path") or ""))
    if not original_path.exists():
        raise ValueError("本地原始策略源码不存在，请重新下载")
    strategy_id = str(archive.get("cloned_strategy_id") or "")
    if not strategy_id:
        raise ValueError("缺少克隆策略 ID")

    standardized = standardize_code(original_path.read_text(encoding="utf-8"))
    target_dir = manager_dir / "strategies" / post_id
    target_dir.mkdir(parents=True, exist_ok=True)
    standardized_path = target_dir / "standardized.py"
    standardized_path.write_text(standardized, encoding="utf-8")

    update_strategy(client, strategy_id, code=standardized)
    submitted = run_backtest(
        client,
        strategy_id=strategy_id,
        start_date=start_date,
        end_date=end_date,
        capital=capital,
        frequency=frequency,
    )
    remote_backtest_id = str(submitted.get("id") or "")
    metrics: dict[str, Any] = {}
    status = "submitted"
    if remote_backtest_id:
        try:
            metrics = get_backtest_stats(client, remote_backtest_id).get("metrics", {})
            status = "done" if metrics else "submitted"
        except Exception:
            status = "submitted"

    result_dir = manager_dir / "backtests" / post_id
    result_dir.mkdir(parents=True, exist_ok=True)
    result_path = result_dir / f"{remote_backtest_id or 'pending'}.json"
    result_path.write_text(json.dumps({"submitted": submitted, "metrics": metrics}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    with connect(db_path) as conn:
        conn.execute(
            "UPDATE strategy_archives SET standardized_code_path = ?, updated_at = ? WHERE post_id = ?",
            (str(standardized_path), now_text(), post_id),
        )
        cursor = conn.execute(
            """
            INSERT INTO backtest_runs(
                post_id, strategy_archive_id, remote_strategy_id, remote_backtest_id,
                start_date, end_date, capital, frequency, status,
                annual_return, sharpe, max_drawdown, trading_days, metrics_json,
                result_json_path, submitted_at, completed_at
            )
            VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                post_id,
                archive.get("id"),
                strategy_id,
                remote_backtest_id,
                start_date,
                end_date,
                capital,
                frequency,
                status,
                float_or_none(metrics.get("annual_algo_return") or metrics.get("annual_return")),
                float_or_none(metrics.get("sharpe")),
                float_or_none(metrics.get("max_drawdown")),
                int_or_none(metrics.get("trading_days")),
                json.dumps(metrics, ensure_ascii=False),
                str(result_path),
                now_text(),
                now_text() if status == "done" else None,
            ),
        )
        conn.commit()
        run_id = cursor.lastrowid
    return {"run_id": run_id, "remote_backtest_id": remote_backtest_id, "status": status, "metrics": metrics}


def float_or_none(value: Any) -> float | None:
    try:
        if value in ("", None):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def int_or_none(value: Any) -> int | None:
    try:
        if value in ("", None):
            return None
        return int(float(value))
    except (TypeError, ValueError):
        return None
