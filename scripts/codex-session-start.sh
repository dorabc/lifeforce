#!/usr/bin/env bash
# Codex SessionStart hook：把 lifeforce 启动上下文包装成 Codex hook JSON。
set -u

RUNTIME="$(cd -- "$(dirname -- "$0")" && pwd -P)"
PAYLOAD="$(cat 2>/dev/null || true)"
CONTEXT="$(printf '%s' "$PAYLOAD" | /bin/bash "$RUNTIME/session-start.sh" 2>/dev/null || true)"

# Codex 需要 hookSpecificOutput 才会把额外上下文注入当前 session；
# 空上下文时输出空对象，避免 hook 的诊断信息污染对话。
printf '%s' "$CONTEXT" | python3 -c '
import json
import sys

context = sys.stdin.read()
if not context.strip():
    print("{}")
else:
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "SessionStart",
            "additionalContext": context,
        }
    }, ensure_ascii=False))
' 2>/dev/null || printf '%s\n' '{}'

exit 0
