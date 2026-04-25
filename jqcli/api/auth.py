from __future__ import annotations

import re
from typing import Any

import httpx

from jqcli.errors import ApiError, NetworkError


LOGIN_PAGE = "/user/login/index"
LOGIN_ENDPOINT = "/user/login/doLogin"


def extract_page_token(html: str) -> str | None:
    match = re.search(r"window\.tokenData\s*=\s*\{\s*name\s*:\s*['\"]?token['\"]?\s*,\s*value\s*:\s*['\"]([^'\"]+)", html)
    if match:
        return match.group(1)
    match = re.search(r"name=[\"']token[\"'][^>]+value=[\"']([^\"']+)", html)
    if match:
        return match.group(1)
    return None


def login_with_password(api_base: str, username: str, password: str, *, timeout: float = 30) -> dict[str, Any]:
    base = api_base.rstrip("/")
    try:
        with httpx.Client(base_url=base, follow_redirects=True, timeout=timeout, trust_env=False) as client:
            page = client.get(LOGIN_PAGE)
            page.raise_for_status()
            token = extract_page_token(page.text)
            if not token:
                raise ApiError("无法从登录页提取 token")
            response = client.post(
                LOGIN_ENDPOINT,
                data={
                    "CyLoginForm[username]": username,
                    "CyLoginForm[pwd]": password,
                    "token": token,
                },
                headers={
                    "X-Requested-With": "XMLHttpRequest",
                    "Referer": f"{base}{LOGIN_PAGE}",
                },
            )
            response.raise_for_status()
            try:
                payload = response.json()
            except ValueError as exc:
                raise ApiError("登录接口返回了无效 JSON") from exc
            if payload.get("code") != "00000":
                message = payload.get("msg") or "登录失败"
                if payload.get("error"):
                    message = f"{message}: {payload['error']}"
                raise ApiError(str(message), details={"code": payload.get("code")})
            return {
                "payload": payload,
                "cookie": "; ".join(f"{cookie.name}={cookie.value}" for cookie in client.cookies.jar),
            }
    except httpx.RequestError as exc:
        raise NetworkError() from exc
    except httpx.HTTPStatusError as exc:
        raise ApiError(f"登录请求失败（HTTP {exc.response.status_code}）", status_code=exc.response.status_code) from exc

