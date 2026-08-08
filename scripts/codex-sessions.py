#!/usr/bin/env python3
"""List Codex session pointers for a workspace without printing transcript text."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path


def session_meta(path: Path) -> dict | None:
    try:
        with path.open(encoding="utf-8", errors="replace") as stream:
            for line in stream:
                try:
                    record = json.loads(line)
                except ValueError:
                    continue
                if record.get("type") == "session_meta":
                    payload = record.get("payload")
                    return payload if isinstance(payload, dict) else None
    except OSError:
        return None
    return None


def main() -> int:
    parser = argparse.ArgumentParser(
        description="列出 Codex 相关 session 指针；不输出 transcript 内容。"
    )
    parser.add_argument(
        "cwd",
        nargs="?",
        default=os.getcwd(),
        help="项目工作目录；默认当前目录，包含其子目录 session",
    )
    parser.add_argument(
        "--sessions-root",
        default=os.path.expanduser("~/.codex/sessions"),
        help="Codex session 根目录",
    )
    args = parser.parse_args()
    target = str(Path(args.cwd).expanduser().resolve()).rstrip(os.sep)
    root = Path(args.sessions_root).expanduser()
    if not root.is_dir():
        return 0

    rows = []
    for path in root.rglob("*.jsonl"):
        meta = session_meta(path)
        if not meta:
            continue
        cwd = str(meta.get("cwd") or "")
        if cwd != target and not cwd.startswith(target + os.sep):
            continue
        rows.append(
            {
                "ts": meta.get("timestamp", ""),
                "session": meta.get("id", ""),
                "cwd": cwd,
                "transcript": str(path),
                "source": meta.get("source", ""),
            }
        )

    for row in sorted(rows, key=lambda item: (item["ts"], item["session"])):
        print(json.dumps(row, ensure_ascii=False, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
