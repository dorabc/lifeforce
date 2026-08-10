#!/usr/bin/env python3
"""Read-only bridge from OpenWiki's local personal wiki to lifeforce hooks.

The bridge deliberately does not invoke the OpenWiki agent, connectors, or
network calls.  It only searches Markdown already written under
``~/.openwiki/wiki`` and emits a bounded context block for Claude/Codex.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path


STOP_TERMS = {
    "about",
    "after",
    "again",
    "also",
    "帮忙",
    "可以",
    "一个",
    "一下",
    "这个",
    "那个",
    "如何",
    "怎么",
    "需要",
    "请问",
    "现在",
    "然后",
    "直接",
    "结果",
    "信息",
    "查询",
    "分析",
    "历史",
    "任务",
    "完整",
    "处理",
    "看看",
    "the",
    "with",
    "from",
    "that",
    "this",
    "what",
    "when",
    "where",
    "which",
    "your",
}
MAX_NOTES = 4
MAX_NOTE_CHARS = 4200
MAX_CONTEXT_CHARS = 12000
MAX_SESSION_CHARS = 7000


def wiki_root() -> Path:
    configured = os_value("OPENWIKI_WIKI_DIR")
    return Path(configured).expanduser() if configured else Path.home() / ".openwiki" / "wiki"


def os_value(name: str) -> str:
    # Keeping the import local makes the module's read-only behavior obvious
    # and avoids a mutable global configuration object.
    import os

    return os.environ.get(name, "").strip()


def payload_text(payload: object) -> str:
    """Collect likely prompt text from Claude/Codex hook payload variants."""
    if isinstance(payload, str):
        return payload
    if isinstance(payload, list):
        return "\n".join(payload_text(item) for item in payload)
    if not isinstance(payload, dict):
        return ""

    preferred_keys = (
        "prompt",
        "user_prompt",
        "userPrompt",
        "message",
        "user_message",
        "userMessage",
        "text",
    )
    pieces: list[str] = []
    for key in preferred_keys:
        if key in payload:
            value = payload_text(payload[key])
            if value.strip():
                pieces.append(value)
    if pieces:
        return "\n".join(pieces)

    ignored = {
        "cwd",
        "working_directory",
        "session_id",
        "thread_id",
        "transcript_path",
        "agent_transcript_path",
    }
    for key, value in payload.items():
        if key in ignored:
            continue
        nested = payload_text(value)
        if nested.strip():
            pieces.append(nested)
    return "\n".join(pieces)


def cwd_from(payload: dict[str, object]) -> str:
    return str(payload.get("cwd") or payload.get("working_directory") or Path.cwd())


def project_hint(cwd: str) -> str:
    """Reuse lifeforce's explicit mapping when available, then cwd basename."""
    try:
        backend = (Path.home() / ".lifeforce-backend").read_text(encoding="utf-8").strip()
    except OSError:
        backend = ""
    vault: Path | None = None
    if backend != "openwiki":
        try:
            vault_value = (Path.home() / ".lifeforce-vault").read_text(encoding="utf-8").strip()
            vault = Path(vault_value)
        except OSError:
            pass

    if vault and vault.is_dir():
        mapping_path = vault / ".lifeforce" / "projects.json"
        try:
            mapping = json.loads(mapping_path.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError):
            mapping = {}
        if isinstance(mapping, dict):
            matches: list[tuple[int, str]] = []
            for name, fragments in mapping.items():
                values = [fragments] if isinstance(fragments, str) else fragments
                if not isinstance(values, list):
                    continue
                lengths = [
                    len(str(fragment))
                    for fragment in values
                    if str(fragment).strip() and str(fragment).lower() in cwd.lower()
                ]
                if lengths:
                    matches.append((max(lengths), str(name)))
            if matches:
                return max(matches)[1]

        projects = vault / "projects"
        if projects.is_dir():
            names = [item.name for item in projects.iterdir() if item.is_dir()]
            lower_cwd = cwd.lower()
            parts = {part.lower() for part in Path(cwd).parts}
            exact = [name for name in names if name.lower() in parts]
            if exact:
                return max(exact, key=len)
            contained = [name for name in names if name.lower() in lower_cwd]
            if contained:
                return max(contained, key=len)

    try:
        return Path(cwd).name
    except (TypeError, ValueError):
        return ""


def terms_for(prompt: str) -> list[str]:
    terms: set[str] = set()
    for run in re.findall(r"[\u4e00-\u9fff]{2,}", prompt):
        normalized = run.casefold()
        if normalized not in STOP_TERMS:
            terms.add(normalized)
        if len(run) <= 18:
            for size in (2, 3, 4):
                for index in range(0, len(run) - size + 1):
                    fragment = run[index : index + size].casefold()
                    if fragment not in STOP_TERMS:
                        terms.add(fragment)
    for token in re.findall(r"[A-Za-z][A-Za-z0-9_.:/-]{1,}", prompt):
        normalized = token.casefold()
        if normalized not in STOP_TERMS:
            terms.add(normalized)
    return sorted(terms, key=lambda item: (-len(item), item))


def frontmatter(text: str) -> dict[str, str]:
    text = text.lstrip("\ufeff")
    if not text.startswith("---"):
        return {}
    match = re.search(r"^---\s*$", text[3:], flags=re.MULTILINE)
    if not match:
        return {}
    body = text[3 : 3 + match.start()]
    result: dict[str, str] = {}
    for line in body.splitlines():
        field = re.match(r"^([A-Za-z_][\w-]*):\s*(.*?)\s*$", line)
        if not field:
            continue
        value = field.group(2).strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
            value = value[1:-1]
        result[field.group(1)] = value
    return result


