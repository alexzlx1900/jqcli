from urllib.parse import parse_qs

import httpx

from jqcli.api.client import ApiClient
from jqcli.api.strategy import (
    create_strategy,
    delete_strategy,
    get_strategy,
    list_strategies,
    parse_strategy_edit_html,
    parse_strategy_list_html,
    update_strategy,
)


def client_with(handler):
    return ApiClient("https://example.test", token="tok", transport=httpx.MockTransport(handler))


STRATEGY_LIST_HTML = """
<table>
  <tr class="algorithm_list">
    <td><div _algorithmId="c8546c1d149c650ec420bbee2fe12637"><input type="checkbox"></div></td>
    <td><a href="/algorithm/index/edit?algorithmId=41faea7d0299bc92c71364d9cd878259&amp;backtest=1">混合策略</a></td>
    <td>Code</td>
    <td>2025-10-08 12:48:07</td>
    <td>0</td>
    <td>1</td>
    <td><a href="/algorithm/backtest/list?algorithmId=41faea7d0299bc92c71364d9cd878259">回测</a></td>
  </tr>
  <tr class="algorithm_list">
    <td><span _algorithmId="internal-2"></span></td>
    <td><a href="/algorithm/index/edit?algorithmId=edit-2">全天候ETF</a></td>
    <td>Code</td>
    <td>2025-07-01 11:18:21</td>
    <td>2</td>
    <td>3</td>
    <td></td>
  </tr>
</table>
"""

STRATEGY_EDIT_HTML = """
<form name="AlgorithmModel">
  <input type="hidden" id="backtestId" value="bt-hidden">
  <input type="hidden" id="algorithmId" name="algorithm[algorithmId]" value="save-id">
  <input type="hidden" name="algorithm[userId]" value="u1">
  <input type="hidden" name="algorithm[accessControl]" id="accessControl" value="0">
  <input type="text" name="algorithm[name]" id="title-box" value="策略名">
  <input type="hidden" name="backtest[type]" id="type" value="1">
  <textarea name="algorithm[code]" id="code">print(1)</textarea>
</form>
"""


def test_parse_strategy_list_html():
    payload = parse_strategy_list_html(STRATEGY_LIST_HTML)

    assert payload == {
        "items": [
            {
                "id": "41faea7d0299bc92c71364d9cd878259",
                "internal_id": "c8546c1d149c650ec420bbee2fe12637",
                "name": "混合策略",
                "type": "Code",
                "created_at": "",
                "updated_at": "2025-10-08 12:48:07",
                "run_count": 0,
                "backtest_count": 1,
            },
            {
                "id": "edit-2",
                "internal_id": "internal-2",
                "name": "全天候ETF",
                "type": "Code",
                "created_at": "",
                "updated_at": "2025-07-01 11:18:21",
                "run_count": 2,
                "backtest_count": 3,
            },
        ]
    }


def test_list_strategies_requests_real_list_page():
    def handler(request):
        assert request.url.path == "/algorithm/index/list"
        return httpx.Response(200, text=STRATEGY_LIST_HTML)

    payload = list_strategies(client_with(handler), limit=1)

    assert len(payload["items"]) == 1
    assert payload["items"][0]["id"] == "41faea7d0299bc92c71364d9cd878259"


def test_list_strategies_can_sort_by_name_and_return_all():
    client = client_with(lambda request: httpx.Response(200, text=STRATEGY_LIST_HTML))

    payload = list_strategies(client, sort="name", limit=1, all_items=True)

    assert [item["name"] for item in payload["items"]] == ["全天候ETF", "混合策略"]


