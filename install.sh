#!/usr/bin/env bash
# Install lifeforce into a user-selected Obsidian vault or OpenWiki-only runtime.
set -euo pipefail

usage() {
  cat <<'EOF'
用法：
  bash install.sh /path/to/obsidian-vault [--no-claude-hooks] [--no-codex-hooks]
  bash install.sh --openwiki-only [--no-claude-hooks] [--no-codex-hooks]

安装内容：
  - 旧 vault 模式把路径写入 ~/.lifeforce-vault；OpenWiki-only 模式把 runtime 写入 ~/.lifeforce-runtime
  - 安装 .lifeforce/skill、索引脚本、OpenWiki 桥接脚本、Claude/Codex lifecycle hook 和 Codex 历史 wiki 脚本
  - 链接到 ~/.claude/skills、~/.codex/skills、~/.gemini/skills
  - 默认幂等追加 Claude 和 Codex 的 SessionStart/UserPromptSubmit/Stop hook
EOF
}

VAULT_ARG=""
OPENWIKI_ONLY=0
CLAUDE_HOOKS=1
CODEX_HOOKS=1
while [ "$#" -gt 0 ]; do
  case "$1" in
    --openwiki-only)
      OPENWIKI_ONLY=1
      ;;
    --no-claude-hooks)
      CLAUDE_HOOKS=0
      ;;
    --no-codex-hooks)
      CODEX_HOOKS=0
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    --*)
      echo "未知参数：$1" >&2
      usage >&2
      exit 2
      ;;
    *)
      if [ -n "$VAULT_ARG" ] || [ "$OPENWIKI_ONLY" -eq 1 ]; then
        echo "vault 路径只能提供一次，且不能与 --openwiki-only 同时使用" >&2
        usage >&2
        exit 2
      fi
      VAULT_ARG="$1"
      ;;
  esac
  shift
done

if [ "$OPENWIKI_ONLY" -eq 1 ] && [ -n "$VAULT_ARG" ]; then
  echo "vault 路径不能与 --openwiki-only 同时使用" >&2
  usage >&2
  exit 2
fi
if [ -z "$VAULT_ARG" ] && [ "$OPENWIKI_ONLY" -eq 0 ]; then
  echo "请提供 vault 路径，或使用 --openwiki-only" >&2
  usage >&2
  exit 2
fi

REPO_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
HOME_DIR="${HOME:?HOME 未设置}"
if [ "$OPENWIKI_ONLY" -eq 0 ] && [ ! -d "$VAULT_ARG" ]; then
  echo "vault 目录不存在：$VAULT_ARG" >&2
  exit 1
fi
if [ "$OPENWIKI_ONLY" -eq 1 ]; then
  RUNTIME="$HOME_DIR/.lifeforce"
  SKILL_DIR="$RUNTIME/skill"
else
  VAULT="$(cd -- "$VAULT_ARG" && pwd -P)"
  RUNTIME="$VAULT/.lifeforce"
  SKILL_DIR="$RUNTIME/skill"
fi

