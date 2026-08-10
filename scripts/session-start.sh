#!/usr/bin/env bash
# Claude Code/Codex SessionStart hook：输出 L0 地图、当前项目 L1 索引和积压数量。
set -u

RUNTIME="$(cd -- "$(dirname -- "$0")" && pwd -P)"
BACKEND="$(cat "$HOME/.lifeforce-backend" 2>/dev/null || true)"
if [ "$BACKEND" = "openwiki" ]; then
  V=""
else
  V="$(cat "$HOME/.lifeforce-vault" 2>/dev/null || true)"
fi
PAYLOAD="$(cat 2>/dev/null || true)"
CWD="$(printf '%s' "$PAYLOAD" | python3 -c '
import json
import sys
try:
    print(json.load(sys.stdin).get("cwd", ""))
except Exception:
    print("")
' 2>/dev/null || true)"
[ -n "$CWD" ] || CWD="$(pwd)"

if [ -z "$V" ] || [ ! -d "$V" ]; then
  python3 "$RUNTIME/openwiki-context.py" --session --cwd "$CWD" 2>/dev/null || true
  exit 0
fi

python3 - "$V" "$CWD" <<'PY' 2>/dev/null || exit 0
import json
import sys
from pathlib import Path

vault = Path(sys.argv[1])
cwd = sys.argv[2]
projects = vault / "projects"


def project_for(path: str) -> str:
    mapping_path = vault / ".lifeforce" / "projects.json"
    if mapping_path.exists():
        try:
            mapping = json.loads(mapping_path.read_text(encoding="utf-8"))
            candidates = []
            for name, fragments in mapping.items():
                if isinstance(fragments, str):
                    fragments = [fragments]
                if any(str(fragment).lower() in path.lower() for fragment in fragments):
                    candidates.append((len(name), name))
            if candidates:
                return max(candidates)[1]
        except (OSError, ValueError, TypeError):
            pass

    if not projects.is_dir():
        return ""
    lower_path = path.lower()
    names = [item.name for item in projects.iterdir() if item.is_dir()]
    path_parts = {part.lower() for part in Path(path).parts}
    exact = [name for name in names if name.lower() in path_parts]
    if exact:
        return max(exact, key=len)
    contained = [name for name in names if name.lower() in lower_path]
    return max(contained, key=len) if contained else ""


project = project_for(cwd)
print("[lifeforce] 已加载经验库")
map_file = vault / "MAP.md"
if map_file.exists():
    print(map_file.read_text(encoding="utf-8", errors="ignore").strip())
if project:
    index = projects / project / "_index.md"
    print(f"\n[lifeforce] 当前项目：{project}")
    if index.exists():
        # 索引由 reindex.py 控制大小；hook 再设一道输出上限。
        lines = index.read_text(encoding="utf-8", errors="ignore").splitlines()
        print("\n".join(lines[:200]))
else:
    print(f"\n[lifeforce] 当前 cwd 未匹配项目：{cwd}")

pending = 0
inbox = vault / ".lifeforce" / "inbox.jsonl"
if inbox.exists():
    for line in inbox.read_text(encoding="utf-8", errors="ignore").splitlines():
        try:
            item = json.loads(line)
        except ValueError:
            continue
        if item.get("done") is False and (not project or project.lower() in str(item.get("cwd", "")).lower()):
            pending += 1
if pending:
    print(f"\n[lifeforce] 当前项目有 {pending} 条 session 流水待沉淀；需要时执行 /lifeforce daily。")
PY

python3 "$RUNTIME/openwiki-context.py" --session --cwd "$CWD" 2>/dev/null || true

exit 0
