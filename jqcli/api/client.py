from __future__ import annotations

from typing import Any

import httpx

from jqcli.errors import ApiError, NetworkError, NotAuthenticatedError, NotFoundError


class ApiClient:
    def __init__(
        self,
        api_base: str,
        *,
        token: str | None = None,
        cookie: str | None = None,
        timeout: float = 30,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.api_base = api_base.rstrip("/")
        self.token = token
        self.cookie = cookie
        self._client = httpx.Client(base_url=self.api_base, timeout=timeout, transport=transport, trust_env=False)

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> ApiClient:
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        self.close()

    def _headers(self) -> dict[str, str]:
        headers: dict[str, str] = {"X-Requested-With": "XMLHttpRequest"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        if self.cookie:
            headers["Cookie"] = self.cookie
        return headers

    def _send(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        headers = {**self._headers(), **kwargs.pop("headers", {})}
        try:
            response = self._client.request(method, path, headers=headers, **kwargs)
        except httpx.RequestError as exc:
            raise NetworkError() from exc
        if response.status_code in (401, 403):
            raise NotAuthenticatedError("登录已过期或凭据无效")
        if response.status_code == 404:
            raise NotFoundError("资源不存在")
        if response.status_code >= 400:
            raise ApiError(f"请求失败（HTTP {response.status_code}）", status_code=response.status_code)
        self._raise_for_login_redirect(response)
        return response

    @staticmethod
    def _raise_for_login_redirect(response: httpx.Response) -> None:
        try:
            data = response.json()
        except ValueError:
            return
        if not isinstance(data, dict):
            return
        redirect = str(data.get("redirect") or data.get("url") or "")
        code = str(data.get("code") or "")
        status = str(data.get("status") or "")
        if "/user/login" in redirect or code == "10001" or (status == "1" and redirect):
            raise NotAuthenticatedError("登录已过期或凭据无效")

    def request(self, method: str, path: str, **kwargs: Any) -> Any:
        response = self._send(method, path, **kwargs)
        if not response.content:
            return None
        try:
            return response.json()
        except ValueError as exc:
            raise ApiError("服务端返回了无效 JSON") from exc

    def request_text(self, method: str, path: str, **kwargs: Any) -> str:
        response = self._send(method, path, **kwargs)
        return response.text

    def get(self, path: str, **kwargs: Any) -> Any:
        return self.request("GET", path, **kwargs)

    def get_text(self, path: str, **kwargs: Any) -> str:
        return self.request_text("GET", path, **kwargs)

    def post(self, path: str, **kwargs: Any) -> Any:
        return self.request("POST", path, **kwargs)

    def put(self, path: str, **kwargs: Any) -> Any:
        return self.request("PUT", path, **kwargs)

    def delete(self, path: str, **kwargs: Any) -> Any:
        return self.request("DELETE", path, **kwargs)
