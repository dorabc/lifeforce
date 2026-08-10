#!/usr/bin/env bash
# Claude Code/Codex Stop hook：只追加 session 指针，不解析 transcript，也不生成笔记。
set -u

RUNTIME="$(cd -- "$(dirname -- "$0")" && pwd -P)"
INBOX="$RUNTIME/inbox.jsonl"
TOOL="${LIFEFORCE_TOOL:-claude-code}"
TS="$(date +%Y-%m-%dT%H:%M:%S%z)"
mkdir -p "$RUNTIME"

# Hook 失败不能阻塞用户 session；Python 只使用标准库，避免额外安装 jq。
python3 -c '
import json
import os
import sys

inbox, tool, timestamp = sys.argv[1:]
try:
    payload = json.load(sys.stdin)
except Exception:
    raise SystemExit(0)

record = {
    "ts": timestamp,
    "tool": tool,
    "cwd": payload.get("cwd") or payload.get("working_directory", ""),
    "session": payload.get("session_id") or payload.get("thread_id") or payload.get("conversation_id", ""),
    "transcript": payload.get("transcript_path") or payload.get("agent_transcript_path", ""),
    "done": False,
}
try:
    key = (record.get("session"), record.get("cwd"), record.get("transcript"))
    if key[0] or key[2]:
        try:
            with open(inbox, "rb") as stream:
                stream.seek(0, 2)
                stream.seek(max(0, stream.tell() - 8192))
                lines = stream.read().splitlines()
            if lines:
                previous = json.loads(lines[-1])
                previous_key = (previous.get("session"), previous.get("cwd"), previous.get("transcript"))
                if previous_key == key:
                    raise SystemExit(0)
        except (OSError, ValueError, TypeError):
            pass
    with open(inbox, "a", encoding="utf-8") as stream:
        json.dump(record, stream, ensure_ascii=False, separators=(",", ":"))
        stream.write("\n")
except OSError:
    pass
' "$INBOX" "$TOOL" "$TS" 2>/dev/null || true
exit 0
