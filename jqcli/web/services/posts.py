from __future__ import annotations

import csv
import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from jqcli.web.db import connect, row_to_dict, rows_to_dicts

from .post_labels import labels_for_post


def now_text() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def import_posts(
    db_path: Path,
    archive_path: Path,
    candidates_path: Path | None = None,
    *,
    refresh_labels: bool = True,
    skip_existing: bool = False,
) -> dict[str, int]:
    candidate_ids = load_candidate_ids(candidates_path)
    seen = 0
    imported = 0
    skipped = 0
    refreshed_at = now_text()
    with connect(db_path) as conn:
        existing_ids = existing_post_ids(conn) if skip_existing else set()
        existing_keys = existing_post_keys(conn) if skip_existing else set()
        if archive_path.exists():
            with archive_path.open(encoding="utf-8") as file:
                for line in file:
                    if not line.strip():
                        continue
                    raw = json.loads(line)
                    post_id = str(raw.get("id") or raw.get("post_id") or "")
                    if post_id in existing_ids:
                        seen += 1
                        skipped += 1
                        continue
                    row = normalize_archive_post(raw, candidate_ids, refreshed_at)
                    if not row:
                        continue
                    logical_key = post_logical_key(row)
                    if skip_existing and logical_key in existing_keys:
                        seen += 1
                        skipped += 1
                        continue
                    seen += 1
                    upsert_post(conn, row)
                    if skip_existing:
                        existing_keys.add(logical_key)
                    imported += 1
        conn.commit()
        label_count = ensure_labels(conn) if refresh_labels else 0
        duplicate_count = mark_duplicate_posts(conn) if imported else 0
    return {
        "seen": seen,
        "imported": imported,
        "skipped": skipped,
        "candidate_ids": len(candidate_ids),
        "labels": label_count,
        "hidden_duplicates": duplicate_count,
    }


def existing_post_ids(conn: Any) -> set[str]:
    return {str(row["id"]) for row in conn.execute("SELECT id FROM posts")}


def existing_post_keys(conn: Any) -> set[str]:
    return {
        str(row["logical_key"])
        for row in conn.execute("SELECT logical_key FROM post_index WHERE logical_key IS NOT NULL AND logical_key != ''")
    }


def post_logical_key(row: dict[str, Any]) -> str:
    content = str(row.get("content_preview") or row.get("content") or "")
    content_hash = hashlib.sha1(content.strip().encode("utf-8")).hexdigest() if content.strip() else ""
    parts = [
        normalize_key_part(row.get("author_name")),
        normalize_key_part(row.get("title")),
        normalize_key_part(row.get("published_at")),
        content_hash,
    ]
    return "\x1f".join(parts)


