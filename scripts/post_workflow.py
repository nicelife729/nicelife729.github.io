from __future__ import annotations

import argparse
from datetime import date, datetime, timezone
import hashlib
from html import escape
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import unicodedata
from urllib.parse import unquote, urlsplit

import yaml
from PIL import Image, ImageOps


FRONT_MATTER = re.compile(r"\A---\s*\n(.*?)\n---\s*\n", re.DOTALL)
MARKDOWN_IMAGE = re.compile(
    r"!\[([^\]]*)\]\((?:<([^>]+)>|([^\s)]+))(?:\s+[\"'][^\"']*[\"'])?\)"
)
MARKDOWN_LINK = re.compile(
    r"(?<!!)\[[^\]]+\]\((?:<([^>]+)>|([^\s)]+))(?:\s+[\"'][^\"']*[\"'])?\)"
)
HTML_IMAGE = re.compile(r"<img\b[^>]*>", re.IGNORECASE)
HTML_ANCHOR = re.compile(r"<a\b[^>]*>", re.IGNORECASE)
HTML_ATTRIBUTE = re.compile(
    r"(?P<name>[\w:-]+)\s*=\s*(?:\"(?P<double>[^\"]*)\"|'(?P<single>[^']*)'|(?P<bare>[^\s\"'=<>`]+))",
    re.IGNORECASE,
)
SUPPORTED_IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg"}


def emit(payload: dict[str, object], returncode: int = 0) -> int:
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return returncode


def safe_slug(value: str) -> str:
    slug = value.strip()
    if not slug or slug in {".", ".."} or re.search(r"[/\\\x00]", slug):
        raise ValueError("slug 必须是单个安全的目录名")
    return slug


def slugify_title(title: str) -> str:
    normalized = unicodedata.normalize("NFKC", title).casefold()
    slug = re.sub(r"[^\w]+", "-", normalized, flags=re.UNICODE).strip("-_")
    return safe_slug(slug)


def draft_paths(root: Path, slug_value: str) -> tuple[str, Path, Path]:
    slug = safe_slug(slug_value)
    matches: list[tuple[Path, Path]] = []
    drafts = root / "drafts"
    if drafts.is_dir():
        for article in sorted(drafts.glob("*/article.md")):
            try:
                metadata, _ = parse_article(article)
            except (OSError, ValueError):
                continue
            if metadata.get("slug") == slug:
                matches.append((article.parent, article))
    if not matches:
        raise ValueError(f"找不到 slug 为 {slug} 的草稿")
    if len(matches) > 1:
        locations = ", ".join(
            article.relative_to(root).as_posix() for _, article in matches
        )
        raise ValueError(f"检测到重复草稿 slug {slug}：{locations}")
    draft, article = matches[0]
    return slug, draft, article


def content_fingerprint(draft: Path, article: Path) -> str:
    digest = hashlib.sha256()
    digest.update(article.read_bytes())
    originals = draft / "images" / "original"
    if originals.is_dir():
        for image in sorted(path for path in originals.rglob("*") if path.is_file()):
            digest.update(image.relative_to(originals).as_posix().encode("utf-8"))
            digest.update(image.read_bytes())
    return digest.hexdigest()


def read_state(draft: Path) -> dict[str, object]:
    path = draft / "state.json"
    if not path.is_file():
        return {}
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise ValueError(f"无法解析 {path.name}：{error}") from error
    if not isinstance(state, dict):
        raise ValueError(f"{path.name} 必须是 JSON 对象")
    return state


