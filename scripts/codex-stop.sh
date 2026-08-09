#!/usr/bin/env bash
# Codex Stop hook：只记录 session 指针，不解析 transcript，也不生成笔记。
set -u

RUNTIME="$(cd -- "$(dirname -- "$0")" && pwd -P)"
LIFEFORCE_TOOL=codex exec /bin/bash "$RUNTIME/capture.sh"
