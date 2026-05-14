from __future__ import annotations

import base64
import csv
import re
from html import unescape
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from .client import ApiClient


_VOID_TAGS = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}


class _StrategyListParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.rows: list[dict[str, Any]] = []
        self._in_row = False
        self._row_depth = 0
        self._row_html: list[str] = []
        self._cell_depth = 0
        self._cell_text: list[str] = []
        self._cells: list[str] = []
        self._links: list[str] = []
        self._internal_id: str | None = None
        self._folder_id: str | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs_dict = dict(attrs)
        if tag == "tr" and self._has_class(attrs_dict, "algorithm_list"):
            self._in_row = True
            self._row_depth = 1
            self._row_html = [self.get_starttag_text() or ""]
            self._cells = []
            self._links = []
            self._internal_id = attrs_dict.get("_algorithmid") or attrs_dict.get("_algorithmId")
            self._folder_id = attrs_dict.get("_fid") or attrs_dict.get("_fId")
            return
        if not self._in_row:
            return
        self._row_html.append(self.get_starttag_text() or "")
        if self._internal_id is None:
            self._internal_id = attrs_dict.get("_algorithmid") or attrs_dict.get("_algorithmId")
        if self._folder_id is None:
            self._folder_id = attrs_dict.get("_fid") or attrs_dict.get("_fId")
        if tag in _VOID_TAGS:
            return
        self._row_depth += 1
        if tag in {"td", "th"}:
            self._cell_depth = 1
            self._cell_text = []
        elif self._cell_depth:
            self._cell_depth += 1
        if tag == "a" and attrs_dict.get("href"):
            self._links.append(str(attrs_dict["href"]))

    def handle_endtag(self, tag: str) -> None:
        if not self._in_row:
            return
        self._row_html.append(f"</{tag}>")
        if self._cell_depth:
            self._cell_depth -= 1
            if self._cell_depth == 0 and tag in {"td", "th"}:
                self._cells.append(_normalize_text(" ".join(self._cell_text)))
        self._row_depth -= 1
        if self._row_depth == 0:
            self.rows.append(
                {
                    "html": "".join(self._row_html),
                    "cells": self._cells,
                    "links": self._links,
                    "internal_id": self._internal_id,
                    "folder_id": self._folder_id,
                }
            )
            self._in_row = False

    def handle_data(self, data: str) -> None:
        if not self._in_row:
            return
        self._row_html.append(data)
        if self._cell_depth:
            self._cell_text.append(data)

    def handle_entityref(self, name: str) -> None:
        self.handle_data(unescape(f"&{name};"))

    def handle_charref(self, name: str) -> None:
        self.handle_data(unescape(f"&#{name};"))

    @staticmethod
    def _has_class(attrs: dict[str, str | None], class_name: str) -> bool:
        return class_name in str(attrs.get("class", "")).split()


class _FormParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.fields: dict[str, str] = {}
        self.ids: dict[str, str] = {}
        self._textarea_name: str | None = None
        self._textarea_id: str | None = None
        self._textarea_data: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs_dict = {key: value or "" for key, value in attrs}
        if tag == "input":
            value = attrs_dict.get("value", "")
            name = attrs_dict.get("name")
            id_ = attrs_dict.get("id")
            if name:
                self.fields[name] = value
            if id_:
                self.ids[id_] = value
        elif tag == "textarea":
            self._textarea_name = attrs_dict.get("name") or None
            self._textarea_id = attrs_dict.get("id") or None
            self._textarea_data = []

    def handle_endtag(self, tag: str) -> None:
        if tag != "textarea" or (self._textarea_name is None and self._textarea_id is None):
            return
        value = "".join(self._textarea_data)
        if self._textarea_name:
            self.fields[self._textarea_name] = value
        if self._textarea_id:
            self.ids[self._textarea_id] = value
        self._textarea_name = None
        self._textarea_id = None
        self._textarea_data = []

    def handle_data(self, data: str) -> None:
        if self._textarea_name is not None or self._textarea_id is not None:
            self._textarea_data.append(data)


def _normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def _strategy_id_from_links(links: list[str]) -> str | None:
    for link in links:
        query = parse_qs(urlparse(link).query)
        values = query.get("algorithmId")
        if values and values[0]:
            return values[0]
    return None


