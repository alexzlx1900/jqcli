import json

from click.testing import CliRunner

from jqcli.cli import main


def test_community_latest_json(monkeypatch, tmp_path):
    captured = {}
    monkeypatch.setattr("jqcli.commands.community.make_client", lambda app: object())

    def fake_list(client, **kwargs):
        captured.update(kwargs)
        return {"items": [{"id": "p1"}], "page_size": kwargs["page_size"]}

    monkeypatch.setattr("jqcli.commands.community.list_latest_posts", fake_list)

    result = CliRunner().invoke(
        main,
        [
            "--config",
            str(tmp_path / "c.json"),
            "--format",
            "json",
            "community",
            "latest",
            "--max-pages",
            "2",
            "--until",
            "2026-04-24",
        ],
    )

    assert result.exit_code == 0
    assert captured["page_size"] == 50
    assert captured["max_pages"] == 2
    assert captured["until"] == "2026-04-24"
    assert captured["since_id"] is None
    assert json.loads(result.output)["items"] == [{"id": "p1"}]


def test_community_latest_page_size(monkeypatch, tmp_path):
    captured = {}
    monkeypatch.setattr("jqcli.commands.community.make_client", lambda app: object())

    def fake_list(client, **kwargs):
        captured["kwargs"] = kwargs
        return {"items": []}

    monkeypatch.setattr("jqcli.commands.community.list_latest_posts", fake_list)

    result = CliRunner().invoke(
        main,
        [
            "--config",
            str(tmp_path / "c.json"),
            "--format",
            "json",
            "community",
            "latest",
            "--page-size",
            "10",
        ],
    )

    assert result.exit_code == 0
    assert captured["kwargs"]["page_size"] == 10
    assert captured["kwargs"]["max_pages"] is None


def test_community_latest_since_id(monkeypatch, tmp_path):
    captured = {}
    monkeypatch.setattr("jqcli.commands.community.make_client", lambda app: object())

    def fake_list(client, **kwargs):
        captured["kwargs"] = kwargs
        return {"items": []}

    monkeypatch.setattr("jqcli.commands.community.list_latest_posts", fake_list)

    result = CliRunner().invoke(
        main,
        [
            "--config",
            str(tmp_path / "c.json"),
            "--format",
            "json",
            "community",
            "latest",
            "--since-id",
            "p1",
        ],
    )

    assert result.exit_code == 0
    assert captured["kwargs"]["since_id"] == "p1"


def test_community_latest_stream(monkeypatch, tmp_path):
    captured = {}
    monkeypatch.setattr("jqcli.commands.community.make_client", lambda app: object())

    def fake_iter(client, **kwargs):
        captured["kwargs"] = kwargs
        yield {"type": "post", "page": 1, "item": {"id": "p1"}}
        yield {"type": "progress", "page": 1, "page_items": 1}
        yield {"type": "done", "pages_read": 1, "items_seen": 1}

    monkeypatch.setattr("jqcli.commands.community.iter_latest_posts", fake_iter)

    result = CliRunner().invoke(
        main,
        [
            "--config",
            str(tmp_path / "c.json"),
            "community",
            "latest",
            "--stream",
            "--since-id",
            "p0",
        ],
    )

    assert result.exit_code == 0
    assert captured["kwargs"]["since_id"] == "p0"
    lines = [json.loads(line) for line in result.output.splitlines()]
    assert [line["type"] for line in lines] == ["post", "progress", "done"]
    assert lines[0]["item"]["id"] == "p1"


def test_community_detail_json(monkeypatch, tmp_path):
    captured = {}
    monkeypatch.setattr("jqcli.commands.community.make_client", lambda app: object())

    def fake_detail(client, post_id, **kwargs):
        captured["post_id"] = post_id
        captured["kwargs"] = kwargs
        return {"post": {"id": post_id}, "discussion": {"items": []}}

    monkeypatch.setattr("jqcli.commands.community.get_post_detail", fake_detail)

    result = CliRunner().invoke(
        main,
        [
            "--config",
            str(tmp_path / "c.json"),
            "--format",
            "json",
            "community",
            "detail",
            "p1",
            "--reply-page",
            "2",
            "--reply-pages",
            "3",
            "--all-replies",
        ],
    )

    assert result.exit_code == 0
    assert captured["post_id"] == "p1"
    assert captured["kwargs"] == {"reply_page": 2, "reply_pages": 3, "all_replies": True, "with_backtest_stats": False}
    assert json.loads(result.output)["post"]["id"] == "p1"


def test_community_detail_with_backtest_stats(monkeypatch, tmp_path):
    captured = {}
    monkeypatch.setattr("jqcli.commands.community.make_client", lambda app: object())

    def fake_detail(client, post_id, **kwargs):
        captured["post_id"] = post_id
        captured["kwargs"] = kwargs
        return {
            "post": {"id": post_id},
            "strategy": {"backtest": {"stats": {"annual_algo_return": 0.3}}},
            "discussion": {"items": []},
        }

    monkeypatch.setattr("jqcli.commands.community.get_post_detail", fake_detail)

    result = CliRunner().invoke(
        main,
        [
            "--config",
            str(tmp_path / "c.json"),
            "--format",
            "json",
            "community",
            "detail",
            "p1",
            "--with-backtest-stats",
        ],
    )

    assert result.exit_code == 0
    assert captured["kwargs"]["with_backtest_stats"] is True
    assert json.loads(result.output)["strategy"]["backtest"]["stats"]["annual_algo_return"] == 0.3


def test_community_clone_strategy_check_only(monkeypatch, tmp_path):
    captured = {}
    monkeypatch.setattr("jqcli.commands.community.make_authenticated_client", lambda app: object())

    def fake_check(client, post_id, **kwargs):
        captured["post_id"] = post_id
        captured["kwargs"] = kwargs
        return {"post_id": post_id, "can_clone": True}

    monkeypatch.setattr("jqcli.commands.community.check_strategy_clone", fake_check)

    result = CliRunner().invoke(
        main,
        [
            "--config",
            str(tmp_path / "c.json"),
            "--token",
            "tok",
            "--format",
            "json",
            "community",
            "clone-strategy",
            "p1",
            "--backtest-id",
            "bt1",
        ],
    )

    assert result.exit_code == 0
    assert captured["post_id"] == "p1"
    assert captured["kwargs"] == {"backtest_id": "bt1", "reply_id": None}
    payload = json.loads(result.output)
    assert payload["execute"] is False
    assert "传 --yes" in payload["hint"]


def test_community_clone_strategy_execute(monkeypatch, tmp_path):
    captured = {}
    monkeypatch.setattr("jqcli.commands.community.make_authenticated_client", lambda app: object())

    def fake_clone(client, post_id, **kwargs):
        captured["post_id"] = post_id
        captured["kwargs"] = kwargs
        return {"ok": True, "post_id": post_id}

    monkeypatch.setattr("jqcli.commands.community.clone_strategy", fake_clone)

    result = CliRunner().invoke(
        main,
        [
            "--config",
            str(tmp_path / "c.json"),
            "--token",
            "tok",
            "--format",
            "json",
            "community",
            "clone-strategy",
            "p1",
            "--backtest-id",
            "bt1",
            "--reply-id",
            "r1",
            "--yes",
        ],
    )

    assert result.exit_code == 0
    assert captured["post_id"] == "p1"
    assert captured["kwargs"] == {"backtest_id": "bt1", "reply_id": "r1"}
    assert json.loads(result.output)["ok"] is True
