from __future__ import annotations

import base64
import re
from html import unescape
from html.parser import HTMLParser
from typing import Any

from .client import ApiClient
from .strategy import parse_strategy_edit_html
from jqcli.errors import ApiError


STATUS_MAP = {"0": "running", "1": "failed", "2": "done", "3": "cancelled"}
BUILD_ERROR_MESSAGES = {
    "50000": "免费回测时间不足；如确认消耗积分继续运行，请传入 --use-credit。",
    "50001": "积分不足，无法继续运行回测。",
}


class _BacktestListParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.rows: list[dict[str, Any]] = []
        self._in_row = False
        self._depth = 0
        self._cell_depth = 0
        self._cell_text: list[str] = []
        self._cells: list[str] = []
        self._attrs: dict[str, str] = {}
        self._source_id = ""

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs_dict = {key.lower(): value or "" for key, value in attrs}
        if tag == "tr" and "backtest-tr" in attrs_dict.get("class", "").split():
            self._in_row = True
            self._depth = 1
            self._cells = []
            self._attrs = attrs_dict
            self._source_id = ""
            return
        if not self._in_row:
            return
        if tag == "input" and "source-code" in attrs_dict.get("class", "").split():
            self._source_id = attrs_dict.get("_backtestid", "")
        if tag not in {"input", "br", "img", "meta", "link"}:
            self._depth += 1
        if tag in {"td", "th"}:
            self._cell_depth = 1
            self._cell_text = []
        elif self._cell_depth and tag != "br":
            self._cell_depth += 1
        if tag == "br" and self._cell_depth:
            self._cell_text.append(" ")

    def handle_endtag(self, tag: str) -> None:
        if not self._in_row:
            return
        if tag in {"input", "br", "img", "meta", "link"}:
            return
        if self._cell_depth:
            self._cell_depth -= 1
            if self._cell_depth == 0 and tag in {"td", "th"}:
                self._cells.append(_normalize(" ".join(self._cell_text)))
        self._depth -= 1
        if self._depth == 0:
            self.rows.append({"attrs": self._attrs, "cells": self._cells, "source_id": self._source_id})
            self._in_row = False

    def handle_data(self, data: str) -> None:
        if self._in_row and self._cell_depth:
            self._cell_text.append(data)


class _InputParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.ids: dict[str, str] = {}
        self.names: dict[str, str] = {}

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag != "input":
            return
        attrs_dict = {key: value or "" for key, value in attrs}
        value = attrs_dict.get("value", "")
        if attrs_dict.get("id"):
            self.ids[str(attrs_dict["id"])] = value
        if attrs_dict.get("name"):
            self.names[str(attrs_dict["name"])] = value


def _normalize(value: str) -> str:
    return re.sub(r"\s+", " ", unescape(value)).strip()


def parse_backtest_list_html(html: str, *, strategy_id: str) -> dict[str, Any]:
    parser = _BacktestListParser()
    parser.feed(html)
    items: list[dict[str, Any]] = []
    for row in parser.rows:
        cells = row["cells"]
        attrs = row["attrs"]
        offset = 0 if cells and cells[0].isdigit() else 1
        raw_status = attrs.get("_status", "")
        date_range = cells[offset + 3] if len(cells) > offset + 3 else ""
        start_date, end_date = _split_date_range(date_range)
        items.append(
            {
                "id": attrs.get("_backtestid2") or attrs.get("_backtestid", ""),
                "list_id": attrs.get("_backtestid", ""),
                "source_id": row.get("source_id", ""),
                "strategy_id": strategy_id,
                "name": cells[offset + 1] if len(cells) > offset + 1 else "",
                "status": _parse_status(raw_status, cells),
                "start_date": start_date,
                "end_date": end_date,
                "capital": _parse_number(cells[offset + 4]) if len(cells) > offset + 4 else None,
                "frequency": cells[offset + 6] if len(cells) > offset + 6 else "",
                "metrics": {
                    "algorithm_return": cells[offset + 7] if len(cells) > offset + 7 else "",
                    "benchmark_return": cells[offset + 8] if len(cells) > offset + 8 else "",
                    "max_drawdown": cells[offset + 9] if len(cells) > offset + 9 else "",
                },
                "submitted_at": cells[offset + 2] if len(cells) > offset + 2 else "",
            }
        )
    return {"items": items}


def _split_date_range(value: str) -> tuple[str, str]:
    dates = re.findall(r"\d{4}-\d{2}-\d{2}", value)
    if len(dates) >= 2:
        return dates[0], dates[1]
    if len(dates) == 1:
        return dates[0], ""
    parts = [part.strip() for part in value.split(" - ")]
    if len(parts) >= 2:
        return parts[0], parts[-1]
    return value, ""