def _folder_id_from_row(row: dict[str, Any]) -> str | None:
    if row.get("folder_id"):
        return str(row["folder_id"])
    for link in row["links"]:
        query = parse_qs(urlparse(link).query)
        values = query.get("fId")
        if values and values[0]:
            return values[0]
    return None


def parse_strategy_list_html(html: str) -> dict[str, Any]:
    parser = _StrategyListParser()
    parser.feed(html)
    items: list[dict[str, Any]] = []
    folders: list[dict[str, Any]] = []
    for row in parser.rows:
        cells = list(row["cells"])
        strategy_id = _strategy_id_from_links(row["links"])
        if not strategy_id:
            folder_id = _folder_id_from_row(row)
            if folder_id:
                folders.append({"id": folder_id, "name": cells[1] if len(cells) > 1 else ""})
            continue
        item: dict[str, Any] = {
            "id": strategy_id,
            "internal_id": row["internal_id"],
            "name": cells[1] if len(cells) > 1 else "",
            "type": cells[2] if len(cells) > 2 else "",
            "created_at": "",
            "updated_at": cells[3] if len(cells) > 3 else "",
        }
        if len(cells) > 4 and cells[4] != "":
            item["run_count"] = _parse_int(cells[4])
        if len(cells) > 5 and cells[5] != "":
            item["backtest_count"] = _parse_int(cells[5])
        items.append(item)
    payload: dict[str, Any] = {"items": items}
    if folders:
        payload["folders"] = folders
    return payload


def _parse_int(value: str) -> int | str:
    try:
        return int(value)
    except ValueError:
        return value


def _listing_max_page(html: str) -> int:
    pages = [1]
    for href in re.findall(r"""href=["']([^"']+)["']""", html):
        parsed = urlparse(unescape(href))
        if parsed.path != "/algorithm/index/list":
            continue
        values = parse_qs(parsed.query).get("page")
        if not values:
            continue
        try:
            pages.append(int(values[0]))
        except ValueError:
            continue
    return max(pages)


def _listing_params(*, folder_id: str | None = None, page: int | None = None) -> dict[str, Any]:
    params: dict[str, Any] = {}
    if folder_id:
        params["fId"] = folder_id
    if page and page > 1:
        params["page"] = page
    return params


def _list_strategy_pages(client: ApiClient, *, folder_id: str | None = None) -> dict[str, list[dict[str, Any]]]:
    html = client.get_text("/algorithm/index/list", params=_listing_params(folder_id=folder_id))
    first_payload = parse_strategy_list_html(html)
    items = list(first_payload["items"])
    folders = list(first_payload.get("folders", []))
    for page in range(2, _listing_max_page(html) + 1):
        page_html = client.get_text("/algorithm/index/list", params=_listing_params(folder_id=folder_id, page=page))
        payload = parse_strategy_list_html(page_html)
        items.extend(payload["items"])
        folders.extend(payload.get("folders", []))
    return {"items": items, "folders": folders}


def list_strategies(client: ApiClient, *, sort: str = "updated", limit: int = 50, all_items: bool = False) -> dict[str, Any]:
    items: list[dict[str, Any]] = []
    folders: list[dict[str, Any]] = []
    seen_items: set[str] = set()
    seen_folders: set[str] = set()
    pending_folder_ids: list[str | None] = [None]
    while pending_folder_ids:
        folder_id = pending_folder_ids.pop(0)
        if folder_id is not None:
            if folder_id in seen_folders:
                continue
            seen_folders.add(folder_id)
        payload = _list_strategy_pages(client, folder_id=folder_id)
        for item in payload["items"]:
            item_id = str(item.get("id", ""))
            if item_id in seen_items:
                continue
            seen_items.add(item_id)
            if folder_id:
                item["folder_id"] = folder_id
            items.append(item)
        for folder in payload["folders"]:
            folder_id_value = str(folder.get("id", ""))
            if not folder_id_value or folder_id_value in seen_folders:
                continue
            folders.append(folder)
            pending_folder_ids.append(folder_id_value)
    if sort == "name":
        items.sort(key=lambda item: str(item.get("name", "")))
    elif sort == "updated":
        items.sort(key=lambda item: str(item.get("updated_at", "")), reverse=True)
    if not all_items:
        items = items[:limit]
    return {"items": items}


