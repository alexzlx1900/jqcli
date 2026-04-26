from __future__ import annotations

import argparse
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from typing import Any

from jqcli.api.backtest import get_backtest_stats
from jqcli.api.client import ApiClient
from jqcli.api.community import iter_latest_posts, normalize_detail
from jqcli.config import load_config, load_env_file, resolve_credentials


CORE_STATS_FIELDS = (
    "trading_days",
    "algorithm_return",
    "benchmark_return",
    "annual_algo_return",
    "annual_bm_return",
    "max_drawdown",
    "max_drawdown_period",
    "sharpe",
    "sortino",
    "information",
    "alpha",
    "beta",
    "algorithm_volatility",
    "benchmark_volatility",
    "win_ratio",
    "profit_loss_ratio",
    "turnover_rate",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Archive JoinQuant community post list data and enrich backtest stats.")
    parser.add_argument("--config", type=Path, help="jqcli config path")
    parser.add_argument("--env-file", type=Path, help="env file path; defaults to .env when present")
    parser.add_argument("--api-base", help="JoinQuant API base URL")
    parser.add_argument("--token", help="token for this run")
    parser.add_argument("--cookie", help="cookie for this run")
    parser.add_argument("--timeout", type=float, help="HTTP timeout in seconds")

    parser.add_argument("--phase", choices=("sync", "all", "list", "enrich"), default="sync")
    parser.add_argument("--store", type=Path, default=Path("data/community_posts_archive.jsonl"), help="canonical archive JSONL for sync phase")
    parser.add_argument("--seed", type=Path, action="append", default=[], help="existing JSONL to import before sync; can be repeated")
    parser.add_argument("--list-out", type=Path, help="raw list JSONL output")
    parser.add_argument("--enriched-out", type=Path, help="enriched JSONL output; defaults to <list-out>.enriched.jsonl")
    parser.add_argument("--state", type=Path, help="state JSON path; defaults to <list-out>.state.json")
    parser.add_argument("--resume", dest="resume", action="store_true", default=True)
    parser.add_argument("--no-resume", dest="resume", action="store_false")
    parser.add_argument("--force", action="store_true", help="overwrite selected output files before running")

    parser.add_argument("--page-size", type=int, default=50)
    parser.add_argument("--max-pages", type=int)
    parser.add_argument("--until", help="stop when a non-top post is older than this time")
    parser.add_argument("--list-type", type=int, default=1)
    parser.add_argument("--tags", default="")
    parser.add_argument("--page-sleep", type=float, default=0.0, help="sleep seconds after each list page")

    parser.add_argument("--backtest-workers", type=int, default=4)
    parser.add_argument("--detail-workers", type=int, default=4)
    parser.add_argument("--skip-detail", action="store_true", help="sync phase: do not fetch missing post details")
    parser.add_argument("--skip-backtest", action="store_true", help="sync phase: do not fetch missing backtest stats")
    parser.add_argument("--max-detail", type=int, help="sync phase: fetch at most N missing details")
    parser.add_argument("--max-backtest", type=int, help="sync phase: fetch at most N missing backtest stats")
    parser.add_argument("--retries", type=int, default=2)
    parser.add_argument("--retry-sleep", type=float, default=1.0)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    load_env_file(args.env_file)
    config = load_config(args.config)
    token, cookie = resolve_credentials(config, token=args.token, cookie=args.cookie)
    api_base = args.api_base or config.api_base
    timeout = args.timeout if args.timeout is not None else config.timeout
    list_out = args.list_out
    enriched_out = args.enriched_out or (list_out.with_suffix(list_out.suffix + ".enriched.jsonl") if list_out else None)
    state_path = args.state or (args.store.with_suffix(args.store.suffix + ".state.json") if args.phase == "sync" else None)

    if args.phase == "sync":
        sync_archive(
            api_base=api_base,
            token=token,
            cookie=cookie,
            timeout=timeout,
            store_path=args.store,
            state_path=state_path or args.store.with_suffix(args.store.suffix + ".state.json"),
            seed_paths=resolve_seed_paths(args.seed, list_out, enriched_out),
            resume=args.resume,
            force=args.force,
            page_size=args.page_size,
            max_pages=args.max_pages,
            until=args.until,
            list_type=args.list_type,
            tags=args.tags,
            page_sleep=args.page_sleep,
            detail_workers=max(1, args.detail_workers),
            backtest_workers=max(1, args.backtest_workers),
            skip_detail=args.skip_detail,
            skip_backtest=args.skip_backtest,
            max_detail=args.max_detail,
            max_backtest=args.max_backtest,
            retries=max(0, args.retries),
            retry_sleep=max(0.0, args.retry_sleep),
        )
        return 0

    if list_out is None:
        raise SystemExit("--list-out is required for phase list/enrich/all")
    assert enriched_out is not None
    state_path = args.state or list_out.with_suffix(list_out.suffix + ".state.json")

    if args.phase in {"all", "list"}:
        if args.force and list_out.exists():
            list_out.unlink()
        fetch_list(
            api_base=api_base,
            token=token,
            cookie=cookie,
            timeout=timeout,
            out_path=list_out,
            state_path=state_path,
            resume=args.resume,
            page_size=args.page_size,
            max_pages=args.max_pages,
            until=args.until,
            list_type=args.list_type,
            tags=args.tags,
            page_sleep=args.page_sleep,
        )

    if args.phase in {"all", "enrich"}:
        if enriched_out.resolve() == list_out.resolve():
            raise SystemExit("--enriched-out 不能和 --list-out 相同")
        if args.force and enriched_out.exists():
            enriched_out.unlink()
        enrich_backtests(
            api_base=api_base,
            token=token,
            cookie=cookie,
            timeout=timeout,
            list_path=list_out,
            out_path=enriched_out,
            state_path=state_path,
            resume=args.resume,
            workers=max(1, args.backtest_workers),
            retries=max(0, args.retries),
            retry_sleep=max(0.0, args.retry_sleep),
        )
    return 0


def resolve_seed_paths(seed_paths: list[Path], list_out: Path | None, enriched_out: Path | None) -> list[Path]:
    candidates: list[Path] = []
    candidates.extend(seed_paths)
    if enriched_out is not None:
        candidates.append(enriched_out)
    if list_out is not None:
        candidates.append(list_out)
    candidates.extend(
        [
            Path("data/community_posts_until_20200101.enriched.jsonl"),
            Path("data/community_posts_until_20200101.list.jsonl"),
        ]
    )
    resolved: list[Path] = []
    seen: set[Path] = set()
    for path in candidates:
        if not path.exists():
            continue
        key = path.resolve()
        if key in seen:
            continue
        resolved.append(path)
        seen.add(key)
    return resolved


def sync_archive(
    *,
    api_base: str,
    token: str | None,
    cookie: str | None,
    timeout: float,
    store_path: Path,
    state_path: Path,
    seed_paths: list[Path],
    resume: bool,
    force: bool,
    page_size: int,
    max_pages: int | None,
    until: str | None,
    list_type: int,
    tags: str,
    page_sleep: float,
    detail_workers: int,
    backtest_workers: int,
    skip_detail: bool,
    skip_backtest: bool,
    max_detail: int | None,
    max_backtest: int | None,
    retries: int,
    retry_sleep: float,
) -> None:
    if force and store_path.exists():
        store_path.unlink()
    store_path.parent.mkdir(parents=True, exist_ok=True)
    state = read_state(state_path) if resume else {}
    archive = load_archive(store_path)
    imported = import_seed_archives(archive, seed_paths)
    if imported:
        write_archive(store_path, archive)
        print(f"sync imported={imported} existing_total={len(archive)}", file=sys.stderr)

    latest_time = latest_published_at(archive.values())
    effective_until = until
    if latest_time is not None:
        effective_until = latest_time.strftime("%Y-%m-%d %H:%M:%S")

    fetched = fetch_incremental_lists(
        archive=archive,
        api_base=api_base,
        token=token,
        cookie=cookie,
        timeout=timeout,
        page_size=page_size,
        max_pages=max_pages,
        until=effective_until,
        list_type=list_type,
        tags=tags,
        page_sleep=page_sleep,
    )
    if fetched:
        write_archive(store_path, archive)

    details_ok = details_failed = 0
    if not skip_detail:
        details_ok, details_failed = fill_missing_details(
            archive=archive,
            api_base=api_base,
            token=token,
            cookie=cookie,
            timeout=timeout,
            workers=detail_workers,
            retries=retries,
            retry_sleep=retry_sleep,
            limit=max_detail,
        )
        if details_ok or details_failed:
            write_archive(store_path, archive)

    stats_ok = stats_failed = 0
    if not skip_backtest:
        stats_ok, stats_failed = fill_missing_backtest_stats(
            archive=archive,
            api_base=api_base,
            token=token,
            cookie=cookie,
            timeout=timeout,
            workers=backtest_workers,
            retries=retries,
            retry_sleep=retry_sleep,
            limit=max_backtest,
        )
        if stats_ok or stats_failed:
            write_archive(store_path, archive)

    update_state(
        state_path,
        state,
        "sync",
        {
            "items_total": len(archive),
            "list_fetched_this_run": fetched,
            "details_ok_this_run": details_ok,
            "details_failed_this_run": details_failed,
            "stats_ok_this_run": stats_ok,
            "stats_failed_this_run": stats_failed,
            "incremental_until": effective_until or "",
            "latest_published_at": latest_published_at_string(archive.values()),
        },
    )
    print(
        "sync done "
        f"total={len(archive)} list_fetched={fetched} "
        f"details_ok={details_ok} details_failed={details_failed} "
        f"stats_ok={stats_ok} stats_failed={stats_failed} out={store_path}",
        file=sys.stderr,
    )


def fetch_incremental_lists(
    *,
    archive: dict[str, dict[str, Any]],
    api_base: str,
    token: str | None,
    cookie: str | None,
    timeout: float,
    page_size: int,
    max_pages: int | None,
    until: str | None,
    list_type: int,
    tags: str,
    page_sleep: float,
) -> int:
    fetched = 0
    client = ApiClient(api_base, token=token, cookie=cookie, timeout=timeout)
    try:
        for event in iter_latest_posts(
            client,
            page_size=page_size,
            max_pages=max_pages,
            until=until,
            list_type=list_type,
            tags=tags,
            all_pages=until is None,
        ):
            event_type = event.get("type")
            if event_type == "post":
                item = event.get("item")
                if not isinstance(item, dict):
                    continue
                post_id = str(item.get("id", ""))
                existing = archive.get(post_id, {"id": post_id})
                archive[post_id] = merge_post(existing, canonical_from_list(item))
                fetched += 1
            elif event_type == "progress":
                print(
                    f"sync list page={event.get('page')} fetched={fetched} items_seen={event.get('items_seen')}",
                    file=sys.stderr,
                )
                if page_sleep > 0:
                    time.sleep(page_sleep)
    finally:
        client.close()
    return fetched


def fetch_list(
    *,
    api_base: str,
    token: str | None,
    cookie: str | None,
    timeout: float,
    out_path: Path,
    state_path: Path,
    resume: bool,
    page_size: int,
    max_pages: int | None,
    until: str | None,
    list_type: int,
    tags: str,
    page_sleep: float,
) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    state = read_state(state_path) if resume else {}
    list_state = state.get("list") if isinstance(state.get("list"), dict) else {}
    start_page = int(list_state.get("last_page", 0)) + 1 if resume else 1
    existing_ids = read_existing_ids(out_path) if resume else set()
    written = 0
    skipped = 0

    client = ApiClient(api_base, token=token, cookie=cookie, timeout=timeout)
    try:
        with out_path.open("a", encoding="utf-8") as handle:
            for event in iter_latest_posts(
                client,
                page_size=page_size,
                max_pages=max_pages,
                until=until,
                list_type=list_type,
                tags=tags,
                all_pages=True,
                start_page=start_page,
            ):
                event_type = event.get("type")
                if event_type == "post":
                    item = event.get("item")
                    if not isinstance(item, dict):
                        continue
                    post_id = str(item.get("id", ""))
                    if post_id in existing_ids:
                        skipped += 1
                        continue
                    write_json_line(handle, compact_post(item))
                    existing_ids.add(post_id)
                    written += 1
                elif event_type == "progress":
                    update_state(
                        state_path,
                        state,
                        "list",
                        {
                            "last_page": event.get("page"),
                            "items_written": len(existing_ids),
                            "written_this_run": written,
                            "skipped_this_run": skipped,
                            "curr_time": event.get("curr_time", ""),
                        },
                    )
                    print(
                        f"list page={event.get('page')} written={written} skipped={skipped} total_seen={event.get('items_seen')}",
                        file=sys.stderr,
                    )
                    if page_sleep > 0:
                        time.sleep(page_sleep)
                elif event_type == "done":
                    update_state(
                        state_path,
                        state,
                        "list",
                        {
                            "done": True,
                            "pages_read_last_run": event.get("pages_read"),
                            "items_seen_last_run": event.get("items_seen"),
                            "stopped_by_until": event.get("stopped_by_until"),
                            "stopped_by_since_id": event.get("stopped_by_since_id"),
                            "total_count": event.get("total_count"),
                        },
                    )
    finally:
        client.close()

    print(f"list done written={written} skipped={skipped} out={out_path}", file=sys.stderr)


def enrich_backtests(
    *,
    api_base: str,
    token: str | None,
    cookie: str | None,
    timeout: float,
    list_path: Path,
    out_path: Path,
    state_path: Path,
    resume: bool,
    workers: int,
    retries: int,
    retry_sleep: float,
) -> None:
    if not list_path.exists():
        raise SystemExit(f"list input not found: {list_path}")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    state = read_state(state_path) if resume else {}
    enriched_ids = read_existing_ids(out_path) if resume else set()
    rows = [row for row in read_jsonl(list_path) if str(row.get("id", "")) not in enriched_ids]
    processed = 0
    stats_ok = 0
    stats_failed = 0

    with out_path.open("a", encoding="utf-8") as handle:
        with ThreadPoolExecutor(max_workers=workers) as executor:
            iterator = executor.map(
                lambda row: enrich_one(row, api_base, token, cookie, timeout, retries, retry_sleep),
                rows,
            )
            for enriched in iterator:
                write_json_line(handle, enriched)
                processed += 1
                backtest = enriched.get("backtest") if isinstance(enriched.get("backtest"), dict) else {}
                if backtest.get("stats"):
                    stats_ok += 1
                if backtest.get("stats_error"):
                    stats_failed += 1
                update_state(
                    state_path,
                    state,
                    "enrich",
                    {
                        "items_written": len(enriched_ids) + processed,
                        "processed_this_run": processed,
                        "stats_ok_this_run": stats_ok,
                        "stats_failed_this_run": stats_failed,
                        "last_post_id": enriched.get("id", ""),
                    },
                )
                if processed % 50 == 0:
                    print(
                        f"enrich processed={processed} stats_ok={stats_ok} stats_failed={stats_failed}",
                        file=sys.stderr,
                    )

    print(
        f"enrich done processed={processed} stats_ok={stats_ok} stats_failed={stats_failed} out={out_path}",
        file=sys.stderr,
    )


def enrich_one(
    row: dict[str, Any],
    api_base: str,
    token: str | None,
    cookie: str | None,
    timeout: float,
    retries: int,
    retry_sleep: float,
) -> dict[str, Any]:
    post = dict(row)
    backtest = dict(post.get("backtest") if isinstance(post.get("backtest"), dict) else {})
    backtest_id = str(backtest.get("id", ""))
    if not backtest_id:
        backtest.setdefault("stats", {})
        post["backtest"] = backtest
        return post

    try:
        stats = fetch_stats_with_retry(api_base, token, cookie, timeout, backtest_id, retries, retry_sleep)
        backtest["stats"] = pick_stats(stats)
        backtest.pop("stats_error", None)
    except Exception as exc:  # noqa: BLE001 - archive should keep going and record per-row failures.
        backtest.setdefault("stats", {})
        backtest["stats_error"] = str(exc)
    post["backtest"] = backtest
    return post


def fetch_stats_with_retry(
    api_base: str,
    token: str | None,
    cookie: str | None,
    timeout: float,
    backtest_id: str,
    retries: int,
    retry_sleep: float,
) -> dict[str, Any]:
    attempts = retries + 1
    last_error: Exception | None = None
    for attempt in range(attempts):
        client = ApiClient(api_base, token=token, cookie=cookie, timeout=timeout)
        try:
            return get_backtest_stats(client, backtest_id)["metrics"]
        except Exception as exc:  # noqa: BLE001 - retry all request/parsing failures.
            last_error = exc
            if attempt + 1 < attempts and retry_sleep > 0:
                time.sleep(retry_sleep)
        finally:
            client.close()
    assert last_error is not None
    raise last_error


def fill_missing_details(
    *,
    archive: dict[str, dict[str, Any]],
    api_base: str,
    token: str | None,
    cookie: str | None,
    timeout: float,
    workers: int,
    retries: int,
    retry_sleep: float,
    limit: int | None,
) -> tuple[int, int]:
    rows = [row for row in archive.values() if row.get("id") and not row.get("detail_fetched_at")]
    rows.sort(key=lambda row: str(row.get("published_at", "")), reverse=True)
    if limit is not None:
        rows = rows[:limit]
    ok = 0
    failed = 0
    with ThreadPoolExecutor(max_workers=workers) as executor:
        iterator = executor.map(
            lambda row: fetch_detail_one(row, api_base, token, cookie, timeout, retries, retry_sleep),
            rows,
        )
        for detail in iterator:
            post_id = str(detail.get("id", ""))
            if not post_id:
                failed += 1
                continue
            archive[post_id] = merge_post(archive.get(post_id, {"id": post_id}), detail)
            if detail.get("detail_error"):
                failed += 1
            else:
                ok += 1
            if (ok + failed) % 50 == 0:
                print(f"sync detail processed={ok + failed} ok={ok} failed={failed}", file=sys.stderr)
    return ok, failed


def fill_missing_backtest_stats(
    *,
    archive: dict[str, dict[str, Any]],
    api_base: str,
    token: str | None,
    cookie: str | None,
    timeout: float,
    workers: int,
    retries: int,
    retry_sleep: float,
    limit: int | None,
) -> tuple[int, int]:
    rows = []
    for row in archive.values():
        backtest = row.get("backtest") if isinstance(row.get("backtest"), dict) else {}
        if backtest.get("id") and not backtest.get("stats"):
            rows.append(row)
    rows.sort(key=lambda row: str(row.get("published_at", "")), reverse=True)
    if limit is not None:
        rows = rows[:limit]
    ok = 0
    failed = 0
    with ThreadPoolExecutor(max_workers=workers) as executor:
        iterator = executor.map(
            lambda row: enrich_one(row, api_base, token, cookie, timeout, retries, retry_sleep),
            rows,
        )
        for enriched in iterator:
            post_id = str(enriched.get("id", ""))
            if not post_id:
                failed += 1
                continue
            archive[post_id] = merge_post(archive.get(post_id, {"id": post_id}), enriched)
            backtest = enriched.get("backtest") if isinstance(enriched.get("backtest"), dict) else {}
            if backtest.get("stats"):
                ok += 1
            elif backtest.get("stats_error"):
                failed += 1
            if (ok + failed) % 50 == 0:
                print(f"sync stats processed={ok + failed} ok={ok} failed={failed}", file=sys.stderr)
    return ok, failed


def fetch_detail_one(
    row: dict[str, Any],
    api_base: str,
    token: str | None,
    cookie: str | None,
    timeout: float,
    retries: int,
    retry_sleep: float,
) -> dict[str, Any]:
    post_id = str(row.get("id", ""))
    attempts = retries + 1
    last_error: Exception | None = None
    for attempt in range(attempts):
        client = ApiClient(api_base, token=token, cookie=cookie, timeout=timeout)
        try:
            payload = client.get(
                "/community/post/detailV2",
                params={"postId": post_id},
                headers={"Referer": f"{api_base.rstrip('/')}/view/community/detail/{post_id}"},
            )
            data = extract_response_data(payload, name="社区文章详情接口")
            detail = normalize_detail(data, requested_post_id=post_id)
            return canonical_from_detail(detail)
        except Exception as exc:  # noqa: BLE001 - archive should keep going and record per-row failures.
            last_error = exc
            if attempt + 1 < attempts and retry_sleep > 0:
                time.sleep(retry_sleep)
        finally:
            client.close()
    return {
        "id": post_id,
        "detail_error": str(last_error) if last_error else "unknown detail error",
        "detail_attempted_at": datetime.now().isoformat(timespec="seconds"),
    }


def canonical_from_list(item: dict[str, Any]) -> dict[str, Any]:
    post = compact_post(item)
    post["list_fetched_at"] = datetime.now().isoformat(timespec="seconds")
    backtest = post.get("backtest") if isinstance(post.get("backtest"), dict) else {}
    backtest.setdefault("name", "")
    post["backtest"] = backtest
    return post


def canonical_from_detail(detail: dict[str, Any]) -> dict[str, Any]:
    post_id = str(detail.get("requested_id") or detail.get("id") or "")
    backtest = detail.get("backtest") if isinstance(detail.get("backtest"), dict) else {}
    return {
        "id": post_id,
        "internal_post_id": detail.get("id", ""),
        "title": detail.get("title", ""),
        "url": detail.get("url", ""),
        "content": detail.get("content", ""),
        "author": detail.get("author", {}),
        "published_at": detail.get("published_at", ""),
        "updated_at": detail.get("updated_at", ""),
        "last_active_at": detail.get("last_active_at", ""),
        "last_reply_id": detail.get("last_reply_id", ""),
        "reply_count": detail.get("reply_count", 0),
        "view_count": detail.get("view_count", 0),
        "like_count": detail.get("like_count", 0),
        "dislike_count": detail.get("dislike_count", 0),
        "collection_count": detail.get("collection_count", 0),
        "is_top": detail.get("is_top", False),
        "is_best": detail.get("is_best", False),
        "is_rich": detail.get("is_rich", False),
        "is_worth": detail.get("is_worth", False),
        "type": detail.get("type"),
        "status": detail.get("status", ""),
        "ip_address": detail.get("ip_address", ""),
        "tags": detail.get("tags", []),
        "bounty": detail.get("bounty", []),
        "curr_time": detail.get("curr_time", ""),
        "backtest": {
            "id": backtest.get("id", ""),
            "name": backtest.get("name", ""),
            "clone_count": backtest.get("clone_count", 0),
        },
        "research": detail.get("research", {}),
        "file": detail.get("file", {}),
        "detail_fetched_at": datetime.now().isoformat(timespec="seconds"),
    }


def canonicalize_existing(row: dict[str, Any]) -> dict[str, Any]:
    post_id = str(row.get("id") or row.get("requested_id") or "")
    post = dict(row)
    post["id"] = post_id
    if not post.get("url") and post_id:
        post["url"] = f"https://www.joinquant.com/view/community/detail/{post_id}"
    backtest = dict(post.get("backtest") if isinstance(post.get("backtest"), dict) else {})
    backtest.setdefault("id", "")
    backtest.setdefault("name", "")
    backtest.setdefault("clone_count", 0)
    if isinstance(backtest.get("stats"), dict):
        backtest["stats"] = pick_stats(backtest["stats"])
    post["backtest"] = backtest
    post.setdefault("author", {})
    post.setdefault("tags", [])
    post.setdefault("research", {})
    post.setdefault("file", {})
    if post.get("content") and not post.get("detail_fetched_at"):
        post["detail_fetched_at"] = ""
    return post


def merge_post(existing: dict[str, Any], incoming: dict[str, Any]) -> dict[str, Any]:
    merged = dict(existing)
    for key, value in incoming.items():
        if key == "backtest":
            merged[key] = merge_dicts(merged.get(key), value)
        elif key in {"author", "research", "file"}:
            merged[key] = merge_dicts(merged.get(key), value)
        elif key in {"tags", "bounty"}:
            if value:
                merged[key] = value
        elif value not in (None, "", [], {}):
            merged[key] = value
        elif key not in merged:
            merged[key] = value
    if merged.get("id") and not merged.get("url"):
        merged["url"] = f"https://www.joinquant.com/view/community/detail/{merged['id']}"
    return merged


def merge_dicts(left: Any, right: Any) -> dict[str, Any]:
    merged = dict(left) if isinstance(left, dict) else {}
    if not isinstance(right, dict):
        return merged
    for key, value in right.items():
        if key == "stats":
            if isinstance(value, dict) and value:
                merged[key] = pick_stats(value)
            elif key not in merged:
                merged[key] = {}
        elif value not in (None, "", [], {}):
            merged[key] = value
        elif key not in merged:
            merged[key] = value
    return merged


def extract_response_data(payload: Any, *, name: str) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise RuntimeError(f"{name} returned non-object response")
    if payload.get("code") != "00000":
        raise RuntimeError(str(payload.get("msg") or f"{name} failed"))
    data = payload.get("data")
    if not isinstance(data, dict):
        raise RuntimeError(f"{name} missing data object")
    return data


def load_archive(path: Path) -> dict[str, dict[str, Any]]:
    if not path.exists():
        return {}
    archive: dict[str, dict[str, Any]] = {}
    for row in read_jsonl(path):
        post = canonicalize_existing(row)
        post_id = str(post.get("id", ""))
        if post_id:
            archive[post_id] = merge_post(archive.get(post_id, {"id": post_id}), post)
    return archive


def import_seed_archives(archive: dict[str, dict[str, Any]], paths: list[Path]) -> int:
    imported = 0
    for path in paths:
        for row in read_jsonl(path):
            post = canonicalize_existing(row)
            post_id = str(post.get("id", ""))
            if not post_id:
                continue
            before = json.dumps(archive.get(post_id, {}), sort_keys=True, ensure_ascii=False)
            archive[post_id] = merge_post(archive.get(post_id, {"id": post_id}), post)
            after = json.dumps(archive[post_id], sort_keys=True, ensure_ascii=False)
            if before != after:
                imported += 1
    return imported


def write_archive(path: Path, archive: dict[str, dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    rows = sorted(archive.values(), key=lambda row: str(row.get("published_at", "")), reverse=True)
    with tmp_path.open("w", encoding="utf-8") as handle:
        for row in rows:
            write_json_line(handle, row)
    tmp_path.replace(path)


def latest_published_at(rows) -> datetime | None:
    latest: datetime | None = None
    for row in rows:
        value = parse_time(str(row.get("published_at", "")))
        if value is not None and (latest is None or value > latest):
            latest = value
    return latest


def latest_published_at_string(rows) -> str:
    latest = latest_published_at(rows)
    return latest.strftime("%Y-%m-%d %H:%M:%S") if latest else ""


def parse_time(value: str) -> datetime | None:
    if not value:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            pass
    return None


def compact_post(item: dict[str, Any]) -> dict[str, Any]:
    backtest = item.get("backtest") if isinstance(item.get("backtest"), dict) else {}
    return {
        "id": item.get("id", ""),
        "title": item.get("title", ""),
        "url": item.get("url", ""),
        "author": item.get("author", {}),
        "published_at": item.get("published_at", ""),
        "updated_at": item.get("updated_at", ""),
        "last_active_at": item.get("last_active_at", ""),
        "last_reply_at": item.get("last_reply_at", ""),
        "reply_count": item.get("reply_count", 0),
        "view_count": item.get("view_count", 0),
        "like_count": item.get("like_count", 0),
        "collection_count": item.get("collection_count", 0),
        "is_top": item.get("is_top", False),
        "is_best": item.get("is_best", False),
        "tags": item.get("tags", []),
        "content_preview": item.get("content_preview", ""),
        "backtest": {
            "id": backtest.get("id", ""),
            "clone_count": backtest.get("clone_count", 0),
            "pic_url": backtest.get("pic_url", ""),
        },
        "research": item.get("research", {}),
        "file": item.get("file", {}),
    }


def pick_stats(stats: dict[str, Any]) -> dict[str, Any]:
    return {key: stats[key] for key in CORE_STATS_FIELDS if key in stats}


def read_jsonl(path: Path):
    with path.open("r", encoding="utf-8") as handle:
        for line_no, line in enumerate(handle, start=1):
            stripped = line.strip()
            if not stripped:
                continue
            try:
                value = json.loads(stripped)
            except json.JSONDecodeError as exc:
                raise SystemExit(f"invalid JSONL at {path}:{line_no}: {exc}") from exc
            if isinstance(value, dict):
                yield value


def read_existing_ids(path: Path) -> set[str]:
    if not path.exists():
        return set()
    return {str(row.get("id", "")) for row in read_jsonl(path) if row.get("id")}


def read_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SystemExit(f"invalid state file {path}: {exc}") from exc
    return value if isinstance(value, dict) else {}


def update_state(path: Path, state: dict[str, Any], section: str, values: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    section_data = state.get(section)
    if not isinstance(section_data, dict):
        section_data = {}
        state[section] = section_data
    section_data.update(values)
    section_data["updated_at"] = datetime.now().isoformat(timespec="seconds")
    path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_json_line(handle, payload: dict[str, Any]) -> None:
    handle.write(json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n")
    handle.flush()


if __name__ == "__main__":
    raise SystemExit(main())
