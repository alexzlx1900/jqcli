from __future__ import annotations

import math
from datetime import datetime, time
from typing import Any
from urllib.parse import parse_qs, urlparse

from jqcli.errors import ApiError, UsageError

from .client import ApiClient


COMMUNITY_CATEGORY_TAG_IDS = {
    1: "3",
    2: "10",
    3: "13",
    4: "14",
    5: "16",
}


def parse_until(value: str | None) -> datetime | None:
    if value is None:
        return None
    value = value.strip()
    if not value:
        raise UsageError("--until 不能为空")
    if len(value) == 10:
        try:
            return datetime.combine(datetime.strptime(value, "%Y-%m-%d").date(), time.min)
        except ValueError as exc:
            raise UsageError("--until 日期格式应为 YYYY-MM-DD 或 YYYY-MM-DD HH:MM:SS") from exc
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        try:
            return datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
        except ValueError as exc:
            raise UsageError("--until 日期格式应为 YYYY-MM-DD 或 YYYY-MM-DD HH:MM:SS") from exc


def parse_joinquant_time(value: str | None) -> datetime | None:
    if not value:
        return None
    value = value.strip()
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            pass
    return None


def normalize_post(raw: dict[str, Any]) -> dict[str, Any]:
    user = raw.get("user") if isinstance(raw.get("user"), dict) else {}
    tags = raw.get("tagInfo") if isinstance(raw.get("tagInfo"), list) else []
    return {
        "id": str(raw.get("postId", "")),
        "title": str(raw.get("title", "")),
        "url": f"https://www.joinquant.com/view/community/detail/{raw.get('postId', '')}",
        "author": {
            "id": str(user.get("userId", "")),
            "name": str(user.get("alias", "")),
        },
        "published_at": str(raw.get("addTime", "")),
        "updated_at": str(raw.get("modTime", "")),
        "last_active_at": str(raw.get("lastActiveTime", "")),
        "last_reply_at": str(raw.get("lastReplyTime", "")),
        "reply_count": _int_or_zero(raw.get("replyCount")),
        "view_count": _int_or_zero(raw.get("viewCount")),
        "like_count": _int_or_zero(raw.get("likeCount")),
        "collection_count": _int_or_zero(raw.get("collectionCount")),
        "is_top": _bool_int(raw.get("isTop")),
        "is_best": _bool_int(raw.get("isBest")),
        "backtest": {
            "id": str(raw.get("backtestId", "")),
            "clone_count": _int_or_zero(raw.get("backtestCloneCount")),
            "pic_url": str(raw.get("backtestPicUrl", "")),
        },
        "research": {
            "notebook_path": str(raw.get("notebookPath", "")),
            "notebook_report": str(raw.get("notebookReport", "")),
            "notebook_clone_count": _int_or_zero(raw.get("notebookCloneCount")),
        },
        "file": {
            "key": str(raw.get("fileKey", "")),
            "name": str(raw.get("fileName", "")),
            "type": str(raw.get("fileType", "")),
            "download_count": _int_or_zero(raw.get("fileDownloadCount")),
        },
        "tags": [
            {
                "id": str(tag.get("tagKey", tag.get("tagId", ""))),
                "name": str(tag.get("name", "")),
            }
            for tag in tags
            if isinstance(tag, dict)
        ],
        "content_preview": str(raw.get("content", "")),
    }