def _parse_number(value: str) -> float | None:
    try:
        return float(value)
    except ValueError:
        return None


def _parse_status(raw_status: str, cells: list[str]) -> str:
    text = " ".join(cells)
    if "完成" in text:
        return "done"
    if "失败" in text:
        return "failed"
    if "取消" in text:
        return "cancelled"
    if "运行" in text or "回测中" in text or "进行中" in text:
        return "running"
    return STATUS_MAP.get(raw_status, raw_status)


def _metrics_have_core_stats(metrics: Any) -> bool:
    return isinstance(metrics, dict) and metrics.get("annual_algo_return") is not None and metrics.get("sharpe") is not None


def _metrics_have_any_stats(metrics: Any) -> bool:
    if not isinstance(metrics, dict):
        return False
    return any(
        metrics.get(key) is not None
        for key in (
            "annual_algo_return",
            "algorithm_return",
            "max_drawdown",
            "sharpe",
            "trading_days",
        )
    )


def _fetch_stats(client: ApiClient, backtest_id: str) -> dict[str, Any]:
    payload = client.get("/algorithm/backtest/stats", params={"backtestId": backtest_id})
    return payload if isinstance(payload, dict) else {}


def _parse_backtest_detail(client: ApiClient, backtest_id: str) -> _InputParser:
    html = client.get_text("/algorithm/backtest/detail", params={"backtestId": backtest_id})
    parser = _InputParser()
    parser.feed(html)
    return parser


def run_backtest(
    client: ApiClient,
    *,
    strategy_id: str,
    start_date: str,
    end_date: str | None = None,
    capital: float | None = None,
    frequency: str = "day",
    compile_only: bool = False,
    use_credit: bool = False,
) -> dict[str, Any]:
    html = client.get_text("/algorithm/index/edit", params={"algorithmId": strategy_id})
    detail = parse_strategy_edit_html(html, requested_id=strategy_id)
    form = dict(detail["_form"])
    form["algorithm[algorithmId]"] = str(detail["save_id"])
    form["algorithm[code]"] = base64.b64encode(str(detail.get("code", "")).encode("utf-8")).decode("ascii")
    form["encrType"] = "base64"
    form["backtest[startTime]"] = f"{start_date} 00:00:00"
    if end_date is not None:
        form["backtest[endTime]"] = f"{end_date} 23:59:59"
    if capital is not None:
        form["backtest[baseCapital]"] = str(capital)
    form["backtest[frequency]"] = "minute" if frequency == "minute" else "day"
    form["backtest[type]"] = "1" if compile_only else "0"
    if use_credit:
        form["useCredit"] = "1"
    data = client.post(
        "/algorithm/index/build",
        data=form,
        headers={"Referer": f"{client.api_base}/algorithm/index/edit?algorithmId={strategy_id}"},
    )
    inner: dict[str, Any] = {}
    if isinstance(data, dict) and isinstance(data.get("data"), dict):
        inner = data["data"]
    if not inner or not (inner.get("backtestId_") or inner.get("backtestId")):
        raw_msg = str(data.get("msg", "")) if isinstance(data, dict) else ""
        message = BUILD_ERROR_MESSAGES.get(raw_msg) or f"创建回测失败：{raw_msg or data}"
        raise ApiError(message, details={"response": data})
    return {
        "id": str(inner.get("backtestId_") or inner.get("backtestId") or ""),
        "list_id": str(inner.get("backtestId") or ""),
        "strategy_id": strategy_id,
        "mode": "compile" if compile_only else "backtest",
        "status": "running",
        "response": data,
    }


def list_backtests(
    client: ApiClient,
    *,
    strategy_id: str,
    status: str = "all",
    limit: int = 50,
    all_items: bool = False,
    compile_only: bool = False,
) -> dict[str, Any]:
    path = "/algorithm/backtest/buildList" if compile_only else "/algorithm/backtest/list"
    html = client.get_text(path, params={"algorithmId": strategy_id})
    payload = parse_backtest_list_html(html, strategy_id=strategy_id)
    items = payload["items"]
    if status != "all":
        items = [item for item in items if item.get("status") == status]
    if not all_items:
        items = items[:limit]
    return {"items": items}


