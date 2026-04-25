import httpx
import pytest

from jqcli.api.auth import extract_page_token, login_with_password
from jqcli.errors import ApiError


def test_extract_page_token_from_window_data():
    html = '<script>window.tokenData={name:"token",value:"abc123"}</script>'

    assert extract_page_token(html) == "abc123"


def test_login_with_password_success(monkeypatch):
    def handler(request):
        if request.url.path == "/user/login/index":
            return httpx.Response(200, text='<script>window.tokenData={name:"token",value:"tok"}</script>')
        assert request.url.path == "/user/login/doLogin"
        assert b"CyLoginForm%5Busername%5D=u" in request.content
        assert b"CyLoginForm%5Bpwd%5D=p" in request.content
        return httpx.Response(200, json={"code": "00000", "data": {"user": {}}}, headers={"set-cookie": "sid=abc; Path=/"})

    class FakeClient(httpx.Client):
        def __init__(self, *args, **kwargs):
            super().__init__(transport=httpx.MockTransport(handler), *args, **kwargs)

    monkeypatch.setattr("jqcli.api.auth.httpx.Client", FakeClient)

    result = login_with_password("https://example.test", "u", "p")

    assert result["payload"]["code"] == "00000"
    assert "sid=abc" in result["cookie"]


def test_login_with_password_failure(monkeypatch):
    def handler(request):
        if request.url.path == "/user/login/index":
            return httpx.Response(200, text='<script>window.tokenData={name:"token",value:"tok"}</script>')
        return httpx.Response(200, json={"code": "20000", "msg": "bad"})

    class FakeClient(httpx.Client):
        def __init__(self, *args, **kwargs):
            super().__init__(transport=httpx.MockTransport(handler), *args, **kwargs)

    monkeypatch.setattr("jqcli.api.auth.httpx.Client", FakeClient)

    with pytest.raises(ApiError):
        login_with_password("https://example.test", "u", "p")

