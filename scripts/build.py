#!/usr/bin/env python3
"""Build the static Knowora site using only the Python standard library."""

from __future__ import annotations

import datetime as dt
import html
import json
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.parse import quote


ROOT = Path(__file__).resolve().parents[1]
CONTENT_DIR = ROOT / "content"
SITE_DIR = ROOT / "site"
ASSETS_DIR = SITE_DIR / "assets"
DIST_DIR = ROOT / "dist"
MAX_DOCUMENT_BYTES = 5 * 1024 * 1024
PLACEHOLDERS = {"待补充", "不适用"}
REPO_URL = "https://github.com/Abs0lutely/Knowora"
META_PATTERN = re.compile(
    r'<script\b(?=[^>]*\bid=["\']doc-meta["\'])(?=[^>]*\btype=["\']application/json["\'])[^>]*>(.*?)</script>',
    re.IGNORECASE | re.DOTALL,
)
URL_PATTERN = re.compile(
    r"https?://[^\s\"'<>)]*|(?<!:)//[a-z0-9.-]+\.[a-z]{2,}(?:/[^\s\"'<>)]*)?",
    re.IGNORECASE,
)
SVG_NAMESPACE = "http://www.w3.org/2000/svg"
DATE_PATTERN = re.compile(r"\d{4}-\d{2}-\d{2}\Z")


@dataclass
class Document:
    id: str
    path: Path
    metadata: dict[str, Any]
    modified: str

    @property
    def title(self) -> str:
        return self.metadata["title"]

    @property
    def course(self) -> str:
        return self.metadata["course"]

    @property
    def chapter(self) -> str:
        return self.metadata["chapter"]


@dataclass
class Course:
    id: str
    data: dict[str, Any]
    documents: list[Document]


def rel_url(from_file: Path, target: Path) -> str:
    """Return a browser-friendly relative URL between output paths."""
    return quote(Path(os.path.relpath(target, from_file.parent)).as_posix(), safe="/.-_~")


def read_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        fail(f"Invalid JSON in {relative(path)}: {exc}")
    if not isinstance(data, dict):
        fail(f"Expected a JSON object in {relative(path)}")
    return data


def relative(path: Path) -> str:
    try:
        return path.relative_to(ROOT).as_posix()
    except ValueError:
        return str(path)


def fail(message: str) -> None:
    raise SystemExit(message)


def require_text(value: Any, field: str, path: Path) -> str:
    if not isinstance(value, str) or not value.strip():
        fail(f"Missing or invalid {field} in {relative(path)}")
    return value.strip()


def validate_date(value: Any, field: str, path: Path) -> str:
    text = require_text(value, field, path)
    if not DATE_PATTERN.fullmatch(text):
        fail(f"{field} must use YYYY-MM-DD in {relative(path)}")
    try:
        dt.date.fromisoformat(text)
    except ValueError:
        fail(f"Invalid {field} date in {relative(path)}: {text}")
    return text


def parse_metadata(path: Path, course_id: str, chapter_ids: set[str]) -> dict[str, Any]:
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        fail(f"Cannot read {relative(path)}: {exc}")
    match = META_PATTERN.search(text)
    if not match:
        fail(f"Missing doc-meta block in {relative(path)}")
    try:
        metadata = json.loads(match.group(1))
    except json.JSONDecodeError as exc:
        fail(f"Invalid doc-meta JSON in {relative(path)}: {exc}")
    if not isinstance(metadata, dict):
        fail(f"Expected doc-meta to be a JSON object in {relative(path)}")

    require_text(metadata.get("title"), "title", path)
    if metadata.get("course") != course_id:
        fail(f"doc-meta course must be {course_id!r} in {relative(path)}")
    chapter = metadata.get("chapter")
    if not isinstance(chapter, str) or chapter not in chapter_ids:
        fail(f"Unknown chapter {chapter!r} in {relative(path)}")
    if path.parent.name != chapter:
        fail(f"Document directory does not match doc-meta chapter {chapter!r} in {relative(path)}")
    tags = metadata.get("tags")
    if not isinstance(tags, list) or any(not isinstance(tag, str) or not tag.strip() for tag in tags):
        fail(f"tags must be an array of non-empty strings in {relative(path)}")
    for field in ("prerequisites", "related"):
        refs = metadata.get(field, [])
        if not isinstance(refs, list) or any(not isinstance(ref, str) or not ref.strip() for ref in refs):
            fail(f"{field} must be an array of document IDs in {relative(path)}")
        metadata[field] = refs
    source = require_text(metadata.get("source"), "source", path)
    if source in PLACEHOLDERS:
        print(f"WARNING: source is still a placeholder in {relative(path)}", file=sys.stderr)
    review = metadata.get("review")
    if (
        not isinstance(review, dict)
        or not isinstance(review.get("status"), str)
        or review["status"] not in {"unreviewed", "reviewed"}
    ):
        fail(f"review.status must be unreviewed or reviewed in {relative(path)}")
    if review["status"] == "reviewed":
        require_text(review.get("by"), "review.by", path)
        validate_date(review.get("date"), "review.date", path)
    metadata["created"] = validate_date(metadata.get("created"), "created", path)
    return metadata