HOOK_COMMAND_PREFIX="/bin/bash"
if [[ "$HOME_DIR" == /mnt/* ]]; then
  HOOK_COMMAND_PREFIX="wsl.exe env HOME=$(printf '%q' "$HOME_DIR") /bin/bash"
fi

for required in "$REPO_DIR/skill/SKILL.md" "$REPO_DIR/scripts/reindex.py" "$REPO_DIR/scripts/capture.sh" "$REPO_DIR/scripts/session-start.sh" "$REPO_DIR/scripts/prompt-context.py" "$REPO_DIR/scripts/prompt-context.sh" "$REPO_DIR/scripts/openwiki-context.py" "$REPO_DIR/scripts/migrate-openwiki.py" "$REPO_DIR/scripts/codex-session-start.sh" "$REPO_DIR/scripts/codex-prompt-submit.sh" "$REPO_DIR/scripts/codex-stop.sh" "$REPO_DIR/scripts/codex-sessions.py" "$REPO_DIR/scripts/codex-history-wiki.py" "$REPO_DIR/scripts/ai-history-wiki.py" "$REPO_DIR/scripts/configure_codex_hooks.py"; do
  if [ ! -f "$required" ]; then
    echo "安装包缺少文件：$required" >&2
    exit 1
  fi
done

if [ "$OPENWIKI_ONLY" -eq 1 ]; then
  mkdir -p "$SKILL_DIR"
else
  mkdir -p "$SKILL_DIR" "$VAULT/projects"
fi
cp -R "$REPO_DIR/skill/." "$SKILL_DIR/"
cp "$REPO_DIR/scripts/capture.sh" "$RUNTIME/capture.sh"
cp "$REPO_DIR/scripts/session-start.sh" "$RUNTIME/session-start.sh"
cp "$REPO_DIR/scripts/prompt-context.py" "$RUNTIME/prompt-context.py"
cp "$REPO_DIR/scripts/prompt-context.sh" "$RUNTIME/prompt-context.sh"
cp "$REPO_DIR/scripts/openwiki-context.py" "$RUNTIME/openwiki-context.py"
cp "$REPO_DIR/scripts/migrate-openwiki.py" "$RUNTIME/migrate-openwiki.py"
cp "$REPO_DIR/scripts/codex-session-start.sh" "$RUNTIME/codex-session-start.sh"
cp "$REPO_DIR/scripts/codex-prompt-submit.sh" "$RUNTIME/codex-prompt-submit.sh"
cp "$REPO_DIR/scripts/codex-stop.sh" "$RUNTIME/codex-stop.sh"
cp "$REPO_DIR/scripts/codex-sessions.py" "$RUNTIME/codex-sessions.py"
cp "$REPO_DIR/scripts/codex-history-wiki.py" "$RUNTIME/codex-history-wiki.py"
cp "$REPO_DIR/scripts/ai-history-wiki.py" "$RUNTIME/ai-history-wiki.py"
if [ "$OPENWIKI_ONLY" -eq 0 ]; then
  cp "$REPO_DIR/scripts/reindex.py" "$RUNTIME/reindex.py"
fi
chmod +x "$RUNTIME/capture.sh" "$RUNTIME/session-start.sh" "$RUNTIME/prompt-context.py" "$RUNTIME/prompt-context.sh" "$RUNTIME/openwiki-context.py" "$RUNTIME/migrate-openwiki.py" "$RUNTIME/codex-session-start.sh" "$RUNTIME/codex-prompt-submit.sh" "$RUNTIME/codex-stop.sh" "$RUNTIME/codex-sessions.py" "$RUNTIME/codex-history-wiki.py" "$RUNTIME/ai-history-wiki.py"
if [ "$OPENWIKI_ONLY" -eq 0 ]; then
  chmod +x "$RUNTIME/reindex.py"
fi

ORIGINAL_UMASK="$(umask)"
umask 077
printf '%s\n' "$RUNTIME" > "$HOME_DIR/.lifeforce-runtime"
chmod 600 "$HOME_DIR/.lifeforce-runtime"
if [ "$OPENWIKI_ONLY" -eq 1 ]; then
  printf '%s\n' "openwiki" > "$HOME_DIR/.lifeforce-backend"
else
  printf '%s\n' "hybrid" > "$HOME_DIR/.lifeforce-backend"
fi
chmod 600 "$HOME_DIR/.lifeforce-backend"
if [ "$OPENWIKI_ONLY" -eq 0 ]; then
  printf '%s\n' "$VAULT" > "$HOME_DIR/.lifeforce-vault"
  chmod 600 "$HOME_DIR/.lifeforce-vault"
fi
umask "$ORIGINAL_UMASK"
if [ "$OPENWIKI_ONLY" -eq 0 ]; then
  python3 "$RUNTIME/reindex.py"
fi

link_skill() {
  local skill_root="$1"
  local link_path="$skill_root/lifeforce"
  mkdir -p "$skill_root"
  if [ -L "$link_path" ]; then
    if [ "$(readlink "$link_path")" = "$SKILL_DIR" ]; then
      echo "已存在：$link_path"
    else
      echo "跳过已有软链接（请手动处理）：$link_path" >&2
    fi
  elif [ -e "$link_path" ]; then
    echo "跳过已有目录/文件（请手动处理）：$link_path" >&2
  else
    ln -s "$SKILL_DIR" "$link_path"
    echo "已链接：$link_path"
  fi
}

link_skill "$HOME_DIR/.claude/skills"
link_skill "$HOME_DIR/.codex/skills"
link_skill "$HOME_DIR/.gemini/skills"
if [ -d "$HOME_DIR/.gemini/antigravity-ide" ]; then
  link_skill "$HOME_DIR/.gemini/antigravity-ide/skills"
fi
if [ -d "$HOME_DIR/.gemini/antigravity-cli" ]; then
  link_skill "$HOME_DIR/.gemini/antigravity-cli/skills"
fi

if [ "$CLAUDE_HOOKS" -eq 1 ]; then
  python3 "$REPO_DIR/scripts/configure_claude_hooks.py" \
    --settings "$HOME_DIR/.claude/settings.json" \
    --session-start "$RUNTIME/session-start.sh" \
    --prompt-context "$RUNTIME/prompt-context.sh" \
    --capture "$RUNTIME/capture.sh" \
    --command-prefix "$HOOK_COMMAND_PREFIX"
fi

if [ "$CODEX_HOOKS" -eq 1 ]; then
  python3 "$REPO_DIR/scripts/configure_codex_hooks.py" \
    --hooks "$HOME_DIR/.codex/hooks.json" \
    --session-start "$RUNTIME/codex-session-start.sh" \
    --prompt-context "$RUNTIME/codex-prompt-submit.sh" \
    --capture "$RUNTIME/codex-stop.sh" \
    --command-prefix "$HOOK_COMMAND_PREFIX"
fi

cat <<EOF

lifeforce 已安装。
$(if [ "$OPENWIKI_ONLY" -eq 1 ]; then echo '模式：OpenWiki-only'; else echo "vault：$VAULT"; fi)
显式使用：/lifeforce、/lifeforce find <关键词>、/lifeforce save、/lifeforce daily
Codex 默认已配置 SessionStart/Stop hook；如不需要可用 --no-codex-hooks 跳过。
如果已安装 OpenWiki，hook 会自动读取 ~/.openwiki/wiki；迁移旧经验可运行：
$(if [ "$OPENWIKI_ONLY" -eq 0 ]; then echo "python3 \"$RUNTIME/migrate-openwiki.py\""; else echo '已有旧 vault 时，用带 vault 路径的安装命令再执行迁移。'; fi)
EOF
