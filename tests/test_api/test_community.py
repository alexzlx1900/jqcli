from urllib.parse import parse_qs

import httpx
import pytest

from jqcli.api.client import ApiClient
from jqcli.api.community import (
    check_strategy_clone,
    clone_strategy,
    get_post_detail,
    iter_latest_posts,
    list_latest_posts,
    parse_until,
)
from jqcli.errors import UsageError


def client_with(handler):
    return ApiClient("https://example.test", transport=httpx.MockTransport(handler))


def response_for(items, *, total_count="100", curr_time="2026-04-25 21:00:00"):
    return httpx.Response(
        200,
        json={
            "data": {
                "list": items,
                "currTime": curr_time,
                "currPage": 1,
                "totalCount": total_count,
            },
            "status": "0",
            "code": "00000",
            "msg": "",
        },
    )


def post(post_id, add_time, *, is_top="0", title="文章"):
    return {
        "postId": post_id,
        "title": title,
        "content": "preview",
        "backtestId": "bt1",
        "backtestCloneCount": "6",
        "backtestPicUrl": "https://image.example/bt.png",
        "notebookPath": "/notebook/path",
        "notebookReport": "report-id",
        "notebookCloneCount": "7",
        "fileKey": "file-key",
        "fileName": "file.png",
        "fileType": "image/png",
        "fileDownloadCount": "8",
        "replyCount": "2",
        "viewCount": "3",
        "likeCount": "4",
        "collectionCount": "5",
        "isTop": is_top,
        "isBest": "0",
        "addTime": add_time,
        "modTime": add_time,
        "lastActiveTime": add_time,
        "lastReplyTime": add_time,
        "tagInfo": [{"tagKey": "1", "name": "策略"}],
        "user": {"userId": "u1", "alias": "作者"},
    }


def test_list_latest_posts_defaults_to_fifty_one_page():
    seen = []

    def handler(request):
        seen.append(request)
        return response_for([post("p1", "2026-04-25 10:00:00")])

    payload = list_latest_posts(client_with(handler))

    assert len(payload["items"]) == 1
    assert payload["page_size"] == 50
    assert payload["pages_read"] == 1
    assert payload["items"][0]["id"] == "p1"
    assert payload["items"][0]["backtest"] == {
        "id": "bt1",
        "clone_count": 6,
        "pic_url": "https://image.example/bt.png",
    }
    assert payload["items"][0]["research"] == {
        "notebook_path": "/notebook/path",
        "notebook_report": "report-id",
        "notebook_clone_count": 7,
    }
    assert payload["items"][0]["file"] == {
        "key": "file-key",
        "name": "file.png",
        "type": "image/png",
        "download_count": 8,
    }
    query = parse_qs(seen[0].url.query.decode())
    assert query["limit"] == ["50"]
    assert query["page"] == ["1"]
    assert query["type"] == ["isNewPublish"]
    assert query["cate"] == ["3"]


def test_list_latest_posts_reads_max_pages():
    pages = []

    def handler(request):
        query = parse_qs(request.url.query.decode())
        page = int(query["page"][0])
        pages.append(page)
        return response_for([post(f"p{page}", f"2026-04-2{page} 10:00:00")])

    payload = list_latest_posts(client_with(handler), max_pages=3)

    assert pages == [1, 2, 3]
    assert [item["id"] for item in payload["items"]] == ["p1", "p2", "p3"]
    assert payload["pages_read"] == 3


def test_iter_latest_posts_streams_post_progress_and_done():
    def handler(request):
        page = int(parse_qs(request.url.query.decode())["page"][0])
        return response_for([post(f"p{page}", f"2026-04-2{page} 10:00:00")])

    events = list(iter_latest_posts(client_with(handler), max_pages=2))

    assert [event["type"] for event in events] == ["post", "progress", "post", "progress", "done"]
    assert events[0]["item"]["id"] == "p1"
    assert events[1]["page"] == 1
    assert events[-1]["items_seen"] == 2
    assert events[-1]["pages_read"] == 2


def test_list_latest_posts_stops_at_since_id():
    def handler(request):
        page = int(parse_qs(request.url.query.decode())["page"][0])
        if page == 1:
            return response_for([
                post("p-new", "2026-04-25 10:00:00"),
                post("p-seen", "2026-04-24 10:00:00"),
                post("p-old", "2026-04-23 10:00:00"),
            ])
        return response_for([post("p2", "2026-04-22 10:00:00")])

    payload = list_latest_posts(client_with(handler), since_id="p-seen", max_pages=3)

    assert [item["id"] for item in payload["items"]] == ["p-new"]
    assert payload["pages_read"] == 1
    assert payload["stopped_by_since_id"] is True