def strip_code_comments(text: str, language: str) -> str:
    """Remove JS/CSS comments without treating comment markers inside strings as comments."""
    result: list[str] = []
    index = 0
    quote: str | None = None
    escaped = False
    while index < len(text):
        char = text[index]
        next_char = text[index + 1] if index + 1 < len(text) else ""
        if quote:
            result.append(char)
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote:
                quote = None
            index += 1
        elif char in {"'", '"', "`"}:
            quote = char
            result.append(char)
            index += 1
        elif char == "/" and next_char == "*":
            end = text.find("*/", index + 2)
            index = len(text) if end == -1 else end + 2
        elif language == "js" and char == "/" and next_char == "/":
            end = text.find("\n", index + 2)
            index = len(text) if end == -1 else end
        else:
            result.append(char)
            index += 1
    return "".join(result)


def check_external_urls(path: Path) -> None:
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        fail(f"Cannot scan {relative(path)}: {exc}")

    def scan(value: str, line_number: int) -> None:
        for match in URL_PATTERN.finditer(value):
            url = match.group(0).rstrip(".,;:")
            if not url.startswith(SVG_NAMESPACE):
                fail(f"External URL in {relative(path)}:{line_number}: {url}")

    class ResourceScanner(HTMLParser):
        resource_attributes = {
            "href",
            "xlink:href",
            "src",
            "srcset",
            "action",
            "formaction",
            "poster",
            "data",
            "cite",
        }

        def __init__(self) -> None:
            super().__init__(convert_charrefs=True)
            self.mode: str | None = None

        def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
            for key, value in attrs:
                if value is None:
                    continue
                line_number = self.getpos()[0]
                if key.lower() in self.resource_attributes:
                    scan(value, line_number)
                elif key.lower() == "style":
                    scan(strip_code_comments(value, "css"), line_number)
            if tag.lower() == "script":
                self.mode = "js"
            elif tag.lower() == "style":
                self.mode = "css"

        def handle_endtag(self, tag: str) -> None:
            if tag.lower() in {"script", "style"}:
                self.mode = None

        def handle_data(self, data: str) -> None:
            if self.mode:
                scan(strip_code_comments(data, self.mode), self.getpos()[0])

    try:
        ResourceScanner().feed(text)
    except (ValueError, AssertionError) as exc:
        fail(f"Cannot parse HTML resources in {relative(path)}: {exc}")


def git_modified_date(path: Path, fallback: str) -> str:
    try:
        result = subprocess.run(
            ["git", "log", "-1", "--format=%cs", "--", relative(path)],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        )
        value = result.stdout.strip()
        return value if DATE_PATTERN.fullmatch(value) else fallback
    except (OSError, subprocess.SubprocessError):
        return fallback


