#!/usr/bin/env bash
# Claude/Codex UserPromptSubmit hook：输出当前任务命中的 lifeforce 和 OpenWiki 候选。
set -u

RUNTIME="$(cd -- "$(dirname -- "$0")" && pwd -P)"
PAYLOAD="$(cat 2>/dev/null || true)"

# 两个检索器都必须 fail-open：OpenWiki 未安装或未初始化时，旧的
# lifeforce vault 仍然可以独立工作；反过来也一样。
printf '%s' "$PAYLOAD" | python3 "$RUNTIME/prompt-context.py" 2>/dev/null || true
printf '%s' "$PAYLOAD" | python3 "$RUNTIME/openwiki-context.py" 2>/dev/null || true