def test_list_latest_posts_until_ignores_old_top_for_stop():
    pages = []

    def handler(request):
        page = int(parse_qs(request.url.query.decode())["page"][0])
        pages.append(page)
        if page == 1:
            return response_for([
                post("top-old", "2020-01-01 00:00:00", is_top="1"),
                post("new", "2026-04-25 10:00:00"),
            ])
        return response_for([post("old", "2026-04-20 10:00:00")])

    payload = list_latest_posts(client_with(handler), until="2026-04-24")

    assert pages == [1, 2]
    assert [item["id"] for item in payload["items"]] == ["new"]
    assert payload["stopped_by_until"] is True
    assert payload["pages_read"] == 2


def test_parse_until_rejects_bad_value():
    with pytest.raises(UsageError):
        parse_until("bad")


def test_get_post_detail_includes_strategy_and_discussion():
    seen = []

    def handler(request):
        seen.append(request)
        if request.url.path == "/community/post/detailV2":
            return httpx.Response(
                200,
                json={
                    "data": {
                        "postId": "p1-real",
                        "title": "详情标题",
                        "content": "正文",
                        "backtestId": "bt1",
                        "backtestName": "策略回测",
                        "backtestCloneCount": "9",
                        "notebookPath": "/research",
                        "notebookReport": "report",
                        "notebookCloneCount": "10",
                        "fileKey": "fk",
                        "fileName": "a.py",
                        "fileType": "text/x-python",
                        "fileSize": "11",
                        "fileDownloadCount": "12",
                        "replyCount": "1",
                        "viewCount": "2",
                        "likeCount": "3",
                        "collectionCount": "4",
                        "addTime": "2026-04-25 10:00:00",
                        "modTime": "2026-04-25 11:00:00",
                        "lastActiveTime": "2026-04-25 12:00:00",
                        "isTop": "0",
                        "isBest": "0",
                        "isRich": "0",
                        "isWorth": "1",
                        "type": 1,
                        "status": "0",
                        "ipAddress": "北京",
                        "tagInfo": [{"tagKey": "1", "name": "策略"}],
                        "author": {"userId": "u1", "alias": "作者", "headImgKey": "h", "vipType": "VIP"},
                        "currTime": "2026-04-25 12:00:00",
                    },
                    "code": "00000",
                },
            )
        return httpx.Response(
            200,
            json={
                "data": {
                    "replyArr": [
                        {
                            "replyId": "r1",
                            "postId": "p1-real",
                            "content": "回复",
                            "backtestId": "rbt",
                            "backtestName": "回复回测",
                            "overallReturn": "0.12",
                            "addTime": "2026-04-25 12:00:00",
                            "modTime": "2026-04-25 12:00:00",
                            "isBest": "1",
                            "isRich": "0",
                            "isOwner": False,
                            "isPostUser": True,
                            "subReply": {
                                "list": [
                                    {
                                        "replyId": "sr1",
                                        "postId": "p1-real",
                                        "content": "子回复",
                                        "user": {"userId": "u3", "alias": "子作者"},
                                    }
                                ],
                                "leaveCount": "2",
                            },
                            "user": {"userId": "u2", "alias": "回复者"},
                        }
                    ],
                    "totalCount": "1",
                    "canChooseBest": True,
                    "isFaq": False,
                    "currTime": "2026-04-25 12:00:00",
                },
                "code": "00000",
            },
        )

    payload = get_post_detail(client_with(handler), "p1")

    assert [request.url.path for request in seen] == ["/community/post/detailV2", "/community/post/replyList"]
    assert payload["post"]["requested_id"] == "p1"
    assert payload["post"]["id"] == "p1-real"
    assert payload["strategy"]["backtest"] == {"id": "bt1", "name": "策略回测", "clone_count": 9}
    assert payload["strategy"]["research"]["notebook_path"] == "/research"
    assert payload["strategy"]["file"]["name"] == "a.py"
    assert payload["discussion"]["total_count"] == 1
    assert payload["discussion"]["items"][0]["id"] == "r1"
    assert payload["discussion"]["items"][0]["backtest"]["id"] == "rbt"
    assert payload["discussion"]["items"][0]["sub_replies"][0]["id"] == "sr1"
    assert payload["discussion"]["items"][0]["sub_reply_remaining_count"] == 2