def normalize_detail(raw: dict[str, Any], *, requested_post_id: str) -> dict[str, Any]:
    author = raw.get("author") if isinstance(raw.get("author"), dict) else {}
    tags = raw.get("tagInfo") if isinstance(raw.get("tagInfo"), list) else []
    return {
        "id": str(raw.get("postId", "")),
        "requested_id": requested_post_id,
        "title": str(raw.get("title", "")),
        "url": f"https://www.joinquant.com/view/community/detail/{requested_post_id}",
        "content": str(raw.get("content", "")),
        "author": {
            "id": str(author.get("userId", raw.get("userId", ""))),
            "name": str(author.get("alias", "")),
            "head_img_key": str(author.get("headImgKey", "")),
            "vip_type": str(author.get("vipType", "")),
        },
        "published_at": str(raw.get("addTime", "")),
        "updated_at": str(raw.get("modTime", "")),
        "last_active_at": str(raw.get("lastActiveTime", "")),
        "last_reply_id": str(raw.get("lastReplyId", "")),
        "reply_count": _int_or_zero(raw.get("replyCount")),
        "view_count": _int_or_zero(raw.get("viewCount")),
        "like_count": _int_or_zero(raw.get("likeCount")),
        "dislike_count": _int_or_zero(raw.get("disLikeCount")),
        "collection_count": _int_or_zero(raw.get("collectionCount")),
        "is_top": _bool_int(raw.get("isTop")),
        "is_best": _bool_int(raw.get("isBest")),
        "is_rich": _bool_int(raw.get("isRich")),
        "is_worth": _bool_int(raw.get("isWorth")),
        "type": _int_or_none(raw.get("type")),
        "status": str(raw.get("status", "")),
        "ip_address": str(raw.get("ipAddress", "")),
        "backtest": {
            "id": str(raw.get("backtestId", "")),
            "name": str(raw.get("backtestName", "")),
            "clone_count": _int_or_zero(raw.get("backtestCloneCount")),
        },
        "research": {
            "notebook_path": str(raw.get("notebookPath", "")),
            "notebook_report": str(raw.get("notebookReport", "")),
            "notebook_clone_count": _int_or_zero(raw.get("notebookCloneCount")),
        },
        "file": {
            "key": str(raw.get("fileKey", "")),
            "name": str(raw.get("fileName", "")),
            "type": str(raw.get("fileType", "")),
            "size": _int_or_zero(raw.get("fileSize")),
            "download_count": _int_or_zero(raw.get("fileDownloadCount")),
        },
        "tags": [
            {
                "id": str(tag.get("tagKey", tag.get("tagId", ""))),
                "name": str(tag.get("name", "")),
            }
            for tag in tags
            if isinstance(tag, dict)
        ],
        "bounty": raw.get("bounty") if isinstance(raw.get("bounty"), (dict, list)) else [],
        "curr_time": str(raw.get("currTime", "")),
    }


def normalize_reply(raw: dict[str, Any]) -> dict[str, Any]:
    user = raw.get("user") if isinstance(raw.get("user"), dict) else {}
    sub_reply = raw.get("subReply")
    if isinstance(sub_reply, dict):
        sub_items = sub_reply.get("list") if isinstance(sub_reply.get("list"), list) else []
        leave_count = _int_or_zero(sub_reply.get("leaveCount"))
    elif isinstance(sub_reply, list):
        sub_items = sub_reply
        leave_count = 0
    else:
        sub_items = []
        leave_count = 0

    return {
        "id": str(raw.get("replyId", "")),
        "post_id": str(raw.get("postId", "")),
        "content": str(raw.get("content", "")),
        "author": {
            "id": str(user.get("userId", raw.get("userId", ""))),
            "name": str(user.get("alias", "")),
            "head_img_key": str(user.get("headImgKey", "")),
            "vip_type": str(user.get("vipType", "")),
        },
        "published_at": str(raw.get("addTime", "")),
        "updated_at": str(raw.get("modTime", "")),
        "ip_address": str(raw.get("ipAddress", "")),
        "is_best": _bool_int(raw.get("isBest")),
        "is_rich": _bool_int(raw.get("isRich")),
        "is_owner": bool(raw.get("isOwner")),
        "is_post_user": bool(raw.get("isPostUser")),
        "backtest": {
            "id": str(raw.get("backtestId", "")),
            "name": str(raw.get("backtestName", "")),
            "overall_return": _float_or_none(raw.get("overallReturn")),
        },
        "parent_reply_id": str(raw.get("pReplyId", "")),
        "original_reply_id": str(raw.get("oReplyId", "")),
        "sub_replies": [normalize_reply(item) for item in sub_items if isinstance(item, dict)],
        "sub_reply_remaining_count": leave_count,
    }


def list_latest_posts(
    client: ApiClient,
    *,
    page_size: int = 50,
    max_pages: int | None = None,
    until: str | None = None,
    list_type: int = 1,
    tags: str = "",
) -> dict[str, Any]:
    if page_size <= 0:
        raise UsageError("--page-size 必须大于 0")
    if max_pages is not None and max_pages <= 0:
        raise UsageError("--max-pages 必须大于 0")

    until_dt = parse_until(until)
    effective_max_pages = max_pages if max_pages is not None else (None if until_dt is not None else 1)
    cate = COMMUNITY_CATEGORY_TAG_IDS.get(list_type, str(list_type))
    items: list[dict[str, Any]] = []
    total_count: int | None = None
    curr_time = ""
    stopped_by_until = False
    page = 1

    while effective_max_pages is None or page <= effective_max_pages:
        payload = client.get(
            "/community/post/listV2",
            params={
                "limit": page_size,
                "page": page,
                "type": "isNewPublish",
                "cate": cate,
                "tags": tags,
            },
            headers={"Referer": f"{client.api_base}/view/community/list?listType={list_type}&type=isNewPublish&tags={tags}"},
        )
        data = _extract_data(payload)
        page_items = data.get("list") if isinstance(data.get("list"), list) else []
        if total_count is None:
            total_count = _int_or_none(data.get("totalCount"))
        curr_time = str(data.get("currTime", curr_time))
        if not page_items:
            break

        for raw in page_items:
            if not isinstance(raw, dict):
                continue
            item = normalize_post(raw)
            published_at = parse_joinquant_time(item["published_at"])
            if until_dt is not None and published_at is not None and published_at < until_dt:
                if item["is_top"]:
                    continue
                stopped_by_until = True
                break
            items.append(item)

        if stopped_by_until:
            break
        page += 1

    return {
        "items": items,
        "page_size": page_size,
        "pages_read": page if stopped_by_until else page - 1,
        "max_pages": effective_max_pages,
        "until": until,
        "stopped_by_until": stopped_by_until,
        "total_count": total_count,
        "curr_time": curr_time,
    }


