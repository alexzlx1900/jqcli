#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import shutil
from pathlib import Path


def default_codex_home() -> Path:
    return Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex")


def copy_skill(source: Path, target: Path) -> None:
    if target.exists():
        shutil.rmtree(target)
    ignore = shutil.ignore_patterns("__pycache__", "*.pyc", ".DS_Store")
    shutil.copytree(source, target, ignore=ignore)


def main() -> int:
    parser = argparse.ArgumentParser(description="Install the joinquant-operator skill into Codex skills.")
    parser.add_argument("--codex-home", type=Path, default=default_codex_home(), help="Codex home directory.")
    parser.add_argument("--name", default="joinquant-operator", help="Installed skill directory name.")
    args = parser.parse_args()

    source = Path(__file__).resolve().parents[1]
    target = args.codex_home / "skills" / args.name
    target.parent.mkdir(parents=True, exist_ok=True)
    copy_skill(source, target)
    print(f"installed {source} -> {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
