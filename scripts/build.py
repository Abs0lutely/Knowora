#!/usr/bin/env python3
"""Build the first-stage static knowledge site using only the Python stdlib."""

from __future__ import annotations

import html
import json
import re
import shutil
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
CONTENT_DIR = ROOT / "content"
DIST_DIR = ROOT / "dist"
META_PATTERN = re.compile(
    r'<script\b(?=[^>]*\bid=["\']doc-meta["\'])(?=[^>]*\btype=["\']application/json["\'])[^>]*>(.*?)</script>',
    re.IGNORECASE | re.DOTALL,
)


def read_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit(f"Invalid JSON in {path.relative_to(ROOT)}: {exc}") from exc
    if not isinstance(data, dict):
        raise SystemExit(f"Expected a JSON object in {path.relative_to(ROOT)}")
    return data


def read_document_metadata(path: Path, course_id: str, chapter_ids: set[str]) -> dict[str, Any]:
    relative = path.relative_to(ROOT)
    text = path.read_text(encoding="utf-8")
    match = META_PATTERN.search(text)
    if not match:
        raise SystemExit(f"Missing doc-meta block in {relative}")
    try:
        metadata = json.loads(match.group(1))
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Invalid doc-meta JSON in {relative}: {exc}") from exc
    if not isinstance(metadata, dict):
        raise SystemExit(f"Expected doc-meta to be a JSON object in {relative}")
    if metadata.get("course") != course_id:
        raise SystemExit(f"doc-meta course does not match directory in {relative}")
    if metadata.get("chapter") not in chapter_ids:
        raise SystemExit(f"doc-meta chapter is not listed in course.json in {relative}")
    title = metadata.get("title")
    if not isinstance(title, str) or not title.strip():
        raise SystemExit(f"doc-meta title is missing in {relative}")
    return metadata


def collect_catalog() -> list[dict[str, Any]]:
    catalog: list[dict[str, Any]] = []
    for course_file in sorted(CONTENT_DIR.glob("*/course.json")):
        course_dir = course_file.parent
        course_id = course_dir.name
        course = read_json(course_file)
        chapters = course.get("chapters")
        if not isinstance(chapters, list):
            raise SystemExit(f"Expected chapters list in {course_file.relative_to(ROOT)}")
        chapter_map: dict[str, dict[str, Any]] = {}
        for item in chapters:
            if not isinstance(item, dict) or not isinstance(item.get("id"), str):
                raise SystemExit(f"Invalid chapter entry in {course_file.relative_to(ROOT)}")
            chapter_map[item["id"]] = item

        documents: list[dict[str, str]] = []
        for path in sorted(course_dir.rglob("*.html")):
            metadata = read_document_metadata(path, course_id, set(chapter_map))
            documents.append(
                {
                    "title": metadata["title"],
                    "url": path.relative_to(ROOT).as_posix(),
                    "chapter": metadata["chapter"],
                }
            )

        catalog.append(
            {
                "id": course_id,
                "name": course.get("name", course_id),
                "chapters": chapters,
                "documents": documents,
            }
        )
    if not catalog:
        raise SystemExit("No course.json files found under content/")
    return catalog


def render_homepage(catalog: list[dict[str, Any]]) -> str:
    groups: list[str] = []
    for course in catalog:
        chapter_map = {chapter["id"]: chapter["title"] for chapter in course["chapters"]}
        chapter_sections: list[str] = []
        for chapter in course["chapters"]:
            documents = [doc for doc in course["documents"] if doc["chapter"] == chapter["id"]]
            if not documents:
                continue
            links = "\n".join(
                f'<li><a href="{html.escape(doc["url"], quote=True)}">{html.escape(doc["title"])}</a></li>'
                for doc in documents
            )
            chapter_sections.append(
                f'<section class="chapter"><h3>{html.escape(chapter_map[chapter["id"]])}</h3><ul>{links}</ul></section>'
            )
        if not chapter_sections:
            continue
        groups.append(
            '<section class="course-card">'
            f'<h2>{html.escape(course["name"])}</h2>'
            f'<p class="count">{len(course["documents"])} 篇文档</p>'
            f'{"".join(chapter_sections)}'
            '</section>'
        )

    return """<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="description" content="面向大学生自学的结构力学知识点与互动教程。">
  <title>结构力学自学知识点</title>
  <style>
    :root { color-scheme: light; font-family: system-ui, -apple-system, "Segoe UI", sans-serif; color: #172033; background: #f4f6fb; }
    * { box-sizing: border-box; }
    body { margin: 0; }
    header { padding: 3rem 1.25rem 2.5rem; color: #fff; background: linear-gradient(125deg, #183b72, #286c91); }
    .wrap { width: min(100% - 2rem, 960px); margin-inline: auto; }
    h1 { margin: 0 0 .6rem; font-size: clamp(1.8rem, 5vw, 2.8rem); }
    header p { margin: 0; color: #d9e8f5; line-height: 1.7; }
    main { padding-block: 1.5rem 3rem; }
    .course-card { margin: 1rem 0; padding: 1.25rem clamp(1rem, 4vw, 1.75rem); border: 1px solid #e1e7f0; border-radius: 16px; background: #fff; box-shadow: 0 8px 24px #183b720c; }
    .course-card > h2 { margin: 0; font-size: 1.35rem; }
    .count { margin: .25rem 0 1rem; color: #66738a; font-size: .9rem; }
    .chapter { padding-top: .75rem; border-top: 1px solid #edf0f5; }
    .chapter h3 { margin: .35rem 0; color: #41516d; font-size: 1rem; }
    ul { display: flex; flex-wrap: wrap; gap: .55rem; margin: .65rem 0 0; padding: 0; list-style: none; }
    a { display: inline-block; padding: .55rem .75rem; border-radius: 9px; color: #145b91; background: #eef6fc; text-decoration: none; line-height: 1.45; }
    a:hover, a:focus-visible { color: #0c3f69; background: #dceefa; text-decoration: underline; }
    footer { padding: 1rem; color: #758197; text-align: center; font-size: .85rem; }
    @media (max-width: 520px) { header { padding-block: 2.25rem 1.75rem; } ul { display: grid; grid-template-columns: 1fr; } a { display: block; } }
  </style>
</head>
<body>
  <header><div class="wrap"><h1>结构力学自学知识点</h1><p>按主题整理的讲解与互动练习，打开文档即可开始学习。</p></div></header>
  <main class="wrap">
    """ + "\n    ".join(groups) + """
  </main>
  <footer>知识点持续整理中</footer>
</body>
</html>
"""


def build() -> None:
    if not CONTENT_DIR.is_dir():
        raise SystemExit("Missing content/ directory")
    catalog = collect_catalog()
    if DIST_DIR.exists():
        shutil.rmtree(DIST_DIR)
    shutil.copytree(CONTENT_DIR, DIST_DIR / "content")
    (DIST_DIR / "index.html").write_text(render_homepage(catalog), encoding="utf-8")
    print(f"Built {sum(len(course['documents']) for course in catalog)} documents across {len(catalog)} groups into dist/")


if __name__ == "__main__":
    build()
