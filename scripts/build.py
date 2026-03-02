#!/usr/bin/env python3
"""Build the markdown-driven personal website into static HTML."""

from __future__ import annotations

import argparse
import datetime as dt
import html
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from jinja2 import Environment, FileSystemLoader, StrictUndefined, select_autoescape
from markdown import markdown


SECTION_DEFS = [
    {
        "name": "posts",
        "label": "Posts",
        "description": "Original writing and updates.",
    },
    {
        "name": "reads",
        "label": "Reads",
        "description": "Notes from books and articles.",
    },
    {
        "name": "projects",
        "label": "Projects",
        "description": "Things I am building and exploring.",
    },
    {
        "name": "links",
        "label": "Links",
        "description": "Useful resources I revisit often.",
    },
]


class BuildError(Exception):
    """Raised when input content or configuration is invalid."""


@dataclass(frozen=True)
class SiteConfig:
    root_dir: Path
    content_dir: Path
    templates_dir: Path
    assets_dir: Path
    output_dir: Path
    site_title: str
    base_url: str


@dataclass
class ContentItem:
    source_path: Path
    title: str
    subtitle: str
    author: str
    date: dt.date
    date_display: str
    summary: str
    preview_text: str
    tags: list[str]
    draft: bool
    slug: str
    external_url: str | None
    read_path: str | None
    body_markdown: str
    rendered_html: str


@dataclass
class HomeContent:
    title: str
    metadata: dict[str, Any]
    rendered_html: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build static personal website")
    parser.add_argument("--clean", action="store_true", help="Remove output directory before building")
    parser.add_argument(
        "--include-drafts",
        action="store_true",
        help="Include content entries with draft: true",
    )
    parser.add_argument("--verbose", action="store_true", help="Print build progress")
    return parser.parse_args()


def build_config() -> SiteConfig:
    root_dir = Path(__file__).resolve().parent.parent
    base_url = resolve_base_url(root_dir)
    site_title = os.environ.get("SITE_TITLE", "Ernesto Personal Website")

    return SiteConfig(
        root_dir=root_dir,
        content_dir=root_dir / "content",
        templates_dir=root_dir / "templates",
        assets_dir=root_dir / "assets",
        output_dir=root_dir / "docs",
        site_title=site_title,
        base_url=base_url,
    )


def resolve_base_url(root_dir: Path) -> str:
    explicit_base_url = os.environ.get("BASE_URL")
    if explicit_base_url:
        return normalize_base_url(explicit_base_url)

    github_repo = os.environ.get("GITHUB_REPOSITORY", "").strip()
    if github_repo:
        return repo_slug_to_base_url(github_repo)

    remote_repo = read_origin_repo_slug(root_dir)
    if remote_repo:
        return repo_slug_to_base_url(remote_repo)

    return "/"


def read_origin_repo_slug(root_dir: Path) -> str:
    try:
        result = subprocess.run(
            ["git", "-C", str(root_dir), "config", "--get", "remote.origin.url"],
            capture_output=True,
            text=True,
            check=True,
        )
    except (FileNotFoundError, subprocess.CalledProcessError):
        return ""

    origin_url = result.stdout.strip()
    if not origin_url:
        return ""

    prefix_map = (
        "git@github.com:",
        "https://github.com/",
        "ssh://git@github.com/",
    )
    for prefix in prefix_map:
        if origin_url.startswith(prefix):
            slug = origin_url[len(prefix) :]
            return slug[:-4] if slug.endswith(".git") else slug

    return ""


def repo_slug_to_base_url(repo_slug: str) -> str:
    repo_name = repo_slug.split("/")[-1].strip()
    if not repo_name:
        return "/"
    if repo_name.endswith(".github.io"):
        return "/"
    return normalize_base_url(f"/{repo_name}/")


