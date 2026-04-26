from urllib.parse import parse_qs

import httpx

from jqcli.api.backtest import (
    delete_backtest,
    delete_backtest_record,
    get_backtest,
    get_backtest_logs,
    get_backtest_result,
    get_backtest_stats,
    list_backtests,
    parse_backtest_list_html,
    run_backtest,
)
from jqcli.api.client import ApiClient


def client_with(handler):
    return ApiClient("https://example.test", token="tok", transport=httpx.MockTransport(handler))


STRATEGY_EDIT_HTML = """
<form name="AlgorithmModel">
  <input type="hidden" id="algorithmId" name="algorithm[algorithmId]" value="save-id">
  <input type="text" name="algorithm[name]" id="title-box" value="策略名">
  <input type="hidden" name="backtest[type]" id="type" value="1">
  <textarea name="algorithm[code]" id="code">print(1)</textarea>
</form>
"""

BACKTEST_LIST_HTML = """
<table>
  <tbody>
    <tr class="backtest-tr" _backtestId="list-id" _backtestId2="detail-id" _idx="1" _status="2">
      <td _type="checkbox"><input class="hidden source-code" _backtestId="source-id" backtestId_="list-id"></input></td>
      <td>1</td>
      <td><span class="backtest-name" title="策略名">策略名</span></td>
      <td>2025-10-08<br/>12:46:24</td>
      <td>2019-01-01<br/>- 2025-10-01</td>
      <td>1000000</td>
      <td>--</td>
      <td>每天</td>
      <td>12.3%</td>
      <td>4.5%</td>
      <td>6.7%</td>
      <td><span class="backtest-list__backtest-status">完成</span></td>
    </tr>
  </tbody>
</table>
"""

BACKTEST_DETAIL_HTML = """
<input type="hidden" name="backtest[algorithmId]" id="algorithmId" value="strategy-save-id">
<input type="hidden" name="backtest[backtestId]" id="backtestId" value="source-id">
<input type="text" name="startTime" id="startTime" value="2019-01-01">
"""


def test_parse_backtest_list_html():
    payload = parse_backtest_list_html(BACKTEST_LIST_HTML, strategy_id="s1")

    assert payload["items"][0]["id"] == "detail-id"
    assert payload["items"][0]["list_id"] == "list-id"
    assert payload["items"][0]["source_id"] == "source-id"
    assert payload["items"][0]["status"] == "done"
    assert payload["items"][0]["start_date"] == "2019-01-01"
    assert payload["items"][0]["end_date"] == "2025-10-01"


def test_run_backtest_payload():
    seen = []

    def handler(request):
        seen.append(request.url.path)
        if request.url.path == "/algorithm/index/edit":
            return httpx.Response(200, text=STRATEGY_EDIT_HTML)
        assert request.url.path == "/algorithm/index/build"
        form = parse_qs(request.content.decode())
        assert form["algorithm[algorithmId]"] == ["save-id"]
        assert form["backtest[startTime]"] == ["2023-01-01 00:00:00"]
        assert form["backtest[endTime]"] == ["2023-12-31 23:59:59"]
        assert form["backtest[baseCapital]"] == ["1000.0"]
        assert form["backtest[type]"] == ["0"]
        return httpx.Response(200, json={"data": {"backtestId_": "bt1", "backtestId": "list-bt1"}})

    assert run_backtest(
        client_with(handler),
        strategy_id="s1",
        start_date="2023-01-01",
        end_date="2023-12-31",
        capital=1000.0,
    )["id"] == "bt1"
    assert seen == ["/algorithm/index/edit", "/algorithm/index/build"]


def test_run_backtest_compile_mode_sets_type_one():
    def handler(request):
        if request.url.path == "/algorithm/index/edit":
            return httpx.Response(200, text=STRATEGY_EDIT_HTML)
        form = parse_qs(request.content.decode())
        assert form["backtest[type]"] == ["1"]
        return httpx.Response(200, json={"data": {"backtestId_": "bt1", "backtestId": "list-bt1"}})

    payload = run_backtest(
        client_with(handler),
        strategy_id="s1",
        start_date="2023-01-01",
        compile_only=True,
    )

    assert payload["mode"] == "compile"


def test_list_backtests_query():
    def handler(request):
        assert request.url.path == "/algorithm/backtest/list"
        assert request.url.params["algorithmId"] == "s1"
        return httpx.Response(200, text=BACKTEST_LIST_HTML)

    assert list_backtests(client_with(handler), strategy_id="s1", status="done", limit=20)["items"][0]["id"] == "detail-id"


def test_list_backtests_compile_mode_requests_build_list():
    def handler(request):
        assert request.url.path == "/algorithm/backtest/buildList"
        return httpx.Response(200, text=BACKTEST_LIST_HTML)

    assert list_backtests(client_with(handler), strategy_id="s1", compile_only=True)["items"][0]["id"] == "detail-id"


