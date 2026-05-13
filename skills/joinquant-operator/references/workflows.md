# JoinQuant Workflows

## Environment and Auth Check

1. Run `jq_skill_selfcheck.py`.
2. Run `auth status`.
3. If unauthenticated, prefer `.env` with `JQCLI_USERNAME/JQCLI_PASSWORD` or `JQCLI_COOKIE`.
4. For password login, pipe the password through stdin; do not place it in shell history.

## Edit and Validate a Strategy

1. `strategy ls` to identify the current strategy id.
2. `strategy show <id> --code` to inspect current code when needed.
3. Apply local code edits in a file.
4. `strategy edit <id> --file <file>`.
5. Run a compile check: `backtest run <id> --compile --start <date> --end <date> --wait`.
6. If compile/runtime fails, read `backtest logs <id> --error` before changing code again.
7. Run a formal backtest only after compile mode is clean.

## Run and Diagnose a Backtest

1. Submit with explicit date range, capital, frequency, and `--wait` if the user wants one-shot validation.
2. Use `backtest stats` for core metrics and `backtest result` for curve data.
3. If status is failed or cancelled, read error logs first.
4. When waiting times out, do not assume failure; use `backtest ls` and `backtest show` later.

## Community Strategy Review and Clone

1. Use `community latest` or `community detail` to inspect post content.
2. Read `--with-backtest-stats` before recommending clone.
3. Run `community clone-strategy` without `--yes` to check eligibility and credit cost.
4. Ask for explicit confirmation if the action may deduct credits.
5. After clone, use `strategy ls` to find the new strategy and optionally compile-test it.

## Local Web Manager

1. Start with `web run --host 127.0.0.1 --port 5050`.
2. Keep the server local unless the user explicitly asks for network access.
3. Use the web manager for archived community posts, downloaded strategies, standardization, and tracked standardized backtests.
