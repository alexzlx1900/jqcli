from __future__ import annotations

import re
import sys
from urllib.parse import urljoin

import httpx

from jqcli.config import load_config


def main() -> int:
    args = [arg for arg in sys.argv[1:] if arg != "--auth"]
    use_auth = "--auth" in sys.argv[1:]
    url = args[0] if args else "https://www.joinquant.com/user/login/index"
    headers = {}
    if use_auth:
        config = load_config()
        if config.cookie:
            headers["Cookie"] = config.cookie
    with httpx.Client(follow_redirects=True, timeout=20, trust_env=False, headers=headers) as client:
        response = client.get(url)
        print("status", response.status_code)
        print("url", response.url)
        html = response.text
        for pattern in ["form", "csrf", "login", "ajax", "passport", "captcha", "remember"]:
            match = re.search(pattern, html, re.I)
            if match:
                start = max(0, match.start() - 220)
                end = min(len(html), match.end() + 380)
                print(f"--- {pattern}")
                print(html[start:end].replace("\n", " ")[:900])
        print("--- scripts")
        for src in re.findall(r"<script[^>]+src=[\"']([^\"']+)", html):
            print(urljoin(str(response.url), src))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
