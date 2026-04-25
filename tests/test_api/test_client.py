import httpx
import pytest

from jqcli.api.client import ApiClient
from jqcli.errors import ApiError, NetworkError, NotAuthenticatedError, NotFoundError


def make_client(handler):
    return ApiClient("https://example.test", token="tok", transport=httpx.MockTransport(handler))


def test_client_adds_auth_header():
    def handler(request):
        assert request.headers["authorization"] == "Bearer tok"
        return httpx.Response(200, json={"ok": True})

    client = make_client(handler)
    assert client.get("/ping") == {"ok": True}


def test_client_can_return_text_response():
    client = make_client(lambda request: httpx.Response(200, text="<html></html>"))

    assert client.get_text("/page") == "<html></html>"


@pytest.mark.parametrize(
    ("status_code", "error_type"),
    [(401, NotAuthenticatedError), (403, NotAuthenticatedError), (404, NotFoundError), (500, ApiError)],
)
def test_client_maps_error_status(status_code, error_type):
    client = make_client(lambda request: httpx.Response(status_code, json={"error": "x"}))

    with pytest.raises(error_type):
        client.get("/x")


def test_client_maps_network_error():
    def handler(request):
        raise httpx.ConnectError("boom", request=request)

    client = make_client(handler)

    with pytest.raises(NetworkError):
        client.get("/x")
