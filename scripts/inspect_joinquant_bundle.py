from __future__ import annotations

import re

import httpx


URLS = [
    "https://cdn.joinquant.com/std/dist/modules/user/login/index.bundle.js?v=17679309750001776925000058",
    "https://cdn.joinquant.com/std/dist/asset/general/login-dialog.bundle.js?v=17679309750001776925000058",
]


def main() -> int:
    with httpx.Client(timeout=20, trust_env=False) as client:
        for url in URLS:
            response = client.get(url)
            text = response.text
            print("URL", url)
            print("STATUS", response.status_code, "LEN", len(text))
            for pattern in ["login", "captcha", "password", "token", "/user/", "ajax", "sms", "passport"]:
                match = re.search(pattern, text, re.I)
                if not match:
                    continue
                start = max(0, match.start() - 300)
                end = min(len(text), match.end() + 600)
                print(f"--- {pattern}")
                print(text[start:end][:1000])
            print("--- endpoints")
            endpoints = sorted(set(re.findall(r"['\"](/[^'\"]{3,120})['\"]", text)))
            for endpoint in endpoints:
                if any(key in endpoint.lower() for key in ("user", "login", "captcha", "algorithm", "backtest")):
                    print(endpoint)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

