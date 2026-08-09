#!/usr/bin/env bash
# Codex UserPromptSubmit hook：把经验候选包装成 Codex hook JSON。
set -u

RUNTIME="$(cd -- "$(dirname -- "$0")" && pwd -P)"
PAYLOAD="$(cat 2>/dev/null || true)"
CONTEXT="$(printf '%s' "$PAYLOAD" | /bin/bash "$RUNTIME/prompt-context.sh" 2>/dev/null || true)"

printf '%s' "$CONTEXT" | python3 -c '
import json
import sys

context = sys.stdin.read()
if not context.strip():
    print("{}")
else:
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "UserPromptSubmit",
            "additionalContext": context,
        }
    }, ensure_ascii=False))
' 2>/dev/null || printf '%s\n' '{}'

exit 0
