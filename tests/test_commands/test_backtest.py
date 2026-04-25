import json

from click.testing import CliRunner

from jqcli.cli import main


def test_backtest_run_json(monkeypatch, tmp_path):
    captured = {}
    monkeypatch.setattr("jqcli.commands.backtest.make_client", lambda app: object())

    def fake_run(client, **kwargs):
        captured.update(kwargs)
        return {"id": "bt1", "status": "running"}

    monkeypatch.setattr("jqcli.commands.backtest.run_backtest", fake_run)

    result = CliRunner().invoke(
        main,
        [
            "--config",
            str(tmp_path / "c.json"),
            "--token",
            "tok",
            "--format",
            "json",
            "backtest",
            "run",
            "s1",
            "--start",
            "2023-01-01",
            "--end",
            "2023-12-31",
        ],
    )

    assert result.exit_code == 0
    assert captured["strategy_id"] == "s1"
    assert captured["compile_only"] is False
    assert json.loads(result.output)["id"] == "bt1"


def test_backtest_run_compile_flag(monkeypatch, tmp_path):
    captured = {}
    monkeypatch.setattr("jqcli.commands.backtest.make_client", lambda app: object())

    def fake_run(client, **kwargs):
        captured.update(kwargs)
        return {"id": "bt1", "status": "running", "mode": "compile"}

    monkeypatch.setattr("jqcli.commands.backtest.run_backtest", fake_run)

    result = CliRunner().invoke(
        main,
        [
            "--config",
            str(tmp_path / "c.json"),
            "--token",
            "tok",
            "--format",
            "json",
            "backtest",
            "run",
            "s1",
            "--start",
            "2023-01-01",
            "--compile",
        ],
    )

    assert result.exit_code == 0
    assert captured["compile_only"] is True
    assert json.loads(result.output)["mode"] == "compile"


def test_backtest_run_wait(monkeypatch, tmp_path):
    monkeypatch.setattr("jqcli.commands.backtest.make_client", lambda app: object())
    monkeypatch.setattr("jqcli.commands.backtest.run_backtest", lambda client, **kwargs: {"id": "bt1", "status": "running"})
    monkeypatch.setattr(
        "jqcli.commands.backtest.wait_for_backtest",
        lambda client, backtest_id, timeout, poll_interval: {"id": backtest_id, "status": "done"},
    )

    result = CliRunner().invoke(
        main,
        [
            "--config",
            str(tmp_path / "c.json"),
            "--token",
            "tok",
            "--format",
            "json",
            "backtest",
            "run",
            "s1",
            "--start",
            "2023-01-01",
            "--wait",
        ],
    )

    assert result.exit_code == 0
    assert json.loads(result.output)["status"] == "done"


def test_backtest_ls_json(monkeypatch, tmp_path):
    monkeypatch.setattr("jqcli.commands.backtest.make_client", lambda app: object())
    monkeypatch.setattr("jqcli.commands.backtest.list_backtests", lambda client, **kwargs: {"items": [{"id": "bt1"}]})

    result = CliRunner().invoke(
        main,
        ["--config", str(tmp_path / "c.json"), "--token", "tok", "--format", "json", "backtest", "ls", "s1"],
    )

    assert result.exit_code == 0
    assert json.loads(result.output) == {"items": [{"id": "bt1"}]}


def test_backtest_ls_compile_flag(monkeypatch, tmp_path):
    captured = {}
    monkeypatch.setattr("jqcli.commands.backtest.make_client", lambda app: object())

    def fake_list(client, **kwargs):
        captured.update(kwargs)
        return {"items": []}

    monkeypatch.setattr("jqcli.commands.backtest.list_backtests", fake_list)

    result = CliRunner().invoke(
        main,
        [
            "--config",
            str(tmp_path / "c.json"),
            "--token",
            "tok",
            "--format",
            "json",
            "backtest",
            "ls",
            "s1",
            "--compile",
        ],
    )

    assert result.exit_code == 0
    assert captured["compile_only"] is True


def test_backtest_show_json(monkeypatch, tmp_path):
    monkeypatch.setattr("jqcli.commands.backtest.make_client", lambda app: object())
    monkeypatch.setattr("jqcli.commands.backtest.get_backtest", lambda client, backtest_id: {"id": backtest_id, "status": "done"})

    result = CliRunner().invoke(
        main,
        ["--config", str(tmp_path / "c.json"), "--token", "tok", "--format", "json", "backtest", "show", "bt1"],
    )

    assert result.exit_code == 0
    assert json.loads(result.output)["id"] == "bt1"


def test_backtest_rm_non_interactive_requires_yes(tmp_path):
    result = CliRunner().invoke(
        main,
        [
            "--config",
            str(tmp_path / "c.json"),
            "--token",
            "tok",
            "--format",
            "json",
            "--non-interactive",
            "backtest",
            "rm",
            "bt1",
        ],
    )

    assert result.exit_code == 7
    assert json.loads(result.stderr)["error"]["code"] == "confirmation_required"


def test_backtest_rm_with_yes(monkeypatch, tmp_path):
    monkeypatch.setattr("jqcli.commands.backtest.make_client", lambda app: object())
    monkeypatch.setattr(
        "jqcli.commands.backtest.delete_backtest_record",
        lambda client, backtest_id, compile_only=False: {"ok": True, "id": backtest_id, "compile_only": compile_only},
    )

    result = CliRunner().invoke(
        main,
        [
            "--config",
            str(tmp_path / "c.json"),
            "--token",
            "tok",
            "--format",
            "json",
            "--non-interactive",
            "backtest",
            "rm",
            "bt1",
            "--yes",
        ],
    )

    assert result.exit_code == 0
    assert json.loads(result.output) == {"ok": True, "id": "bt1", "compile_only": False}


def test_backtest_rm_compile_flag(monkeypatch, tmp_path):
    monkeypatch.setattr("jqcli.commands.backtest.make_client", lambda app: object())
    monkeypatch.setattr(
        "jqcli.commands.backtest.delete_backtest_record",
        lambda client, backtest_id, compile_only=False: {"ok": True, "id": backtest_id, "compile_only": compile_only},
    )

    result = CliRunner().invoke(
        main,
        [
            "--config",
            str(tmp_path / "c.json"),
            "--token",
            "tok",
            "--format",
            "json",
            "--non-interactive",
            "backtest",
            "rm",
            "bt1",
            "--yes",
            "--compile",
        ],
    )

    assert result.exit_code == 0
    assert json.loads(result.output) == {"ok": True, "id": "bt1", "compile_only": True}


def test_wait_for_backtest_reaches_done(monkeypatch):
    from jqcli.commands import backtest

    states = iter([
        {"id": "bt1", "status": "running"},
        {"id": "bt1", "status": "done"},
    ])
    monkeypatch.setattr(backtest, "get_backtest", lambda client, backtest_id: next(states))
    monkeypatch.setattr(backtest.time, "sleep", lambda seconds: None)

    assert backtest.wait_for_backtest(object(), "bt1", timeout=1, poll_interval=0)["status"] == "done"