def write_state(draft: Path, state: dict[str, object]) -> None:
    (draft / "state.json").write_text(
        json.dumps(state, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def category_names(root: Path) -> set[str]:
    path = root / "config" / "blog-categories.yml"
    if not path.is_file():
        raise ValueError(f"找不到博客分类白名单：{path}")
    try:
        config = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as error:
        raise ValueError(f"博客分类配置无法解析：{error}") from error
    if not isinstance(config, dict) or config.get("version") != 1:
        raise ValueError("博客分类配置必须使用 version: 1")
    categories = config.get("categories")
    if not isinstance(categories, list):
        raise ValueError("博客分类配置缺少 categories 列表")
    names = {
        item.get("name").strip()
        for item in categories
        if isinstance(item, dict) and isinstance(item.get("name"), str)
        and item.get("name").strip()
    }
    if len(names) != len(categories):
        raise ValueError("博客分类配置存在空名称或重复名称")
    return names


def parse_article(article: Path) -> tuple[dict[str, object], str]:
    content = article.read_text(encoding="utf-8")
    match = FRONT_MATTER.match(content)
    if not match:
        raise ValueError("文章缺少 YAML front matter")
    try:
        metadata = yaml.safe_load(match.group(1)) or {}
    except yaml.YAMLError as error:
        raise ValueError(f"front matter 无法解析：{error}") from error
    if not isinstance(metadata, dict):
        raise ValueError("front matter 必须是键值结构")
    return metadata, content[match.end() :]


def html_attributes(tag: str) -> dict[str, str]:
    attributes: dict[str, str] = {}
    for match in HTML_ATTRIBUTE.finditer(tag):
        value = match.group("double") or match.group("single") or match.group("bare") or ""
        attributes[match.group("name").lower()] = value
    return attributes


def image_references(body: str) -> list[tuple[str, str, str]]:
    references = [
        (match.group(2) or match.group(3), match.group(1).strip(), "Markdown")
        for match in MARKDOWN_IMAGE.finditer(body)
    ]
    for match in HTML_IMAGE.finditer(body):
        attributes = html_attributes(match.group(0))
        if "src" in attributes:
            references.append((attributes["src"], attributes.get("alt", "").strip(), "HTML"))
    return references


def link_references(body: str) -> list[str]:
    references = [
        match.group(1) or match.group(2) for match in MARKDOWN_LINK.finditer(body)
    ]
    for match in HTML_ANCHOR.finditer(body):
        href = html_attributes(match.group(0)).get("href")
        if href:
            references.append(href)
    return references


def internal_link_exists(root: Path, slug: str, target: str) -> tuple[bool, bool]:
    path = unquote(urlsplit(target).path)
    if not path:
        return True, False
    docs = (root / "docs").resolve()
    if path.startswith("/"):
        candidate = docs / path.lstrip("/")
    else:
        candidate = docs / "blog" / "posts" / slug / path
    candidate = candidate.resolve()
    try:
        candidate.relative_to(docs)
    except ValueError:
        return False, True
    candidates = [candidate]
    if not candidate.suffix:
        candidates.extend(
            [candidate.with_suffix(".md"), candidate / "index.md"]
        )
    return any(item.is_file() for item in candidates), False


def local_image_source(
    draft: Path, article: Path, raw_target: str
) -> tuple[Path | None, str | None, str | None]:
    target = unquote(raw_target)
    parsed = urlsplit(target)
    if parsed.scheme in {"http", "https"} or parsed.netloc:
        return None, "external", None
    if parsed.scheme or target.startswith("/"):
        return None, None, f"图片路径必须位于当前草稿目录：{target}"
    source = (article.parent / parsed.path).resolve()
    try:
        source.relative_to(draft.resolve())
    except ValueError:
        return None, None, f"图片路径越过草稿目录：{target}"
    if not source.is_file():
        return None, None, f"找不到图片：{target}"
    if source.suffix.lower() not in SUPPORTED_IMAGE_SUFFIXES:
        return None, None, f"不支持的图片格式：{target}"
    return source, None, None


def published_image_name(source: Path) -> str:
    if source.suffix.lower() in {".jpg", ".jpeg", ".png"}:
        return f"{source.stem}.webp"
    return source.name


def analyze_draft(
    slug: str, draft: Path, article: Path
) -> tuple[dict[str, object], str, list[str], list[str]]:
    errors: list[str] = []
    advisories: list[str] = []
    try:
        metadata, body = parse_article(article)
    except ValueError as error:
        return {}, article.read_text(encoding="utf-8"), [str(error)], advisories

    if not metadata.get("date"):
        errors.append("front matter 缺少 date")
    if metadata.get("draft") is not True:
        errors.append("本地草稿必须设置 draft: true")
    if metadata.get("comments") is not True:
        errors.append("文章必须设置 comments: true")
    if metadata.get("slug") != slug:
        errors.append(f"front matter 的 slug 必须是 {slug}")
    tags = metadata.get("tags")
    if not isinstance(tags, list) or not tags or not all(str(tag).strip() for tag in tags):
        errors.append("front matter 至少需要一个有效 tag")

    headings = re.findall(r"^#\s+(.+)$", body, flags=re.MULTILINE)
    if len(headings) != 1:
        errors.append("正文必须且只能包含一个一级标题")
    if "<!-- more -->" not in body:
        errors.append("正文缺少摘要分隔符 <!-- more -->")

    output_sources: dict[str, Path] = {}
    for raw_target, alt, syntax in image_references(body):
        target = unquote(raw_target)
        if not alt:
            errors.append(f"{syntax} 图片 {target} 缺少替代文本")
        source, kind, path_error = local_image_source(draft, article, raw_target)
        if kind == "external":
            advisories.append(f"外部图片仅做提示，不下载或事实核验：{target}")
            continue
        if path_error:
            errors.append(path_error)
            continue
        assert source is not None
        suffix = source.suffix.lower()
        if suffix != ".svg":
            try:
                with Image.open(source) as image:
                    image.verify()
            except (OSError, SyntaxError) as error:
                errors.append(f"无法读取图片 {target}：{error}")
        else:
            svg = source.read_text(encoding="utf-8", errors="replace").lower()
            if "<script" in svg or re.search(r"\bon\w+\s*=", svg):
                errors.append(f"SVG 包含脚本或事件处理器：{target}")
        output_name = published_image_name(source)
        previous = output_sources.get(output_name)
        if previous is not None and previous != source:
            errors.append(
                f"图片输出文件名冲突：{previous.relative_to(draft)} 与 "
                f"{source.relative_to(draft)} 都会生成 images/{output_name}"
            )
        output_sources[output_name] = source

    root = draft.parent.parent
    for raw_target in link_references(body):
        target = unquote(raw_target)
        parsed = urlsplit(target)
        if parsed.scheme in {"http", "https", "mailto", "tel"} or parsed.netloc:
            advisories.append(f"外部链接仅做提示，不执行网络核验：{target}")
            continue
        if parsed.scheme:
            errors.append(f"不支持的链接协议：{target}")
            continue
        exists, escaped = internal_link_exists(root, slug, target)
        if escaped:
            errors.append(f"内部链接越过 docs 目录：{target}")
        elif not exists:
            errors.append(f"找不到内部链接目标：{target}")

    paragraphs = [
        paragraph.replace("\n", " ").strip()
        for paragraph in re.split(r"\n\s*\n", body)
        if paragraph.strip() and not paragraph.lstrip().startswith(("#", "!", "<!--"))
    ]
    long_paragraphs = sum(len(paragraph) > 240 for paragraph in paragraphs)
    if long_paragraphs:
        advisories.append(f"有 {long_paragraphs} 个段落超过 240 个字符，建议拆分")
    if "在这里写文章导语。" in body or "在这里开始正文。" in body:
        advisories.append("正文仍包含模板占位文字")
    return metadata, body, errors, advisories


def update_review_checks(draft: Path, errors: list[str], advisories: list[str]) -> None:
    report_path = draft / "review.md"
    if not report_path.is_file():
        return
    lines = ["<!-- publish-checks:start -->"]
    lines.extend(f"- 阻断：{item}" for item in errors)
    lines.extend(f"- 建议：{item}" for item in advisories)
    if not errors and not advisories:
        lines.append("- 已通过确定性发布检查。")
    lines.append("<!-- publish-checks:end -->")
    replacement = "\n".join(lines)
    report = report_path.read_text(encoding="utf-8")
    marker = re.compile(
        r"<!-- publish-checks:start -->.*?<!-- publish-checks:end -->", re.DOTALL
    )
    if marker.search(report):
        report = marker.sub(replacement, report)
    else:
        report = report.rstrip() + "\n\n" + replacement + "\n"
    report_path.write_text(report, encoding="utf-8")


def update_review_images(draft: Path, images: list[dict[str, object]]) -> None:
    report_path = draft / "review.md"
    if not report_path.is_file():
        return
    lines = [
        "<!-- image-report:start -->",
        "",
        "| 原图 | 发布图 | 原始字节 | 发布字节 | 节省 |",
        "| --- | --- | ---: | ---: | ---: |",
    ]
    if images:
        for image in images:
            source_bytes = int(image["source_bytes"])
            output_bytes = int(image["output_bytes"])
            saved = 0 if not source_bytes else round((1 - output_bytes / source_bytes) * 100)
            lines.append(
                f"| {image['source']} | {image['output']} | {source_bytes} | "
                f"{output_bytes} | {saved}% |"
            )
    else:
        lines.append("| 无本地图片 | — | 0 | 0 | 0% |")
    lines.extend(["", "<!-- image-report:end -->"])
    replacement = "\n".join(lines)
    report = report_path.read_text(encoding="utf-8")
    marker = re.compile(
        r"<!-- image-report:start -->.*?<!-- image-report:end -->", re.DOTALL
    )
    if marker.search(report):
        report = marker.sub(replacement, report)
    else:
        report = report.rstrip() + "\n\n" + replacement + "\n"
    report_path.write_text(report, encoding="utf-8")


def new_draft(root: Path, arguments: argparse.Namespace) -> int:
    slug = safe_slug(arguments.slug) if arguments.slug else slugify_title(arguments.title)
    try:
        created = date.fromisoformat(arguments.date)
    except ValueError as error:
        raise ValueError("date 必须使用 YYYY-MM-DD 格式") from error
    drafts = root / "drafts"
    draft = drafts / f"{created.isoformat()}-{slug}"
    article = draft / "article.md"
    existing_directories = []
    if drafts.is_dir():
        dated_name = re.compile(rf"^\d{{4}}-\d{{2}}-\d{{2}}-{re.escape(slug)}$")
        existing_directories = [
            path
            for path in drafts.iterdir()
            if path.is_dir() and (path.name == slug or dated_name.fullmatch(path.name))
        ]
    try:
        draft_paths(root, slug)
    except ValueError as error:
        if not str(error).startswith("找不到 slug 为"):
            raise
    else:
        existing_directories.append(draft)
    if existing_directories:
        return emit({"status": "error", "errors": ["草稿已经存在"]}, 2)
    posts = root / "docs" / "blog" / "posts"
    if (posts / f"{slug}.md").exists() or (posts / slug).exists():
        return emit(
            {"status": "error", "errors": ["该 slug 已被正式文章使用"]}, 2
        )

    tags = arguments.tag or ["随笔"]
    tag_lines = "\n".join(f"  - {tag}" for tag in tags)
    content = (
        "---\n"
        f"date: {created.isoformat()}\n"
        "draft: true\n"
        "comments: true\n"
        f"slug: {slug}\n"
        "tags:\n"
        f"{tag_lines}\n"
        "---\n\n"
        f"# {arguments.title}\n\n"
        "在这里写文章导语。\n\n"
        "<!-- more -->\n\n"
        "在这里开始正文。\n"
    )
    (draft / "images" / "original").mkdir(parents=True)
    article.write_text(content, encoding="utf-8")
    return emit(
        {
            "status": "draft",
            "slug": slug,
            "article": article.relative_to(root).as_posix(),
        }
    )


def pull_logseq(logseq_root: Path) -> None:
    if not (logseq_root / ".git").exists():
        raise ValueError(f"Logseq 路径不是 Git 仓库：{logseq_root}")
    try:
        completed = subprocess.run(
            ["git", "pull", "--ff-only"],
            cwd=logseq_root,
            text=True,
            capture_output=True,
            check=False,
            timeout=60,
        )
    except subprocess.TimeoutExpired as error:
        raise ValueError("Logseq git pull --ff-only 超时") from error
    if completed.returncode:
        detail = (completed.stderr or completed.stdout).strip()
        raise ValueError(f"Logseq git pull --ff-only 失败：{detail}")


def logseq_properties(content: str) -> dict[str, str]:
    properties: dict[str, str] = {}
    pattern = re.compile(r"^[ \t]*(?:-\s+)?([A-Za-z][\w-]*)::\s*(.*?)\s*$")
    for line in content.splitlines():
        match = pattern.match(line)
        if match:
            properties[match.group(1)] = match.group(2)
    return properties


def parse_logseq_created(value: str, source: str | None = None) -> date:
    created = value.strip()
    if created.startswith("[[") and created.endswith("]]"):
        created = created[2:-2].strip()
    try:
        return date.fromisoformat(created)
    except ValueError as error:
        location = f" {source}" if source else ""
        raise ValueError(
            f"Logseq 文章{location} 的 created 必须是 [[YYYY-MM-DD]] 或 YYYY-MM-DD"
        ) from error


def logseq_indent_width(value: str) -> int:
    return len(value.expandtabs(4))


def logseq_section(content: str, heading: str) -> list[str]:
    lines = content.splitlines()
    start: int | None = None
    section_width = 0
    heading_pattern = re.compile(
        rf"^([ \t]*)-\s+##\s+{re.escape(heading)}\s*$", re.IGNORECASE
    )
    for index, line in enumerate(lines):
        match = heading_pattern.match(line)
        if match:
            start = index + 1
            section_width = logseq_indent_width(match.group(1))
            break
    if start is None:
        raise ValueError(f"Logseq 文章缺少 ## {heading} 区块")

    section_lines: list[tuple[int, str]] = []
    block_pattern = re.compile(r"^([ \t]*)-\s?(.*)$")
    for line in lines[start:]:
        match = block_pattern.match(line)
        if match:
            width = logseq_indent_width(match.group(1))
            if width <= section_width:
                break
            section_lines.append((width, match.group(2).rstrip()))
        elif section_lines:
            section_lines.append((section_lines[-1][0], line.strip()))

    nonempty_widths = [width for width, text in section_lines if text.strip()]
    child_width = min(nonempty_widths, default=section_width + 4)
    rendered: list[str] = []
    for width, text in section_lines:
        text = text.strip()
        if not text:
            continue
        if width <= child_width:
            rendered.append(text)
        else:
            depth = max(0, (width - child_width) // 4)
            rendered.append(f"{'  ' * max(0, depth - 1)}- {text}")
    return rendered


def logseq_page_title(page: Path) -> str:
    title = page.stem.replace("___", "/")
    return title.rsplit("/", 1)[-1].strip()


def find_logseq_article(
    logseq_root: Path, slug: str
) -> tuple[Path, dict[str, str], str]:
    matches: list[tuple[Path, dict[str, str], str]] = []
    pages = logseq_root / "pages"
    if not pages.is_dir():
        raise ValueError(f"Logseq 仓库缺少 pages 目录：{logseq_root}")
    for page in sorted(pages.rglob("*.md")):
        content = page.read_text(encoding="utf-8")
        properties = logseq_properties(content)
        if properties.get("class") == "article" and properties.get("slug") == slug:
            matches.append((page, properties, content))
    if not matches:
        raise ValueError(f"Logseq 中找不到 class:: article 且 slug:: {slug} 的文章")
    if len(matches) > 1:
        locations = ", ".join(
            item[0].relative_to(logseq_root).as_posix() for item in matches
        )
        raise ValueError(f"Logseq 中存在重复 slug {slug}：{locations}")
    return matches[0]


def queue_logseq_articles(root: Path, arguments: argparse.Namespace) -> int:
    logseq_root = (
        arguments.logseq_root.resolve()
        if arguments.logseq_root
        else (root.parent.parent / "knowledge-base" / "logseq").resolve()
    )
    pull_logseq(logseq_root)
    pages = logseq_root / "pages"
    if not pages.is_dir():
        raise ValueError(f"Logseq 仓库缺少 pages 目录：{logseq_root}")

    articles: list[dict[str, object]] = []
    for page in sorted(pages.rglob("*.md")):
        properties = logseq_properties(page.read_text(encoding="utf-8"))
        if properties.get("class") != "article":
            continue
        if properties.get("status") != "ready-to-publish":
            continue
        raw_created = properties.get("created", "").strip()
        tags = [
            tag.strip()
            for tag in properties.get("blog-tags", "").split(",")
            if tag.strip()
        ]
        missing = [
            name
            for name, value in (
                ("slug", properties.get("slug", "").strip()),
                ("created", raw_created),
                ("blog-tags", tags),
            )
            if not value
        ]
        if missing:
            source = page.relative_to(logseq_root).as_posix()
            raise ValueError(
                f"Logseq 待发布文章 {source} 缺少必填属性：{', '.join(missing)}"
            )
        source = page.relative_to(logseq_root).as_posix()
        created = parse_logseq_created(raw_created, source).isoformat()
        articles.append(
            {
                "slug": properties.get("slug", "").strip(),
                "created": created,
                "blog_tags": tags,
                "source": source,
            }
        )
    sources_by_slug: dict[str, list[str]] = {}
    for article in articles:
        sources_by_slug.setdefault(str(article["slug"]), []).append(
            str(article["source"])
        )
    duplicates = {
        slug: sources
        for slug, sources in sources_by_slug.items()
        if len(sources) > 1
    }
    if duplicates:
        details = "; ".join(
            f"重复 slug {slug}：{', '.join(sources)}"
            for slug, sources in sorted(duplicates.items())
        )
        raise ValueError(f"Logseq 待发布队列存在{details}")
    articles.sort(key=lambda article: (str(article["created"]), str(article["slug"])))
    return emit({"status": "queue", "articles": articles})


def copy_logseq_images(
    logseq_root: Path,
    page: Path,
    markdown: str,
    destination: Path,
) -> tuple[str, list[str]]:
    replacements: dict[str, str] = {}
    copied: list[str] = []
    output_sources: dict[str, Path] = {}
    assets_root = (logseq_root / "assets").resolve()
    for raw_target, _, _ in image_references(markdown):
        parsed = urlsplit(unquote(raw_target))
        if parsed.scheme in {"http", "https"} or parsed.netloc:
            continue
        if parsed.scheme or raw_target.startswith("/"):
            raise ValueError(f"Logseq 图片必须使用仓库内相对路径：{raw_target}")
        source = (page.parent / parsed.path).resolve()
        try:
            source.relative_to(assets_root)
        except ValueError as error:
            raise ValueError(f"Logseq 图片越过 assets 目录：{raw_target}") from error
        if not source.is_file():
            raise ValueError(f"找不到 Logseq 图片：{raw_target}")
        if source.suffix.lower() not in SUPPORTED_IMAGE_SUFFIXES:
            raise ValueError(f"不支持的 Logseq 图片格式：{raw_target}")
        previous = output_sources.get(source.name)
        if previous is not None and previous != source:
            raise ValueError(f"Logseq 图片文件名冲突：{source.name}")
        if previous == source:
            replacements[raw_target] = f"images/original/{source.name}"
            continue
        output_sources[source.name] = source
        destination.mkdir(parents=True, exist_ok=True)
        target = destination / source.name
        shutil.copy2(source, target)
        replacements[raw_target] = f"images/original/{source.name}"
        copied.append(target.name)

    def rewrite(match: re.Match[str]) -> str:
        raw_target = match.group(2) or match.group(3)
        replacement = replacements.get(raw_target)
        if not replacement:
            return match.group(0)
        return match.group(0).replace(raw_target, replacement, 1)

    return MARKDOWN_IMAGE.sub(rewrite, markdown), copied


def import_logseq_draft(root: Path, arguments: argparse.Namespace) -> int:
    slug = safe_slug(arguments.slug)
    logseq_root = (
        arguments.logseq_root.resolve()
        if arguments.logseq_root
        else (root.parent.parent / "knowledge-base" / "logseq").resolve()
    )
    pull_logseq(logseq_root)
    page, properties, source_content = find_logseq_article(logseq_root, slug)
    tags = [tag.strip() for tag in (arguments.tag or []) if tag.strip()]
    if not tags:
        tags = [
            tag.strip()
            for tag in properties.get("blog-tags", "").split(",")
            if tag.strip()
        ]
    if not tags:
        raise ValueError("Logseq blog-tags 必须至少包含一个公开标签")

    created = parse_logseq_created(properties.get("created", ""))

    title = logseq_page_title(page)
    if not title:
        raise ValueError("无法从 Logseq 页面名取得文章标题")
    summary = logseq_section(source_content, "摘要")
    body = logseq_section(source_content, "正文")
    references = logseq_section(source_content, "ref.")
    if not summary:
        raise ValueError("Logseq 文章摘要不能为空")
    if not body:
        raise ValueError("Logseq 文章正文不能为空")

    draft = root / "drafts" / f"{created.isoformat()}-{slug}"
    source_path = page.relative_to(logseq_root).as_posix()
    existing: tuple[str, Path, Path] | None = None
    try:
        existing = draft_paths(root, slug)
    except ValueError as error:
        if not str(error).startswith("找不到 slug 为"):
            raise
    if draft.exists() and existing is None:
        raise ValueError(f"目标草稿目录已存在但不属于该 slug：{draft.relative_to(root)}")
    if existing is not None:
        _, existing_draft, existing_article = existing
        if existing_draft != draft:
            raise ValueError(
                "Logseq created 与现有草稿目录不一致；拒绝自动移动或覆盖草稿"
            )
        state = read_state(existing_draft)
        imported_fingerprint = state.get("imported_fingerprint")
        if state.get("source") != source_path or not imported_fingerprint:
            raise ValueError("现有草稿没有匹配的 Logseq 导入来源，拒绝覆盖")
        if content_fingerprint(existing_draft, existing_article) != imported_fingerprint:
            raise ValueError("本地生成草稿或原图已被修改；请在 Logseq 修改后再导入")
    posts = root / "docs" / "blog" / "posts"
    if existing is None and (
        (posts / f"{slug}.md").exists() or (posts / slug).exists()
    ):
        return emit(
            {"status": "error", "slug": slug, "errors": ["该 slug 已被正式文章使用"]},
            2,
        )

    tag_lines = "\n".join(f"  - {tag}" for tag in tags)
    sections = [
        f"# {title}",
        "\n\n".join(summary),
        "<!-- more -->",
        "\n\n".join(body),
    ]
    if references:
        sections.extend(["## 参考资料", "\n\n".join(references)])
    article_body = "\n\n".join(sections) + "\n"
    drafts_root = root / "drafts"
    drafts_root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".logseq-import-", dir=drafts_root) as staging_name:
        staging = Path(staging_name)
        originals = staging / "images" / "original"
        originals.mkdir(parents=True)
        article_body, copied = copy_logseq_images(
            logseq_root,
            page,
            article_body,
            originals,
        )
        content = (
            "---\n"
            f"date: {created.isoformat()}\n"
            "draft: true\n"
            "comments: true\n"
            f"slug: {slug}\n"
            "tags:\n"
            f"{tag_lines}\n"
            "---\n\n"
            f"{article_body}"
        )
        staged_article = staging / "article.md"
        staged_article.write_text(content, encoding="utf-8")
        imported_fingerprint = content_fingerprint(staging, staged_article)
        new_state = {
            "slug": slug,
            "source": source_path,
            "source_status": properties.get("status"),
            "imported_at": datetime.now(timezone.utc).isoformat(),
            "imported_fingerprint": imported_fingerprint,
        }
        if existing is None:
            write_state(staging, new_state)
            staging.rename(draft)
        else:
            _, existing_draft, existing_article = existing
            if (
                content_fingerprint(existing_draft, existing_article)
                == imported_fingerprint
            ):
                state = read_state(existing_draft)
                state.update(
                    {
                        "source_status": properties.get("status"),
                        "imported_at": new_state["imported_at"],
                    }
                )
                write_state(existing_draft, state)
                return emit(
                    {
                        "status": "unchanged",
                        "slug": slug,
                        "article": existing_article.relative_to(root).as_posix(),
                        "source": source_path,
                        "images": copied,
                    }
                )
            existing_article.write_bytes(staged_article.read_bytes())
            existing_originals = existing_draft / "images" / "original"
            if existing_originals.exists():
                shutil.rmtree(existing_originals)
            shutil.copytree(originals, existing_originals)
            write_state(existing_draft, new_state)

    article = draft / "article.md"
    return emit(
        {
            "status": "imported",
            "slug": slug,
            "article": article.relative_to(root).as_posix(),
            "source": source_path,
            "images": copied,
        }
    )


def review_draft(root: Path, arguments: argparse.Namespace) -> int:
    slug, draft, article = draft_paths(root, arguments.slug)
    fingerprint = content_fingerprint(draft, article)
    state = read_state(draft)
    report_path = draft / "review.md"

    if arguments.complete:
        if not arguments.verdict:
            return emit(
                {
                    "status": "blocked",
                    "slug": slug,
                    "errors": ["完成审稿时必须使用 --verdict 选择 pass 或 needs-revision"],
                },
                2,
            )
        if arguments.category and arguments.verdict != "pass":
            return emit(
                {
                    "status": "blocked",
                    "slug": slug,
                    "errors": ["只有 pass 审稿结果可以指定公开分类"],
                },
                2,
            )
        if arguments.category and arguments.category not in category_names(root):
            return emit(
                {
                    "status": "blocked",
                    "slug": slug,
                    "errors": [f"公开分类不在白名单中：{arguments.category}"],
                },
                2,
            )
        if state.get("review_started_fingerprint") != fingerprint:
            return emit(
                {
                    "status": "blocked",
                    "slug": slug,
                    "errors": ["正文或原图已在审稿期间变化，请重新开始审稿"],
                },
                2,
            )
        if not report_path.is_file():
            return emit(
                {"status": "blocked", "slug": slug, "errors": ["找不到审稿报告"]},
                2,
            )
        report = report_path.read_text(encoding="utf-8")
        placeholders = (
            "请在这里记录结构与叙事顺序建议",
            "请在这里记录措辞、段落和术语建议",
        )
        if any(item in report for item in placeholders):
            return emit(
                {
                    "status": "blocked",
                    "slug": slug,
                    "errors": ["审稿报告尚未填写完整"],
                },
                2,
            )
        report_hash = hashlib.sha256(report.encode("utf-8")).hexdigest()
        reviewed_at = datetime.now(timezone.utc).isoformat()
        if arguments.verdict == "needs-revision":
            state.pop("review_fingerprint", None)
            state.pop("review_category", None)
            state.update(
                {
                    "review_verdict": "needs-revision",
                    "review_report_hash": report_hash,
                    "reviewed_at": reviewed_at,
                    "revision_feedback": {
                        "fingerprint": fingerprint,
                        "report_hash": report_hash,
                        "report": report_path.relative_to(root).as_posix(),
                    },
                }
            )
            write_state(draft, state)
            return emit(
                {
                    "status": "needs_revision",
                    "slug": slug,
                    "fingerprint": fingerprint,
                    "report": report_path.relative_to(root).as_posix(),
                }
            )
        state.pop("revision_feedback", None)
        if arguments.category:
            state["review_category"] = arguments.category
        else:
            state.pop("review_category", None)
        state.update(
            {
                "review_verdict": "pass",
                "review_fingerprint": fingerprint,
                "review_report_hash": report_hash,
                "reviewed_at": reviewed_at,
            }
        )
        write_state(draft, state)
        result: dict[str, object] = {
                "status": "reviewed",
                "slug": slug,
                "fingerprint": fingerprint,
                "report": report_path.relative_to(root).as_posix(),
            }
        if arguments.category:
            result["category"] = arguments.category
        return emit(result)

    revision_feedback = state.get("revision_feedback")
    if (
        isinstance(revision_feedback, dict)
        and revision_feedback.get("fingerprint") == fingerprint
    ):
        return emit(
            {
                "status": "blocked",
                "slug": slug,
                "errors": ["上次退稿后内容尚未修改；请先在内容源中重写后再审"],
            },
            2,
        )

    content = article.read_text(encoding="utf-8")
    title_match = re.search(r"^#\s+(.+)$", content, flags=re.MULTILINE)
    title = title_match.group(1).strip() if title_match else slug
    report = (
        f"# 审稿报告：{title}\n\n"
        f"> 内容指纹：`{fingerprint}`\n\n"
        "## 阻断项\n\n"
        "- 确定性格式检查将在 `check` 阶段写入。\n\n"
        "## 结构建议\n\n"
        "- 请在这里记录结构与叙事顺序建议；不直接修改正文。\n\n"
        "## 表达建议\n\n"
        "- 请在这里记录措辞、段落和术语建议；不直接修改正文。\n\n"
        "## 发布检查\n\n"
        "<!-- publish-checks:start -->\n"
        "- 尚未执行。\n"
        "<!-- publish-checks:end -->\n"
    )
    report_path.write_text(report, encoding="utf-8")
    state.pop("review_fingerprint", None)
    state.pop("review_report_hash", None)
    state.update(
        {
            "slug": slug,
            "review_started_fingerprint": fingerprint,
            "review_started_at": datetime.now(timezone.utc).isoformat(),
        }
    )
    write_state(draft, state)
    return emit(
        {
            "status": "review_pending",
            "slug": slug,
            "fingerprint": fingerprint,
            "report": report_path.relative_to(root).as_posix(),
        }
    )


def draft_status(root: Path, arguments: argparse.Namespace) -> int:
    slug, draft, article = draft_paths(root, arguments.slug)
    fingerprint = content_fingerprint(draft, article)
    state = read_state(draft)

    def freshness(key: str) -> str:
        recorded = state.get(key)
        if not recorded:
            return "missing"
        return "current" if recorded == fingerprint else "stale"

    review = freshness("review_fingerprint")
    revision_feedback = state.get("revision_feedback")
    if (
        review == "missing"
        and isinstance(revision_feedback, dict)
        and revision_feedback.get("fingerprint") == fingerprint
    ):
        review = "needs_revision"
    if review == "missing" and state.get("review_started_fingerprint"):
        review = (
            "pending"
            if state.get("review_started_fingerprint") == fingerprint
            else "stale"
        )
    check = freshness("check_fingerprint")
    preview = freshness("preview_fingerprint")
    prepared = freshness("prepared_fingerprint")
    phase = "draft"
    if review == "needs_revision":
        phase = "needs_revision"
    if review == "current":
        phase = "reviewed"
    if check == "current":
        phase = "checked"
    if preview == "current":
        phase = "previewed"
    if prepared == "current":
        phase = "prepared"
    return emit(
        {
            "status": phase,
            "slug": slug,
            "fingerprint": fingerprint,
            "review": review,
            "check": check,
            "preview": preview,
            "prepared": prepared,
        }
    )


def check_draft(root: Path, arguments: argparse.Namespace) -> int:
    slug, draft, article = draft_paths(root, arguments.slug)
    fingerprint = content_fingerprint(draft, article)
    _, _, errors, advisories = analyze_draft(slug, draft, article)
    update_review_checks(draft, errors, advisories)
    state = read_state(draft)
    state["last_check"] = {
        "fingerprint": fingerprint,
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "errors": errors,
        "advisories": advisories,
    }
    if errors:
        state.pop("check_fingerprint", None)
    else:
        state["check_fingerprint"] = fingerprint
    write_state(draft, state)
    return emit(
        {
            "status": "blocked" if errors else "checked",
            "slug": slug,
            "fingerprint": fingerprint,
            "errors": errors,
            "advisories": advisories,
        },
        2 if errors else 0,
    )


def clear_generated_directory(destination: Path) -> None:
    destination_parent = destination.parent.resolve()
    destination_resolved = destination.resolve()
    if (
        destination_resolved == destination_parent
        or destination_parent not in destination_resolved.parents
    ):
        raise ValueError("拒绝清理不安全的生成目录")
    if destination.exists():
        shutil.rmtree(destination)


def publication_front_matter(content: str, category: str | None) -> str:
    match = FRONT_MATTER.match(content)
    if not match:
        raise ValueError("文章缺少 YAML front matter")
    try:
        metadata = yaml.safe_load(match.group(1)) or {}
    except yaml.YAMLError as error:
        raise ValueError(f"front matter 无法解析：{error}") from error
    if not isinstance(metadata, dict):
        raise ValueError("front matter 必须是键值结构")
    body = content[match.end() :]
    heading = re.search(r"^#\s+(.+)$", body, flags=re.MULTILINE)
    if not heading:
        raise ValueError("无法生成公开元数据：缺少一级标题")
    before_more = body.split("<!-- more -->", 1)[0]
    without_title = re.sub(
        r"^#\s+.+$", "", before_more, count=1, flags=re.MULTILINE
    )
    paragraphs = [
        part.strip()
        for part in re.split(r"\n\s*\n", without_title)
        if part.strip()
    ]
    if not paragraphs:
        raise ValueError("无法生成公开元数据：摘要为空")
    metadata["title"] = heading.group(1).strip()
    metadata["description"] = paragraphs[0]
    if category:
        metadata["category"] = category
    else:
        metadata.pop("category", None)
    front_matter = yaml.safe_dump(
        metadata, allow_unicode=True, sort_keys=False
    ).rstrip()
    return f"---\n{front_matter}\n---\n\n{body}"


def render_article_copy(
    draft: Path,
    article: Path,
    destination: Path,
    category: str | None = None,
) -> list[dict[str, object]]:
    clear_generated_directory(destination)
    (destination / "images").mkdir(parents=True)

    content = article.read_text(encoding="utf-8")
    optimized: list[dict[str, object]] = []
    replacements: dict[str, str] = {}
    published_sources: dict[Path, str] = {}
    output_sources: dict[str, Path] = {}
    for raw_target, _, _ in image_references(content):
        source, kind, path_error = local_image_source(draft, article, raw_target)
        if kind == "external":
            continue
        if path_error:
            raise ValueError(path_error)
        assert source is not None
        if source in published_sources:
            replacements[raw_target] = published_sources[source]
            continue
        suffix = source.suffix.lower()
        output_name = published_image_name(source)
        previous = output_sources.get(output_name)
        if previous is not None and previous != source:
            raise ValueError(f"图片输出文件名冲突：{output_name}")
        output_sources[output_name] = source
        output = destination / "images" / output_name
        if suffix in {".jpg", ".jpeg", ".png"}:
            with Image.open(source) as opened:
                image = ImageOps.exif_transpose(opened)
                if image.width > 1600:
                    height = round(image.height * 1600 / image.width)
                    image = image.resize((1600, height), Image.Resampling.LANCZOS)
                save_options: dict[str, object] = {"format": "WEBP", "method": 6}
                if suffix == ".png":
                    save_options["lossless"] = True
                else:
                    save_options["quality"] = 85
                image.save(output, **save_options)
        elif suffix in {".svg", ".gif", ".webp"}:
            shutil.copy2(source, output)
        else:
            raise ValueError(f"不支持的图片格式：{source.name}")

        published_target = f"images/{output_name}"
        replacements[raw_target] = published_target
        published_sources[source] = published_target
        optimized.append(
            {
                "source": source.relative_to(draft).as_posix(),
                "output": published_target,
                "source_bytes": source.stat().st_size,
                "output_bytes": output.stat().st_size,
            }
        )

    def rewrite(match: re.Match[str]) -> str:
        raw_target = match.group(2) or match.group(3)
        replacement = replacements.get(raw_target)
        if not replacement:
            return match.group(0)
        return match.group(0).replace(raw_target, replacement, 1)

    def rewrite_html(match: re.Match[str]) -> str:
        tag = match.group(0)

        def rewrite_attribute(attribute: re.Match[str]) -> str:
            if attribute.group("name").lower() != "src":
                return attribute.group(0)
            raw_target = (
                attribute.group("double")
                or attribute.group("single")
                or attribute.group("bare")
                or ""
            )
            replacement = replacements.get(raw_target)
            if not replacement:
                return attribute.group(0)
            original = attribute.group(0)
            value_start = attribute.start("double")
            value_group = "double"
            if value_start < 0:
                value_group = "single" if attribute.start("single") >= 0 else "bare"
            start, end = attribute.span(value_group)
            start -= attribute.start()
            end -= attribute.start()
            return original[:start] + replacement + original[end:]

        return HTML_ATTRIBUTE.sub(rewrite_attribute, tag)

    rendered = MARKDOWN_IMAGE.sub(rewrite, content)
    rendered = HTML_IMAGE.sub(rewrite_html, rendered)
    rendered = publication_front_matter(rendered, category)
    (destination / "index.md").write_text(rendered, encoding="utf-8")
    return optimized


def preview_draft(root: Path, arguments: argparse.Namespace) -> int:
    slug, draft, article = draft_paths(root, arguments.slug)
    fingerprint = content_fingerprint(draft, article)
    metadata, _ = parse_article(article)
    state = read_state(draft)
    errors: list[str] = []
    if state.get("review_fingerprint") != fingerprint:
        revision_feedback = state.get("revision_feedback")
        if (
            isinstance(revision_feedback, dict)
            and revision_feedback.get("fingerprint") == fingerprint
        ):
            errors.append("当前内容已被退稿；请先修改内容源并重新审稿")
        elif state.get("review_started_fingerprint") == fingerprint:
            errors.append("当前内容尚未完成审稿报告")
        else:
            errors.append("当前内容尚未审稿，或审稿结果已经失效")
    if state.get("check_fingerprint") != fingerprint:
        errors.append("当前内容尚未通过检查，或检查结果已经失效")
    if errors:
        return emit({"status": "blocked", "slug": slug, "errors": errors}, 2)

    destination = root / "docs" / "blog" / "posts" / "drafts" / slug
    category = state.get("review_category")
    optimized = render_article_copy(
        draft,
        article,
        destination,
        category if isinstance(category, str) else None,
    )
    update_review_images(draft, optimized)
    state.update(
        {
            "preview_fingerprint": fingerprint,
            "previewed_at": datetime.now(timezone.utc).isoformat(),
            "preview_path": destination.relative_to(root).as_posix(),
            "images": optimized,
        }
    )
    write_state(draft, state)
    return emit(
        {
            "status": "previewed",
            "slug": slug,
            "fingerprint": fingerprint,
            "preview": destination.relative_to(root).as_posix(),
            "url": article_url(slug, metadata),
            "images": optimized,
        }
    )


def created_date(metadata: dict[str, object]) -> date:
    raw = metadata.get("date")
    if isinstance(raw, dict):
        raw = raw.get("created")
    if isinstance(raw, datetime):
        return raw.date()
    if isinstance(raw, date):
        return raw
    try:
        return date.fromisoformat(str(raw))
    except (TypeError, ValueError) as error:
        raise ValueError("date 必须使用 YYYY-MM-DD 格式") from error


def article_url(slug: str, metadata: dict[str, object]) -> str:
    published = created_date(metadata)
    return (
        f"/blog/{published.year}/{published.month:02d}/{published.day:02d}/{slug}/"
    )


def homepage_card(slug: str, metadata: dict[str, object], body: str) -> str:
    heading = re.search(r"^#\s+(.+)$", body, flags=re.MULTILINE)
    if not heading:
        raise ValueError("无法生成首页卡片：缺少一级标题")
    title = heading.group(1).strip()
    before_more = body.split("<!-- more -->", 1)[0]
    without_title = re.sub(r"^#\s+.+$", "", before_more, count=1, flags=re.MULTILINE)
    paragraphs = [part.strip() for part in re.split(r"\n\s*\n", without_title) if part.strip()]
    if not paragraphs:
        raise ValueError("无法生成首页卡片：摘要为空")
    summary = paragraphs[0]
    published = created_date(metadata)
    tags = metadata.get("tags")
    assert isinstance(tags, list)
    tag_markup = "\n".join(
        f'  <span class="home-post-tag">{escape(str(tag))}</span>' for tag in tags
    )
    link_title = title.replace("]", r"\]")
    source_path = f"blog/posts/{slug}/index.md"
    return (
        '<div class="home-post-card" markdown="1">\n\n'
        '<p class="home-post-meta">\n'
        f'  <time datetime="{published.isoformat()}">'
        f"{published.year} 年 {published.month} 月 {published.day} 日</time>\n"
        f"{tag_markup}\n"
        "</p>\n\n"
        f"### [{link_title}]({source_path})\n\n"
        f"{summary}\n\n"
        f"[阅读全文 :lucide-arrow-right:]({source_path}){{ .home-post-cta }}\n\n"
        "</div>"
    )


def update_homepage(root: Path, card: str) -> None:
    homepage = root / "docs" / "index.md"
    if not homepage.is_file():
        raise ValueError("找不到 docs/index.md")
    content = homepage.read_text(encoding="utf-8")
    marker = re.compile(
        r"<!-- latest-post:start -->.*?<!-- latest-post:end -->", re.DOTALL
    )
    if not marker.search(content):
        raise ValueError("首页缺少 latest-post 管理标记")
    replacement = (
        "<!-- latest-post:start -->\n" + card + "\n<!-- latest-post:end -->"
    )
    homepage.write_text(marker.sub(replacement, content), encoding="utf-8")


def prepare_draft(root: Path, arguments: argparse.Namespace) -> int:
    slug, draft, article = draft_paths(root, arguments.slug)
    fingerprint = content_fingerprint(draft, article)
    metadata, body, errors, advisories = analyze_draft(slug, draft, article)
    state = read_state(draft)
    if state.get("review_fingerprint") != fingerprint:
        errors.append("当前内容尚未审稿，或审稿结果已经失效")
    if state.get("check_fingerprint") != fingerprint:
        errors.append("当前内容尚未通过检查，或检查结果已经失效")
    if state.get("preview_fingerprint") != fingerprint:
        errors.append("当前内容尚未生成预览，或预览结果已经失效")

    destination = root / "docs" / "blog" / "posts" / slug
    legacy_destination = destination.with_suffix(".md")
    if legacy_destination.exists():
        errors.append("检测到同 slug 的旧式正式文章；请先显式迁移，不能直接覆盖")
    if destination.exists() and not arguments.overwrite:
        errors.append("正式文章目录已经存在；更新文章时必须显式使用 --overwrite")
    if destination.exists() and arguments.overwrite:
        manifest = state.get("published_manifest")
        expected = set(manifest) if isinstance(manifest, list) else set()
        actual = {
            path.relative_to(destination).as_posix()
            for path in destination.rglob("*")
            if path.is_file()
        }
        if not expected or actual != expected:
            errors.append("正式文章目录存在工作流未管理的文件或内容漂移，拒绝覆盖")
    try:
        card = homepage_card(slug, metadata, body) if not errors else ""
        if not errors:
            homepage = root / "docs" / "index.md"
            content = homepage.read_text(encoding="utf-8")
            if not re.search(
                r"<!-- latest-post:start -->.*?<!-- latest-post:end -->",
                content,
                flags=re.DOTALL,
            ):
                errors.append("首页缺少 latest-post 管理标记")
    except (AssertionError, OSError, ValueError) as error:
        errors.append(str(error))
        card = ""
    if errors:
        return emit(
            {
                "status": "blocked",
                "slug": slug,
                "errors": errors,
                "advisories": advisories,
            },
            2,
        )

    category = state.get("review_category")
    optimized = render_article_copy(
        draft,
        article,
        destination,
        category if isinstance(category, str) else None,
    )
    published_path = destination / "index.md"
    public_content = re.sub(
        r"(?m)^draft:\s*true\s*\n", "", published_path.read_text(encoding="utf-8")
    )
    published_path.write_text(public_content, encoding="utf-8")
    update_homepage(root, card)
    preview_destination = root / "docs" / "blog" / "posts" / "drafts" / slug
    clear_generated_directory(preview_destination)
    published_manifest = sorted(
        path.relative_to(destination).as_posix()
        for path in destination.rglob("*")
        if path.is_file()
    )
    state.update(
        {
            "prepared_fingerprint": fingerprint,
            "prepared_at": datetime.now(timezone.utc).isoformat(),
            "published_path": destination.relative_to(root).as_posix(),
            "images": optimized,
            "published_manifest": published_manifest,
        }
    )
    write_state(draft, state)
    return emit(
        {
            "status": "prepared",
            "slug": slug,
            "fingerprint": fingerprint,
            "published": destination.relative_to(root).as_posix(),
            "url": article_url(slug, metadata),
            "homepage": "docs/index.md",
            "images": optimized,
            "advisories": advisories,
        }
    )
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Zensical 文章草稿与发布工作流")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    commands = parser.add_subparsers(dest="command", required=True)

    create = commands.add_parser("new", help="创建本地草稿")
    create.add_argument("--title", required=True)
    create.add_argument("--slug")
    create.add_argument("--tag", action="append")
    create.add_argument("--date", default=date.today().isoformat())
    create.set_defaults(handler=new_draft)

    import_logseq = commands.add_parser(
        "import-logseq", help="从只读 Logseq 仓库导入本地草稿"
    )
    import_logseq.add_argument("slug")
    import_logseq.add_argument("--logseq-root", type=Path)
    import_logseq.add_argument("--tag", action="append")
    import_logseq.set_defaults(handler=import_logseq_draft)

    queue_logseq = commands.add_parser(
        "queue-logseq", help="扫描 Logseq 中待发布的文章"
    )
    queue_logseq.add_argument("--logseq-root", type=Path)
    queue_logseq.set_defaults(handler=queue_logseq_articles)

    review = commands.add_parser("review", help="生成不修改正文的审稿报告")
    review.add_argument("slug")
    review.add_argument("--complete", action="store_true", help="确认审稿报告已经填写完成")
    review.add_argument("--verdict", choices=("pass", "needs-revision"))
    review.add_argument("--category")
    review.set_defaults(handler=review_draft)

    status = commands.add_parser("status", help="查询草稿当前阶段")
    status.add_argument("slug")
    status.set_defaults(handler=draft_status)

    check = commands.add_parser("check", help="检查元数据与本地资源")
    check.add_argument("slug")
    check.set_defaults(handler=check_draft)

    preview = commands.add_parser("preview", help="生成 Zensical 本地预览副本")
    preview.add_argument("slug")
    preview.set_defaults(handler=preview_draft)

    prepare = commands.add_parser("prepare", help="生成正式文章并更新首页")
    prepare.add_argument("slug")
    prepare.add_argument("--overwrite", action="store_true")
    prepare.set_defaults(handler=prepare_draft)
    return parser


def main() -> int:
    parser = build_parser()
    arguments = parser.parse_args()
    try:
        return arguments.handler(arguments.root.resolve(), arguments)
    except ValueError as error:
        return emit({"status": "error", "errors": [str(error)]}, 2)


if __name__ == "__main__":
    sys.exit(main())
