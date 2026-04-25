from __future__ import annotations

import csv
import json
from pathlib import Path


SRC = Path("/tmp/jqcli_community_latest_until_20250101.json")
OUT_JSON = Path("/tmp/jqcli_community_clone_gt100_like_gt50.json")
OUT_CSV = Path("/tmp/jqcli_community_clone_gt100_like_gt50.csv")


def main() -> None:
    data = json.loads(SRC.read_text(encoding="utf-8"))
    rows = []
    for item in data["items"]:
        backtest = item.get("backtest") or {}
        clone_count = int(backtest.get("clone_count") or 0)
        like_count = int(item.get("like_count") or 0)
        if clone_count <= 100 or like_count <= 50:
            continue
        rows.append(
            {
                "published_at": item.get("published_at", ""),
                "title": item.get("title", ""),
                "author": (item.get("author") or {}).get("name", ""),
                "url": item.get("url", ""),
                "post_id": item.get("id", ""),
                "backtest_id": backtest.get("id", ""),
                "clone_count": clone_count,
                "like_count": like_count,
                "reply_count": item.get("reply_count", 0),
                "view_count": item.get("view_count", 0),
                "is_best": item.get("is_best", False),
            }
        )

    rows.sort(key=lambda row: (-row["clone_count"], -row["like_count"], row["published_at"]))
    OUT_JSON.write_text(json.dumps({"count": len(rows), "items": rows}, ensure_ascii=False, indent=2), encoding="utf-8")

    fieldnames = [
        "published_at",
        "title",
        "author",
        "url",
        "post_id",
        "backtest_id",
        "clone_count",
        "like_count",
        "reply_count",
        "view_count",
        "is_best",
    ]
    with OUT_CSV.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"count\t{len(rows)}")
    print(f"json\t{OUT_JSON}")
    print(f"csv\t{OUT_CSV}")
    for index, row in enumerate(rows, 1):
        print(
            "\t".join(
                [
                    str(index),
                    str(row["clone_count"]),
                    str(row["like_count"]),
                    str(row["published_at"]),
                    str(row["title"]),
                    str(row["author"]),
                    str(row["url"]),
                ]
            )
        )


if __name__ == "__main__":
    main()