def test_get_backtest():
    seen = []

    def handler(request):
        seen.append(request.url.path)
        if request.url.path == "/algorithm/backtest/detail":
            return httpx.Response(200, text=BACKTEST_DETAIL_HTML)
        if request.url.path == "/algorithm/backtest/source":
            assert request.url.params["backtestId"] == "source-id"
            return httpx.Response(200, json={"data": {"source": "print(1)"}})
        if request.url.path == "/algorithm/backtest/stats":
            return httpx.Response(200, json={"data": {"algorithm_return": 0.1}})
        raise AssertionError(request.url.path)

    payload = get_backtest(client_with(handler), "bt1")

    assert payload["id"] == "bt1"
    assert payload["code"] == "print(1)"
    assert payload["metrics"] == {"algorithm_return": 0.1}
    assert seen == ["/algorithm/backtest/detail", "/algorithm/backtest/source", "/algorithm/backtest/stats"]


def test_get_backtest_stats():
    def handler(request):
        assert request.url.path == "/algorithm/backtest/stats"
        assert request.url.params["backtestId"] == "bt1"
        return httpx.Response(200, json={"data": {"annual_algo_return": 0.3, "sharpe": 1.2}})

    payload = get_backtest_stats(client_with(handler), "bt1")

    assert payload["id"] == "bt1"
    assert payload["metrics"] == {"annual_algo_return": 0.3, "sharpe": 1.2}


def test_get_backtest_stats_resolves_inner_id_when_report_is_not_ready_for_detail_id():
    seen = []

    def handler(request):
        seen.append((request.url.path, str(request.url.params.get("backtestId", ""))))
        if request.url.path == "/algorithm/backtest/stats" and request.url.params["backtestId"] == "detail-id":
            return httpx.Response(200, json={"data": []})
        if request.url.path == "/algorithm/backtest/detail":
            return httpx.Response(200, text=BACKTEST_DETAIL_HTML)
        if request.url.path == "/algorithm/backtest/stats" and request.url.params["backtestId"] == "source-id":
            return httpx.Response(200, json={"data": {"annual_algo_return": 0.3, "sharpe": 1.2}})
        raise AssertionError(request.url.path)

    payload = get_backtest_stats(client_with(handler), "detail-id")

    assert payload["resolved_id"] == "source-id"
    assert payload["metrics"]["annual_algo_return"] == 0.3
    assert seen == [
        ("/algorithm/backtest/stats", "detail-id"),
        ("/algorithm/backtest/detail", "detail-id"),
        ("/algorithm/backtest/stats", "source-id"),
    ]


def test_get_backtest_result():
    def handler(request):
        assert request.url.path == "/algorithm/backtest/result"
        assert request.url.params["backtestId"] == "bt1"
        assert request.url.params["offset"] == "10"
        assert request.url.params["userRecordOffset"] == "2"
        return httpx.Response(200, json={"data": {"state": "2", "result": {"count": 1}}})

    payload = get_backtest_result(client_with(handler), "bt1", offset=10, user_record_offset=2)

    assert payload["id"] == "bt1"
    assert payload["offset"] == 10
    assert payload["user_record_offset"] == 2
    assert payload["data"]["result"]["count"] == 1


def test_get_backtest_logs_page():
    def handler(request):
        assert request.url.path == "/algorithm/backtest/log"
        assert request.url.params["backtestId"] == "bt1"
        assert request.url.params["offset"] == "10"
        return httpx.Response(200, json={"data": {"state": "2", "logArr": ["a", "b"], "offset": 10, "max": False}})

    payload = get_backtest_logs(client_with(handler), "bt1", offset=10)

    assert payload["kind"] == "log"
    assert payload["logs"] == ["a", "b"]
    assert payload["next_offset"] == 12


def test_get_backtest_logs_all_pages():
    seen_offsets = []

    def handler(request):
        assert request.url.path == "/algorithm/backtest/log"
        offset = int(request.url.params["offset"])
        seen_offsets.append(offset)
        logs = ["a", "b"] if offset == 0 else []
        return httpx.Response(200, json={"data": {"state": "2", "logArr": logs, "offset": offset, "max": False}})

    payload = get_backtest_logs(client_with(handler), "bt1", all_items=True)

    assert payload["logs"] == ["a", "b"]
    assert seen_offsets == [0, 2]


def test_get_backtest_error_logs():
    def handler(request):
        assert request.url.path == "/algorithm/backtest/error"
        assert request.url.params["backtestId"] == "bt1"
        assert "offset" not in request.url.params
        return httpx.Response(200, json={"data": {"state": "3", "logArr": ["Traceback"]}})

    payload = get_backtest_logs(client_with(handler), "bt1", error=True)

    assert payload["kind"] == "error"
    assert payload["logs"] == ["Traceback"]


def test_delete_backtest():
    def handler(request):
        assert request.url.path == "/algorithm/backtest/del"
        assert request.url.params["type"] == "0"
        form = parse_qs(request.content.decode())
        assert form["backtestId"] == ["bt1"]
        return httpx.Response(200, json={"status": 0})

    assert delete_backtest(client_with(handler), "bt1")["ok"] is True


def test_delete_backtest_compile_mode_uses_type_one():
    def handler(request):
        assert request.url.path == "/algorithm/backtest/del"
        assert request.url.params["type"] == "1"
        return httpx.Response(200, json={"status": 0})

    payload = delete_backtest_record(client_with(handler), "bt1", compile_only=True)

    assert payload["ok"] is True
    assert payload["mode"] == "compile"
