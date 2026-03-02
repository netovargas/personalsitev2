# Personal Website Static Generator

A markdown-driven static site generator for a personal website.

## What it builds

The site is generated from markdown content and templates into static HTML for hosting on GitHub Pages, S3, or any static host.

Generated output (under `docs/`):

- `index.html` (home)
- `posts/index.html`
- `reads/index.html`
- `reads/<slug>/index.html` (full read pages)
- `projects/index.html`
- `links/index.html`
- `assets/style.css`

## Project structure

- `content/home.md`
- `content/posts/*.md`
- `content/reads/*.md`
- `content/projects/*.md`
- `content/links/*.md`
- `templates/base.html`
- `templates/home.html`
- `templates/section.html`
- `assets/style.css`
- `scripts/build.py`

## Requirements

- Python 3.10+
- Dependencies in `requirements.txt`:
  - Markdown
  - Jinja2
  - PyYAML

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Usage

Run from the repository root:

```bash
python scripts/build.py
```

Useful flags:

```bash
python scripts/build.py --clean
python scripts/build.py --include-drafts
python scripts/build.py --verbose
```

You can combine flags:

```bash
python scripts/build.py --clean --include-drafts --verbose
```

## Environment variables

- `BASE_URL` (optional override)
  - If unset, the build script auto-detects:
    - `/<repo-name>/` for project pages
    - `/` for `<user>.github.io` repositories
- `SITE_TITLE` (default `Ernesto Personal Website`)

Example:

```bash
BASE_URL=/PersonalWebsite/ SITE_TITLE="Ernesto's Site" python scripts/build.py --clean
```

## Content format

Each markdown file must start with YAML front matter:

```md
---
title: Example Title
subtitle: Optional subtitle
author: Optional author
date: 2026-03-01
summary: Optional short summary
tags: [one, two]
draft: false
slug: example-title
external_url: https://example.com
---

Markdown body goes here.
```

Required fields:

- `title` (string)
- `date` (ISO format `YYYY-MM-DD`)

Optional fields:

- `summary` (string)
- `subtitle` (string)
- `author` (string)
- `tags` (list of strings)
- `draft` (boolean)
- `slug` (string; if omitted, generated from filename)
- `external_url` (string, useful in `links`)

### Reads behavior

- The `reads` page renders a preview for each read.
- Each read title links to its full page at `reads/<slug>/index.html`.
- `subtitle` and `author` are displayed on the reads list and full read page when present.

## Adding content

1. Create a markdown file in one of the section folders:
   - `content/posts/`
   - `content/reads/`
   - `content/projects/`
   - `content/links/`
2. Add valid front matter and body content.
3. Run the build script.

The home page content is read from `content/home.md`.

## Preview locally

After building, open `docs/index.html` in a browser.

## Deploying with GitHub Pages

A workflow is included at `.github/workflows/deploy.yml`.

On pushes to `main`, it will:

1. Install Python dependencies
2. Run `python scripts/build.py --clean`
3. Publish the `docs/` directory to GitHub Pages

The build script infers `BASE_URL` automatically from the repo name on GitHub Actions.

### Deploy script

Use `scripts/deploy_github_pages.sh` to trigger the GitHub Pages workflow manually:

```bash
scripts/deploy_github_pages.sh
```

Options:

- `--ref <git-ref>`: deploy from a specific branch/tag
- `--skip-build`: skip local build validation before triggering deploy
- `--no-watch`: trigger deploy and exit without waiting for workflow completion

Examples:

```bash
scripts/deploy_github_pages.sh --ref main
scripts/deploy_github_pages.sh --skip-build --no-watch
```

Requirements for deploy script:

- GitHub CLI (`gh`) installed
- Authenticated session (`gh auth login`)
- Repository connected to GitHub

## Troubleshooting

- `Build failed: ... expected YAML front matter ...`
  - Ensure each markdown file starts and ends front matter with `---`.
- `Build failed: ... date must be ISO format ...`
  - Use `YYYY-MM-DD`.
- Missing dependency errors (`No module named ...`)
  - Activate your virtual environment and reinstall requirements.
