#!/usr/bin/env python3
"""Validate internal Markdown links.

Two link "worlds" are checked with different rules:

* Published pages (every *.md except the repo docs in DOCS) are served by
  Jekyll. Their internal links must use site paths: a root-relative page
  link (`/dubai/`) has to match a declared `permalink`, a root-relative
  asset (`/agencies.json`) has to be a real served file, and a relative
  `*.md` link is always wrong because it 404s on the live site.

* Repo docs (README.md, NEW_PAGES_2026.md) are read on GitHub, not served
  by Jekyll, so their relative links must point at files/dirs that actually
  exist in the repository.

External links (http/https/mailto/tel), protocol-relative links, and pure
`#anchor` links are skipped — external link health is a separate check.
Exit code is non-zero on any broken link so CI blocks the merge.
"""
from __future__ import annotations

import glob
import os
import re
import sys

# Repo docs that are NOT served as Jekyll pages (viewed on GitHub instead).
DOCS = {"README.md", "NEW_PAGES_2026.md"}

# Files Jekyll generates at the site root that won't exist on disk.
GENERATED = {"sitemap.xml"}

# Link and image targets: [text](url) / ![alt](url), ignoring any "title".
LINK_RE = re.compile(r"!?\[[^\]]*\]\(\s*(<[^>]+>|[^)\s]+)(?:\s+\"[^\"]*\")?\s*\)")

SKIP_SCHEMES = ("http://", "https://", "mailto:", "tel:", "ftp://", "//")


def collect_permalinks() -> set[str]:
    perms: set[str] = set()
    for path in glob.glob("*.md"):
        if path in DOCS:
            continue
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
        m = re.match(r"^---\s*\n(.*?)\n---", text, re.DOTALL)
        if not m:
            continue
        pm = re.search(r"^permalink:\s*(.+)$", m.group(1), re.MULTILINE)
        if pm:
            perms.add(pm.group(1).strip().strip('"').strip("'"))
    return perms


def extract_targets(text: str) -> list[str]:
    targets = []
    for raw in LINK_RE.findall(text):
        raw = raw.strip()
        if raw.startswith("<") and raw.endswith(">"):
            raw = raw[1:-1]
        targets.append(raw)
    return targets


def strip_frag(target: str) -> str:
    """Drop #fragment and ?query, keeping just the path."""
    return target.split("#", 1)[0].split("?", 1)[0]


def is_external(target: str) -> bool:
    return target.startswith(SKIP_SCHEMES) or target.startswith("#") or not target


def has_extension(path: str) -> bool:
    return "." in path.rsplit("/", 1)[-1]


def check_root_relative(target: str, path: str, permalinks: set[str], root_assets: set[str]) -> str | None:
    """A `/...` link resolves to a Jekyll page permalink or a served asset,
    regardless of whether it appears in a served page or a repo doc."""
    p = strip_frag(target)
    if has_extension(p):
        name = p.lstrip("/")
        if name not in root_assets and name not in GENERATED:
            return f"{path}: link '{target}' -> no served asset '{name}'"
    else:
        page = p if p.endswith("/") else p + "/"
        if page != "/" and page not in permalinks:
            return f"{path}: link '{target}' -> no page with permalink '{page}'"
    return None


def check_published(path: str, permalinks: set[str], root_assets: set[str]) -> list[str]:
    errors: list[str] = []
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    for target in extract_targets(text):
        if is_external(target):
            continue
        p = strip_frag(target)
        if not p:  # was a pure #anchor
            continue

        if p.startswith("/"):
            err = check_root_relative(target, path, permalinks, root_assets)
            if err:
                errors.append(err)
        elif p.endswith(".md"):
            errors.append(
                f"{path}: relative link '{target}' 404s on the live site "
                f"— use the target page's permalink instead"
            )
        else:
            resolved = os.path.normpath(os.path.join(os.path.dirname(path), p))
            if not os.path.exists(resolved):
                errors.append(f"{path}: link '{target}' -> missing file '{resolved}'")
    return errors


def check_doc(path: str, permalinks: set[str], root_assets: set[str]) -> list[str]:
    """Repo docs are read on GitHub. Root-relative links point at the live
    site (validated against permalinks); relative links must resolve to real
    files/dirs so in-repo navigation works."""
    errors: list[str] = []
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    base = os.path.dirname(path)
    for target in extract_targets(text):
        if is_external(target):
            continue
        p = strip_frag(target)
        if not p:
            continue

        if p.startswith("/"):
            err = check_root_relative(target, path, permalinks, root_assets)
            if err:
                errors.append(err)
            continue

        resolved = os.path.normpath(os.path.join(base, p))
        if p.endswith("/"):
            if not os.path.isdir(resolved):
                hint = f" (did you mean '{p.rstrip('/')}.md'?)" if os.path.isfile(resolved.rstrip("/") + ".md") else ""
                errors.append(f"{path}: link '{target}' -> no directory '{resolved}'{hint}")
        elif not os.path.isfile(resolved):
            errors.append(f"{path}: link '{target}' -> missing file '{resolved}'")
    return errors


def _in_ci() -> bool:
    return os.environ.get("GITHUB_ACTIONS") == "true"


def main() -> int:
    permalinks = collect_permalinks()
    root_assets = {f for f in os.listdir(".") if os.path.isfile(f)}

    errors: list[str] = []
    warnings: list[str] = []
    references_home = False

    for path in sorted(glob.glob("*.md")):
        with open(path, encoding="utf-8") as fh:
            if any(strip_frag(t) == "/" for t in extract_targets(fh.read())):
                references_home = True
        if path in DOCS:
            errors.extend(check_doc(path, permalinks, root_assets))
        else:
            errors.extend(check_published(path, permalinks, root_assets))

    # Pages link to "/" but there is no index page to serve it.
    if references_home and not any(os.path.exists(f"index{ext}") for ext in (".md", ".html")):
        warnings.append("pages link to '/' but no index.md/index.html exists to serve the homepage")

    for w in warnings:
        print(f"::warning::{w}" if _in_ci() else f"WARN  {w}")

    if errors:
        for e in errors:
            print(f"::error::{e}" if _in_ci() else f"ERROR {e}")
        print(f"\nFAILED: {len(errors)} broken internal link(s).")
        return 1

    print(f"OK: internal links valid across {len(glob.glob('*.md'))} Markdown file(s).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