def collect_catalog() -> tuple[list[Course], list[str]]:
    courses: list[Course] = []
    warnings: list[str] = []
    document_paths: dict[str, Path] = {}
    for course_file in sorted(CONTENT_DIR.glob("*/course.json")):
        course_id = course_file.parent.name
        data = read_json(course_file)
        require_text(data.get("name"), "name", course_file)
        textbook = require_text(data.get("textbook"), "textbook", course_file)
        if textbook in PLACEHOLDERS:
            warnings.append(f"textbook is still a placeholder in {relative(course_file)}")
        chapters = data.get("chapters")
        if not isinstance(chapters, list) or not chapters:
            fail(f"chapters must be a non-empty array in {relative(course_file)}")
        chapter_ids: set[str] = set()
        for chapter in chapters:
            if not isinstance(chapter, dict):
                fail(f"Invalid chapter entry in {relative(course_file)}")
            chapter_id = require_text(chapter.get("id"), "chapter.id", course_file)
            require_text(chapter.get("title"), "chapter.title", course_file)
            if chapter_id in chapter_ids:
                fail(f"Duplicate chapter ID {chapter_id!r} in {relative(course_file)}")
            chapter_ids.add(chapter_id)

        documents: list[Document] = []
        for path in sorted(course_file.parent.rglob("*.html")):
            size = path.stat().st_size
            if size > MAX_DOCUMENT_BYTES:
                fail(f"Document exceeds 5 MiB in {relative(path)} ({size} bytes)")
            check_external_urls(path)
            metadata = parse_metadata(path, course_id, chapter_ids)
            doc_id = f"{course_id}/{path.stem}"
            if doc_id in document_paths:
                fail(
                    f"Duplicate document ID {doc_id!r} in {relative(document_paths[doc_id])} "
                    f"and {relative(path)}"
                )
            document_paths[doc_id] = path
            documents.append(Document(doc_id, path, metadata, git_modified_date(path, metadata["created"])))
        courses.append(Course(course_id, data, documents))

    if not courses:
        fail("No course.json files found under content/")
    all_docs = {doc.id: doc for course in courses for doc in course.documents}
    for course in courses:
        for doc in course.documents:
            for field in ("prerequisites", "related"):
                for reference in doc.metadata[field]:
                    if reference not in all_docs:
                        fail(f"Unknown {field} reference {reference!r} in {relative(doc.path)}")
    for warning in warnings:
        print(f"WARNING: {warning}", file=sys.stderr)
    return courses, warnings


def esc(value: Any) -> str:
    return html.escape(str(value), quote=True)


def page_shell(title: str, body: str, page_path: Path, root: Path) -> str:
    css = rel_url(page_path, root / "site/assets/css/site.css")
    return f'''<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="description" content="面向大学生自学的知识点网站 Knowora。">
  <title>{esc(title)} · Knowora</title>
  <link rel="stylesheet" href="{css}">
</head>
<body>
  <header class="site-header"><a class="brand" href="{rel_url(page_path, root / 'index.html')}">Knowora</a><nav aria-label="主导航"><a href="{rel_url(page_path, root / 'index.html')}">首页</a><a href="{rel_url(page_path, root / 'tags/index.html')}">标签</a><a href="{rel_url(page_path, root / 'recent/index.html')}">最近更新</a></nav></header>
  <main class="container">{body}</main>
  <footer class="site-footer">面向大学生自学的知识点网站 · 内容持续整理中</footer>
</body>
</html>'''


def document_link(doc: Document, page: Path, root: Path) -> str:
    wrapper = root / "docs" / doc.course / f"{doc.path.stem}.html"
    return f'<a href="{rel_url(page, wrapper)}">{esc(doc.title)}</a>'


def grouped_course_content(course: Course, page: Path, root: Path) -> str:
    chunks: list[str] = []
    for chapter in course.data["chapters"]:
        docs = [doc for doc in course.documents if doc.chapter == chapter["id"]]
        if docs:
            items = "".join(f"<li>{document_link(doc, page, root)}</li>" for doc in docs)
        else:
            items = '<li class="empty">待补充</li>'
        chunks.append(f'<section class="chapter"><h3>{esc(chapter["title"])}</h3><ul>{items}</ul></section>')
    return "".join(chunks)


