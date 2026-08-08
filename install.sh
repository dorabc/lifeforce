#!/usr/bin/env bash
# Install lifeforce into a user-selected Obsidian vault and AI skill directories.
set -euo pipefail

usage() {
  cat <<'EOF'
用法：
  bash install.sh /path/to/obsidian-vault [--no-claude-hooks]

安装内容：
  - 把 vault 路径写入 ~/.lifeforce-vault
  - 安装 .lifeforce/skill、reindex.py 和两个 Claude hook
  - 链接到 ~/.claude/skills、~/.codex/skills、~/.gemini/skills
  - 默认幂等追加 Claude SessionStart/Stop hook
EOF
}

if [ "$#" -lt 1 ]; then
  usage >&2
  exit 2
fi

VAULT_ARG="$1"
shift
CLAUDE_HOOKS=1
while [ "$#" -gt 0 ]; do
  case "$1" in
    --no-claude-hooks)
      CLAUDE_HOOKS=0
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "未知参数：$1" >&2
      usage >&2
      exit 2
      ;;
  esac
  shift
done

REPO_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
HOME_DIR="${HOME:?HOME 未设置}"
if [ ! -d "$VAULT_ARG" ]; then
  echo "vault 目录不存在：$VAULT_ARG" >&2
  exit 1
fi
VAULT="$(cd -- "$VAULT_ARG" && pwd -P)"

for required in "$REPO_DIR/skill/SKILL.md" "$REPO_DIR/scripts/reindex.py" "$REPO_DIR/scripts/capture.sh" "$REPO_DIR/scripts/session-start.sh" "$REPO_DIR/scripts/codex-sessions.py"; do
  if [ ! -f "$required" ]; then
    echo "安装包缺少文件：$required" >&2
    exit 1
  fi
done

RUNTIME="$VAULT/.lifeforce"
SKILL_DIR="$RUNTIME/skill"
mkdir -p "$SKILL_DIR" "$VAULT/projects"
cp -R "$REPO_DIR/skill/." "$SKILL_DIR/"
cp "$REPO_DIR/scripts/reindex.py" "$RUNTIME/reindex.py"
cp "$REPO_DIR/scripts/capture.sh" "$RUNTIME/capture.sh"
cp "$REPO_DIR/scripts/session-start.sh" "$RUNTIME/session-start.sh"
cp "$REPO_DIR/scripts/codex-sessions.py" "$RUNTIME/codex-sessions.py"
chmod +x "$RUNTIME/reindex.py" "$RUNTIME/capture.sh" "$RUNTIME/session-start.sh" "$RUNTIME/codex-sessions.py"

ORIGINAL_UMASK="$(umask)"
umask 077
printf '%s\n' "$VAULT" > "$HOME_DIR/.lifeforce-vault"
chmod 600 "$HOME_DIR/.lifeforce-vault"
umask "$ORIGINAL_UMASK"
python3 "$RUNTIME/reindex.py"

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

if [ "$CLAUDE_HOOKS" -eq 1 ]; then
  python3 "$REPO_DIR/scripts/configure_claude_hooks.py" \
    --settings "$HOME_DIR/.claude/settings.json" \
    --session-start "$RUNTIME/session-start.sh" \
    --capture "$RUNTIME/capture.sh"
fi

cat <<EOF

lifeforce 已安装。
vault：$VAULT
显式使用：/lifeforce、/lifeforce find <关键词>、/lifeforce save、/lifeforce daily
EOF
