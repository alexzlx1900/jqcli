from __future__ import annotations

import json
import sys
from typing import Any

import click
from rich.console import Console

from .errors import JqcliError, error_payload


def write_json(payload: Any, *, err: bool = False) -> None:
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    if err:
        click.echo(text, err=True)
        return
    stream = sys.stderr if err else sys.stdout
    stream.write(text + "\n")


def write_json_line(payload: Any, *, err: bool = False) -> None:
    text = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    if err:
        click.echo(text, err=True)
        return
    stream = sys.stderr if err else sys.stdout
    stream.write(text + "\n")
    stream.flush()


def write_error(error: JqcliError, *, json_format: bool) -> None:
    if json_format:
        write_json(error_payload(error), err=True)
    else:
        Console(stderr=True).print(f"[red]错误:[/red] {error.message}")


def mask_sensitive(value: str) -> str:
    lowered = value.lower()
    for key in ("authorization", "cookie", "token", "password"):
        if key in lowered:
            return "<redacted>"
    return value