def test_get_post_detail_can_include_backtest_stats():
    seen = []

    def handler(request):
        seen.append(request.url.path)
        if request.url.path == "/community/post/detailV2":
            return httpx.Response(
                200,
                json={
                    "data": {
                        "postId": "p1",
                        "title": "详情标题",
                        "backtestId": "bt1",
                        "backtestName": "策略回测",
                    },
                    "code": "00000",
                },
            )
        if request.url.path == "/community/post/replyList":
            return httpx.Response(200, json={"data": {"replyArr": [], "totalCount": "0"}, "code": "00000"})
        if request.url.path == "/algorithm/backtest/stats":
            assert request.url.params["backtestId"] == "bt1"
            return httpx.Response(200, json={"data": {"annual_algo_return": 0.3}, "code": "00000"})
        raise AssertionError(request.url.path)

    payload = get_post_detail(client_with(handler), "p1", with_backtest_stats=True)

    assert seen == ["/community/post/detailV2", "/community/post/replyList", "/algorithm/backtest/stats"]
    assert payload["post"]["backtest"] == {"id": "bt1", "name": "策略回测", "clone_count": 0}
    assert payload["strategy"]["backtest"]["stats"] == {"annual_algo_return": 0.3}


def test_get_post_detail_reads_all_reply_pages():
    pages = []

    def handler(request):
        if request.url.path == "/community/post/detailV2":
            return httpx.Response(200, json={"data": {"postId": "p1", "title": "t"}, "code": "00000"})
        page = int(parse_qs(request.url.query.decode())["page"][0])
        pages.append(page)
        return httpx.Response(
            200,
            json={
                "data": {
                    "replyArr": [{"replyId": f"r{page}", "content": "x"}],
                    "totalCount": "41",
                },
                "code": "00000",
            },
        )

    payload = get_post_detail(client_with(handler), "p1", all_replies=True)

    assert pages == [1, 2, 3]
    assert [item["id"] for item in payload["discussion"]["items"]] == ["r1", "r2", "r3"]


def test_check_strategy_clone_uses_backtest_check_endpoint():
    seen = []

    def handler(request):
        seen.append(request)
        form = parse_qs(request.content.decode())
        assert request.url.path == "/community/post/checkBacktestView"
        assert form["postId"] == ["p1"]
        assert form["backId"] == ["bt1"]
        assert form["ruleKey"] == ["clone_algorithm"]
        return httpx.Response(
            200,
            json={
                "data": {
                    "amount": "48",
                    "reduce": 10,
                    "secret": "secret",
                    "random": 1777127557,
                    "isview": 1,
                    "reason": "more",
                    "usable": 2,
                },
                "code": "00000",
            },
        )

    payload = check_strategy_clone(client_with(handler), "p1", backtest_id="bt1")

    assert len(seen) == 1
    assert payload["can_clone"] is True
    assert payload["amount"] == 48
    assert payload["reduce"] == 10
    assert payload["secret_present"] is True
    assert "secret" not in payload


def test_clone_strategy_posts_deal_credits_after_check():
    seen = []

    def handler(request):
        seen.append(request)
        if request.url.path == "/community/post/checkBacktestView":
            return httpx.Response(
                200,
                json={
                    "data": {
                        "amount": "48",
                        "reduce": "10",
                        "secret": "secret",
                        "random": "1777127557",
                        "isview": "1",
                        "reason": "more",
                        "usable": "2",
                    },
                    "code": "00000",
                },
            )
        assert request.url.path == "/community/post/dealCreditsHander"
        form = parse_qs(request.content.decode())
        assert form["postId"] == ["p1"]
        assert form["backId"] == ["bt1"]
        assert form["ruleKey"] == ["clone_algorithm"]
        assert form["secret"] == ["secret"]
        assert form["random"] == ["1777127557"]
        assert form["reason"] == ["more"]
        return httpx.Response(
            200,
            json={
                "data": {
                    "url": "/algorithm/index/edit?algorithmId=a1&startTime=2020-01-01",
                },
                "code": "00000",
            },
        )

    payload = clone_strategy(client_with(handler), "p1", backtest_id="bt1")

    assert [request.url.path for request in seen] == [
        "/community/post/checkBacktestView",
        "/community/post/dealCreditsHander",
    ]
    assert payload["ok"] is True
    assert payload["strategy_id"] == "a1"
    assert payload["url"] == "/algorithm/index/edit?algorithmId=a1&startTime=2020-01-01"


def test_clone_strategy_returns_check_url_without_deal_credits():
    seen = []

    def handler(request):
        seen.append(request)
        assert request.url.path == "/community/post/checkBacktestView"
        return httpx.Response(
            200,
            json={
                "data": {
                    "url": "/algorithm/index/edit?algorithmId=a2",
                    "reduce": 0,
                },
                "code": "00000",
            },
        )

    payload = clone_strategy(client_with(handler), "p1", backtest_id="bt1")

    assert [request.url.path for request in seen] == ["/community/post/checkBacktestView"]
    assert payload["ok"] is True
    assert payload["from_check"] is True
    assert payload["strategy_id"] == "a2"
    assert payload["cost"] == 0
