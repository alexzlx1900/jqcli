from __future__ import annotations

import re

import httpx


URLS = [
    "https://cdn.joinquant.com/themes/jq/static/algorithm/js/edit.min.js?v=1776925000061",
    "https://cdn.joinquant.com/themes/jq/static/algorithm/js/detail.min.js?v=1776925000061",
    "https://cdn.joinquant.com/themes/jq/static/algorithm/js/newTrade.min.js?v=1776925000061",
    "https://cdn.joinquant.com/themes/jq/static/algorithm/js/newTradeStd.min.js?v=1776925000061",
    "https://cdn.joinquant.com/themes/jq/static/algorithm/js/backtestList.min.js?v=1776925000061",
    "https://cdn.joinquant.com/themes/jq/static/algorithm/js/buildList.min.js?v=1776925000061",
]

PATTERNS = [
    "daily-new-backtest-button",
    "new-backtest",
    "backtest\\[",
    "batchContinueBacktest",
    "continue",
    "buildList",
    "/algorithm/index/build",
    "/algorithm/backtest",
    "type=0",
    "type=1",
]


def main() -> int:
    with httpx.Client(timeout=20, trust_env=False) as client:
        for url in URLS:
            text = client.get(url).text
            print("URL", url, "LEN", len(text))
            for pattern in PATTERNS:
                print("PAT", pattern)
                for match in list(re.finditer(pattern, text, re.I))[:4]:
                    start = max(0, match.start() - 500)
                    end = min(len(text), match.end() + 900)
                    print(text[start:end])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
