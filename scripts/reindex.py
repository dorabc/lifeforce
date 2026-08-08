#!/usr/bin/env python3
"""从经验笔记的 frontmatter 重建 MAP.md 和各项目 _index.md。"""

from __future__ import annotations

import re
from collections import defaultdict
from pathlib import Path


VAULT = Path(__file__).resolve().parents[1]
PROJECTS = VAULT / "projects"
MAX_PER_CATEGORY = 12


def parse_frontmatter(text: str) -> dict[str, str]:
    """读取本 skill 所需的标量 frontmatter，不引入 PyYAML。"""
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
        value = field.group(2)
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
            value = value[1:-1]
        result[field.group(1)] = value
    return result


def hit_count(value: str) -> int:
    match = re.search(r"\d+", value or "")
    return int(match.group()) if match else 0


def clean(value: str) -> str:
    """Keep generated Markdown tables and bullets structurally valid."""
    return " ".join(value.replace("|", "\\|").splitlines()).strip()


def relative_link(path: Path, label: str) -> str:
    relative = path.relative_to(VAULT).with_suffix("")
    target = "/".join(relative.parts)
    return f"[[{target}|{clean(label)}]]"


def notes(project: Path) -> list[dict[str, object]]:
    result = []
    for path in sorted(project.rglob("*.md")):
        if path.name.startswith("_"):
            continue
        metadata = parse_frontmatter(path.read_text(encoding="utf-8", errors="ignore"))
        relative = path.relative_to(project)
        result.append(
            {
                "path": path,
                "title": path.stem,
                "relative": relative,
                "category": "/".join(relative.parts[:-1]) or "未分类",
                "summary": metadata.get("summary", ""),
                "updated": metadata.get("updated", ""),
                "hits": hit_count(metadata.get("hits", "")),
            }
        )
    return result


def write_project_index(project: Path) -> list[dict[str, object]]:
    items = notes(project)
    by_category: dict[str, list[dict[str, object]]] = defaultdict(list)
    for item in items:
        by_category[str(item["category"])].append(item)

    output = [
        "---",
        "lifeforce: index",
        f"project: {project.name}",
        f"count: {len(items)}",
        "note: reindex.py 自动生成，勿手改",
        "---",
        "",
        f"# {project.name}",
        "",
        f"共 **{len(items)}** 条经验 · {len(by_category)} 个分类",
        "",
    ]

    for category in sorted(by_category):
        category_items = list(by_category[category])
        # 稳定排序：先按更新时间，再按 hits；最终 hits 和 updated 都降序。
        category_items.sort(key=lambda item: str(item["updated"]), reverse=True)
        category_items.sort(key=lambda item: int(item["hits"]), reverse=True)
        output.append(f"## {category} ({len(category_items)})")
        for item in category_items[:MAX_PER_CATEGORY]:
            summary = clean(str(item["summary"]))
            suffix = f" — {summary}" if summary else ""
            hit = f" `×{item['hits']}`" if item["hits"] else ""
            output.append(f"- {relative_link(item['path'], item['title'])}{suffix}{hit}")
        if len(category_items) > MAX_PER_CATEGORY:
            query_path = f"projects/{project.name}/{category}"
            output.append(
                f"- …另 {len(category_items) - MAX_PER_CATEGORY} 条，"
                f"`rg -i --type md '关键词' '{query_path}'`"
            )
        output.append("")

    (project / "_index.md").write_text("\n".join(output).rstrip() + "\n", encoding="utf-8")
    return items


def main() -> None:
    PROJECTS.mkdir(parents=True, exist_ok=True)
    rows: list[str] = []
    total = 0
    for project in sorted(path for path in PROJECTS.iterdir() if path.is_dir()):
        items = write_project_index(project)
        total += len(items)
        categories = sorted({str(item["category"]) for item in items})
        latest = max(
            (str(item["updated"]) for item in items if item["updated"]),
            default="—",
        )
        rows.append(
            f"| {relative_link(project / '_index.md', project.name)} | {len(items)} | "
            f"{clean(', '.join(categories[:6]) or '—')} | {latest} |"
        )

    map_lines = [
        "---",
        "lifeforce: map",
        "note: reindex.py 自动生成，勿手改",
        "---",
        "",
        "# lifeforce 地图",
        "",
        f"{len(rows)} 个项目 · {total} 条经验",
        "",
        "| 项目 | 条数 | 分类 | 最近更新 |",
        "|---|---:|---|---|",
        *rows,
        "",
        "> 查经验：先读项目 `_index.md`；没命中就 `rg -i --type md '关键词' projects/`。",
        "> 记经验：`/lifeforce save`。",
    ]
    (VAULT / "MAP.md").write_text("\n".join(map_lines) + "\n", encoding="utf-8")
    print(f"reindex: {len(rows)} 个项目，{total} 条经验")


if __name__ == "__main__":
    main()
