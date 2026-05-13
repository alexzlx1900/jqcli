# jqcli Command Reference

Always prefer:

```bash
python skills/joinquant-operator/scripts/jq_skill_bridge.py -- --non-interactive --format json <command>
```

Omit `--non-interactive` only when a human-facing table or local server is explicitly desired.

## Auth

```bash
jqcli --format json auth status
jqcli --format json auth login --username <user> --password-stdin
jqcli --format json auth import-cookie --cookie '<cookie>'
jqcli --format json auth import-token --token <token>
jqcli --format json auth logout
```

`auth status` checks local/env credentials only; it does not prove the remote cookie is still valid.
When copying from browser DevTools, pass the complete `Cookie` request header to `--cookie`; the single `token=` cookie value is not enough for JoinQuant strategy pages.

## Strategy

```bash
jqcli --non-interactive --format json strategy ls --limit 10
jqcli --non-interactive --format json strategy show <strategy_id>
jqcli --non-interactive --format json strategy show <strategy_id> --code
jqcli --non-interactive --format json strategy new "<name>" --file strategy.py
jqcli --non-interactive --format json strategy new "<name>" --code-stdin
jqcli --non-interactive --format json strategy edit <strategy_id> --name "<name>"
jqcli --non-interactive --format json strategy edit <strategy_id> --file strategy.py
jqcli --non-interactive --format json strategy edit <strategy_id> --code-stdin
jqcli --non-interactive --format json strategy rm <strategy_id> --yes
```

`strategy rm --yes` is destructive. Confirm with the user first.

## Backtest

```bash
jqcli --non-interactive --format json backtest run <strategy_id> --start YYYY-MM-DD --end YYYY-MM-DD --capital 1000000 --freq day --wait
jqcli --non-interactive --format json backtest run <strategy_id> --start YYYY-MM-DD --end YYYY-MM-DD --compile --wait
jqcli --non-interactive --format json backtest ls <strategy_id> --limit 10
jqcli --non-interactive --format json backtest ls <strategy_id> --compile
jqcli --non-interactive --format json backtest show <backtest_id>
jqcli --non-interactive --format json backtest stats <backtest_id>
jqcli --non-interactive --format json backtest result <backtest_id>
jqcli --non-interactive --format json backtest logs <backtest_id> --error
jqcli --non-interactive --format json backtest logs <backtest_id> --all
jqcli --non-interactive --format json backtest rm <list_id> --yes
```

Use `list_id` from `backtest ls` for deletion. Confirm before `rm --yes`.

## Community

```bash
jqcli --format json community latest --max-pages 1
jqcli --format json community latest --until YYYY-MM-DD --stream
jqcli --format json community detail <post_id> --with-backtest-stats
jqcli --non-interactive --format json community clone-strategy <post_id> --backtest-id <backtest_id>
jqcli --non-interactive --format json community clone-strategy <post_id> --backtest-id <backtest_id> --yes
```

`clone-strategy` without `--yes` only checks clone eligibility and possible credit cost. Confirm with the user before `--yes`.

## Local Web Manager

```bash
jqcli web run --host 127.0.0.1 --port 5050
```

Only use non-local hosts with explicit user approval and `--allow-public`. Do not run debug mode on public hosts.
