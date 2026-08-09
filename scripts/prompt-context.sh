#!/usr/bin/env bash
# Claude/Codex UserPromptSubmit hook：输出当前任务命中的经验候选。
set -u

RUNTIME="$(cd -- "$(dirname -- "$0")" && pwd -P)"
exec python3 "$RUNTIME/prompt-context.py"
