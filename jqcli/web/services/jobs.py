from __future__ import annotations

import json
import threading
import traceback
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from jqcli.web.db import connect, row_to_dict


def now_text() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def create_job(db_path: Path, job_type: str, message: str = "") -> str:
    job_id = uuid.uuid4().hex
    now = now_text()
    with connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO jobs(id, type, status, message, created_at, updated_at)
            VALUES(?, ?, 'pending', ?, ?, ?)
            """,
            (job_id, job_type, message, now, now),
        )
        conn.commit()
    return job_id


def update_job(db_path: Path, job_id: str, **fields: Any) -> None:
    if not fields:
        return
    fields["updated_at"] = now_text()
    assignments = ", ".join(f"{key}=?" for key in fields)
    values = list(fields.values()) + [job_id]
    with connect(db_path) as conn:
        conn.execute(f"UPDATE jobs SET {assignments} WHERE id = ?", values)
        conn.commit()


def get_job(db_path: Path, job_id: str) -> dict[str, Any] | None:
    with connect(db_path) as conn:
        return row_to_dict(conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone())


def start_job(db_path: Path, job_type: str, target: Callable[[str], dict[str, Any] | None], message: str = "") -> str:
    job_id = create_job(db_path, job_type, message)

    def runner() -> None:
        update_job(db_path, job_id, status="running")
        try:
            result = target(job_id) or {}
            update_job(
                db_path,
                job_id,
                status="done",
                result_json=json.dumps(result, ensure_ascii=False),
                finished_at=now_text(),
            )
        except Exception as exc:  # pragma: no cover - exercised through integration failures
            update_job(
                db_path,
                job_id,
                status="failed",
                error=f"{exc}\n{traceback.format_exc()}",
                finished_at=now_text(),
            )

    thread = threading.Thread(target=runner, daemon=True)
    thread.start()
    return job_id
