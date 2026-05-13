#!/usr/bin/env python3
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
BRIDGE = ROOT / "skills" / "joinquant-operator" / "scripts" / "jq_skill_bridge.py"


def run(args: list[str]) -> dict[str, object]:
    completed = subprocess.run(
        [sys.executable, str(BRIDGE), "--", *args],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    return {
        "args": args,
        "exit_code": completed.returncode,
        "stdout": completed.stdout.strip(),
        "stderr": completed.stderr.strip(),
    }


def parse_json(text: str) -> object | None:
    if not text:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def main() -> int:
    command = subprocess.run(
        [sys.executable, str(BRIDGE), "--print-command"],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    auth = run(["--format", "json", "auth", "status"])
    auth_json = parse_json(str(auth["stdout"]))
    error_probe = run(["--config", str(ROOT / ".jqcli-selfcheck-missing.json"), "--format", "json", "strategy", "ls"])
    error_json = parse_json(str(error_probe["stderr"]) or str(error_probe["stdout"]))

    payload = {
        "ok": command.returncode == 0 and auth["exit_code"] == 0 and isinstance(auth_json, dict) and isinstance(error_json, dict),
        "repo_root": str(ROOT),
        "jqcli_command": command.stdout.strip(),
        "auth_status": auth_json,
        "json_error_probe": error_json,
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if payload["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