def test_list_strategies_follows_pages_and_folders():
    root_page_1 = """
    <table>
      <tbody>
        <tr class="algorithm_list">
          <td _fId="f1"></td>
          <td><a href="/algorithm/index/list?fId=f1">文件夹</a></td>
          <td></td><td></td><td></td><td></td><td></td>
        </tr>
      </tbody>
    </table>
    <a href="/algorithm/index/list?page=2">2</a>
    """
    root_page_2 = """
    <table>
      <tbody>
        <tr class="algorithm_list">
          <td><span _algorithmId="internal-root"></span></td>
          <td><a href="/algorithm/index/edit?algorithmId=root-id">根策略</a></td>
          <td>Code</td><td>2025-01-02 00:00:00</td><td>1</td><td>2</td><td></td>
        </tr>
      </tbody>
    </table>
    """
    folder_page = """
    <table>
      <tbody>
        <tr class="algorithm_list">
          <td><span _algorithmId="internal-folder"></span></td>
          <td><a href="/algorithm/index/edit?algorithmId=folder-id">文件夹策略</a></td>
          <td>Code</td><td>2025-01-03 00:00:00</td><td>3</td><td>4</td><td></td>
        </tr>
      </tbody>
    </table>
    """
    seen: list[tuple[str, dict[str, str]]] = []

    def handler(request):
        seen.append((request.url.path, dict(request.url.params)))
        params = request.url.params
        if params.get("fId") == "f1":
            return httpx.Response(200, text=folder_page)
        if params.get("page") == "2":
            return httpx.Response(200, text=root_page_2)
        return httpx.Response(200, text=root_page_1)

    payload = list_strategies(client_with(handler), all_items=True)

    assert [item["id"] for item in payload["items"]] == ["folder-id", "root-id"]
    assert payload["items"][0]["folder_id"] == "f1"
    assert seen == [
        ("/algorithm/index/list", {}),
        ("/algorithm/index/list", {"page": "2"}),
        ("/algorithm/index/list", {"fId": "f1"}),
    ]


def test_parse_strategy_edit_html():
    payload = parse_strategy_edit_html(STRATEGY_EDIT_HTML, requested_id="public-id")

    assert payload["id"] == "public-id"
    assert payload["save_id"] == "save-id"
    assert payload["backtest_id"] == "bt-hidden"
    assert payload["name"] == "策略名"
    assert payload["code"] == "print(1)"


def test_get_strategy_reads_edit_page():
    def handler(request):
        assert request.url.path == "/algorithm/index/edit"
        assert request.url.params["algorithmId"] == "s1"
        return httpx.Response(200, text=STRATEGY_EDIT_HTML)

    assert get_strategy(client_with(handler), "s1", include_code=True)["code"] == "print(1)"


def test_update_strategy_payload():
    seen = []

    def handler(request):
        seen.append(request.url.path)
        if request.url.path == "/algorithm/index/edit":
            return httpx.Response(200, text=STRATEGY_EDIT_HTML)
        if request.url.path == "/algorithm/index/list":
            return httpx.Response(200, text=STRATEGY_LIST_HTML)
        assert request.url.path == "/algorithm/index/save"
        form = parse_qs(request.content.decode())
        assert form["algorithm[algorithmId]"] == ["save-id"]
        assert form["algorithm[name]"] == ["new"]
        assert form["encrType"] == ["base64"]
        return httpx.Response(200, json={"data": {"algorithmId": "saved"}})

    payload = update_strategy(client_with(handler), "s1", name="new", code="print(2)")

    assert payload["save_id"] == "saved"
    assert seen == ["/algorithm/index/edit", "/algorithm/index/save", "/algorithm/index/list"]


def test_create_strategy_payload():
    seen = []

    def handler(request):
        seen.append(request.url.path)
        if request.url.path == "/algorithm/index/new":
            form = parse_qs(request.content.decode())
            assert form["code"] == ["print(1)"]
            return httpx.Response(200, json={"data": {"algorithmId": "s1"}})
        if request.url.path == "/algorithm/index/edit":
            return httpx.Response(200, text=STRATEGY_EDIT_HTML)
        if request.url.path == "/algorithm/index/save":
            return httpx.Response(200, json={"data": {"algorithmId": "save-id"}})
        if request.url.path == "/algorithm/index/list":
            return httpx.Response(200, text=STRATEGY_LIST_HTML)
        raise AssertionError(request.url.path)

    assert create_strategy(client_with(handler), name="n", strategy_type="stock", code="print(1)")["id"] == "s1"
    assert seen == [
        "/algorithm/index/new",
        "/algorithm/index/edit",
        "/algorithm/index/save",
        "/algorithm/index/list",
        "/algorithm/index/list",
    ]


def test_delete_strategy():
    seen = []

    def handler(request):
        seen.append(request.url.path)
        if request.url.path == "/algorithm/index/list":
            return httpx.Response(200, text=STRATEGY_LIST_HTML)
        assert request.url.path == "/algorithm/index/del"
        form = parse_qs(request.content.decode())
        assert form["algorithmId"] == ["c8546c1d149c650ec420bbee2fe12637"]
        return httpx.Response(200, json={"status": 0})

    payload = delete_strategy(client_with(handler), "41faea7d0299bc92c71364d9cd878259")

    assert payload["ok"] is True
    assert seen == ["/algorithm/index/list", "/algorithm/index/del"]