def normalize_base_url(base_url: str) -> str:
    cleaned = (base_url or "/").strip()
    if not cleaned:
        return "/"
    if not cleaned.startswith("/"):
        cleaned = "/" + cleaned
    if not cleaned.endswith("/"):
        cleaned = cleaned + "/"
    return cleaned


def build_url(base_url: str, path: str = "") -> str:
    stripped = path.lstrip("/")
    if not stripped:
        return base_url
    return f"{base_url}{stripped}"


def parse_front_matter(raw_text: str, source_path: Path) -> tuple[dict[str, Any], str]:
    lines = raw_text.splitlines()
    if not lines or lines[0].strip() != "---":
        raise BuildError(f"{source_path}: expected YAML front matter starting with '---'")

    end_index = None
    for index in range(1, len(lines)):
        if lines[index].strip() == "---":
            end_index = index
            break

    if end_index is None:
        raise BuildError(f"{source_path}: missing closing '---' for front matter")

    front_matter_text = "\n".join(lines[1:end_index]).strip()
    body = "\n".join(lines[end_index + 1 :]).lstrip("\n")
    metadata = yaml.safe_load(front_matter_text) if front_matter_text else {}

    if metadata is None:
        metadata = {}
    if not isinstance(metadata, dict):
        raise BuildError(f"{source_path}: front matter must be a YAML mapping")

    return metadata, body


def parse_date(value: Any, source_path: Path) -> dt.date:
    if isinstance(value, dt.date):
        return value
    if isinstance(value, str):
        try:
            return dt.date.fromisoformat(value)
        except ValueError as exc:
            raise BuildError(f"{source_path}: date must be ISO format YYYY-MM-DD") from exc
    raise BuildError(f"{source_path}: date is required and must be a string in YYYY-MM-DD")


def validate_content_metadata(metadata: dict[str, Any], source_path: Path) -> dict[str, Any]:
    title = metadata.get("title")
    if not isinstance(title, str) or not title.strip():
        raise BuildError(f"{source_path}: title is required and must be a non-empty string")

    date = parse_date(metadata.get("date"), source_path)

    summary = metadata.get("summary", "")
    if summary is None:
        summary = ""
    if not isinstance(summary, str):
        raise BuildError(f"{source_path}: summary must be a string")

    subtitle = metadata.get("subtitle", "")
    if subtitle is None:
        subtitle = ""
    if not isinstance(subtitle, str):
        raise BuildError(f"{source_path}: subtitle must be a string")

    author = metadata.get("author", "")
    if author is None:
        author = ""
    if not isinstance(author, str):
        raise BuildError(f"{source_path}: author must be a string")

    tags = metadata.get("tags", [])
    if tags is None:
        tags = []
    if isinstance(tags, str):
        tags = [tags]
    if not isinstance(tags, list) or any(not isinstance(tag, str) for tag in tags):
        raise BuildError(f"{source_path}: tags must be a list of strings")

    draft = metadata.get("draft", False)
    if not isinstance(draft, bool):
        raise BuildError(f"{source_path}: draft must be true or false")

    raw_slug = metadata.get("slug", source_path.stem)
    if not isinstance(raw_slug, str) or not raw_slug.strip():
        raise BuildError(f"{source_path}: slug must be a non-empty string")
    slug = slugify(raw_slug)
    if "/" in slug or "\\" in slug or slug in {".", ".."}:
        raise BuildError(f"{source_path}: slug cannot include path separators")

    external_url = metadata.get("external_url")
    if external_url is not None and not isinstance(external_url, str):
        raise BuildError(f"{source_path}: external_url must be a string")

    return {
        "title": title.strip(),
        "subtitle": subtitle.strip(),
        "author": author.strip(),
        "date": date,
        "summary": summary.strip(),
        "tags": [tag.strip() for tag in tags if tag.strip()],
        "draft": draft,
        "slug": slug,
        "external_url": external_url,
    }


def human_date(date_value: dt.date) -> str:
    return date_value.strftime("%B %d, %Y").replace(" 0", " ")