def normalize_key_part(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def post_count(db_path: Path) -> int:
    with connect(db_path) as conn:
        return int(conn.execute("SELECT COUNT(*) AS c FROM posts").fetchone()["c"])


def rebuild_post_index_if_needed(db_path: Path) -> None:
    with connect(db_path) as conn:
        post_total = int(conn.execute("SELECT COUNT(*) AS c FROM posts").fetchone()["c"])
        index_total = int(conn.execute("SELECT COUNT(*) AS c FROM post_index").fetchone()["c"])
        if post_total and post_total != index_total:
            rebuild_post_index(conn)
            conn.commit()
        mark_duplicate_posts(conn)


def load_candidate_ids(path: Path | None) -> set[str]:
    if path is None or not path.exists():
        return set()
    ids: set[str] = set()
    with path.open(encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        for row in reader:
            if row.get("id"):
                ids.add(str(row["id"]))
    return ids


def normalize_archive_post(raw: dict[str, Any], candidate_ids: set[str], refreshed_at: str) -> dict[str, Any] | None:
    post_id = str(raw.get("id") or raw.get("post_id") or "")
    if not post_id:
        return None
    backtest = raw.get("backtest") if isinstance(raw.get("backtest"), dict) else {}
    stats = backtest.get("stats") if isinstance(backtest.get("stats"), dict) else {}
    author = raw.get("author") if isinstance(raw.get("author"), dict) else {}
    trading_days = int_or_none(stats.get("trading_days"))
    period_years = round(trading_days / 250, 2) if trading_days is not None else None
    return {
        "id": post_id,
        "title": str(raw.get("title") or ""),
        "url": str(raw.get("url") or f"https://www.joinquant.com/view/community/detail/{post_id}"),
        "published_at": str(raw.get("published_at") or ""),
        "updated_at": str(raw.get("updated_at") or raw.get("detail_fetched_at") or ""),
        "author_name": str(author.get("name") or raw.get("author_name") or ""),
        "content": str(raw.get("content") or ""),
        "content_preview": str(raw.get("content_preview") or raw.get("content") or "")[:500],
        "view_count": int_or_none(raw.get("view_count")),
        "like_count": int_or_none(raw.get("like_count")),
        "reply_count": int_or_none(raw.get("reply_count")),
        "backtest_id": str(backtest.get("id") or ""),
        "backtest_name": str(backtest.get("name") or ""),
        "trading_days": trading_days,
        "period_years": period_years,
        "annual_return": float_or_none(stats.get("annual_algo_return") or stats.get("annual_return")),
        "sharpe": float_or_none(stats.get("sharpe")),
        "max_drawdown": float_or_none(stats.get("max_drawdown")),
        "clone_count": int_or_none(backtest.get("clone_count")),
        "is_original_candidate": 1 if post_id in candidate_ids else 0,
        "source": "archive",
        "raw_json": "",
        "created_at": refreshed_at,
        "refreshed_at": refreshed_at,
    }


def upsert_post(conn: Any, row: dict[str, Any]) -> None:
    existing = conn.execute("SELECT created_at FROM posts WHERE id = ?", (row["id"],)).fetchone()
    if existing:
        row["created_at"] = existing["created_at"]
    columns = list(row)
    placeholders = ",".join("?" for _ in columns)
    assignments = ",".join(f"{column}=excluded.{column}" for column in columns if column != "id")
    conn.execute(
        f"INSERT INTO posts ({','.join(columns)}) VALUES ({placeholders}) ON CONFLICT(id) DO UPDATE SET {assignments}",
        [row[column] for column in columns],
    )
    upsert_post_index(conn, row)


def upsert_post_index(conn: Any, row: dict[str, Any]) -> None:
    index_columns = [
        "id",
        "title",
        "url",
        "published_at",
        "updated_at",
        "author_name",
        "content_preview",
        "view_count",
        "like_count",
        "reply_count",
        "backtest_id",
        "backtest_name",
        "trading_days",
        "period_years",
        "annual_return",
        "sharpe",
        "max_drawdown",
        "clone_count",
        "is_original_candidate",
        "is_hidden_duplicate",
        "duplicate_of",
        "logical_key",
    ]
    data = {column: row.get(column) for column in index_columns}
    data["is_hidden_duplicate"] = 0
    data["duplicate_of"] = None
    data["logical_key"] = post_logical_key(row)
    columns = list(data)
    placeholders = ",".join("?" for _ in columns)
    assignments = ",".join(f"{column}=excluded.{column}" for column in columns if column != "id")
    conn.execute(
        f"INSERT INTO post_index({','.join(columns)}) VALUES({placeholders}) ON CONFLICT(id) DO UPDATE SET {assignments}",
        [data[column] for column in columns],
    )


def rebuild_post_index(conn: Any) -> None:
    conn.execute("DELETE FROM post_index")
    conn.execute(
        """
        INSERT INTO post_index(
            id, title, url, published_at, updated_at, author_name, content_preview,
            view_count, like_count, reply_count, backtest_id, backtest_name,
            trading_days, period_years, annual_return, sharpe, max_drawdown,
            clone_count, is_original_candidate, logical_key
        )
        SELECT
            id, title, url, published_at, updated_at, author_name, content_preview,
            view_count, like_count, reply_count, backtest_id, backtest_name,
            trading_days, period_years, annual_return, sharpe, max_drawdown,
            clone_count, is_original_candidate, ''
        FROM posts
        """
    )
    fill_missing_logical_keys(conn)
    conn.execute(
        """
        UPDATE post_index
        SET labels_text = '|原创候选|'
        WHERE is_original_candidate = 1
        """
    )
    mark_duplicate_posts(conn)


def mark_duplicate_posts(conn: Any) -> int:
    conn.execute("UPDATE post_index SET is_hidden_duplicate = 0, duplicate_of = NULL")
    fill_missing_logical_keys(conn)
    duplicate_keys = conn.execute(
        """
        SELECT logical_key
        FROM post_index
        WHERE logical_key IS NOT NULL AND logical_key != ''
        GROUP BY logical_key
        HAVING COUNT(*) > 1
        """
    ).fetchall()
    hidden: list[tuple[str, str]] = []
    for group in duplicate_keys:
        rows = conn.execute(
            """
            SELECT id, backtest_id, clone_count, like_count
            FROM post_index
            WHERE logical_key = ?
            """,
            (group["logical_key"],),
        ).fetchall()
        ranked = sorted(
            rows,
            key=lambda row: (
                1 if str(row["backtest_id"] or "") else 0,
                int(row["clone_count"] or 0),
                int(row["like_count"] or 0),
                str(row["id"] or ""),
            ),
            reverse=True,
        )
        canonical_id = str(ranked[0]["id"])
        hidden.extend((canonical_id, str(row["id"])) for row in ranked[1:])
    if hidden:
        conn.executemany(
            "UPDATE post_index SET is_hidden_duplicate = 1, duplicate_of = ? WHERE id = ?",
            hidden,
        )
    conn.commit()
    return len(hidden)


def fill_missing_logical_keys(conn: Any) -> int:
    rows = conn.execute(
        """
        SELECT id,
               title,
               published_at,
               author_name,
               content_preview
        FROM post_index
        WHERE logical_key IS NULL OR logical_key = ''
        """
    ).fetchall()
    updates = [(post_logical_key(dict(row)), row["id"]) for row in rows]
    if updates:
        conn.executemany("UPDATE post_index SET logical_key = ? WHERE id = ?", updates)
    return len(updates)


def rebuild_logical_keys(conn: Any) -> int:
    rows = conn.execute(
        """
        SELECT id, title, published_at, author_name, content_preview
        FROM post_index
        """
    ).fetchall()
    updates = [(post_logical_key(dict(row)), row["id"]) for row in rows]
    if updates:
        conn.executemany("UPDATE post_index SET logical_key = ? WHERE id = ?", updates)
    return len(updates)


def ensure_labels(conn: Any) -> int:
    posts = conn.execute(
        """
        SELECT id, content, period_years, sharpe, is_original_candidate
        FROM posts
        """
    )
    count = 0
    now = now_text()
    for row in posts:
        post = dict(row)
        label_rows = [
            (post["id"], label["label"], label.get("score"), label.get("reason", ""), now)
            for label in labels_for_post(post)
        ]
        if not label_rows:
            continue
        conn.executemany(
            """
            INSERT INTO post_labels(post_id, label, score, reason, created_at)
            VALUES(?, ?, ?, ?, ?)
            ON CONFLICT(post_id, label) DO UPDATE SET score=excluded.score, reason=excluded.reason
            """,
            label_rows,
        )
        conn.execute("UPDATE post_index SET labels_text = ? WHERE id = ?", (labels_text([item[1] for item in label_rows]), post["id"]))
        count += len(label_rows)
    conn.commit()
    return count


def labels_text(labels: list[str]) -> str:
    return "|" + "|".join(sorted(set(labels))) + "|" if labels else ""


def list_posts(db_path: Path, params: dict[str, Any]) -> dict[str, Any]:
    page = max(1, int(params.get("page") or 1))
    page_size = min(200, max(1, int(params.get("page_size") or 50)))
    joins, where, values = build_filters(params)
    sort = str(params.get("sort") or "published_desc")
    order_by = sort_clause(sort)
    list_table = "post_index p"
    if str(params.get("label") or "") == "原创候选" and sort == "published_desc":
        list_table = "post_index p INDEXED BY idx_post_index_original_published_period"
    elif sort == "published_desc" and not params.get("min_period_years"):
        list_table = "post_index p INDEXED BY idx_post_index_published_at"
    offset = (page - 1) * page_size
    with connect(db_path) as conn:
        total = conn.execute(f"SELECT COUNT(*) AS c FROM post_index p {joins} {where}", values).fetchone()["c"]
        rows = conn.execute(
            f"""
            SELECT p.id,
                   p.title,
                   p.url,
                   p.published_at,
                   p.updated_at,
                   p.author_name,
                   p.content_preview,
                   p.view_count,
                   p.like_count,
                   p.reply_count,
                   p.backtest_id,
                   p.backtest_name,
                   p.trading_days,
                   p.period_years,
                   p.annual_return,
                   p.sharpe,
                   p.max_drawdown,
                   p.clone_count,
                   p.is_original_candidate,
                   p.is_hidden_duplicate,
                   p.duplicate_of,
                   a.status AS download_status,
                   a.cloned_strategy_id,
                   br.id AS last_backtest_run_id,
                   br.status AS last_backtest_status,
                   br.start_date AS last_backtest_start,
                   br.end_date AS last_backtest_end,
                   br.annual_return AS last_backtest_annual_return,
                   br.sharpe AS last_backtest_sharpe
            FROM {list_table}
            LEFT JOIN strategy_archives a ON a.post_id = p.id
            LEFT JOIN backtest_runs br ON br.id = (
                SELECT id FROM backtest_runs WHERE post_id = p.id ORDER BY id DESC LIMIT 1
            )
            {joins}
            {where}
            {order_by}
            LIMIT ? OFFSET ?
            """,
            values + [page_size, offset],
        ).fetchall()
        items = rows_to_dicts(rows)
        attach_labels(conn, items)
    return {"items": items, "page": page, "page_size": page_size, "total": total}


def get_post(db_path: Path, post_id: str) -> dict[str, Any] | None:
    with connect(db_path) as conn:
        post = row_to_dict(conn.execute("SELECT * FROM posts WHERE id = ?", (post_id,)).fetchone())
        if not post:
            return None
        labels = rows_to_dicts(conn.execute("SELECT label, score, reason FROM post_labels WHERE post_id = ? ORDER BY label", (post_id,)))
        archive = row_to_dict(conn.execute("SELECT * FROM strategy_archives WHERE post_id = ?", (post_id,)).fetchone())
        runs = rows_to_dicts(conn.execute("SELECT * FROM backtest_runs WHERE post_id = ? ORDER BY id DESC", (post_id,)).fetchall())
    post["labels"] = labels
    post["archive"] = archive
    post["backtest_runs"] = runs
    return post


def attach_labels(conn: Any, items: list[dict[str, Any]]) -> None:
    if not items:
        return
    ids = [item["id"] for item in items]
    placeholders = ",".join("?" for _ in ids)
    rows = conn.execute(f"SELECT post_id, label FROM post_labels WHERE post_id IN ({placeholders}) ORDER BY label", ids).fetchall()
    grouped: dict[str, list[str]] = {post_id: [] for post_id in ids}
    for row in rows:
        grouped[row["post_id"]].append(row["label"])
    for item in items:
        item["labels"] = grouped.get(item["id"], [])


def build_filters(params: dict[str, Any]) -> tuple[str, str, list[Any]]:
    joins = ""
    clauses: list[str] = []
    values: list[Any] = []
    q = str(params.get("q") or "").strip()
    if q:
        clauses.append("(p.title LIKE ? OR p.content_preview LIKE ?)")
        values.extend([f"%{q}%", f"%{q}%"])
    if str(params.get("include_duplicates") or "") != "1":
        clauses.append("p.is_hidden_duplicate=0")
    if params.get("published_from"):
        clauses.append("p.published_at >= ?")
        values.append(params["published_from"])
    if params.get("published_to"):
        clauses.append("p.published_at <= ?")
        values.append(params["published_to"])
    if params.get("min_period_years"):
        clauses.append("p.period_years >= ?")
        values.append(float(params["min_period_years"]))
    if params.get("min_sharpe"):
        clauses.append("p.sharpe >= ?")
        values.append(float(params["min_sharpe"]))
    if params.get("max_sharpe"):
        clauses.append("p.sharpe <= ?")
        values.append(float(params["max_sharpe"]))
    if params.get("downloaded") in {"0", "1"}:
        if params["downloaded"] == "1":
            clauses.append("EXISTS (SELECT 1 FROM strategy_archives a WHERE a.post_id=p.id AND a.status='downloaded')")
        else:
            clauses.append("NOT EXISTS (SELECT 1 FROM strategy_archives a WHERE a.post_id=p.id AND a.status='downloaded')")
    if params.get("backtested") in {"0", "1"}:
        if params["backtested"] == "1":
            clauses.append("EXISTS (SELECT 1 FROM backtest_runs br WHERE br.post_id=p.id)")
        else:
            clauses.append("NOT EXISTS (SELECT 1 FROM backtest_runs br WHERE br.post_id=p.id)")
    if params.get("label"):
        label = str(params["label"])
        if label == "原创候选":
            clauses.append("p.is_original_candidate=1")
        else:
            clauses.append("p.labels_text LIKE ?")
            values.append(f"%|{label}|%")
    return joins, ("WHERE " + " AND ".join(clauses)) if clauses else "", values


def sort_clause(sort: str) -> str:
    mapping = {
        "published_asc": "ORDER BY p.published_at ASC",
        "sharpe_desc": "ORDER BY p.sharpe DESC NULLS LAST",
        "annual_desc": "ORDER BY p.annual_return DESC NULLS LAST",
        "period_desc": "ORDER BY p.period_years DESC NULLS LAST",
    }
    return mapping.get(sort, "ORDER BY p.published_at DESC")


def int_or_none(value: Any) -> int | None:
    try:
        if value in ("", None):
            return None
        return int(float(value))
    except (TypeError, ValueError):
        return None


def float_or_none(value: Any) -> float | None:
    try:
        if value in ("", None):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None
