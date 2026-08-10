#!/usr/bin/env python3
"""Add Claude Code, Gemini CLI, and Antigravity/agy history to OpenWiki.

The importer is offline and read-only with respect to original session stores.
It writes bounded, redacted watchlist pages under each project's ``history``
subtree.  Antigravity's protected conversation blobs are never decoded or
copied; only its user-facing brain artifacts and metadata are indexed.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import re
import subprocess
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path


GENERATED_MARKER = "<!-- lifeforce-generated: ai-history-wiki -->"
BLOCK_START = "<!-- lifeforce-ai-history:start -->"
BLOCK_END = "<!-- lifeforce-ai-history:end -->"
SOURCE_LABELS = {
    "claude-code": "Claude Code",
    "gemini-cli": "Gemini CLI",
    "agy": "Antigravity / agy",
}


def load_base():
    path = Path(__file__).with_name("codex-history-wiki.py")
    spec = importlib.util.spec_from_file_location("lifeforce_codex_history", path)
    if spec is None or spec.loader is None:
        raise SystemExit(f"无法加载基础历史索引器：{path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


BASE = load_base()


def expand_path(value: str | Path) -> Path:
    return Path(value).expanduser()


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def content_text(value: object) -> str:
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, list):
        parts: list[str] = []
        for item in value:
            if isinstance(item, str):
                parts.append(item)
                continue
            if not isinstance(item, dict):
                continue
            kind = str(item.get("type") or "")
            if kind and kind not in {"text", "input_text", "output_text"}:
                continue
            text = item.get("text") or item.get("content")
            if isinstance(text, str):
                parts.append(text)
        return "\n".join(parts).strip()
    if isinstance(value, dict):
        for key in ("content", "text", "parts"):
            if key in value:
                text = content_text(value[key])
                if text:
                    return text
    return ""


def add_candidate(target: list[str], text: str, *, answer: bool = False) -> None:
    cleaned = BASE.redact(text) if answer else BASE.extract_request(text)
    if not BASE.useful(cleaned, answer=answer):
        return
    limit = 1400 if answer else 1000
    cleaned = cleaned[:limit]
    if cleaned not in target:
        target.append(cleaned)


def source_path(path: Path, root: Path, label: str) -> str:
    try:
        return f"{label}/{path.relative_to(root).as_posix()}"
    except ValueError:
        return f"{label}/{path.name}"


def parse_claude_session(path: Path, root: Path) -> dict | None:
    session_ids: list[str] = []
    cwds: list[str] = []
    timestamps: list[str] = []
    requests: list[str] = []
    answers: list[str] = []
    records = 0
    try:
        stream = path.open(encoding="utf-8", errors="replace")
    except OSError:
        return None
    with stream:
        for line in stream:
            try:
                item = json.loads(line)
            except ValueError:
                continue
            if not isinstance(item, dict):
                continue
            records += 1
            if item.get("sessionId"):
                session_ids.append(str(item["sessionId"]))
            if item.get("cwd"):
                cwds.append(str(item["cwd"]))
            if item.get("timestamp"):
                timestamps.append(str(item["timestamp"]))
            kind = item.get("type")
            message = item.get("message")
            text = content_text(message)
            if kind == "user":
                # Claude records subagent completions as synthetic user messages.
                # Their result can be useful evidence, but the wrapper is not a
                # human demand and must not pollute demand-signals.md.
                if re.search(r"<task-notification\b", text, re.IGNORECASE):
                    for result in re.findall(r"<result>(.*?)</result>", text, re.IGNORECASE | re.DOTALL):
                        add_candidate(answers, result, answer=True)
                else:
                    add_candidate(requests, text)
            elif kind == "assistant":
                add_candidate(answers, text, answer=True)
    if not session_ids and not requests and not answers:
        return None
    session_id = Counter(session_ids).most_common(1)[0][0] if session_ids else path.stem
    cwd = Counter(cwds).most_common(1)[0][0] if cwds else ""
    fallback = path.parent.name.rsplit("-", 1)[-1]
    return {
        "source": "claude-code",
        "id": session_id,
        "timestamp": max(timestamps, default=datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat()),
        "project": BASE.project_name(cwd) if cwd else fallback,
        "cwd": cwd,
        "file": source_path(path, root, ".claude/projects"),
        "files": {source_path(path, root, ".claude/projects")},
        "requests": requests,
        "answers": answers,
        "records": records,
    }


def gemini_project_root(path: Path) -> str:
    marker = path.parent.parent / ".project_root"
    value = read_text(marker).strip()
    return value


def parse_gemini_session(path: Path, root: Path) -> dict | None:
    metadata: dict = {}
    messages: list[dict] = []
    records = 0
    if path.suffix.lower() == ".jsonl":
        try:
            stream = path.open(encoding="utf-8", errors="replace")
        except OSError:
            return None
        with stream:
            for line in stream:
                try:
                    item = json.loads(line)
                except ValueError:
                    continue
                if not isinstance(item, dict):
                    continue
                records += 1
                if not item.get("type") and item.get("sessionId"):
                    metadata.update(item)
                elif item.get("type") in {"user", "gemini"}:
                    messages.append(item)
    else:
        try:
            payload = json.loads(read_text(path))
        except ValueError:
            return None
        if not isinstance(payload, dict):
            return None
        metadata = payload
        messages = [item for item in payload.get("messages", []) if isinstance(item, dict)]
        records = len(messages) + 1
    requests: list[str] = []
    answers: list[str] = []
    timestamps: list[str] = []
    for item in messages:
        timestamp = item.get("timestamp")
        if timestamp:
            timestamps.append(str(timestamp))
        text = content_text(item.get("content"))
        if item.get("type") == "user":
            add_candidate(requests, text)
        elif item.get("type") == "gemini":
            add_candidate(answers, text, answer=True)
    session_id = str(metadata.get("sessionId") or path.stem.removeprefix("session-"))
    cwd = gemini_project_root(path)
    # A 64-character directory name is Gemini's project hash, not a project
    # name. Without .project_root there is no reliable mapping, so keep it in
    # one explicit bucket instead of creating misleading hash directories.
    project = BASE.project_name(cwd) if cwd else "gemini-未归类"
    timestamp = str(metadata.get("lastUpdated") or metadata.get("startTime") or max(timestamps, default=""))
    if not timestamp:
        timestamp = datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat()
    relative = source_path(path, root, ".gemini/tmp")
    return {
        "source": "gemini-cli",
        "id": session_id,
        "timestamp": timestamp,
        "project": project,
        "cwd": cwd,
        "file": relative,
        "files": {relative},
        "requests": requests,
        "answers": answers,
        "records": records,
    }


def normalize_project_key(name: str) -> str:
    return re.sub(r"[^0-9a-z\u4e00-\u9fff]+", "", name.casefold())


def project_from_absolute_path(value: str) -> str:
    normalized = value.strip(" \t\r\n'\"`()[]{}.,;:").replace("\\", "/")
    match = re.match(r"^([A-Za-z]):/(.*)$", normalized)
    local: Path | None = None
    if match:
        local = Path(f"/mnt/{match.group(1).lower()}/{match.group(2)}")
    elif normalized.startswith("/mnt/"):
        local = Path(normalized)
    if local is not None:
        candidate = local if local.is_dir() else local.parent
        for parent in (candidate, *candidate.parents):
            if (parent / ".git").exists():
                return parent.name
            if len(parent.parts) <= 3:
                break
    parts = [part for part in normalized.split("/") if part]
    lower = [part.casefold() for part in parts]
    if "codes" in lower:
        rest = parts[lower.index("codes") + 1 :]
        if rest and rest[0].casefold() in {"self", "codeup", "work"} and len(rest) > 1:
            return rest[1]
        if len(rest) > 2 and rest[0].isdigit():
            return rest[2]
        if rest:
            return rest[0]
    return ""


def infer_agy_project(raw_text: str, conversation: Path | None, known_projects: list[str]) -> tuple[str, str]:
    candidates = re.findall(
        r"(?i)(?:read_file|write_file)\(\s*([^\r\n)]+)|\b((?:[A-Za-z]:[\\/]|/mnt/[a-z]/)[^\s`\"'<>|)]+)",
        raw_text,
    )
    flattened = [left or right for left, right in candidates]
    if conversation and conversation.suffix.lower() == ".db":
        try:
            binary_text = conversation.read_bytes().decode("utf-8", errors="ignore")
        except OSError:
            binary_text = ""
        for left, right in re.findall(
            r"(?i)(?:read_file|write_file)\(\s*([^\r\n)]+)|\b((?:[A-Za-z]:[\\/]|/mnt/[a-z]/)[^\s`\"'<>|)]+)",
            binary_text,
        ):
            flattened.append(left or right)
    for value in flattened:
        name = project_from_absolute_path(value)
        if name:
            return name, value
    lower_text = raw_text.casefold()
    for name in sorted(known_projects, key=len, reverse=True):
        if len(name) >= 4 and name.casefold() in lower_text:
            return name, ""
    return "agy-未归类", ""


def parse_agy_sessions(root: Path, known_projects: list[str]) -> list[dict]:
    conversations = root / "conversations"
    brain = root / "brain"
    files_by_id: dict[str, Path] = {}
    if conversations.is_dir():
        for path in conversations.iterdir():
            if path.is_file() and path.suffix.lower() in {".pb", ".db"}:
                current = files_by_id.get(path.stem)
                if current is None or path.suffix.lower() == ".db":
                    files_by_id[path.stem] = path
    ids = set(files_by_id)
    if brain.is_dir():
        ids.update(path.name for path in brain.iterdir() if path.is_dir() and re.fullmatch(r"[0-9a-f-]{36}", path.name))
    result: list[dict] = []
    for session_id in sorted(ids):
        session_brain = brain / session_id
        requests: list[str] = []
        answers: list[str] = []
        raw_parts: list[str] = []
        source_files: set[str] = set()
        timestamps: list[str] = []
        if session_brain.is_dir():
            for path in sorted(session_brain.glob("*.md")):
                if ".resolved" in path.name:
                    continue
                raw = read_text(path)
                if not raw:
                    continue
                raw_parts.append(raw)
                source_files.add(source_path(path, root, ".gemini/antigravity-ide"))
                if path.name.casefold() == "task.md":
                    add_candidate(requests, raw)
                else:
                    add_candidate(answers, raw, answer=True)
                metadata_path = path.with_name(path.name + ".metadata.json")
                if metadata_path.is_file():
                    try:
                        metadata = json.loads(read_text(metadata_path))
                    except ValueError:
                        metadata = {}
                    if isinstance(metadata, dict):
                        summary = metadata.get("summary")
                        if isinstance(summary, str):
                            raw_parts.append(summary)
                            if path.name.casefold() == "task.md":
                                add_candidate(requests, summary)
                            else:
                                add_candidate(answers, summary, answer=True)
                        if metadata.get("updatedAt"):
                            timestamps.append(str(metadata["updatedAt"]))
        conversation = files_by_id.get(session_id)
        if conversation:
            source_files.add(source_path(conversation, root, ".gemini/antigravity-ide"))
            timestamps.append(datetime.fromtimestamp(conversation.stat().st_mtime, timezone.utc).isoformat())
        project, cwd = infer_agy_project("\n".join(raw_parts), conversation, known_projects)
        result.append(
            {
                "source": "agy",
                "id": session_id,
                "timestamp": max(timestamps, default=""),
                "project": project,
                "cwd": cwd,
                "file": sorted(source_files)[0] if source_files else f".gemini/antigravity-ide/brain/{session_id}",
                "files": source_files,
                "requests": requests,
                "answers": answers,
                "records": len(requests) + len(answers),
                "opaque": bool(conversation and conversation.suffix.lower() == ".pb"),
            }
        )
    return result


def prefer_session(current: dict | None, candidate: dict) -> dict:
    if current is None:
        return candidate
    current_score = sum(len(item) for item in current["requests"] + current["answers"])
    candidate_score = sum(len(item) for item in candidate["requests"] + candidate["answers"])
    if candidate_score > current_score:
        candidate["files"].update(current["files"])
        return candidate
    current["files"].update(candidate["files"])
    return current


def collect(args: argparse.Namespace, wiki: Path) -> tuple[list[dict], dict[str, int]]:
    sessions: dict[str, dict] = {}
    scanned = {source: 0 for source in SOURCE_LABELS}
    claude_root = expand_path(args.claude_root)
    if claude_root.is_dir():
        for path in sorted(claude_root.rglob("*.jsonl")):
            if "subagents" in path.parts:
                continue
            scanned["claude-code"] += 1
            item = parse_claude_session(path, claude_root)
            if item:
                key = f"claude-code:{item['id']}"
                sessions[key] = prefer_session(sessions.get(key), item)
    gemini_root = expand_path(args.gemini_root)
    if gemini_root.is_dir():
        for path in sorted(gemini_root.glob("*/chats/session-*.json*")):
            scanned["gemini-cli"] += 1
            item = parse_gemini_session(path, gemini_root)
            if item:
                key = f"gemini-cli:{item['id']}"
                sessions[key] = prefer_session(sessions.get(key), item)
    agy_root = expand_path(args.agy_root)
    known_projects = [path.name for path in (wiki / "projects").iterdir() if path.is_dir()] if (wiki / "projects").is_dir() else []
    if agy_root.is_dir():
        agy_items = parse_agy_sessions(agy_root, known_projects)
        scanned["agy"] = len(agy_items)
        for item in agy_items:
            sessions[f"agy:{item['id']}"] = item
    return list(sessions.values()), scanned


def frontmatter(title: str, description: str, tags: list[str]) -> str:
    timestamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    return (
        "---\n"
        'okf_version: "0.1"\n'
        'type: "Experience Note"\n'
        f"title: {json.dumps(title, ensure_ascii=False)}\n"
        f"description: {json.dumps(description, ensure_ascii=False)}\n"
        f"tags: [{', '.join(tags)}]\n"
        f"timestamp: {timestamp}\n"
        'lifeforce_generated: "ai-history-wiki"\n'
        'confidence: "watchlist"\n'
        "---\n\n"
    )


def write_owned(path: Path, content: str, *, force: bool) -> bool:
    if path.exists():
        existing = read_text(path)
        if GENERATED_MARKER not in existing:
            return False
        if not force:
            return True
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8", newline="\n")
    return True


def upsert_block(path: Path, block: str, *, before: str | None = None) -> bool:
    text = read_text(path)
    if not text:
        return False
    wrapped = f"{BLOCK_START}\n{block.rstrip()}\n{BLOCK_END}"
    pattern = re.compile(re.escape(BLOCK_START) + r".*?" + re.escape(BLOCK_END), re.DOTALL)
    if pattern.search(text):
        updated = pattern.sub(wrapped, text)
    elif before and before in text:
        updated = text.replace(before, wrapped + "\n\n" + before, 1)
    else:
        updated = text.rstrip() + "\n\n" + wrapped + "\n"
    path.write_text(updated, encoding="utf-8", newline="\n")
    return True


def remove_stale_source_pages(project_root: Path) -> None:
    for source in SOURCE_LABELS:
        source_root = project_root / "history" / source
        if not source_root.is_dir():
            continue
        for path in source_root.rglob("*.md"):
            if GENERATED_MARKER in read_text(path):
                path.unlink()
        for directory in sorted((path for path in source_root.rglob("*") if path.is_dir()), reverse=True):
            try:
                directory.rmdir()
            except OSError:
                pass
        try:
            source_root.rmdir()
        except OSError:
            pass


def remove_stale_project_entry(project_root: Path) -> None:
    """Remove only pages/blocks owned by this importer from a stale project."""
    remove_stale_source_pages(project_root)
    index = project_root / "_index.md"
    if index.is_file():
        text = read_text(index)
        if GENERATED_MARKER in text:
            index.unlink()
        elif BLOCK_START in text:
            pattern = re.compile(
                re.escape(BLOCK_START) + r".*?" + re.escape(BLOCK_END) + r"\s*",
                re.DOTALL,
            )
            index.write_text(pattern.sub("", text), encoding="utf-8", newline="\n")
    for directory in sorted((path for path in project_root.rglob("*") if path.is_dir()), reverse=True):
        try:
            directory.rmdir()
        except OSError:
            pass
    try:
        project_root.rmdir()
    except OSError:
        pass


def codex_project_line(project_root: Path) -> str | None:
    """Build the Codex part of the unified per-project history block."""
    index_text = read_text(project_root / "_index.md")
    match = re.search(r"^- session：`(\d+)`", index_text, re.MULTILINE)
    if not match:
        return None
    links: list[str] = []
    if (project_root / "history" / "demand-signals.md").is_file():
        links.append("[需求线索](history/demand-signals.md)")
    if (project_root / "history" / "answer-candidates.md").is_file():
        links.append("[回答候选](history/answer-candidates.md)")
    details = "、".join(links) if links else "仅 session 元数据"
    return f"- **Codex（主干）**：`{match.group(1)}` sessions · {details}"


def codex_session_count(wiki: Path) -> int:
    text = read_text(wiki / "sources" / "codex-history.md")
    match = re.search(r"^- 识别 session：`(\d+)`", text, re.MULTILINE)
    return int(match.group(1)) if match else 0


def rebuild_unified_project_navigation(wiki: Path, projects: dict[str, dict[str, dict]]) -> None:
    """Make quickstart list the union of Codex and supplementary-AI projects."""
    root = wiki / "projects"
    quickstart = wiki / "quickstart.md"
    text = read_text(quickstart)
    if not root.is_dir() or not text:
        return
    other_counts = {
        BASE.slugify(name): sum(len(data["sessions"]) for data in sources.values())
        for name, sources in projects.items()
    }
    rows: list[tuple[int, str, str, int, int]] = []
    for project_root in root.iterdir():
        if not project_root.is_dir() or not (project_root / "_index.md").is_file():
            continue
        index_text = read_text(project_root / "_index.md")
        title_match = re.search(r"^# AI 经验入口 · (.+)$", index_text, re.MULTILINE)
        name = title_match.group(1).strip() if title_match else project_root.name
        codex_match = re.search(r"^- session：`(\d+)`", index_text, re.MULTILINE)
        codex_count = int(codex_match.group(1)) if codex_match else 0
        other_count = other_counts.get(project_root.name, 0)
        rows.append((codex_count + other_count, name, project_root.name, codex_count, other_count))
    rows.sort(key=lambda row: (-row[0], row[1].casefold()))
    lines: list[str] = []
    for total, name, slug, codex_count, other_count in rows:
        parts: list[str] = []
        if codex_count:
            parts.append(f"Codex {codex_count}")
        if other_count:
            parts.append(f"其他 AI {other_count}")
        detail = " + ".join(parts) if parts else f"{total} sessions"
        lines.append(f"- [{name}](projects/{slug}/_index.md) · {detail}")
    section = "## 项目\n\n" + "\n".join(lines) + "\n"
    updated = re.sub(r"(?ms)^## 项目\n.*$", section, text)
    quickstart.write_text(updated, encoding="utf-8", newline="\n")


def aggregate_projects(sessions: list[dict], wiki: Path) -> dict[str, dict[str, dict]]:
    aliases: dict[str, str] = {}
    projects_root = wiki / "projects"
    if projects_root.is_dir():
        for path in projects_root.iterdir():
            if path.is_dir():
                aliases[normalize_project_key(path.name)] = path.name
    projects: dict[str, dict[str, dict]] = defaultdict(
        lambda: defaultdict(lambda: {"sessions": set(), "files": set(), "requests": [], "answers": []})
    )
    for item in sessions:
        raw_name = str(item.get("project") or "未命名项目")
        key = normalize_project_key(raw_name)
        name = aliases.setdefault(key, raw_name)
        item["project"] = name
        data = projects[name][item["source"]]
        data["sessions"].add(item["id"])
        data["files"].update(item["files"])
        for field in ("requests", "answers"):
            for value in item[field]:
                if value not in data[field]:
                    data[field].append(value)
    return projects


def build(args: argparse.Namespace) -> tuple[int, int, list[str]]:
    wiki = expand_path(args.wiki)
    wiki.mkdir(parents=True, exist_ok=True)
    if not args.skip_codex:
        command = [
            sys.executable,
            str(Path(__file__).with_name("codex-history-wiki.py")),
            "--wiki",
            str(wiki),
            "--sessions-root",
            args.codex_root,
            "--archived-root",
            args.codex_archived_root,
        ]
        if args.include_archived:
            command.append("--include-archived")
        if args.force:
            command.append("--force")
        if args.dry_run:
            command.append("--dry-run")
        subprocess.run(command, check=True)

    sessions, scanned = collect(args, wiki)
    projects = aggregate_projects(sessions, wiki)
    if args.dry_run:
        print(f"sessions={len(sessions)} projects={len(projects)} scanned={json.dumps(scanned, ensure_ascii=False)}")
        return sum(scanned.values()), len(sessions), []

    skipped: list[str] = []
    generated_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    current_project_slugs = {BASE.slugify(name) for name in projects}
    projects_root = wiki / "projects"
    if projects_root.is_dir():
        for existing in projects_root.iterdir():
            if existing.is_dir() and existing.name not in current_project_slugs:
                remove_stale_project_entry(existing)
    for name, sources in sorted(projects.items()):
        project_root = wiki / "projects" / BASE.slugify(name)
        remove_stale_source_pages(project_root)
        links: list[str] = []
        codex_line = codex_project_line(project_root)
        if codex_line:
            links.append(codex_line)
        for source, data in sorted(sources.items()):
            label = SOURCE_LABELS[source]
            requests = BASE.choose_representative(data["requests"], 12)
            answers = BASE.choose_representative(data["answers"], 8)
            source_links: list[str] = []
            if requests:
                page = frontmatter(
                    f"{name} · {label} 历史需求线索",
                    f"{name} 项目从 {label} 历史 session 提取的需求线索。",
                    [source, "project", "history", "watchlist"],
                ) + GENERATED_MARKER + f"\n\n# {name} · {label} 历史需求线索\n\n"
                page += "以下内容仅用于定位原 session，不是已经验证的需求或事实。\n\n"
                page += "\n".join(f"- {value}" for value in requests)
                page += "\n\n## 复用边界\n\n使用前必须复核环境、版本、权限和来源 session。\n"
                path = project_root / "history" / source / "demand-signals.md"
                if write_owned(path, page, force=args.force):
                    source_links.append(f"[需求线索](history/{source}/demand-signals.md)")
                else:
                    skipped.append(path.relative_to(wiki).as_posix())
            if answers:
                page = frontmatter(
                    f"{name} · {label} 回答候选",
                    f"{name} 项目从 {label} 历史 session 提取的回答候选。",
                    [source, "project", "history", "watchlist"],
                ) + GENERATED_MARKER + f"\n\n# {name} · {label} 回答候选\n\n"
                page += "以下内容是历史回答/产物候选，不能直接视为当前可执行指令。\n\n"
                page += "\n\n".join(f"> {value}" for value in answers)
                page += "\n\n## 复用边界\n\n确认后再提升为项目分类目录中的 canonical experience。\n"
                path = project_root / "history" / source / "answer-candidates.md"
                if write_owned(path, page, force=args.force):
                    source_links.append(f"[回答候选](history/{source}/answer-candidates.md)")
                else:
                    skipped.append(path.relative_to(wiki).as_posix())
            details = "、".join(source_links) if source_links else "仅 session 元数据"
            links.append(f"- **{label}**：`{len(data['sessions'])}` sessions · {details}")
        block = "## 全来源历史线索\n\n" + "\n".join(links)
        index = project_root / "_index.md"
        index_text = read_text(index)
        if not index.exists() or GENERATED_MARKER in index_text:
            page = frontmatter(
                f"AI 经验入口 · {name}",
                f"{name} 项目的跨 AI 经验与历史入口。",
                ["ai-history", "project", "watchlist"],
            ) + GENERATED_MARKER + f"\n\n# AI 经验入口 · {name}\n\n"
            page += "## 可复用经验\n\n- 当前还没有已验证的 canonical experience。\n\n"
            page += block + "\n\n## 复用边界\n\n历史页只用于定位原 session，确认后的结论保存到项目分类子目录。\n"
            if not write_owned(index, page, force=True):
                skipped.append(index.relative_to(wiki).as_posix())
        else:
            upsert_block(index, block, before="## 复用边界")

    source_counts = Counter(item["source"] for item in sessions)
    codex_count = codex_session_count(wiki)
    total_count = codex_count + len(sessions)
    source_page = frontmatter(
        "全 AI Session 融合统计",
        "以 Codex 为主干，融合 Claude Code、Gemini CLI 和 Antigravity/agy session。",
        ["ai-history", "source", "provenance"],
    ) + GENERATED_MARKER + "\n\n# 全 AI Session 融合统计\n\n"
    source_page += f"- 扫描时间：`{generated_at}`\n- **合计：`{total_count}` sessions**\n- **Codex 主干：`{codex_count}` sessions（完整保留）**\n- 其他 AI 增量：`{len(sessions)}` sessions，涉及 `{len(projects)}` 个项目\n"
    for source, label in SOURCE_LABELS.items():
        source_page += f"- {label}：扫描 `{scanned[source]}` 个文件/会话容器，识别 `{source_counts[source]}` sessions\n"
    source_page += "\n## 来源位置\n\n- Claude Code：`~/.claude/projects`（排除 subagents）\n- Gemini CLI：`~/.gemini/tmp/*/chats`\n- Antigravity/agy：`~/.gemini/antigravity-ide/conversations` 与 `brain`\n\n"
    source_page += "## 隐私与可信度\n\n只保存脱敏后的有限长度线索和来源元数据。Antigravity 的 `.pb` conversation 多为受保护容器，不解密、不复制；仅索引同 ID 的 user-facing brain 产物。所有生成页均为 `watchlist`，确认后再提升为 canonical experience。\n"
    write_owned(wiki / "sources" / "other-ai-history.md", source_page, force=args.force)

    table = frontmatter(
        "Claude、Gemini 与 agy Session 索引",
        "跨 AI session 元数据索引，不含完整 transcript。",
        ["ai-history", "sessions", "provenance"],
    ) + GENERATED_MARKER + "\n\n# Claude、Gemini 与 agy Session 索引\n\n| AI | 时间 | 项目 | session | 来源文件 |\n|---|---|---|---|---|\n"
    for item in sorted(sessions, key=lambda row: (row["timestamp"], row["source"], row["id"])):
        label = SOURCE_LABELS[item["source"]]
        timestamp = str(item["timestamp"]).replace("|", " ")
        table += f"| {label} | {timestamp} | [{item['project']}](../projects/{BASE.slugify(item['project'])}/_index.md) | `{item['id']}` | `{item['file']}` |\n"
    write_owned(wiki / "sources" / "other-ai-sessions.md", table, force=args.force)

    quickstart_block = (
        "## 全 AI Session 融合\n\n"
        "- [全 AI 融合统计](sources/other-ai-history.md)\n"
        "- [Codex Session 索引](sources/codex-sessions.md)\n"
        "- [Claude、Gemini 与 agy Session 索引](sources/other-ai-sessions.md)\n\n"
        "Codex 是主干，其他 AI 按同一项目补充在 history 子树；实际复用时仍优先打开项目分类下的 canonical experience。"
    )
    upsert_block(wiki / "quickstart.md", quickstart_block, before="## 项目")
    rebuild_unified_project_navigation(wiki, projects)

    print(
        f"other_ai_files={sum(scanned.values())} other_ai_sessions={len(sessions)} "
        f"other_ai_projects={len(projects)} sources={json.dumps(source_counts, ensure_ascii=False)}"
    )
    if skipped:
        print("skipped=" + ",".join(skipped))
    return sum(scanned.values()), len(sessions), skipped


def main() -> int:
    parser = argparse.ArgumentParser(description="把 Claude Code、Gemini CLI、agy 历史加入 OpenWiki")
    parser.add_argument("--wiki", default="~/.openwiki/wiki")
    parser.add_argument("--claude-root", default="~/.claude/projects")
    parser.add_argument("--gemini-root", default="~/.gemini/tmp")
    parser.add_argument("--agy-root", default="~/.gemini/antigravity-ide")
    parser.add_argument("--codex-root", default="~/.codex/sessions")
    parser.add_argument("--codex-archived-root", default="~/.codex/archived_sessions")
    parser.add_argument("--include-archived", action="store_true")
    parser.add_argument("--skip-codex", action="store_true", help="Codex 已是最新时只处理其他 AI")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--force", action="store_true", help="覆盖本工具此前生成的页面")
    args = parser.parse_args()
    build(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
