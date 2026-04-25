from __future__ import annotations

import re
import sys
from html import unescape
from urllib.parse import urljoin

import httpx

from jqcli.config import load_config, load_env_file, resolve_credentials


def mask_value(name: str, value: str) -> str:
    lower = name.lower()
    if any(key in lower for key in ("pwd", "password", "token", "cookie")):
        return "<redacted>"
    if len(value) > 140:
        return value[:80] + f"...<{len(value)} chars>"
    return value


def attr(tag: str, name: str) -> str:
    match = re.search(rf"""{name}\s*=\s*["']([^"']*)["']""", tag, re.I)
    return unescape(match.group(1)) if match else ""


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: inspect_joinquant_page.py URL", file=sys.stderr)
        return 2
    load_env_file(None)
    config = load_config()
    _, cookie = resolve_credentials(config)
    headers = {"Cookie": cookie} if cookie else {}
    with httpx.Client(follow_redirects=True, timeout=20, trust_env=False, headers=headers) as client:
        response = client.get(sys.argv[1])
        html = response.text
        print("status", response.status_code)
        print("url", response.url)
        print("len", len(html))
        print("--- inputs")
        for tag in re.findall(r"<input\b[^>]*>", html, re.I):
            name = attr(tag, "name")
            id_ = attr(tag, "id")
            type_ = attr(tag, "type")
            value = attr(tag, "value")
            if name or id_:
                print({"type": type_, "name": name, "id": id_, "value": mask_value(name or id_, value)})
        print("--- textareas")
        for match in re.finditer(r"<textarea\b([^>]*)>(.*?)</textarea>", html, re.I | re.S):
            attrs = match.group(1)
            name = attr(attrs, "name")
            id_ = attr(attrs, "id")
            value = unescape(match.group(2)).strip()
            print({"name": name, "id": id_, "value": mask_value(name or id_, value)})
        print("--- scripts")
        for src in re.findall(r"<script[^>]+src=[\"']([^\"']+)", html, re.I):
            print(urljoin(str(response.url), src))
        print("--- endpoint snippets")
        for endpoint in sorted(set(re.findall(r"""["'](/(?:algorithm|backtest)[^"']{1,180})["']""", html))):
            print(endpoint)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
