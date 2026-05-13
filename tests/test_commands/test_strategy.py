import json

from click.testing import CliRunner

from jqcli.cli import main


def test_strategy_ls_json(monkeypatch, tmp_path):
    monkeypatch.setattr("jqcli.commands.strategy.make_client", lambda app: object())
    monkeypatch.setattr("jqcli.commands.strategy.list_strategies", lambda client, **kwargs: {"items": [{"id": "s1"}]})

    result = CliRunner().invoke(
        main,
        ["--config", str(tmp_path / "c.json"), "--token", "tok", "--format", "json", "strategy", "ls"],
    )

    assert result.exit_code == 0
    assert json.loads(result.output) == {"items": [{"id": "s1"}]}


def test_strategy_requires_auth(tmp_path):
    result = CliRunner(mix_stderr=False).invoke(
        main,
        ["--config", str(tmp_path / "c.json"), "--format", "json", "strategy", "ls"],
    )

    assert result.exit_code == 1
    assert json.loads(result.stderr)["error"]["code"] == "not_authenticated"


def test_strategy_show_writes_output(monkeypatch, tmp_path):
    monkeypatch.setattr("jqcli.commands.strategy.make_client", lambda app: object())
    monkeypatch.setattr(
        "jqcli.commands.strategy.get_strategy",
        lambda client, strategy_id, include_code=False: {"id": strategy_id, "code": "print(1)"},
    )
    output = tmp_path / "strategy.py"

    result = CliRunner().invoke(
        main,
        [
            "--config",
            str(tmp_path / "c.json"),
            "--token",
            "tok",
            "--format",
            "json",
            "strategy",
            "show",
            "s1",
            "--output",
            str(output),
        ],
    )

    assert result.exit_code == 0
    assert output.read_text(encoding="utf-8") == "print(1)"


def test_strategy_new_reads_code_stdin(monkeypatch, tmp_path):
    captured = {}
    monkeypatch.setattr("jqcli.commands.strategy.make_client", lambda app: object())

    def fake_create(client, **kwargs):
        captured.update(kwargs)
        return {"id": "s1"}

    monkeypatch.setattr("jqcli.commands.strategy.create_strategy", fake_create)
    result = CliRunner().invoke(
        main,
        [
            "--config",
            str(tmp_path / "c.json"),
            "--token",
            "tok",
            "--format",
            "json",
            "strategy",
            "new",
            "n",
            "--code-stdin",
        ],
        input="print(1)",
    )

    assert result.exit_code == 0
    assert captured["code"] == "print(1)"
    assert json.loads(result.output) == {"id": "s1"}


def test_strategy_edit_requires_change(monkeypatch, tmp_path):
    monkeypatch.setattr("jqcli.commands.strategy.make_client", lambda app: object())

    result = CliRunner(mix_stderr=False).invoke(
        main,
        [
            "--config",
            str(tmp_path / "c.json"),
            "--token",
            "tok",
            "--format",
            "json",
            "strategy",
            "edit",
            "s1",
        ],
    )

    assert result.exit_code == 3
    assert json.loads(result.stderr)["error"]["code"] == "usage_error"


def test_strategy_rm_non_interactive_requires_yes(tmp_path):
    result = CliRunner(mix_stderr=False).invoke(
        main,
        [
            "--config",
            str(tmp_path / "c.json"),
            "--token",
            "tok",
            "--format",
            "json",
            "--non-interactive",
            "strategy",
            "rm",
            "s1",
        ],
    )

    assert result.exit_code == 7
    assert json.loads(result.stderr)["error"]["code"] == "confirmation_required"


def test_strategy_rm_with_yes(monkeypatch, tmp_path):
    monkeypatch.setattr("jqcli.commands.strategy.make_client", lambda app: object())
    monkeypatch.setattr("jqcli.commands.strategy.delete_strategy", lambda client, strategy_id: {"ok": True, "id": strategy_id})

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
            "strategy",
            "rm",
            "s1",
            "--yes",
        ],
    )

    assert result.exit_code == 0
    assert json.loads(result.output) == {"ok": True, "id": "s1"}


def test_strategy_folder_sync_dry_run(monkeypatch, tmp_path):
    index = tmp_path / "index.csv"
    index.write_text(
        "strategy_id,name,primary_category\n"
        "s1,策略1,small_micro_cap\n"
        "s2,策略2,ml_ai\n",
        encoding="utf-8",
    )
    monkeypatch.setattr("jqcli.commands.strategy.make_client", lambda app: object())
    monkeypatch.setattr(
        "jqcli.commands.strategy.list_strategies",
        lambda client, **kwargs: {
            "items": [
                {"id": "s1", "internal_id": "i1", "name": "策略1"},
                {"id": "s2", "internal_id": "i2", "name": "策略2", "folder_id": "old"},
            ]
        },
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
            "strategy",
            "folder-sync",
            "--from-index",
            str(index),
            "--dry-run",
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["dry_run"] is True
    assert payload["planned_move_count"] == 1
    assert payload["skipped_existing_folder_count"] == 1
    assert "executed" not in payload