def list_strategy_folders(client: ApiClient, *, parent_id: str = "0") -> dict[str, Any]:
    data = client.get("/algorithm/index/GetFileList", params={"pId": parent_id})
    file_arr = {}
    if isinstance(data, dict):
        inner = data.get("data")
        if isinstance(inner, dict):
            file_arr = inner.get("fileArr") or []
        else:
            file_arr = data.get("fileArr") or []
    folders = []
    if isinstance(file_arr, list):
        for item in file_arr:
            if not isinstance(item, dict):
                continue
            folder_id = item.get("fId") or item.get("id")
            name = item.get("name")
            if folder_id is not None and name:
                folders.append({"id": str(folder_id), "name": str(name)})
    return {"items": folders, "parent_id": parent_id}


def create_strategy_folder(client: ApiClient, name: str, *, parent_id: str = "0") -> dict[str, Any]:
    data = client.get("/algorithm/index/AddFile", params={"name": name, "pId": parent_id})
    folder_id = ""
    if isinstance(data, dict):
        inner = data.get("data")
        if inner is not None:
            folder_id = str(inner)
        elif data.get("fId") is not None:
            folder_id = str(data["fId"])
    return {"id": folder_id, "name": name, "parent_id": parent_id, "response": data}


def move_strategies_to_folder(client: ApiClient, internal_ids: list[str], folder_id: str) -> dict[str, Any]:
    ids = ",".join([str(value) for value in internal_ids if str(value)])
    if not ids:
        return {"ok": True, "moved": 0, "folder_id": folder_id, "response": None}
    data = client.get("/algorithm/index/AlgorithmToFile", params={"ids": ids, "fId": folder_id})
    ok = True
    if isinstance(data, dict):
        ok = data.get("status") in (None, 0, "0") and data.get("code") in (None, "00000", 0)
    return {"ok": ok, "moved": len(internal_ids), "folder_id": folder_id, "response": data}


def build_strategy_folder_sync_plan(
    remote_items: list[dict[str, Any]],
    index_rows: list[dict[str, str]],
    *,
    category_names: dict[str, str],
) -> dict[str, Any]:
    remote_by_id = {str(item.get("id", "")): item for item in remote_items}
    remote_by_name = {str(item.get("name", "")): item for item in remote_items}
    categories: dict[str, dict[str, Any]] = {}
    skipped_existing_folder: list[dict[str, Any]] = []
    unmatched: list[dict[str, Any]] = []
    planned_total = 0
    for row in index_rows:
        strategy_id = str(row.get("strategy_id") or "")
        name = str(row.get("name") or "")
        remote = remote_by_id.get(strategy_id) or remote_by_name.get(name)
        if not remote:
            unmatched.append({"strategy_id": strategy_id, "name": name, "reason": "not_found_in_remote"})
            continue
        folder_id = str(remote.get("folder_id") or "")
        if folder_id:
            skipped_existing_folder.append(
                {
                    "strategy_id": strategy_id,
                    "name": name,
                    "remote_id": remote.get("id", ""),
                    "folder_id": folder_id,
                }
            )
            continue
        internal_id = str(remote.get("internal_id") or "")
        if not internal_id:
            unmatched.append({"strategy_id": strategy_id, "name": name, "reason": "missing_internal_id"})
            continue
        category = str(row.get("primary_category") or "uncategorized")
        folder_name = category_names.get(category, category)
        bucket = categories.setdefault(category, {"folder_name": folder_name, "items": []})
        bucket["items"].append(
            {
                "strategy_id": strategy_id,
                "remote_id": remote.get("id", ""),
                "internal_id": internal_id,
                "name": name,
                "current_folder_id": "",
            }
        )
        planned_total += 1
    return {
        "parent_folder_id": "0",
        "categories": categories,
        "planned_move_count": planned_total,
        "skipped_existing_folder_count": len(skipped_existing_folder),
        "skipped_existing_folder": skipped_existing_folder,
        "unmatched_count": len(unmatched),
        "unmatched": unmatched,
    }


def load_strategy_index_rows(path: str) -> list[dict[str, str]]:
    try:
        with Path(path).open(encoding="utf-8-sig", newline="") as file:
            return [dict(row) for row in csv.DictReader(file)]
    except OSError as exc:
        from jqcli.errors import FileError

        raise FileError(f"无法读取索引文件 {path}") from exc