def render_homepage(courses: list[Course], page: Path, root: Path) -> str:
    cards = []
    for course in courses:
        href = rel_url(page, root / "courses" / course.id / "index.html")
        cards.append(
            f'<section class="card course-card"><div class="course-heading"><h2><a href="{href}">{esc(course.data["name"])}</a></h2>'
            f'<span>{len(course.documents)} 篇文档</span></div>{grouped_course_content(course, page, root)}</section>'
        )
    search_path = rel_url(page, root / "search/index.html")
    body = '<section class="hero"><p class="eyebrow">大学生自学知识库</p><h1>把复杂知识点，拆开学清楚。</h1><p>按课程和主题整理的自包含讲解与互动练习。</p><form class="search-form" action="' + search_path + '"><label class="visually-hidden" for="home-search">搜索知识点</label><input id="home-search" name="q" type="search" placeholder="搜索知识点或标签"><button>搜索</button></form></section><div class="page-heading"><h2>课程与教程</h2></div>' + "".join(cards)
    return page_shell("首页", body, page, root)


def render_course(course: Course, page: Path, root: Path) -> str:
    body = f'<div class="page-heading"><p class="eyebrow">课程</p><h1>{esc(course.data["name"])}</h1><p>{len(course.documents)} 篇知识点文档</p></div><section class="card">{grouped_course_content(course, page, root)}</section>'
    return page_shell(course.data["name"], body, page, root)


def render_tags(courses: list[Course], page: Path, root: Path) -> str:
    tags: dict[str, list[Document]] = {}
    for course in courses:
        for doc in course.documents:
            for tag in doc.metadata["tags"]:
                tags.setdefault(tag, []).append(doc)
    sections = []
    for tag in sorted(tags):
        links = "".join(f"<li>{document_link(doc, page, root)}</li>" for doc in tags[tag])
        sections.append(f'<section class="tag-group"><h2>{esc(tag)} <span>{len(tags[tag])}</span></h2><ul>{links}</ul></section>')
    body = '<div class="page-heading"><p class="eyebrow">浏览</p><h1>标签</h1></div>' + ("".join(sections) or '<p class="empty">暂无标签</p>')
    return page_shell("标签", body, page, root)


def render_recent(courses: list[Course], page: Path, root: Path) -> str:
    docs = sorted((doc for course in courses for doc in course.documents), key=lambda doc: (doc.modified, doc.title), reverse=True)
    items = "".join(f'<li><time datetime="{esc(doc.modified)}">{esc(doc.modified)}</time>{document_link(doc, page, root)}</li>' for doc in docs)
    body = '<div class="page-heading"><p class="eyebrow">内容动态</p><h1>最近更新</h1></div><section class="card"><ul class="recent-list">' + items + '</ul></section>'
    return page_shell("最近更新", body, page, root)


def render_search_page(page: Path, root: Path) -> str:
    index_url = rel_url(page, root / "search-index.json")
    body = f'''<div class="page-heading"><p class="eyebrow">全文目录</p><h1>搜索知识点</h1><p>按标题、课程、章节和标签查找。</p></div>
<section class="card"><label for="search-input">关键词</label><input id="search-input" class="search-input" type="search" autocomplete="off" placeholder="输入关键词"><p id="search-count" aria-live="polite"></p><ul id="search-results" class="search-results"></ul></section>
<script>window.KNOWORA_SEARCH_INDEX = "{index_url}";</script><script src="{rel_url(page, root / 'site/assets/js/search.js')}"></script>'''
    return page_shell("搜索", body, page, root)


