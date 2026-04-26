from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any, Iterable


SCHEMA = """
CREATE TABLE IF NOT EXISTS posts (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    url TEXT NOT NULL,
    published_at TEXT,
    updated_at TEXT,
    author_name TEXT,
    content TEXT,
    content_preview TEXT,
    view_count INTEGER,
    like_count INTEGER,
    reply_count INTEGER,
    backtest_id TEXT,
    backtest_name TEXT,
    trading_days INTEGER,
    period_years REAL,
    annual_return REAL,
    sharpe REAL,
    max_drawdown REAL,
    clone_count INTEGER,
    is_original_candidate INTEGER DEFAULT 0,
    source TEXT,
    raw_json TEXT,
    created_at TEXT NOT NULL,
    refreshed_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS post_index (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    url TEXT NOT NULL,
    published_at TEXT,
    updated_at TEXT,
    author_name TEXT,
    content_preview TEXT,
    view_count INTEGER,
    like_count INTEGER,
    reply_count INTEGER,
    backtest_id TEXT,
    backtest_name TEXT,
    trading_days INTEGER,
    period_years REAL,
    annual_return REAL,
    sharpe REAL,
    max_drawdown REAL,
    clone_count INTEGER,
    is_original_candidate INTEGER DEFAULT 0,
    labels_text TEXT DEFAULT '',
    is_hidden_duplicate INTEGER DEFAULT 0,
    duplicate_of TEXT,
    logical_key TEXT
);

CREATE TABLE IF NOT EXISTS post_labels (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    post_id TEXT NOT NULL,
    label TEXT NOT NULL,
    score REAL,
    reason TEXT,
    created_at TEXT NOT NULL,
    UNIQUE(post_id, label)
);

CREATE TABLE IF NOT EXISTS strategy_archives (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    post_id TEXT NOT NULL UNIQUE,
    source_backtest_id TEXT,
    cloned_strategy_id TEXT,
    cloned_strategy_name TEXT,
    original_code_path TEXT,
    standardized_code_path TEXT,
    metadata_path TEXT,
    status TEXT NOT NULL,
    error TEXT,
    downloaded_at TEXT,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS backtest_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    post_id TEXT NOT NULL,
    strategy_archive_id INTEGER,
    remote_strategy_id TEXT,
    remote_backtest_id TEXT,
    start_date TEXT NOT NULL,
    end_date TEXT NOT NULL,
    capital REAL NOT NULL,
    frequency TEXT NOT NULL,
    status TEXT NOT NULL,
    annual_return REAL,
    sharpe REAL,
    max_drawdown REAL,
    trading_days INTEGER,
    metrics_json TEXT,
    result_json_path TEXT,
    submitted_at TEXT,
    completed_at TEXT,
    error TEXT
);

CREATE TABLE IF NOT EXISTS jobs (
    id TEXT PRIMARY KEY,
    type TEXT NOT NULL,
    status TEXT NOT NULL,
    progress_current INTEGER DEFAULT 0,
    progress_total INTEGER,
    message TEXT,
    result_json TEXT,
    error TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    finished_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_posts_published_at ON posts(published_at);
CREATE INDEX IF NOT EXISTS idx_posts_sharpe ON posts(sharpe);
CREATE INDEX IF NOT EXISTS idx_posts_period_years ON posts(period_years);
CREATE INDEX IF NOT EXISTS idx_post_index_published_at ON post_index(published_at);
CREATE INDEX IF NOT EXISTS idx_post_index_period_years ON post_index(period_years);
CREATE INDEX IF NOT EXISTS idx_post_index_sharpe ON post_index(sharpe);
CREATE INDEX IF NOT EXISTS idx_post_index_original ON post_index(is_original_candidate);
CREATE INDEX IF NOT EXISTS idx_post_index_original_period ON post_index(is_original_candidate, period_years);
CREATE INDEX IF NOT EXISTS idx_post_index_original_published ON post_index(is_original_candidate, published_at);
CREATE INDEX IF NOT EXISTS idx_post_index_original_published_period ON post_index(is_original_candidate, published_at, period_years);
CREATE INDEX IF NOT EXISTS idx_post_labels_post_id ON post_labels(post_id);
CREATE INDEX IF NOT EXISTS idx_post_labels_label_post_id ON post_labels(label, post_id);
CREATE INDEX IF NOT EXISTS idx_backtest_runs_post_id ON backtest_runs(post_id);
"""


def connect(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db(db_path: Path) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with connect(db_path) as conn:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.executescript(SCHEMA)
        ensure_columns(conn)


def ensure_columns(conn: sqlite3.Connection) -> None:
    post_index_columns = {row["name"] for row in conn.execute("PRAGMA table_info(post_index)")}
    if "is_hidden_duplicate" not in post_index_columns:
        conn.execute("ALTER TABLE post_index ADD COLUMN is_hidden_duplicate INTEGER DEFAULT 0")
    if "duplicate_of" not in post_index_columns:
        conn.execute("ALTER TABLE post_index ADD COLUMN duplicate_of TEXT")
    if "logical_key" not in post_index_columns:
        conn.execute("ALTER TABLE post_index ADD COLUMN logical_key TEXT")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_post_index_duplicate ON post_index(is_hidden_duplicate)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_post_index_title_time ON post_index(title, published_at)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_post_index_logical_key ON post_index(logical_key)")


def row_to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    return dict(row) if row is not None else None


def rows_to_dicts(rows: Iterable[sqlite3.Row]) -> list[dict[str, Any]]:
    return [dict(row) for row in rows]
