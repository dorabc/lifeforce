#!/usr/bin/env python3
"""Build a redacted, source-linked OpenWiki index from Codex history.

This is intentionally an offline indexer. It never calls a model, network,
connector, or transcript export API. It extracts bounded user-request and
final-answer candidates so a later semantic pass can promote only verified,
reusable knowledge into canonical pages.
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path


GENERATED_MARKER = "<!-- lifeforce-generated: codex-history-wiki -->"

SENSITIVE_MARKERS = (
    "身份证",
    "工号",
    "手机号",
    "电话号码",
    "住址",
    "地址：",
    "客户信息",
    "员工信息",
    "姓名：",
    "cookie",
    "jsessionid",
)

SENSITIVE_ANSWER_MARKERS = (
    "requestid",
    "userid",
    "employeeid",
    "customerid",
    "workcode",
    "申请人",
    "姓名",
    "工号",
    "审批人",
)


def expand_path(value: str | Path) -> Path:
    return Path(value).expanduser()


def text_from_content(content: object) -> str:
    if not isinstance(content, list):
        return ""
    parts: list[str] = []
    for item in content:
        if not isinstance(item, dict):
            continue
        if item.get("type") not in {"input_text", "output_text", "text"}:
            continue
        text = item.get("text")
        if isinstance(text, str):
            parts.append(text)
    return "\n".join(parts).strip()


def redact(text: str) -> str:
    text = text.replace("\r", " ").replace("\n", " ")
    text = re.sub(
        r"<environment_context>.*?</environment_context>",
        " ",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(r"<app-context>.*?</app-context>", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"<recommended_plugins>.*?</recommended_plugins>", " ", text, flags=re.IGNORECASE)
    text = re.sub(
        r"<skills_instructions>.*?</skills_instructions>",
        " ",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(r"<in-app-browser-context.*?</in-app-browser-context>", " ", text)
    text = re.sub(r"<image[^>]*>.*?</image>", " ", text, flags=re.IGNORECASE)
    text = re.sub(
        r"https?://(?:localhost|127\.0\.0\.1|(?:\d{1,3}\.){3}\d{1,3}|[a-z0-9.-]+\.dyrs\.com\.cn)[^\s)>\]]*",
        "<internal-url>",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(
        r"\b(?:[a-z0-9-]+\.)+(?:dyrs|dorabc)\.[a-z]{2,}(?:\.[a-z]{2,})?\b",
        "<internal-host>",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(r"(https?://[^\s)>\]]+)\?[^\s)>\]]*", r"\1", text, flags=re.IGNORECASE)
    text = re.sub(r"\b\d{1,3}(?:\.\d{1,3}){3}\b", "<internal-ip>", text)
    text = re.sub(r"(?i)(?:[a-z]:[\\/]|/mnt/[a-z]/|/home/|/root/|/opt/|/srv/|/var/|/tmp/)[^\s`)>\]]+", "<local-path>", text)
    text = re.sub(
        r"(?i)(api[_ -]?key|access[_ -]?token|refresh[_ -]?token|password|secret|cookie|authorization)\s*[:=]\s*[^\s,;]+",
        r"\1=<redacted>",
        text,
    )
    text = re.sub(
        r"(?i)\b[a-z0-9_-]*(?:session|cookie|token|secret|password|passwd|pwd|authorization)[a-z0-9_-]*\s*=\s*[^\s,;'\"]+",
        "<credential>=<redacted>",
        text,
    )
    text = re.sub(
        r"(?i)\b[a-z0-9_-]*(?:login|auth|csrf|cluster)[a-z0-9_-]*\s*=\s*[^\s,;'\"]+",
        "<credential>=<redacted>",
        text,
    )
    text = re.sub(
        r"(?i)\b(?:workflowid|requestid|documentid|userid|employeeid|workcode)\s*=\s*[^&\s,;]+",
        "<param>=<redacted>",
        text,
    )
    text = re.sub(
        r"选择(?:[^，,。；;]{0,16}?下的)?\s*(?:\[[^\]]*\]|\*+)?[\u4e00-\u9fff]{2,4}",
        "选择<person-or-target>",
        text,
    )
    text = re.sub(
        r"(当前用户是否为|用户是|姓名[：:]|工号[：:]|负责人[：:]|申请人[：:])\s*(?:\[[^\]]*\]|\*+)?[\u4e00-\u9fff]{2,4}",
        r"\1<person>",
        text,
    )
    text = re.sub(
        r"(当前用户(?:是否为|是))\s*\[[^\]]*\]\([^)]*\)",
        r"\1<person>",
        text,
    )
    text = re.sub(
        r"(?i)((?<!\w)`?users?`?(?!\w)\s*\d*\s*(?:条|rows?)?\s*[（(])[^）)]{1,200}[）)]",
        r"\1<redacted-account-list>)",
        text,
    )
    text = re.sub(
        r"(用户名|账号|账户)\s*(?:[:：=]\s*|\s+)[^\s,;，。`]+",
        r"\1：<redacted-account>",
        text,
    )
    text = re.sub(
        r"(密码|口令)\s*(?:[:：=]\s*|\s+)[^\s,;，。`]+",
        r"\1：<redacted-password>",
        text,
    )
    text = re.sub(
        r"(?i)\b[a-z][a-z0-9._-]{2,}-ref\.(?:wav|mp3|m4a|flac)\b",
        "<voice-reference>",
        text,
    )
    text = re.sub(
        r"[\u4e00-\u9fff]{2,4}(?=\s*(?:可以|看不到|看见|没问题|有问题|报错|有什么问题|问题))",
        "<person>",
        text,
    )
    text = re.sub(r"(?i)bearer\s+[A-Za-z0-9._~+/=-]+", "Bearer <redacted>", text)
    # Standalone API keys are often pasted without an ``API_KEY=`` label.
    text = re.sub(r"(?i)\b(?:sk|pk|rk)-[A-Za-z0-9][A-Za-z0-9_-]{10,}\b", "<redacted-key>", text)
    text = re.sub(r"\bAIza[A-Za-z0-9_-]{20,}\b", "<redacted-key>", text)
    text = re.sub(r"\bAKIA[0-9A-Z]{16}\b", "<redacted-key>", text)
    text = re.sub(r"\b[A-Fa-f0-9]{32,}\b", "<redacted-id>", text)
    text = re.sub(r"\b\d{8,}\b", "<redacted-number>", text)
    text = re.sub(r"\b[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b", "<email>", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def extract_request(text: str) -> str:
    # Codex Desktop sometimes wraps the actual request after ambient UI data.
    markers = (
        "## My request for Codex:",
        "## My request:",
        "我的请求：",
    )
    for marker in markers:
        if marker in text:
            text = text.split(marker, 1)[1]
            break
    text = re.sub(r"# Files mentioned by the user:.*?(?=## My request|$)", " ", text)
    text = re.sub(r"<turn_aborted>.*?</turn_aborted>", " ", text, flags=re.IGNORECASE)
    return redact(text)


def useful(text: str, *, answer: bool = False) -> bool:
    if len(text) < 20:
        return False
    markers = (
        "<INSTRUCTIONS>",
        "## Skills A skill",
        "You are Codex",
        "# Context from my IDE setup",
        "<system>",
        "<developer>",
        "tool exec call",
        "TRANSCRIPT START",
        "The following is the Codex agent history",
        "[0-9] assistant:",
        "Tip: GPT-",
        "Skill descriptions were shortened",
        "Skipped loading",
        "<recommended_plugins>",
        "<task-notification>",
        "<local-command-caveat>",
        "<local-command-stdout>",
        "<command-name>",
        "[Request interrupted by user]",
    )
    if any(marker in text for marker in markers):
        return False
    if re.search(r"\[\d+\]\s+(?:assistant|tool|user):", text, re.IGNORECASE):
        return False
    markers_to_check = SENSITIVE_MARKERS + (SENSITIVE_ANSWER_MARKERS if answer else ())
    if any(marker.lower() in text.lower() for marker in markers_to_check):
        return False
    if re.search(r"(?i)\bcurl\s+.*(?:-b|--data-raw)", text):
        return False
    if re.fullmatch(r"\s*(ok|好|好的|继续|继续吧|行|可以|嗯|chat|done|yes|no)\s*[.!。！]*", text, re.I):
        return False
    return True


def project_name(cwd: str) -> str:
    normalized = cwd.replace("\\", "/").rstrip("/")
    name = normalized.rsplit("/", 1)[-1] if normalized else "未命名项目"
    return re.sub(r"\s+", " ", name).strip() or "未命名项目"


def slugify(name: str) -> str:
    slug = re.sub(r"[^\w\-]+", "-", name, flags=re.UNICODE).strip("-").lower()
    return slug or "unnamed-project"


def rel_source(path: Path, roots: list[Path]) -> str:
    for root in roots:
        try:
            return f"{root.name}/{path.relative_to(root).as_posix()}"
        except ValueError:
            continue
    return path.name


def parse_rollout(path: Path) -> tuple[list[dict], list[str], list[str]]:
    metas: list[dict] = []
    requests: list[str] = []
    final_answers: list[str] = []
    try:
        stream = path.open(encoding="utf-8", errors="replace")
    except OSError:
        return metas, requests, final_answers
    with stream:
        for line in stream:
            try:
                record = json.loads(line)
            except ValueError:
                continue
            payload = record.get("payload") or {}
            if record.get("type") == "session_meta" and isinstance(payload, dict):
                metas.append(payload)
            if record.get("type") == "response_item" and isinstance(payload, dict):
                if payload.get("type") != "message":
                    continue
                text = text_from_content(payload.get("content"))
                if payload.get("role") == "user":
                    text = extract_request(text)
                    if useful(text) and text not in requests:
                        requests.append(text[:1000])
            if record.get("type") == "event_msg" and isinstance(payload, dict):
                if payload.get("type") != "agent_message" or payload.get("phase") != "final_answer":
                    continue
                text = redact(str(payload.get("message") or ""))
                if useful(text, answer=True) and text not in final_answers:
                    final_answers.append(text[:1400])
    return metas, requests, final_answers


def choose_representative(values: list[str], limit: int) -> list[str]:
    patterns = (
        r"https?://",
        r"报错|错误|失败|修复|实现|配置|部署|安装",
        r"怎么|如何|帮我|分析|教程|发布",
        r"数据库|接口|页面|视频|图片|skill|mcp|docker|nginx|sql|strapi|openai|codex",
    )
    scored: list[tuple[int, int, str]] = []
    for index, value in enumerate(values):
        signal = sum(bool(re.search(pattern, value, re.IGNORECASE)) for pattern in patterns)
        scored.append((signal * 1000 + min(len(value), 900), -index, value))
    chosen: list[str] = []
    fingerprints: set[str] = set()
    for _, _, value in sorted(scored, reverse=True):
        fingerprint = re.sub(r"\W", "", value.lower())[:36]
        if fingerprint in fingerprints:
            continue
        fingerprints.add(fingerprint)
        chosen.append(value)
        if len(chosen) >= limit:
            break
    return chosen


THEMES: dict[str, tuple[str, ...]] = {
    "AI 工作流与知识沉淀": ("skill", "mcp", "codex", "claude", "agent", "openai", "prompt", "经验", "沉淀"),
    "企业系统与数据集成": ("OA", "EHR", "企业微信", "企微", "Strapi", "接口", "同步", "数据库", "SQL", "审批"),
    "前端产品与视觉交互": ("前端", "主题", "页面", "首页", "布局", "交互", "官网", "React", "CSS", "组件"),
    "部署与生产运维": ("Docker", "docker", "Traefik", "nginx", "SSH", "部署", "服务器", "域名", "SSL", "GPU"),
    "内容研究与发布": ("公众号", "教程", "文章", "发布", "X文章", "GitHub", "日报", "视频", "封面"),
    "个人工具与自动化": ("微信", "小程序", "Chrome", "插件", "下载", "自动化", "作业", "健康"),
}


def write_generated(path: Path, content: str, *, force: bool) -> bool:
    if path.exists() and not force:
        try:
            if GENERATED_MARKER not in path.read_text(encoding="utf-8", errors="replace"):
                return False
        except OSError:
            return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8", newline="\n")
    return True


def project_index_link(name: str) -> str:
    return f"projects/{slugify(name)}/_index.md"


def remove_generated_flat_project_pages(wiki: Path) -> list[str]:
    """Remove only this generator's legacy flat project pages."""
    projects_root = wiki / "projects"
    removed: list[str] = []
    if not projects_root.is_dir():
        return removed
    for path in projects_root.glob("*.md"):
        try:
            content = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if GENERATED_MARKER not in content:
            continue
        path.unlink()
        removed.append(path.relative_to(wiki).as_posix())
    return removed


