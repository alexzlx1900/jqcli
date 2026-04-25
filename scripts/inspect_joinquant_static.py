from __future__ import annotations

import re
import sys

import httpx


DEFAULT_URLS = [
    "https://cdn.joinquant.com/themes/jq/static/algorithm/js/edit.min.js?v=1776925000061",
    "https://cdn.joinquant.com/std/algorithm/js/list.min.js?v=1776925000061",
]


def main() -> int:
    urls = sys.argv[1:] or DEFAULT_URLS
    patterns = [
        "save",
        "new",
        "del",
        "GetFileList",
        "AlgorithmToFile",
        "runBacktest",
        "backtest",
        "compile",
        "ajax",
    ]
    with httpx.Client(timeout=20, trust_env=False) as client:
        for url in urls:
            response = client.get(url)
            text = response.text
            print("URL", url)
            print("STATUS", response.status_code, "LEN", len(text))
            print("--- endpoints")
            endpoints = sorted(set(re.findall(r"""["'](/(?:algorithm|backtest)[^"']{1,180})["']""", text)))
            for endpoint in endpoints:
                print(endpoint)
            for pattern in patterns:
                match = re.search(pattern, text, re.I)
                print(f"--- {pattern}")
                if not match:
                    print("NO")
                    continue
                start = max(0, match.start() - 500)
                end = min(len(text), match.end() + 900)
                print(text[start:end])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
