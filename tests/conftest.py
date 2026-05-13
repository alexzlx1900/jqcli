import pytest


@pytest.fixture(autouse=True)
def clear_jqcli_env(monkeypatch):
    for key in ("JQCLI_TOKEN", "JQCLI_COOKIE", "JQCLI_USERNAME", "JQCLI_PASSWORD"):
        monkeypatch.delenv(key, raising=False)
