from click.testing import CliRunner

from jqcli.cli import main


def test_version_option():
    result = CliRunner().invoke(main, ["--version"])

    assert result.exit_code == 0
    assert "jqcli, version" in result.output


def test_web_run_rejects_public_host_by_default(tmp_path):
    result = CliRunner().invoke(
        main,
        ["--config", str(tmp_path / "c.json"), "web", "run", "--host", "0.0.0.0"],
    )

    assert result.exit_code != 0
    assert "默认只允许监听本机地址" in result.output


def test_web_run_rejects_public_debug_host(tmp_path):
    result = CliRunner().invoke(
        main,
        ["--config", str(tmp_path / "c.json"), "web", "run", "--host", "0.0.0.0", "--allow-public", "--debug"],
    )

    assert result.exit_code != 0
    assert "debug 模式不能监听公开地址" in result.output
