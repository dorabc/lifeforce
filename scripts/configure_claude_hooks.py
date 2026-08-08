#!/usr/bin/env python3
"""Idempotently add lifeforce hooks to Claude Code settings.json."""

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


def add_command_hook(settings: dict, event: str, hook_command: str, matcher: str | None) -> bool:
    hooks = settings.setdefault("hooks", {})
    if not isinstance(hooks, dict):
        raise ValueError("settings.json 的 hooks 必须是对象")
    entries = hooks.setdefault(event, [])
    if not isinstance(entries, list):
        raise ValueError(f"settings.json 的 hooks.{event} 必须是数组")

    for entry in entries:
        if not isinstance(entry, dict):
            continue
        for item in entry.get("hooks", []):
            if isinstance(item, dict) and item.get("type") == "command" and item.get("command") == hook_command:
                return False

    entry = {"hooks": [{"type": "command", "command": hook_command}]}
    if matcher is not None:
        entry["matcher"] = matcher
    entries.append(entry)
    return True


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--settings", required=True, type=Path)
    parser.add_argument("--session-start", required=True, type=Path)
    parser.add_argument("--capture", required=True, type=Path)
    args = parser.parse_args()

    path = args.settings.expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        try:
            settings = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as error:
            raise SystemExit(f"无法读取 Claude settings.json，未做修改：{error}") from error
        if not isinstance(settings, dict):
            raise SystemExit("Claude settings.json 顶层必须是对象，未做修改")
        mode = stat.S_IMODE(path.stat().st_mode)
    else:
        settings = {}
        mode = 0o600

    changed = []
    if add_command_hook(settings, "SessionStart", command(args.session_start), ""):
        changed.append("SessionStart")
    if add_command_hook(settings, "Stop", command(args.capture), None):
        changed.append("Stop")

    if not changed:
        print("Claude hooks 已存在")
        return

    fd, temporary = tempfile.mkstemp(prefix="settings.", suffix=".json", dir=str(path.parent))
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
    print("Claude hooks 已更新：" + ", ".join(changed))


if __name__ == "__main__":
    main()