def render_markdown(content: str) -> str:
    return markdown(content, extensions=["extra", "sane_lists", "toc"])


def strip_html_tags(text: str) -> str:
    without_tags = re.sub(r"<[^>]+>", " ", text)
    normalized = re.sub(r"\s+", " ", without_tags)
    return html.unescape(normalized).strip()


def build_preview_text(summary: str, rendered_html: str, max_chars: int = 280) -> str:
    source_text = summary or strip_html_tags(rendered_html)
    if len(source_text) <= max_chars:
        return source_text
    clipped = source_text[:max_chars].rstrip()
    if " " in clipped:
        clipped = clipped.rsplit(" ", 1)[0]
    return f"{clipped}..."


def slugify(value: str) -> str:
    normalized = value.strip().lower()
    normalized = re.sub(r"[^a-z0-9]+", "-", normalized)
    normalized = normalized.strip("-")
    return normalized or "item"


def load_markdown_file(path: Path) -> tuple[dict[str, Any], str]:
    try:
        raw_text = path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise BuildError(f"Missing file: {path}") from exc
    return parse_front_matter(raw_text, path)


def load_home_content(content_dir: Path) -> HomeContent:
    home_path = content_dir / "home.md"
    metadata, body = load_markdown_file(home_path)
    validated = validate_content_metadata(metadata, home_path)

    return HomeContent(
        title=validated["title"],
        metadata={**metadata, "date": validated["date"].isoformat()},
        rendered_html=render_markdown(body),
    )


def load_section_items(
    content_dir: Path,
    section_name: str,
    include_drafts: bool,
) -> list[ContentItem]:
    section_dir = content_dir / section_name
    if not section_dir.exists() or not section_dir.is_dir():
        raise BuildError(f"Missing section folder: {section_dir}")

    items: list[ContentItem] = []
    for md_path in sorted(section_dir.glob("*.md")):
        metadata, body = load_markdown_file(md_path)
        validated = validate_content_metadata(metadata, md_path)

        if validated["draft"] and not include_drafts:
            continue

        rendered_html = render_markdown(body)
        read_path = f"reads/{validated['slug']}/" if section_name == "reads" else None

        items.append(
            ContentItem(
                source_path=md_path,
                title=validated["title"],
                subtitle=validated["subtitle"],
                author=validated["author"],
                date=validated["date"],
                date_display=human_date(validated["date"]),
                summary=validated["summary"],
                preview_text=build_preview_text(validated["summary"], rendered_html),
                tags=validated["tags"],
                draft=validated["draft"],
                slug=validated["slug"],
                external_url=validated["external_url"],
                read_path=read_path,
                body_markdown=body,
                rendered_html=rendered_html,
            )
        )

    sorted_items = sorted(items, key=lambda item: (-item.date.toordinal(), item.source_path.name.lower()))
    if section_name == "reads":
        seen_slugs: set[str] = set()
        for item in sorted_items:
            if item.slug in seen_slugs:
                raise BuildError(f"Duplicate slug '{item.slug}' in section '{section_name}'")
            seen_slugs.add(item.slug)
    return sorted_items


def validate_structure(config: SiteConfig) -> None:
    required_paths = [
        config.content_dir,
        config.templates_dir,
        config.assets_dir,
        config.assets_dir / "style.css",
    ]

    for path in required_paths:
        if not path.exists():
            raise BuildError(f"Required path not found: {path}")

    for section in SECTION_DEFS:
        section_dir = config.content_dir / section["name"]
        if not section_dir.exists() or not section_dir.is_dir():
            raise BuildError(f"Required section path not found: {section_dir}")


def template_environment(config: SiteConfig) -> Environment:
    env = Environment(
        loader=FileSystemLoader(str(config.templates_dir)),
        autoescape=select_autoescape(["html", "xml"]),
        undefined=StrictUndefined,
        trim_blocks=True,
        lstrip_blocks=True,
    )
    env.globals["url"] = lambda path="": build_url(config.base_url, path)
    return env


