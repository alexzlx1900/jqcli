import json
from pathlib import Path

from jqcli.config import Config, default_config_path, load_config, load_env_file, parse_env_line, resolve_credentials


def test_load_config_uses_explicit_path(tmp_path):
    path = tmp_path / "config.json"
    path.write_text('{"api_base": "https://example.test", "timeout": 12}', encoding="utf-8")

    config = load_config(path)

    assert config.path == path
    assert config.api_base == "https://example.test"
    assert config.timeout == 12


def test_config_save_creates_parent(tmp_path):
    path = tmp_path / "nested" / "config.json"
    config = Config(path=path, data={"token": "abc"})

    config.save()

    assert json.loads(path.read_text(encoding="utf-8")) == {"token": "abc"}


def test_resolve_credentials_env_first(monkeypatch, tmp_path):
    monkeypatch.setenv("JQCLI_TOKEN", "env-token")
    monkeypatch.setenv("JQCLI_COOKIE", "env-cookie")
    config = Config(path=tmp_path / "config.json", data={"token": "file-token", "cookie": "file-cookie"})

    assert resolve_credentials(config, token="cli-token", cookie="cli-cookie") == ("env-token", "env-cookie")


def test_default_config_path_windows(monkeypatch):
    monkeypatch.setattr("sys.platform", "win32")
    monkeypatch.setenv("APPDATA", r"C:\Users\me\AppData\Roaming")

    assert str(default_config_path()).endswith(str(Path("jqcli") / "config.json"))
    assert "jqcli" in str(default_config_path())


def test_parse_env_line_supports_quotes_and_export():
    assert parse_env_line('export JQCLI_USERNAME="user@example.com"') == ("JQCLI_USERNAME", "user@example.com")
    assert parse_env_line("JQCLI_PASSWORD='pass word'") == ("JQCLI_PASSWORD", "pass word")
    assert parse_env_line("# ignored") is None


def test_load_env_file_does_not_override_existing(monkeypatch, tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("JQCLI_TOKEN=file-token\nJQCLI_COOKIE=file-cookie\n", encoding="utf-8")
    monkeypatch.setenv("JQCLI_TOKEN", "existing-token")
    monkeypatch.delenv("JQCLI_COOKIE", raising=False)

    loaded = load_env_file(env_file)

    assert loaded == env_file
    assert __import__("os").environ["JQCLI_TOKEN"] == "existing-token"
    assert __import__("os").environ["JQCLI_COOKIE"] == "file-cookie"
