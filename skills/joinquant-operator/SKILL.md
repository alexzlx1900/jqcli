---
name: joinquant-operator
description: Operate JoinQuant through the jqcli project. Use when managing 聚宽/JoinQuant authentication, strategies, backtests, backtest logs/results, community posts, strategy cloning, or the local jqcli strategy-post web manager.
metadata:
  short-description: Operate JoinQuant with jqcli
---

# JoinQuant Operator

Use this skill for 聚宽/JoinQuant operations through `jqcli`. Prefer the existing CLI and API wrappers over direct JoinQuant HTTP calls.

## First Step

Run the bridge, not raw `jqcli`, unless the user explicitly asks otherwise:

```bash
python skills/joinquant-operator/scripts/jq_skill_bridge.py -- --format json auth status
```

The bridge discovers a usable `jqcli` entrypoint and adds repo-local fallback behavior. For a deeper environment check, run:

```bash
python skills/joinquant-operator/scripts/jq_skill_selfcheck.py
```

## Operating Rules

- Use `--non-interactive --format json` for automated actions.
- Never print raw cookie, token, password, Authorization headers, or full private strategy source unless the user specifically asks to inspect local code.
- Before destructive or externally costly actions, ask for explicit confirmation. This includes `strategy rm --yes`, `backtest rm --yes`, `community clone-strategy --yes`, overwriting local files, and public `web run --allow-public`.
- Use `auth status` before private strategy/backtest operations. If unauthenticated, guide the user to `.env`, `auth login --password-stdin`, or `auth import-cookie`.
- Treat browser `token=<value>` as only one cookie field, not a full remote login proof. For browser-session reuse, import or pass the complete `Cookie` header.
- Prefer `backtest run --compile --wait` for quick syntax/runtime checks and formal `backtest run --wait` for performance validation.
- On backtest failure, read logs before changing code: `backtest logs <id> --error`, then normal logs with `--all` when needed.

## References

- Read `references/commands.md` when choosing exact `jqcli` commands or parameters.
- Read `references/workflows.md` for multi-step flows such as strategy edit-and-test, community clone review, or local web management.
- Read `references/errors.md` when handling JSON errors or exit codes.

Keep the skill lean: if the command exists in `jqcli`, call it; do not reimplement JoinQuant API behavior in the agent.
