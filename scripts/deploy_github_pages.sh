#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
WORKFLOW_NAME="Deploy Pages"

usage() {
  cat <<'EOF'
Usage: scripts/deploy_github_pages.sh [options]

Deploys this site to GitHub Pages by triggering the "Deploy Pages" workflow.

Options:
  --ref <git-ref>    Git ref to run the workflow from (default: current branch)
  --skip-build       Skip local build validation before triggering deploy
  --no-watch         Do not wait for workflow completion
  -h, --help         Show this help
EOF
}

REF=""
SKIP_BUILD=0
WATCH=1

while [[ $# -gt 0 ]]; do
  case "$1" in
    --ref)
      if [[ $# -lt 2 ]]; then
        echo "Error: --ref requires a value." >&2
        exit 1
      fi
      REF="$2"
      shift 2
      ;;
    --skip-build)
      SKIP_BUILD=1
      shift
      ;;
    --no-watch)
      WATCH=0
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Error: unknown option '$1'." >&2
      usage >&2
      exit 1
      ;;
  esac
done

if ! command -v gh >/dev/null 2>&1; then
  echo "Error: GitHub CLI (gh) is required. Install from https://cli.github.com/." >&2
  exit 1
fi

if ! command -v git >/dev/null 2>&1; then
  echo "Error: git is required." >&2
  exit 1
fi

if ! git -C "$ROOT_DIR" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  echo "Error: $ROOT_DIR is not a git repository." >&2
  exit 1
fi

if [[ -z "$REF" ]]; then
  REF="$(git -C "$ROOT_DIR" rev-parse --abbrev-ref HEAD)"
fi

if ! gh auth status >/dev/null 2>&1; then
  echo "Error: gh is not authenticated. Run 'gh auth login' first." >&2
  exit 1
fi

REPO="$(gh repo view --json nameWithOwner --jq .nameWithOwner 2>/dev/null || true)"
if [[ -z "$REPO" || "$REPO" == "null" ]]; then
  ORIGIN="$(git -C "$ROOT_DIR" config --get remote.origin.url || true)"
  REPO="$(echo "$ORIGIN" | sed -E 's#^(git@github.com:|https://github.com/)##; s#\\.git$##')"
fi

if [[ -z "$REPO" || "$REPO" != */* ]]; then
  echo "Error: could not determine GitHub repository (owner/repo)." >&2
  exit 1
fi

if [[ "$SKIP_BUILD" -eq 0 ]]; then
  PYTHON_BIN="python3"
  if [[ -x "$ROOT_DIR/.venv/bin/python" ]]; then
    PYTHON_BIN="$ROOT_DIR/.venv/bin/python"
  fi
  echo "Running local build check..."
  "$PYTHON_BIN" "$ROOT_DIR/scripts/build.py" --clean
fi

echo "Triggering workflow '$WORKFLOW_NAME' on ref '$REF'..."
gh -R "$REPO" workflow run "$WORKFLOW_NAME" --ref "$REF"

if [[ "$WATCH" -eq 1 ]]; then
  echo "Waiting for workflow to complete..."
  sleep 2
  RUN_ID="$(gh -R "$REPO" run list --workflow "$WORKFLOW_NAME" --branch "$REF" --event workflow_dispatch --limit 1 --json databaseId --jq '.[0].databaseId')"
  if [[ -n "$RUN_ID" && "$RUN_ID" != "null" ]]; then
    gh -R "$REPO" run watch "$RUN_ID"
  fi

  PAGES_URL="$(gh -R "$REPO" api repos/{owner}/{repo}/pages --jq '.html_url' 2>/dev/null || true)"
  if [[ -n "$PAGES_URL" ]]; then
    echo "GitHub Pages URL: $PAGES_URL"
  fi
fi

echo "Done."