def remove_generated_project_leaf_pages(project_root: Path) -> None:
    """Clear stale generated leaves before rebuilding one project's subtree."""
    for path in (
        project_root / "history" / "demand-signals.md",
        project_root / "history" / "answer-candidates.md",
    ):
        if not path.is_file():
            continue
        try:
            content = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if GENERATED_MARKER in content:
            path.unlink()
    history = project_root / "history"
    try:
        history.rmdir()
    except OSError:
        pass


def canonical_project_pages(project_root: Path) -> list[tuple[str, str]]:
    """Find user-maintained experience leaves without touching their content."""
    pages: list[tuple[str, str]] = []
    if not project_root.is_dir():
        return pages
    for path in sorted(project_root.rglob("*.md")):
        relative_parts = path.relative_to(project_root).parts
        if path.name == "_index.md" or "history" in relative_parts:
            continue
        try:
            content = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if GENERATED_MARKER in content:
            continue
        title = path.stem
        for line in content.splitlines():
            if line.startswith("# "):
                title = line[2:].strip() or title
                break
        pages.append((title, path.relative_to(project_root).as_posix()))
    return pages


def frontmatter(title: str, description: str, tags: list[str]) -> str:
    tag_text = ", ".join(tags)
    timestamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    return (
        "---\n"
        'okf_version: "0.1"\n'
        'type: "Experience Note"\n'
        f"title: {json.dumps(title, ensure_ascii=False)}\n"
        f"description: {json.dumps(description, ensure_ascii=False)}\n"
        f"tags: [{tag_text}]\n"
        f"timestamp: {timestamp}\n"
        'lifeforce_generated: "codex-history-wiki"\n'
        'confidence: "watchlist"\n'
        "---\n\n"
    )


