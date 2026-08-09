#!/usr/bin/env python3
"""Idempotently add lifeforce hooks to Codex hooks.json."""

from __future__ import annotations

import argparse
import json
import os
import shlex
import stat
import tempfile
from pathlib import Path


def command(path: Path) -> str:
    return f"/bin/bash {shlex.quote(str(path))}"


def add_command_hook(
    settings: dict,
    event: str,
    hook_command: str,
    matcher: str | None,
    *,
    timeout: int,
    status_message: str,
) -> bool:
    hooks = settings.setdefault("hooks", {})
    if not isinstance(hooks, dict):
        raise ValueError("hooks.json 的 hooks 必须是对象")
    entries = hooks.setdefault(event, [])
    if not isinstance(entries, list):
        raise ValueError(f"hooks.json 的 hooks.{event} 必须是数组")

    for entry in entries:
        if not isinstance(entry, dict):
            continue
        for item in entry.get("hooks", []):
            if isinstance(item, dict) and item.get("type") == "command" and item.get("command") == hook_command:
                return False

    item = {
        "type": "command",
        "command": hook_command,
        "timeout": timeout,
        "statusMessage": status_message,
    }
    entry = {"hooks": [item]}
    if matcher is not None:
        entry["matcher"] = matcher
    entries.append(entry)
    return True


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--hooks", required=True, type=Path)
    parser.add_argument("--session-start", required=True, type=Path)
    parser.add_argument("--prompt-context", required=True, type=Path)
    parser.add_argument("--capture", required=True, type=Path)
    args = parser.parse_args()

    path = args.hooks.expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        try:
            settings = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as error:
            raise SystemExit(f"无法读取 Codex hooks.json，未做修改：{error}") from error
        if not isinstance(settings, dict):
            raise SystemExit("Codex hooks.json 顶层必须是对象，未做修改")
        mode = stat.S_IMODE(path.stat().st_mode)
    else:
        settings = {}
        mode = 0o600

    changed = []
    if add_command_hook(
        settings,
        "SessionStart",
        command(args.session_start),
        "startup|resume|clear|compact",
        timeout=10,
        status_message="Loading lifeforce context...",
    ):
        changed.append("SessionStart")
    if add_command_hook(
        settings,
        "Stop",
        command(args.capture),
        None,
        timeout=5,
        status_message="Capturing lifeforce session...",
    ):
        changed.append("Stop")
    if add_command_hook(
        settings,
        "UserPromptSubmit",
        command(args.prompt_context),
        None,
        timeout=5,
        status_message="Finding reusable lifeforce context...",
    ):
        changed.append("UserPromptSubmit")

    if not changed:
        print("Codex hooks 已存在")
        return

    fd, temporary = tempfile.mkstemp(prefix="hooks.", suffix=".json", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(settings, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
        os.chmod(temporary, mode)
        os.replace(temporary, path)
    except Exception:
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise
    print("Codex hooks 已更新：" + ", ".join(changed))


if __name__ == "__main__":
    main()
