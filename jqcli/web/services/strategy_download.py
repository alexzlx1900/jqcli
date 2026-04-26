from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from jqcli.api.client import ApiClient
from jqcli.api.community import clone_strategy
from jqcli.api.strategy import get_strategy, list_strategies
from jqcli.web.db import connect, row_to_dict


def now_text() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def download_strategy_for_post(db_path: Path, manager_dir: Path, client: ApiClient, post_id: str) -> dict[str, Any]:
    with connect(db_path) as conn:
        post = row_to_dict(conn.execute("SELECT * FROM posts WHERE id = ?", (post_id,)).fetchone())
        if not post:
            raise ValueError("帖子不存在")
        archive = row_to_dict(conn.execute("SELECT * FROM strategy_archives WHERE post_id = ?", (post_id,)).fetchone())
        if archive and archive.get("status") == "downloaded" and archive.get("original_code_path") and Path(archive["original_code_path"]).exists():
            return {"status": "downloaded", "archive": archive, "skipped": True}
        mark_archive(conn, post_id, post.get("backtest_id") or "", "cloning")

    before = strategy_ids(client)
    cloned = clone_strategy(client, post_id, backtest_id=post.get("backtest_id") or None)
    strategy_id = str(cloned.get("strategy_id") or "")
    if not strategy_id:
        strategy_id = find_new_strategy_id(client, before)
    if not strategy_id:
        raise RuntimeError("克隆完成但未能定位克隆后的策略 ID")

    detail = get_strategy(client, strategy_id, include_code=True)
    code = str(detail.get("code") or "")
    if not code:
        raise RuntimeError("克隆策略未返回源码")

    target_dir = manager_dir / "strategies" / post_id
    target_dir.mkdir(parents=True, exist_ok=True)
    original_path = target_dir / "original.py"
    metadata_path = target_dir / "metadata.json"
    original_path.write_text(code, encoding="utf-8")
    metadata = {
        "post_id": post_id,
        "post_url": post.get("url"),
        "source_backtest_id": post.get("backtest_id"),
        "cloned_strategy_id": strategy_id,
        "cloned_strategy_name": detail.get("name") or post.get("title"),
        "downloaded_at": now_text(),
        "source_hash": hashlib.sha256(code.encode("utf-8")).hexdigest(),
        "clone_response": cloned,
    }
    metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    with connect(db_path) as conn:
        mark_archive(
            conn,
            post_id,
            post.get("backtest_id") or "",
            "downloaded",
            cloned_strategy_id=strategy_id,
            cloned_strategy_name=str(detail.get("name") or post.get("title") or ""),
            original_code_path=str(original_path),
            metadata_path=str(metadata_path),
            downloaded_at=now_text(),
        )
        archive = row_to_dict(conn.execute("SELECT * FROM strategy_archives WHERE post_id = ?", (post_id,)).fetchone())
    return {"status": "downloaded", "archive": archive, "skipped": False}


def mark_archive(conn: Any, post_id: str, backtest_id: str, status: str, **fields: Any) -> None:
    now = now_text()
    data = {
        "post_id": post_id,
        "source_backtest_id": backtest_id,
        "status": status,
        "updated_at": now,
        **fields,
    }
    columns = list(data)
    placeholders = ",".join("?" for _ in columns)
    assignments = ",".join(f"{column}=excluded.{column}" for column in columns if column != "post_id")
    conn.execute(
        f"INSERT INTO strategy_archives({','.join(columns)}) VALUES({placeholders}) ON CONFLICT(post_id) DO UPDATE SET {assignments}",
        [data[column] for column in columns],
    )
    conn.commit()


def strategy_ids(client: ApiClient) -> set[str]:
    try:
        return {str(item.get("id")) for item in list_strategies(client, all_items=True).get("items", []) if item.get("id")}
    except Exception:
        return set()


def find_new_strategy_id(client: ApiClient, before: set[str]) -> str:
    items = list_strategies(client, sort="updated", limit=20).get("items", [])
    for item in items:
        strategy_id = str(item.get("id") or "")
        if strategy_id and strategy_id not in before:
            return strategy_id
    return str(items[0].get("id") or "") if items else ""
