from click.testing import CliRunner

from jqcli.cli import main


def test_version_option():
    result = CliRunner().invoke(main, ["--version"])

    assert result.exit_code == 0
    assert "jqcli, version" in result.output

