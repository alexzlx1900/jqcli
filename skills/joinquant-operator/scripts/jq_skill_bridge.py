#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path


def repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def candidate_commands() -> list[list[str]]:
    root = repo_root()
    local_bin = root / ".venv" / "bin" / "jqcli"
    commands: list[list[str]] = []
    if local_bin.exists():
        commands.append([str(local_bin)])
    installed = shutil.which("jqcli")
    if installed:
        commands.append([installed])
    commands.append([sys.executable, "-m", "jqcli"])
    return commands


def command_works(command: list[str]) -> bool:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(repo_root()) + os.pathsep + env.get("PYTHONPATH", "")
    result = subprocess.run(
        [*command, "--help"],
        cwd=repo_root(),
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        text=True,
        check=False,
    )
    return result.returncode == 0


def resolve_command() -> list[str]:
    for command in candidate_commands():
        if command_works(command):
            return command
    raise SystemExit("No usable jqcli entrypoint found. Install the project or run from the jqcli repository.")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run jqcli through the JoinQuant skill bridge.")
    parser.add_argument("--print-command", action="store_true", help="Print the resolved jqcli command and exit.")
    parser.add_argument("jqcli_args", nargs=argparse.REMAINDER, help="Arguments passed after -- to jqcli.")
    args = parser.parse_args()

    command = resolve_command()
    if args.print_command:
        print(" ".join(command))
        return 0

    jqcli_args = args.jqcli_args
    if jqcli_args[:1] == ["--"]:
        jqcli_args = jqcli_args[1:]

    env = os.environ.copy()
    env["PYTHONPATH"] = str(repo_root()) + os.pathsep + env.get("PYTHONPATH", "")
    completed = subprocess.run([*command, *jqcli_args], cwd=repo_root(), env=env, text=True, check=False)
    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())
