# jqcli Errors

JSON errors are written as:

```json
{
  "error": {
    "code": "not_authenticated",
    "message": "...",
    "details": {}
  }
}
```

## Error Codes

- `not_authenticated` exit 1: credentials are missing or expired. Run `auth status`, then login or import cookie.
- If `auth status` says authenticated but strategy/backtest calls return `not_authenticated`, the local credential exists but failed remote validation. Re-login or pass the complete browser `Cookie` header.
- `not_found` exit 2: strategy, backtest, or post was not found. Re-list resources before retrying.
- `usage_error` exit 3: arguments are missing or invalid. Re-read command help.
- `api_error` exit 4: JoinQuant returned an unexpected response. Keep raw response only if it is already redacted.
- `network_error` exit 5: connectivity problem. Retry later or check local network.
- `file_error` exit 6: local file read/write failed. Check paths and overwrite flags.
- `confirmation_required` exit 7: non-interactive command needs explicit `--yes`. Ask the user before adding it.
- `timeout` exit 8: wait loop timed out. Query the backtest later instead of assuming failure.

## Redaction

Do not display raw values for keys or headers containing `authorization`, `cookie`, `token`, or `password`. For private strategy code, summarize unless the user explicitly asks to inspect or edit it.