def get_post_detail(
    client: ApiClient,
    post_id: str,
    *,
    reply_page: int = 1,
    reply_pages: int | None = 1,
    all_replies: bool = False,
) -> dict[str, Any]:
    if not post_id:
        raise UsageError("post_id 不能为空")
    if reply_page <= 0:
        raise UsageError("--reply-page 必须大于 0")
    if reply_pages is not None and reply_pages <= 0:
        raise UsageError("--reply-pages 必须大于 0")

    detail_payload = client.get(
        "/community/post/detailV2",
        params={"postId": post_id},
        headers={"Referer": f"{client.api_base}/view/community/detail/{post_id}"},
    )
    detail_raw = _extract_data(detail_payload, name="社区文章详情接口")
    detail = normalize_detail(detail_raw, requested_post_id=post_id)

    discussion = list_replies(
        client,
        post_id,
        start_page=reply_page,
        max_pages=None if all_replies else reply_pages,
    )
    return {
        "post": detail,
        "strategy": {
            "backtest": detail["backtest"],
            "research": detail["research"],
            "file": detail["file"],
        },
        "discussion": discussion,
    }


def check_strategy_clone(
    client: ApiClient,
    post_id: str,
    *,
    backtest_id: str | None = None,
    reply_id: str | None = None,
) -> dict[str, Any]:
    backtest_id = _resolve_backtest_id(client, post_id, backtest_id)
    data = _request_strategy_clone_check(client, post_id=post_id, backtest_id=backtest_id, reply_id=reply_id)
    return {
        "post_id": post_id,
        "backtest_id": backtest_id,
        "reply_id": reply_id or "",
        "rule_key": "clone_algorithm",
        "can_clone": str(data.get("reason", "")) != "deny",
        "reason": str(data.get("reason", "")),
        "amount": _int_or_zero(data.get("amount")),
        "reduce": _int_or_zero(data.get("reduce")),
        "usable": _int_or_zero(data.get("usable")),
        "is_view": _bool_int(data.get("isview")),
        "secret_present": bool(data.get("secret")),
        "random_present": data.get("random") is not None,
        "url": str(data.get("url", "")),
        "redirect": str(data.get("redirect", "")),
    }


def clone_strategy(
    client: ApiClient,
    post_id: str,
    *,
    backtest_id: str | None = None,
    reply_id: str | None = None,
) -> dict[str, Any]:
    backtest_id = _resolve_backtest_id(client, post_id, backtest_id)
    check_data = _request_strategy_clone_check(client, post_id=post_id, backtest_id=backtest_id, reply_id=reply_id)
    check_url = str(check_data.get("url", ""))
    check_redirect = str(check_data.get("redirect", ""))
    if check_url or check_redirect:
        return {
            "ok": True,
            "post_id": post_id,
            "backtest_id": backtest_id,
            "reply_id": reply_id or "",
            "rule_key": "clone_algorithm",
            "cost": _int_or_zero(check_data.get("reduce")),
            "amount_before": _int_or_zero(check_data.get("amount")),
            "reason": str(check_data.get("reason", "")),
            "strategy_id": _strategy_id_from_url(check_url) or _strategy_id_from_url(check_redirect) or "",
            "url": check_url,
            "redirect": check_redirect,
            "source_present": bool(check_data.get("source")),
            "credits": check_data.get("credits") if isinstance(check_data.get("credits"), dict) else {},
            "response": check_data,
            "from_check": True,
        }
    form: dict[str, Any] = {
        "postId": post_id,
        "backId": backtest_id,
        "ruleKey": "clone_algorithm",
        **check_data,
        "secret": check_data.get("secret", ""),
        "random": check_data.get("random", ""),
        "reason": check_data.get("reason", ""),
    }
    if reply_id:
        form["replyId"] = reply_id

    payload = client.post(
        "/community/post/dealCreditsHander",
        data=form,
        headers={"Referer": f"{client.api_base}/view/community/detail/{post_id}"},
    )
    data = _extract_data(payload, name="社区克隆策略接口")
    url = str(data.get("url", ""))
    redirect = str(data.get("redirect", ""))
    return {
        "ok": True,
        "post_id": post_id,
        "backtest_id": backtest_id,
        "reply_id": reply_id or "",
        "rule_key": "clone_algorithm",
        "cost": _int_or_zero(check_data.get("reduce")),
        "amount_before": _int_or_zero(check_data.get("amount")),
        "reason": str(check_data.get("reason", "")),
        "strategy_id": _strategy_id_from_url(url) or _strategy_id_from_url(redirect) or "",
        "url": url,
        "redirect": redirect,
        "source_present": bool(data.get("source")),
        "credits": data.get("credits") if isinstance(data.get("credits"), dict) else {},
        "response": data,
    }