def write_text_file(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def copy_assets(config: SiteConfig) -> None:
    destination = config.output_dir / "assets"
    if destination.exists():
        shutil.rmtree(destination)
    shutil.copytree(config.assets_dir, destination)


def build_site(config: SiteConfig, include_drafts: bool, clean: bool, verbose: bool) -> None:
    validate_structure(config)

    if clean and config.output_dir.exists():
        shutil.rmtree(config.output_dir)

    config.output_dir.mkdir(parents=True, exist_ok=True)
    env = template_environment(config)

    site_context = {
        "title": config.site_title,
        "base_url": config.base_url,
        "nav": [
            {"name": "home", "label": "Home", "path": ""},
            *[
                {
                    "name": section["name"],
                    "label": section["label"],
                    "path": f"{section['name']}/",
                }
                for section in SECTION_DEFS
            ],
        ],
    }

    home = load_home_content(config.content_dir)
    home_template = env.get_template("home.html")
    home_html = home_template.render(
        page_title=home.title,
        current_section="home",
        site=site_context,
        home={
            "title": home.title,
            "metadata": home.metadata,
            "rendered_html": home.rendered_html,
        },
        sections=[
            {
                "name": section["name"],
                "label": section["label"],
                "path": f"{section['name']}/",
                "description": section["description"],
            }
            for section in SECTION_DEFS
        ],
    )
    write_text_file(config.output_dir / "index.html", home_html)
    if verbose:
        print(f"Rendered {config.output_dir / 'index.html'}")

    section_template = env.get_template("section.html")
    read_detail_template = env.get_template("read_detail.html")
    for section in SECTION_DEFS:
        items = load_section_items(config.content_dir, section["name"], include_drafts)
        section_html = section_template.render(
            page_title=section["label"],
            current_section=section["name"],
            site=site_context,
            section={
                "name": section["name"],
                "label": section["label"],
                "description": section["description"],
            },
            items=[
                {
                    "title": item.title,
                    "subtitle": item.subtitle,
                    "author": item.author,
                    "date": item.date.isoformat(),
                    "date_display": item.date_display,
                    "summary": item.summary,
                    "preview_text": item.preview_text,
                    "tags": item.tags,
                    "draft": item.draft,
                    "slug": item.slug,
                    "external_url": item.external_url,
                    "read_path": item.read_path,
                    "rendered_html": item.rendered_html,
                }
                for item in items
            ],
        )
        output_path = config.output_dir / section["name"] / "index.html"
        write_text_file(output_path, section_html)
        if verbose:
            print(f"Rendered {output_path}")

        if section["name"] == "reads":
            for item in items:
                if not item.read_path:
                    continue
                read_html = read_detail_template.render(
                    page_title=item.title,
                    current_section="reads",
                    site=site_context,
                    item={
                        "title": item.title,
                        "subtitle": item.subtitle,
                        "author": item.author,
                        "date": item.date.isoformat(),
                        "date_display": item.date_display,
                        "summary": item.summary,
                        "tags": item.tags,
                        "slug": item.slug,
                        "rendered_html": item.rendered_html,
                        "read_path": item.read_path,
                    },
                )
                read_output_path = config.output_dir / "reads" / item.slug / "index.html"
                write_text_file(read_output_path, read_html)
                if verbose:
                    print(f"Rendered {read_output_path}")

    copy_assets(config)
    if verbose:
        print(f"Copied assets to {config.output_dir / 'assets'}")


def main() -> int:
    args = parse_args()

    try:
        config = build_config()
        build_site(
            config=config,
            include_drafts=args.include_drafts,
            clean=args.clean,
            verbose=args.verbose,
        )
    except BuildError as exc:
        print(f"Build failed: {exc}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