def parse_strategy_edit_html(html: str, *, requested_id: str) -> dict[str, Any]:
    parser = _FormParser()
    parser.feed(html)
    save_id = parser.fields.get("algorithm[algorithmId]") or parser.ids.get("algorithmId") or requested_id
    return {
        "id": requested_id,
        "save_id": save_id,
        "backtest_id": parser.ids.get("backtestId", ""),
        "name": parser.fields.get("algorithm[name]", ""),
        "type": "Code",
        "created_at": "",
        "updated_at": "",
        "code": parser.fields.get("algorithm[code]", ""),
        "_form": parser.fields,
    }


def get_strategy(client: ApiClient, strategy_id: str, *, include_code: bool = False) -> dict[str, Any]:
    html = client.get_text("/algorithm/index/edit", params={"algorithmId": strategy_id})
    payload = parse_strategy_edit_html(html, requested_id=strategy_id)
    payload.pop("_form", None)
    if not include_code:
        payload.pop("code", None)
    return payload


def create_strategy(client: ApiClient, *, name: str, code: str | None, strategy_type: str) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    if code is not None:
        payload["code"] = code
    data = client.post("/algorithm/index/new", data=payload, headers={"Referer": f"{client.api_base}/algorithm/index/list"})
    strategy_id = _extract_strategy_id(data)
    if not strategy_id:
        items = list_strategies(client, sort="updated", limit=10)["items"]
        strategy_id = str(items[0]["id"]) if items else ""
    if name and strategy_id:
        update_strategy(client, strategy_id, name=name, code=code)
    listed = _find_strategy_by_name(client, name) if name else None
    if listed:
        strategy_id = str(listed["id"])
    return {"id": strategy_id, "name": name, "type": strategy_type}


def update_strategy(client: ApiClient, strategy_id: str, *, name: str | None = None, code: str | None = None) -> dict[str, Any]:
    html = client.get_text("/algorithm/index/edit", params={"algorithmId": strategy_id})
    detail = parse_strategy_edit_html(html, requested_id=strategy_id)
    payload: dict[str, Any] = dict(detail["_form"])
    payload["algorithm[algorithmId]"] = str(detail["save_id"])
    if name is not None:
        payload["algorithm[name]"] = name
    if code is not None:
        payload["algorithm[code]"] = base64.b64encode(code.encode("utf-8")).decode("ascii")
        payload["encrType"] = "base64"
    data = client.post(
        "/algorithm/index/save",
        data=payload,
        headers={"Referer": f"{client.api_base}/algorithm/index/edit?algorithmId={strategy_id}"},
    )
    saved_id = _extract_strategy_id(data) or str(detail["save_id"])
    listed = _find_strategy_by_name(client, str(payload.get("algorithm[name]", "")))
    return {
        "id": str(listed["id"]) if listed else strategy_id,
        "save_id": saved_id,
        "name": payload.get("algorithm[name]", ""),
    }


def delete_strategy(client: ApiClient, strategy_id: str) -> dict[str, Any] | None:
    internal_id = _resolve_internal_strategy_id(client, strategy_id)
    data = client.post(
        "/algorithm/index/del",
        data={"algorithmId": internal_id},
        headers={"Referer": f"{client.api_base}/algorithm/index/list"},
    )
    ok = False
    if isinstance(data, dict):
        ok = data.get("status") in (0, "0") or data.get("code") in ("00000", 0)
    return {"ok": ok, "id": strategy_id, "internal_id": internal_id, "response": data}


def _extract_strategy_id(data: Any) -> str | None:
    if not isinstance(data, dict):
        return None
    inner = data.get("data")
    if isinstance(inner, dict):
        for key in ("algorithmId", "id"):
            if inner.get(key):
                return str(inner[key])
    for key in ("algorithmId", "id"):
        if data.get(key):
            return str(data[key])
    return None


def _resolve_internal_strategy_id(client: ApiClient, strategy_id: str) -> str:
    items = list_strategies(client, all_items=True)["items"]
    for item in items:
        if strategy_id in {str(item.get("id", "")), str(item.get("internal_id", ""))}:
            return str(item.get("internal_id") or item["id"])
    try:
        detail = get_strategy(client, strategy_id)
    except Exception:
        detail = {}
    if detail.get("name"):
        for item in list_strategies(client, all_items=True)["items"]:
            if item.get("name") == detail["name"]:
                return str(item.get("internal_id") or item["id"])
    return strategy_id


def _find_strategy_by_name(client: ApiClient, name: str) -> dict[str, Any] | None:
    if not name:
        return None
    items = list_strategies(client, sort="updated", all_items=True)["items"]
    for item in items:
        if item.get("name") == name:
            return item
    return None
