#!/usr/bin/env python3
"""Validate YAML front matter on Jekyll content pages.

Every content Markdown page must open with a front-matter block containing
`title`, `description`, and `permalink`, or jekyll-seo-tag cannot emit a
correct <title>/meta description and Jekyll falls back to a *.html URL
instead of a clean permalink.

Files listed in SKIP are not served as site pages (repo docs) and are exempt.
Exit code is non-zero if any content page fails, so CI blocks the merge.
"""
from __future__ import annotations

import glob
import re
import sys

# Repo docs that are intentionally not Jekyll pages.
SKIP = {"README.md", "NEW_PAGES_2026.md"}

REQUIRED = ("title", "description", "permalink")

# Length guidance for search snippets (warnings only, non-blocking).
TITLE_MAX = 70
DESC_MIN, DESC_MAX = 50, 160


def parse_front_matter(text: str) -> dict[str, str] | None:
    """Return top-level scalar keys from a leading `---` block, or None."""
    if not text.startswith("---"):
        return None
    m = re.match(r"^---\s*\n(.*?)\n---\s*(\n|$)", text, re.DOTALL)
    if not m:
        return None
    fields: dict[str, str] = {}
    for line in m.group(1).splitlines():
        km = re.match(r"^([A-Za-z0-9_-]+):\s*(.*)$", line)
        if km:
            fields[km.group(1)] = km.group(2).strip().strip('"').strip("'")
    return fields


def main() -> int:
    errors: list[str] = []
    warnings: list[str] = []

    for path in sorted(glob.glob("*.md")):
        if path in SKIP:
            continue
        with open(path, encoding="utf-8") as fh:
            text = fh.read()

        fm = parse_front_matter(text)
        if fm is None:
            errors.append(f"{path}: missing or malformed front-matter block")
            continue

        for key in REQUIRED:
            if not fm.get(key):
                errors.append(f"{path}: missing required front-matter key '{key}'")

        permalink = fm.get("permalink", "")
        if permalink and not (permalink.startswith("/") and permalink.endswith("/")):
            errors.append(f"{path}: permalink '{permalink}' must start and end with '/'")

        title = fm.get("title", "")
        if title and len(title) > TITLE_MAX:
            warnings.append(f"{path}: title is {len(title)} chars (>{TITLE_MAX}), may truncate in search")

        desc = fm.get("description", "")
        if desc and not (DESC_MIN <= len(desc) <= DESC_MAX):
            warnings.append(f"{path}: description is {len(desc)} chars (aim {DESC_MIN}-{DESC_MAX})")

    for w in warnings:
        print(f"::warning::{w}" if _in_ci() else f"WARN  {w}")

    if errors:
        for e in errors:
            print(f"::error::{e}" if _in_ci() else f"ERROR {e}")
        print(f"\nFAILED: {len(errors)} front-matter error(s).")
        return 1

    print("OK: all content pages have valid front matter.")
    return 0


def _in_ci() -> bool:
    import os

    return os.environ.get("GITHUB_ACTIONS") == "true"


if __name__ == "__main__":
    sys.exit(main())
