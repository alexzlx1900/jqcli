from __future__ import annotations

import base64
import re
from html import unescape
from html.parser import HTMLParser
from typing import Any

from .client import ApiClient
from .strategy import parse_strategy_edit_html


STATUS_MAP = {"0": "running", "1": "failed", "2": "done", "3": "cancelled"}


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
                "status": STATUS_MAP.get(raw_status, raw_status),
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


def run_backtest(
    client: ApiClient,
    *,
    strategy_id: str,
    start_date: str,
    end_date: str | None = None,
    capital: float | None = None,
    frequency: str = "day",
    compile_only: bool = False,
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
    data = client.post(
        "/algorithm/index/build",
        data=form,
        headers={"Referer": f"{client.api_base}/algorithm/index/edit?algorithmId={strategy_id}"},
    )
    inner: dict[str, Any] = {}
    if isinstance(data, dict) and isinstance(data.get("data"), dict):
        inner = data["data"]
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
    html = client.get_text("/algorithm/backtest/detail", params={"backtestId": backtest_id})
    parser = _InputParser()
    parser.feed(html)
    source = client.get("/algorithm/backtest/source", params={"backtestId": parser.ids.get("backtestId", backtest_id)})
    stats = client.get("/algorithm/backtest/stats", params={"backtestId": parser.ids.get("backtestId", backtest_id)})
    return {
        "id": backtest_id,
        "list_id": parser.ids.get("backtestId", ""),
        "strategy_id": parser.ids.get("algorithmId", ""),
        "status": "done",
        "start_date": parser.ids.get("startTime", ""),
        "code": source.get("data", {}).get("source", "") if isinstance(source, dict) else "",
        "metrics": stats.get("data", stats) if isinstance(stats, dict) else {},
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