def _resolve_backtest_id(client: ApiClient, post_id: str, backtest_id: str | None) -> str:
    if backtest_id:
        return backtest_id
    detail = get_post_detail(client, post_id, reply_pages=1)
    strategy = detail.get("strategy") if isinstance(detail.get("strategy"), dict) else {}
    backtest = strategy.get("backtest") if isinstance(strategy.get("backtest"), dict) else {}
    resolved = str(backtest.get("id", ""))
    if not resolved:
        raise UsageError("文章没有可克隆的回测策略，请传 --backtest-id 或换一篇带策略的文章")
    return resolved


def _request_strategy_clone_check(
    client: ApiClient,
    *,
    post_id: str,
    backtest_id: str,
    reply_id: str | None,
) -> dict[str, Any]:
    if not post_id:
        raise UsageError("post_id 不能为空")
    if not backtest_id:
        raise UsageError("backtest_id 不能为空")
    form = {"postId": post_id, "backId": backtest_id, "ruleKey": "clone_algorithm"}
    if reply_id:
        form["replyId"] = reply_id
    payload = client.post(
        "/community/post/checkBacktestView",
        data=form,
        headers={"Referer": f"{client.api_base}/view/community/detail/{post_id}"},
    )
    return _extract_data(payload, name="社区克隆策略检查接口")


def list_replies(
    client: ApiClient,
    post_id: str,
    *,
    start_page: int = 1,
    max_pages: int | None = 1,
) -> dict[str, Any]:
    items: list[dict[str, Any]] = []
    total_count: int | None = None
    curr_time = ""
    can_choose_best = False
    is_faq = False
    bounty_replies: list[dict[str, Any]] = []
    page = start_page
    pages_read = 0

    while max_pages is None or pages_read < max_pages:
        payload = client.get(
            "/community/post/replyList",
            params={"postId": post_id, "page": page},
            headers={"Referer": f"{client.api_base}/view/community/detail/{post_id}?page={page}"},
        )
        data = _extract_data(payload, name="社区讨论区接口")
        replies = data.get("replyArr") if isinstance(data.get("replyArr"), list) else []
        if total_count is None:
            total_count = _int_or_none(data.get("totalCount"))
        curr_time = str(data.get("currTime", curr_time))
        can_choose_best = bool(data.get("canChooseBest"))
        is_faq = bool(data.get("isFaq"))
        bounty = data.get("bountyReply")
        if isinstance(bounty, dict):
            bounty_replies.append(normalize_reply(bounty))

        items.extend(normalize_reply(item) for item in replies if isinstance(item, dict))
        pages_read += 1

        if not replies:
            break
        if total_count is not None and page >= math.ceil(total_count / 20):
            break
        page += 1

    return {
        "items": items,
        "bounty_items": bounty_replies,
        "start_page": start_page,
        "pages_read": pages_read,
        "max_pages": max_pages,
        "total_count": total_count,
        "can_choose_best": can_choose_best,
        "is_faq": is_faq,
        "curr_time": curr_time,
    }


def _extract_data(payload: Any, *, name: str = "社区列表接口") -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ApiError(f"{name}返回了非 JSON 对象")
    if payload.get("code") != "00000":
        raise ApiError(str(payload.get("msg") or f"{name}请求失败"), details={"response": payload})
    data = payload.get("data")
    if not isinstance(data, dict):
        raise ApiError(f"{name}响应缺少 data 对象", details={"response": payload})
    return data


def _int_or_zero(value: Any) -> int:
    parsed = _int_or_none(value)
    return parsed if parsed is not None else 0


def _int_or_none(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _float_or_none(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _strategy_id_from_url(value: str) -> str | None:
    if not value:
        return None
    parsed = urlparse(value)
    values = parse_qs(parsed.query).get("algorithmId")
    return values[0] if values and values[0] else None


def _bool_int(value: Any) -> bool:
    try:
        return bool(int(value))
    except (TypeError, ValueError):
        return False