def body_without_frontmatter(text: str) -> str:
    text = text.lstrip("\ufeff")
    if not text.startswith("---"):
        return text.strip()
    match = re.search(r"^---\s*$", text[3:], flags=re.MULTILINE)
    if not match:
        return text.strip()
    return text[3 + match.end() :].strip()


def note_status(path: Path, text: str) -> str:
    metadata = frontmatter(text)
    confidence = metadata.get("confidence", "").strip().casefold()
    generated = metadata.get("lifeforce_generated", "").strip().casefold()
    if confidence in {"canonical", "verified", "high"}:
        return "canonical"
    if confidence == "watchlist" or generated:
        return "watchlist"
    return "candidate"


def candidate_files(root: Path) -> list[Path]:
    result: list[Path] = []
    try:
        paths = root.rglob("*.md")
    except OSError:
        return result
    for path in paths:
        try:
            relative = path.relative_to(root)
        except ValueError:
            continue
        if any(part.startswith(".") for part in relative.parts):
            continue
        if path.name in {"_plan.md", "log.md", "index.md"}:
            continue
        result.append(path)
    return result


def score_note(path: Path, text: str, terms: list[str], root: Path, project: str) -> int:
    metadata = frontmatter(text)
    title = (metadata.get("title") or path.stem).casefold()
    description = " ".join(
        [metadata.get("description", ""), metadata.get("summary", ""), metadata.get("tags", "")]
    ).casefold()
    body = body_without_frontmatter(text).casefold()
    relative = path.relative_to(root).as_posix().casefold()
    score = 0
    status = note_status(path, text)
    if status == "canonical":
        score += 40
    elif status == "candidate":
        score += 8
    else:
        score -= 4
    if "/history/" in f"/{relative}/":
        score -= 3
    if project and f"projects/{project.casefold()}/" in f"{relative}/":
        score += 14
    for term in terms:
        if term in title:
            score += 8 if len(term) >= 3 else 5
        elif term in description:
            score += 5 if len(term) >= 3 else 3
        elif term in relative:
            score += 3
        elif term in body:
            score += 1
    return score


def reusable_text(text: str) -> str:
    body = body_without_frontmatter(text)
    if len(body) > MAX_NOTE_CHARS:
        return body[:MAX_NOTE_CHARS].rstrip() + "\n…（OpenWiki 页面已截断）"
    return body


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return ""


def session_context(root: Path, project: str) -> str:
    blocks = ["[lifeforce/OpenWiki] 已加载个人知识图谱（本地只读检索）"]
    quickstart = root / "quickstart.md"
    quickstart_text = read_text(quickstart)
    if quickstart_text:
        excerpt = reusable_text(quickstart_text)
        blocks.extend(["\n--- OpenWiki quickstart ---", excerpt[:2600]])

    candidates: list[tuple[int, Path, str]] = []
    for path in candidate_files(root):
        text = read_text(path)
        if not text:
            continue
        score = score_note(path, text, [project.casefold()] if project else [], root, project)
        if score >= 10:
            candidates.append((score, path, text))
    candidates.sort(key=lambda item: (-item[0], str(item[1])))
    for _, path, text in candidates[:2]:
        status = note_status(path, text)
        blocks.extend([f"\n--- OpenWiki {path.relative_to(root).as_posix()} [{status}] ---", reusable_text(text)])

    output = "\n".join(blocks).strip()
    if len(output) > MAX_SESSION_CHARS:
        output = output[:MAX_SESSION_CHARS].rstrip() + "\n…（OpenWiki 启动上下文已截断）"
    return output


def prompt_context(root: Path, payload: dict[str, object]) -> str:
    prompt = payload_text(payload).strip()
    if not prompt:
        return ""
    project = project_hint(cwd_from(payload))
    terms = terms_for(prompt)
    if project:
        terms = sorted(set(terms + terms_for(project)), key=lambda item: (-len(item), item))
    if not terms:
        return ""

    candidates: list[tuple[int, Path, str]] = []
    for path in candidate_files(root):
        text = read_text(path)
        if not text:
            continue
        score = score_note(path, text, terms, root, project)
        if score >= 4:
            candidates.append((score, path, text))
    candidates.sort(key=lambda item: (-item[0], str(item[1])))
    if not candidates:
        return ""

    blocks = [
        "[lifeforce/OpenWiki 自动复用候选]",
        f"当前任务命中了 {min(len(candidates), MAX_NOTES)} 条 OpenWiki 页面。优先复用标记为 canonical 的已验证经验；watchlist 只用于定位历史 session。以用户明确纠正和当前实测为准，不要把推测当成事实。",
    ]
    for score, path, text in candidates[:MAX_NOTES]:
        status = note_status(path, text)
        blocks.extend(
            [
                f"\n--- {path.relative_to(root).as_posix()} [{status}]（匹配分 {score}）---",
                reusable_text(text),
            ]
        )
    output = "\n".join(blocks).strip()
    if len(output) > MAX_CONTEXT_CHARS:
        output = output[:MAX_CONTEXT_CHARS].rstrip() + "\n…（OpenWiki 自动复用候选已截断）"
    return output


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--session", action="store_true")
    parser.add_argument("--cwd", default="")
    args = parser.parse_args()

    root = wiki_root()
    if not root.is_dir():
        return

    if args.session:
        print(session_context(root, project_hint(args.cwd or str(Path.cwd()))))
        return

    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, OSError):
        return
    if isinstance(payload, dict):
        output = prompt_context(root, payload)
        if output:
            print(output)


if __name__ == "__main__":
    main()