def get_backtest(client: ApiClient, backtest_id: str) -> dict[str, Any]:
    parser = _parse_backtest_detail(client, backtest_id)
    inner_backtest_id = parser.ids.get("backtestId", backtest_id)
    source = client.get("/algorithm/backtest/source", params={"backtestId": inner_backtest_id})
    stats = _fetch_stats(client, inner_backtest_id)
    metrics = stats.get("data", stats) if isinstance(stats, dict) else {}
    return {
        "id": backtest_id,
        "list_id": inner_backtest_id,
        "strategy_id": parser.ids.get("algorithmId", ""),
        "status": "done" if _metrics_have_core_stats(metrics) else "running",
        "start_date": parser.ids.get("startTime", ""),
        "code": source.get("data", {}).get("source", "") if isinstance(source, dict) else "",
        "metrics": metrics,
    }


def get_backtest_stats(client: ApiClient, backtest_id: str) -> dict[str, Any]:
    payload = _fetch_stats(client, backtest_id)
    metrics = payload.get("data", payload) if isinstance(payload, dict) else {}
    resolved_id = backtest_id
    if not _metrics_have_any_stats(metrics):
        parser = _parse_backtest_detail(client, backtest_id)
        inner_backtest_id = parser.ids.get("backtestId", "")
        if inner_backtest_id and inner_backtest_id != backtest_id:
            retry_payload = _fetch_stats(client, inner_backtest_id)
            retry_metrics = retry_payload.get("data", retry_payload) if isinstance(retry_payload, dict) else {}
            if _metrics_have_core_stats(retry_metrics):
                payload = retry_payload
                metrics = retry_metrics
                resolved_id = inner_backtest_id
    return {
        "id": backtest_id,
        "resolved_id": resolved_id,
        "metrics": metrics,
        "response": payload,
    }


def get_backtest_result(
    client: ApiClient,
    backtest_id: str,
    *,
    offset: int = 0,
    user_record_offset: int = 0,
) -> dict[str, Any]:
    payload = client.get(
        "/algorithm/backtest/result",
        params={
            "backtestId": backtest_id,
            "offset": offset,
            "userRecordOffset": user_record_offset,
        },
    )
    data = payload.get("data", payload) if isinstance(payload, dict) else {}
    return {
        "id": backtest_id,
        "offset": offset,
        "user_record_offset": user_record_offset,
        "data": data,
        "response": payload,
    }


def get_backtest_logs(
    client: ApiClient,
    backtest_id: str,
    *,
    offset: int = 0,
    error: bool = False,
    all_items: bool = False,
    max_pages: int = 50,
) -> dict[str, Any]:
    path = "/algorithm/backtest/error" if error else "/algorithm/backtest/log"
    logs: list[str] = []
    responses: list[dict[str, Any]] = []
    current_offset = offset
    state: Any = None
    max_flag = False

    for _ in range(max(1, max_pages)):
        params: dict[str, Any] = {"backtestId": backtest_id}
        if not error:
            params["offset"] = current_offset
        payload = client.get(path, params=params)
        data = payload.get("data", payload) if isinstance(payload, dict) else {}
        page_logs = data.get("logArr", []) if isinstance(data, dict) else []
        if not isinstance(page_logs, list):
            page_logs = []
        logs.extend(str(item) for item in page_logs)
        if isinstance(payload, dict):
            responses.append(payload)
        if isinstance(data, dict):
            state = data.get("state", state)
            max_flag = bool(data.get("max", max_flag))

        if error or not all_items or not page_logs or max_flag:
            break
        current_offset += len(page_logs)

    return {
        "id": backtest_id,
        "kind": "error" if error else "log",
        "offset": offset,
        "next_offset": offset + len(logs) if not error else None,
        "state": state,
        "max": max_flag,
        "logs": logs,
        "response": responses[-1] if len(responses) == 1 else responses,
    }


def delete_backtest(client: ApiClient, backtest_id: str) -> dict[str, Any] | None:
    return delete_backtest_record(client, backtest_id, compile_only=False)


def delete_backtest_record(client: ApiClient, backtest_id: str, *, compile_only: bool = False) -> dict[str, Any] | None:
    data = client.post(
        "/algorithm/backtest/del",
        params={"type": "1" if compile_only else "0"},
        data={"backtestId": backtest_id, "algorithmId": ""},
        headers={"Referer": f"{client.api_base}/algorithm/backtest/{'buildList' if compile_only else 'list'}"},
    )
    ok = False
    if isinstance(data, dict):
        ok = data.get("status") in (0, "0") or data.get("code") in ("00000", 0)
    return {"ok": ok, "id": backtest_id, "mode": "compile" if compile_only else "backtest", "response": data}