def render_document(doc: Document, course: Course, all_docs: dict[str, Document], page: Path, root: Path) -> str:
    content_path = root / doc.path.relative_to(ROOT)
    iframe_src = rel_url(page, content_path)
    course_page = root / "courses" / course.id / "index.html"
    chapter_title = next(ch["title"] for ch in course.data["chapters"] if ch["id"] == doc.chapter)
    refs: list[str] = []
    for field, label in (("prerequisites", "前置知识"), ("related", "相关知识点")):
        docs = [all_docs[ref] for ref in doc.metadata[field]]
        if docs:
            links = "、".join(document_link(item, page, root) for item in docs)
            refs.append(f'<section class="meta-section"><h2>{label}</h2><p>{links}</p></section>')
    course_docs = course.documents
    position = course_docs.index(doc)
    pager: list[str] = []
    if position:
        pager.append(f'<a rel="prev" href="{rel_url(page, root / "docs" / course.id / (course_docs[position - 1].path.stem + ".html"))}">← {esc(course_docs[position - 1].title)}</a>')
    if position + 1 < len(course_docs):
        pager.append(f'<a rel="next" href="{rel_url(page, root / "docs" / course.id / (course_docs[position + 1].path.stem + ".html"))}">{esc(course_docs[position + 1].title)} →</a>')
    status = doc.metadata["review"]["status"]
    status_text = "已校对" if status == "reviewed" else "尚未校对"
    issue_title = quote(f"{doc.title}：内容反馈", safe="")
    issue_body = quote(f"文档：{REPO_URL}/blob/main/{relative(doc.path)}\n\n反馈内容：\n", safe="")
    issue_url = f"{REPO_URL}/issues/new?title={issue_title}&body={issue_body}"
    body = f'''<div class="breadcrumbs"><a href="{rel_url(page, root / 'index.html')}">首页</a> / <a href="{rel_url(page, course_page)}">{esc(course.data['name'])}</a> / {esc(chapter_title)}</div>
<div class="doc-heading"><div><p class="eyebrow">{esc(course.data['name'])} · {esc(chapter_title)}</p><h1>{esc(doc.title)}</h1></div><span class="review-status">{status_text}</span></div>
<iframe class="document-frame" title="{esc(doc.title)}" src="{iframe_src}" loading="eager"></iframe>
<script>const frame=document.querySelector('.document-frame');frame.addEventListener('load',()=>{{try{{const resize=()=>{{frame.style.height=Math.max(640,frame.contentDocument.documentElement.scrollHeight+16)+'px';}};resize();new ResizeObserver(resize).observe(frame.contentDocument.documentElement);}}catch(e){{}}}});</script>
<section class="doc-details">{''.join(refs)}<p class="source-note">依据：{esc(doc.metadata['source'])}</p><a class="report-link" href="{issue_url}" target="_blank" rel="noopener">报错或反馈</a></section>
<nav class="doc-pager" aria-label="上一篇和下一篇">{''.join(pager)}</nav>'''
    return page_shell(doc.title, body, page, root)


def build(project_root: Path = ROOT, output_dir: Path = DIST_DIR) -> None:
    global ROOT, CONTENT_DIR, SITE_DIR, ASSETS_DIR
    ROOT = project_root.resolve()
    CONTENT_DIR = ROOT / "content"
    SITE_DIR = ROOT / "site"
    ASSETS_DIR = SITE_DIR / "assets"
    if not CONTENT_DIR.is_dir():
        fail("Missing content/ directory")
    courses, _warnings = collect_catalog()
    all_docs = {doc.id: doc for course in courses for doc in course.documents}
    if output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True)
    shutil.copytree(CONTENT_DIR, output_dir / "content")
    if ASSETS_DIR.is_dir():
        shutil.copytree(ASSETS_DIR, output_dir / "site/assets")

    outputs: dict[Path, str] = {}
    home = output_dir / "index.html"
    outputs[home] = render_homepage(courses, home, output_dir)
    for course in courses:
        course_page = output_dir / "courses" / course.id / "index.html"
        outputs[course_page] = render_course(course, course_page, output_dir)
        for doc in course.documents:
            wrapper = output_dir / "docs" / course.id / f"{doc.path.stem}.html"
            outputs[wrapper] = render_document(doc, course, all_docs, wrapper, output_dir)
    tag_page = output_dir / "tags/index.html"
    outputs[tag_page] = render_tags(courses, tag_page, output_dir)
    recent_page = output_dir / "recent/index.html"
    outputs[recent_page] = render_recent(courses, recent_page, output_dir)
    search_page = output_dir / "search/index.html"
    outputs[search_page] = render_search_page(search_page, output_dir)
    for path, content in outputs.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    index = []
    for course in courses:
        for doc in course.documents:
            chapter = next(ch["title"] for ch in course.data["chapters"] if ch["id"] == doc.chapter)
            index.append({
                "id": doc.id,
                "title": doc.title,
                "course": course.data["name"],
                "chapter": chapter,
                "tags": doc.metadata["tags"],
                "source": doc.metadata["source"],
                "url": f"docs/{doc.course}/{doc.path.stem}.html",
            })
    (output_dir / "search-index.json").write_text(json.dumps(index, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Built {len(all_docs)} documents across {len(courses)} courses into {output_dir}")


if __name__ == "__main__":
    build()
