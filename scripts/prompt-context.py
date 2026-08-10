#!/usr/bin/env python3
"""Find reusable lifeforce notes for the current user prompt.

This is deliberately a small, local, read-only preflight. It searches only
the current project's saved notes and emits a bounded context block; it never
reads session transcripts and never writes to the vault.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path


STOP_TERMS = {
    "一下",
    "一个",
    "帮我",
    "帮忙",
    "可以",
    "需要",
    "请问",
    "请帮",
    "如何",
    "怎么",
    "现在",
    "然后",
    "直接",
    "结果",
    "信息",
    "查询",
    "分析",
    "历史",
    "任务",
    "匹配",
    "没有",
    "任何",
    "完整",
    "处理",
    "看看",
    "这个",
    "那个",
    "一下子",
}
MAX_NOTES = 3
MAX_NOTE_CHARS = 6000
MAX_CONTEXT_CHARS = 16000


def payload_text(payload: object, preferred: bool = False) -> str:
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
    pieces = []
    for key in preferred_keys:
        if key in payload:
            value = payload_text(payload[key], preferred=True)
            if value.strip():
                pieces.append(value)
    if pieces:
        return "\n".join(pieces)

    # Some hook versions nest the prompt under input/messages/content.
    for key, value in payload.items():
        if key in {"cwd", "working_directory", "session_id", "thread_id", "transcript_path", "agent_transcript_path"}:
            continue
        nested = payload_text(value)
        if nested.strip():
            pieces.append(nested)
    return "\n".join(pieces) if pieces else ""


def cwd_from(payload: dict) -> str:
    return str(payload.get("cwd") or payload.get("working_directory") or Path.cwd())


def project_for(vault: Path, cwd: str) -> str:
    projects = vault / "projects"
    mapping_path = vault / ".lifeforce" / "projects.json"
    if mapping_path.exists():
        try:
            mapping = json.loads(mapping_path.read_text(encoding="utf-8"))
            candidates = []
            for name, fragments in mapping.items():
                if isinstance(fragments, str):
                    fragments = [fragments]
                matches = [str(fragment) for fragment in fragments if str(fragment).lower() in cwd.lower()]
                if matches:
                    candidates.append((max(map(len, matches)), str(name)))
            if candidates:
                return max(candidates)[1]
        except (OSError, ValueError, TypeError):
            pass

    if not projects.is_dir():
        return ""
    lower_cwd = cwd.lower()
    names = [item.name for item in projects.iterdir() if item.is_dir()]
    path_parts = {part.lower() for part in Path(cwd).parts}
    exact = [name for name in names if name.lower() in path_parts]
    if exact:
        return max(exact, key=len)
    contained = [name for name in names if name.lower() in lower_cwd]
    return max(contained, key=len) if contained else ""


def terms_for(prompt: str) -> list[str]:
    terms: set[str] = set()
    for run in re.findall(r"[\u4e00-\u9fff]{2,}", prompt):
        normalized = run.casefold()
        if normalized not in STOP_TERMS:
            terms.add(normalized)
        if len(run) <= 14:
            for size in (2, 3, 4):
                for index in range(0, len(run) - size + 1):
                    fragment = run[index : index + size].casefold()
                    if fragment not in STOP_TERMS:
                        terms.add(fragment)
    for token in re.findall(r"[A-Za-z][A-Za-z0-9_.:-]{1,}", prompt):
        normalized = token.casefold()
        if normalized not in STOP_TERMS:
            terms.add(normalized)
    return sorted(terms, key=lambda item: (-len(item), item))


def frontmatter_summary(text: str) -> str:
    if not text.startswith("---"):
        return ""
    end = text.find("\n---", 3)
    if end < 0:
        return ""
    return text[3:end]


def reusable_text(path: Path, text: str) -> str:
    """Keep reusable sections and omit the audit history from injected context."""
    parts = text.splitlines()
    kept: list[str] = []
    in_history = False
    for line in parts:
        if line.startswith("## "):
            in_history = line.strip() == "## 历史"
        if not in_history:
            kept.append(line)
    result = "\n".join(kept).strip()
    if len(result) > MAX_NOTE_CHARS:
        result = result[:MAX_NOTE_CHARS].rstrip() + "\n…（经验笔记已截断）"
    return result


def score_note(path: Path, text: str, terms: list[str]) -> int:
    title = path.stem.casefold()
    summary = frontmatter_summary(text).casefold()
    body = text.casefold()
    score = 0
    for term in terms:
        if term in title:
            score += 8 if len(term) >= 3 else 5
        elif term in summary:
            score += 5 if len(term) >= 3 else 3
        elif term in body:
            score += 1
    return score


def main() -> None:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, OSError):
        return
    if not isinstance(payload, dict):
        return

    prompt = payload_text(payload).strip()
    if not prompt:
        return
    try:
        backend = (Path.home() / ".lifeforce-backend").read_text(encoding="utf-8").strip()
    except OSError:
        backend = ""
    if backend == "openwiki":
        return
    try:
        vault_value = (Path.home() / ".lifeforce-vault").read_text(encoding="utf-8").strip()
    except OSError:
        return
    vault = Path(vault_value)
    if not vault.is_dir():
        return
    project = project_for(vault, cwd_from(payload))
    if not project:
        return
    project_dir = vault / "projects" / project
    if not project_dir.is_dir():
        return

    terms = terms_for(prompt)
    if not terms:
        return
    candidates = []
    for path in project_dir.rglob("*.md"):
        if path.name.startswith("_"):
            continue
        if path.name == "会话归档总览.md":
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        score = score_note(path, text, terms)
        if score >= 4:
            candidates.append((score, path, text))
    candidates.sort(key=lambda item: (-item[0], str(item[1])))
    if not candidates:
        return

    blocks = [
        "[lifeforce 自动复用候选]",
        f"当前任务命中了 {min(len(candidates), MAX_NOTES)} 条 {project} 项目经验。先把下面结论作为已知基线；实时数据只重新查询变化值，除非验证失败，不要从零重做同一套表分析。若它与用户明确纠正、AGENTS.md 或当前实测冲突，以后者为准。",
    ]
    for score, path, text in candidates[:MAX_NOTES]:
        relative = path.relative_to(vault).as_posix()
        blocks.extend([f"\n--- {relative}（匹配分 {score}）---", reusable_text(path, text)])
    output = "\n".join(blocks).strip()
    if len(output) > MAX_CONTEXT_CHARS:
        output = output[:MAX_CONTEXT_CHARS].rstrip() + "\n…（自动复用候选已截断）"
    print(output)


if __name__ == "__main__":
    main()
