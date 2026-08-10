#!/usr/bin/env python3
"""Import sanitized lifeforce Markdown notes into OpenWiki personal mode.

This is a one-way, non-destructive import. Existing OpenWiki pages are left
untouched so a partially completed migration or a hand-edited page is safe.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path


def configured_path(name: str, default: Path) -> Path:
    import os

    value = os.environ.get(name, "").strip()
    return Path(value).expanduser() if value else default


def read_vault_argument(value: str | None) -> Path | None:
    if value:
        return Path(value).expanduser()
    config = Path.home() / ".lifeforce-vault"
    try:
        value = config.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    return Path(value) if value else None


def parse_frontmatter(text: str) -> dict[str, str]:
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


def yaml_string(value: object) -> str:
    return json.dumps(str(value), ensure_ascii=False)


def title_from(metadata: dict[str, str], body: str, fallback: str) -> str:
    title = metadata.get("title", "").strip()
    if title:
        return title
    heading = re.search(r"^#\s+(.+?)\s*$", body, flags=re.MULTILINE)
    return heading.group(1).strip() if heading else fallback


def tags_from(value: str, project: str) -> list[str]:
    values: list[str] = ["lifeforce", f"project:{project}"]
    raw = value.strip()
    if raw.startswith("[") and raw.endswith("]"):
        raw = raw[1:-1]
    for item in raw.split(","):
        item = item.strip().strip("'\"")
        if item and item not in values:
            values.append(item)
    return values


def target_for(root: Path, source: Path, projects: Path) -> Path:
    return root / "projects" / source.relative_to(projects)


def migrate(
    vault: Path,
    wiki: Path,
    project_filter: str | None,
    dry_run: bool,
) -> tuple[int, int]:
    projects = vault / "projects"
    if not projects.is_dir():
        raise SystemExit(f"lifeforce projects 目录不存在：{projects}")

    imported = 0
    skipped = 0
    for source in sorted(projects.rglob("*.md")):
        relative = source.relative_to(projects)
        if not relative.parts or relative.name.startswith("_") or relative.name in {"MAP.md", "index.md"}:
            continue
        project = relative.parts[0]
        if project_filter and project.casefold() != project_filter.casefold():
            continue

        try:
            text = source.read_text(encoding="utf-8", errors="ignore")
        except OSError as error:
            print(f"跳过无法读取的笔记：{source}（{error}）", file=sys.stderr)
            skipped += 1
            continue

        metadata = parse_frontmatter(text)
        target = target_for(wiki, source, projects)
        if target.exists():
            print(f"跳过已有 OpenWiki 页面：{target}")
            skipped += 1
            continue

        body = body_without_frontmatter(text)
        title = title_from(metadata, body, source.stem)
        summary = metadata.get("summary") or f"来自 lifeforce 项目 {project} 的可复用经验。"
        updated = metadata.get("updated") or metadata.get("created") or ""
        timestamp = updated if re.fullmatch(r"\d{4}-\d{2}-\d{2}", updated) else None
        if timestamp:
            timestamp = f"{timestamp}T00:00:00Z"

        fields = [
            "---",
            "type: Experience Note",
            f"title: {yaml_string(title)}",
            f"description: {yaml_string(summary)}",
            f"tags: {json.dumps(tags_from(metadata.get('tags', ''), project), ensure_ascii=False)}",
        ]
        if timestamp:
            fields.append(f"timestamp: {yaml_string(timestamp)}")
        fields.extend(
            [
                f"lifeforce_id: {yaml_string(metadata.get('id') or relative.with_suffix('').as_posix())}",
                f"lifeforce_project: {yaml_string(project)}",
                f"lifeforce_created: {yaml_string(metadata.get('created', ''))}",
                f"lifeforce_updated: {yaml_string(metadata.get('updated', ''))}",
                f"lifeforce_hits: {metadata.get('hits', '0') or '0'}",
                "---",
                "",
                body,
                "",
            ]
        )
        content = "\n".join(fields)
        if dry_run:
            print(f"将导入：{source} -> {target}")
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
            print(f"已导入：{target}")
        imported += 1

    return imported, skipped


def main() -> None:
    parser = argparse.ArgumentParser(description="把 lifeforce 经验安全导入 OpenWiki personal wiki")
    parser.add_argument("--vault", help="lifeforce vault 路径；默认读取 ~/.lifeforce-vault")
    parser.add_argument(
        "--wiki",
        help="OpenWiki wiki 路径；默认读取 OPENWIKI_WIKI_DIR 或 ~/.openwiki/wiki",
    )
    parser.add_argument("--project", help="只导入一个项目")
    parser.add_argument("--dry-run", action="store_true", help="只列出将导入的页面，不写文件")
    args = parser.parse_args()

    vault = read_vault_argument(args.vault)
    if vault is None:
        raise SystemExit("找不到 lifeforce vault；请传入 --vault 或先运行 install.sh。")
    vault = vault.resolve()
    if not vault.is_dir():
        raise SystemExit(f"lifeforce vault 不存在：{vault}")

    wiki_default = Path.home() / ".openwiki" / "wiki"
    wiki = configured_path("OPENWIKI_WIKI_DIR", wiki_default)
    if args.wiki:
        wiki = Path(args.wiki).expanduser()
    wiki = wiki.resolve()
    if not args.dry_run:
        wiki.mkdir(parents=True, exist_ok=True)

    imported, skipped = migrate(vault, wiki, args.project, args.dry_run)
    action = "待导入" if args.dry_run else "已导入"
    print(f"OpenWiki migration: {action} {imported} 条，跳过 {skipped} 条。")


if __name__ == "__main__":
    main()