def build(args: argparse.Namespace) -> tuple[int, int, list[str]]:
    roots = [expand_path(args.sessions_root)]
    if args.include_archived:
        roots.append(expand_path(args.archived_root))
    roots = [root for root in roots if root.is_dir()]
    if not roots:
        raise SystemExit("没有找到 Codex session 根目录")

    files: list[Path] = []
    for root in roots:
        files.extend(sorted(root.rglob("*.jsonl")))

    sessions: dict[str, dict] = {}
    projects: dict[str, dict] = defaultdict(
        lambda: {"sessions": set(), "files": set(), "requests": [], "answers": []}
    )
    record_count = 0
    for path in files:
        metas, requests, answers = parse_rollout(path)
        if not metas:
            continue
        record_count += len(metas)
        cwd = Counter(str(meta.get("cwd") or "") for meta in metas).most_common(1)[0][0]
        name = project_name(cwd)
        project = projects[name]
        project["files"].add(rel_source(path, roots))
        project["requests"].extend(item for item in requests if item not in project["requests"])
        project["answers"].extend(item for item in answers if item not in project["answers"])
        for meta in metas:
            session_id = str(meta.get("id") or "")
            if not session_id:
                continue
            sessions[session_id] = {
                "id": session_id,
                "timestamp": str(meta.get("timestamp") or ""),
                "project": name,
                "cwd": cwd,
                "source": str(meta.get("source") or ""),
                "file": rel_source(path, roots),
            }
            project["sessions"].add(session_id)

    if args.dry_run:
        print(f"files={len(files)} sessions={len(sessions)} project={len(projects)} records={record_count}")
        return len(files), len(sessions), []

    wiki = expand_path(args.wiki)
    wiki.mkdir(parents=True, exist_ok=True)
    skipped: list[str] = []
    removed_flat = remove_generated_flat_project_pages(wiki)
    generated_at = datetime.now(timezone.utc).isoformat(timespec="seconds")

    project_rows = sorted(projects.items(), key=lambda item: (-len(item[1]["sessions"]), item[0].lower()))
    links = "\n".join(
        f"- [{name}]({project_index_link(name)}) · {len(data['sessions'])} sessions"
        for name, data in project_rows
    )
    quickstart = frontmatter(
        "AI Session 经验库",
        "以 Codex 为主干、由 lifeforce 融合多个 AI session 的可审计项目经验索引。",
        ["ai-history", "codex", "lifeforce", "history"],
    ) + GENERATED_MARKER + f"\n\n# AI Session 经验库\n\n生成时间：`{generated_at}`。\n\n"
    quickstart += "这是一个历史线索层，不把用户需求或模型回答自动当作事实。需要复用时，先查项目分类下的 canonical experience；没有命中时再打开项目页和 history 候选，读取原 session 做验证。解决后把症状、根因、修复、验证和陷阱合并回唯一的 canonical page，让下一次同类问题直接复用。\n\n"
    quickstart += "## 入口\n\n- [主题地图](themes.md)\n- [Codex 来源与统计](sources/codex-history.md)\n- [全量 session 索引](sources/codex-sessions.md)\n- [待验证事项](open-questions.md)\n\n## 项目\n\n" + links + "\n"
    if not write_generated(wiki / "quickstart.md", quickstart, force=args.force):
        skipped.append("quickstart.md")

    index = frontmatter("AI Session 经验索引", "OpenWiki personal wiki 的跨 AI 项目经验入口。", ["ai-history", "codex", "index"]) + GENERATED_MARKER + "\n\n# AI Session 经验索引\n\n[从 quickstart 开始](quickstart.md)。\n"
    if not write_generated(wiki / "index.md", index, force=args.force):
        skipped.append("index.md")

    theme_text = frontmatter("Codex 跨项目主题地图", "从 Codex 历史请求中统计出的主题线索。", ["codex", "themes", "watchlist"]) + GENERATED_MARKER + "\n\n# 跨项目主题地图\n\n以下统计来自用户请求文本和最终回答元数据，仅用于定位经验；未经过逐条 session 复核的内容标记为 `watchlist`。\n\n"
    for theme, keywords in THEMES.items():
        matched_projects: list[tuple[str, int]] = []
        total = 0
        for name, data in project_rows:
            hits = sum(1 for item in data["requests"] if any(keyword.lower() in item.lower() for keyword in keywords))
            if hits:
                matched_projects.append((name, hits)); total += hits
        theme_text += f"## {theme}\n\n线索数：`{total}`。\n\n"
        if matched_projects:
            theme_text += "相关项目：" + "、".join(f"[{name}]({project_index_link(name)})（{hits}）" for name, hits in matched_projects[:8]) + "。\n\n"
        theme_text += "复用规则：先验证环境、版本和权限；不要直接把历史回答当作当前生产指令。\n\n"
    if not write_generated(wiki / "themes.md", theme_text, force=args.force):
        skipped.append("themes.md")

    source_text = frontmatter("Codex 历史来源", "Codex session 的离线扫描统计与隐私边界。", ["codex", "source", "provenance"]) + GENERATED_MARKER + f"\n\n# Codex 历史来源\n\n"
    source_text += f"- 扫描文件：`{len(files)}`\n- 识别 session：`{len(sessions)}`\n- 项目数：`{len(projects)}`\n- 扫描时间：`{generated_at}`\n- 来源：`~/.codex/sessions`" + ("、`~/.codex/archived_sessions`" if args.include_archived else "") + "\n\n"
    source_text += "## 隐私边界\n\n只保存有限长度的需求线索、最终回答候选和 session 元数据；已对明显的 key、token、密码、cookie、邮箱和长 ID 做脱敏。完整 transcript 保留在 Codex 原目录，不复制到 OpenWiki。\n\n"
    source_text += "## 可信度\n\n本批页面是 `watchlist`。项目页中的需求和回答候选是检索入口，不等于已验证结论；确认后应把结论提升到单独的 canonical experience page。\n"
    if not write_generated(wiki / "sources" / "codex-history.md", source_text, force=args.force):
        skipped.append("sources/codex-history.md")

    session_text = frontmatter("Codex Session 全量索引", "Codex session 元数据索引，不含 transcript 正文。", ["codex", "sessions", "provenance"]) + GENERATED_MARKER + "\n\n# Codex Session 全量索引\n\n| 时间 | 项目 | session | 来源文件 |\n|---|---|---|---|\n"
    for item in sorted(sessions.values(), key=lambda row: (row["timestamp"], row["id"])):
        timestamp = item["timestamp"].replace("|", " ")
        session_text += f"| {timestamp} | [{item['project']}](../{project_index_link(item['project'])}) | `{item['id']}` | `{item['file']}` |\n"
    if not write_generated(wiki / "sources" / "codex-sessions.md", session_text, force=args.force):
        skipped.append("sources/codex-sessions.md")

    for name, data in project_rows:
        title = f"AI 经验入口 · {name}"
        project_root = wiki / "projects" / slugify(name)
        remove_generated_project_leaf_pages(project_root)

        page = frontmatter(title, f"{name} 项目的跨 AI 经验与历史入口，Codex 为主干来源。", ["ai-history", "codex", "project", "watchlist"]) + GENERATED_MARKER + f"\n\n# {title}\n\n"
        page += f"- session：`{len(data['sessions'])}`\n- rollout 文件：`{len(data['files'])}`\n\n"
        canonical_pages = canonical_project_pages(project_root)
        page += "## 可复用经验\n\n"
        if canonical_pages:
            for page_title, relative in canonical_pages:
                page += f"- [{page_title}]({relative})\n"
        else:
            page += "- 当前还没有已验证的 canonical experience；解决历史候选对应的问题后，把结论保存到本项目的分类子目录。\n"
        page += "\n## 历史线索\n\n"
        if data["requests"]:
            page += "- [历史需求线索](history/demand-signals.md)\n"
        if data["answers"]:
            page += "- [最终回答候选](history/answer-candidates.md)\n"
        if not data["requests"] and not data["answers"]:
            page += "- 当前没有提取到足够长且可安全保存的历史文本。\n"
        page += "\n## 复用边界\n\n本页是项目级历史入口。涉及生产环境、实时数据、权限、账号、服务器和第三方接口时，必须读取原 session 并重新验证；确认后的非显然结论再保存为单独经验页。\n\n"
        page += "## 来源\n\n"
        for source in sorted(data["files"])[:20]:
            page += f"- `{source}`\n"
        path = project_root / "_index.md"
        if not write_generated(path, page, force=args.force):
            skipped.append(str(path.relative_to(wiki)))

        requests = choose_representative(data["requests"], 12)
        if requests:
            demand_page = frontmatter(
                f"{name} · 历史需求线索",
                f"{name} 项目中从 Codex 历史 session 提取的需求线索。",
                ["codex", "project", "history", "watchlist"],
            ) + GENERATED_MARKER + f"\n\n# {name} · 历史需求线索\n\n"
            demand_page += "以下内容仅用于检索和定位原 session，不是已经验证的需求规格或事实。\n\n"
            for request in requests:
                demand_page += f"- {request}\n"
            demand_page += "\n## 复用边界\n\n使用前请根据来源 session 重新确认时间、范围、版本和权限。\n"
            path = project_root / "history" / "demand-signals.md"
            if not write_generated(path, demand_page, force=args.force):
                skipped.append(str(path.relative_to(wiki)))

        answers = choose_representative(data["answers"], 6)
        if answers:
            answer_page = frontmatter(
                f"{name} · 最终回答候选",
                f"{name} 项目中从 Codex 历史 session 提取的回答候选。",
                ["codex", "project", "history", "watchlist"],
            ) + GENERATED_MARKER + f"\n\n# {name} · 最终回答候选\n\n"
            answer_page += "以下内容是历史回答候选，不能直接视为当前可执行指令。\n\n"
            for answer in answers:
                answer_page += f"> {answer}\n\n"
            answer_page += "## 复用边界\n\n涉及生产环境、实时数据、权限、账号、服务器和第三方接口时，必须读取原 session 并重新验证。\n"
            path = project_root / "history" / "answer-candidates.md"
            if not write_generated(path, answer_page, force=args.force):
                skipped.append(str(path.relative_to(wiki)))

    open_questions = frontmatter("Codex 历史待验证事项", "历史索引完成后仍需语义复核的事项。", ["codex", "questions", "watchlist"]) + GENERATED_MARKER + "\n\n# 待验证事项\n\n- 历史回答候选尚未全部提升为 canonical experience page。\n- 生产环境、账号权限、实时数据库结果和外部服务状态必须重新验证。\n- OpenWiki 的模型 provider 尚未完成初始化；当前页面已按 OpenWiki Markdown/OKF 结构写入，可先本地检索。\n- 在 Windows Codex 中应验证 hooks 是否能通过当前 shell 执行；若不能，改用 WSL 入口或 Windows-compatible command wrapper。\n"
    if not write_generated(wiki / "open-questions.md", open_questions, force=args.force):
        skipped.append("open-questions.md")

    print(f"files={len(files)} sessions={len(sessions)} projects={len(projects)} records={record_count}")
    if removed_flat:
        print("removed_flat=" + ",".join(removed_flat))
    if skipped:
        print("skipped=" + ",".join(skipped))
    return len(files), len(sessions), skipped


def main() -> int:
    parser = argparse.ArgumentParser(description="从 Codex 历史 session 生成脱敏 OpenWiki 索引")
    parser.add_argument("--wiki", default=None, help="OpenWiki wiki 根目录")
    parser.add_argument("--sessions-root", default="~/.codex/sessions")
    parser.add_argument("--archived-root", default="~/.codex/archived_sessions")
    parser.add_argument("--include-archived", action="store_true", help="包含 archived_sessions")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--force", action="store_true", help="覆盖本工具此前生成的页面")
    args = parser.parse_args()
    if args.wiki is None:
        args.wiki = "${OPENWIKI_WIKI_DIR}" if "OPENWIKI_WIKI_DIR" in __import__("os").environ else "~/.openwiki/wiki"
        if args.wiki == "${OPENWIKI_WIKI_DIR}":
            args.wiki = __import__("os").environ["OPENWIKI_WIKI_DIR"]
    build(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
