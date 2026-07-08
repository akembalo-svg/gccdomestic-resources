#!/usr/bin/env python3
"""Validate the JSON-LD structured-data files.

Each *.json file in the repo root is schema.org structured data consumed by
search engines. A malformed file or a missing required key silently breaks
Google Rich Results, so this check parses every file and asserts the minimal
schema.org shape. Exit code is non-zero on any failure.
"""
from __future__ import annotations

import glob
import json
import sys

# Per-file expectations: required top-level keys and, for ItemList files,
# the required keys on each itemListElement entry.
RULES = {
    "business.json": {
        "top": ["@context", "@type", "name", "url"],
    },
    "agencies.json": {
        "top": ["@context", "@type", "itemListElement"],
        "list_key": "itemListElement",
        "item": ["@type", "name"],
    },
    "workers.json": {
        "top": ["@context", "@type", "itemListElement"],
        "list_key": "itemListElement",
        "item": ["@type", "title"],
    },
}


def validate_file(path: str, rules: dict) -> list[str]:
    errors: list[str] = []
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except json.JSONDecodeError as exc:
        return [f"{path}: invalid JSON — {exc}"]

    if not isinstance(data, dict):
        return [f"{path}: top-level JSON-LD must be an object, got {type(data).__name__}"]

    for key in rules.get("top", []):
        if key not in data:
            errors.append(f"{path}: missing required top-level key '{key}'")

    ctx = data.get("@context", "")
    if ctx and "schema.org" not in str(ctx):
        errors.append(f"{path}: @context should reference schema.org, got '{ctx}'")

    list_key = rules.get("list_key")
    if list_key:
        items = data.get(list_key)
        if not isinstance(items, list):
            errors.append(f"{path}: '{list_key}' must be a list")
        else:
            if not items:
                errors.append(f"{path}: '{list_key}' is empty")
            positions = []
            for idx, item in enumerate(items):
                if not isinstance(item, dict):
                    errors.append(f"{path}: {list_key}[{idx}] must be an object")
                    continue
                for key in rules.get("item", []):
                    if key not in item:
                        errors.append(f"{path}: {list_key}[{idx}] missing '{key}'")
                if "position" in item:
                    positions.append(item["position"])
            # positions should be unique
            if len(positions) != len(set(positions)):
                errors.append(f"{path}: duplicate 'position' values in {list_key}")
    return errors


def main() -> int:
    files = sorted(glob.glob("*.json"))
    if not files:
        print("No JSON files found.")
        return 0

    all_errors: list[str] = []
    for path in files:
        rules = RULES.get(path)
        if rules is None:
            # Unknown JSON file: still assert it parses.
            try:
                with open(path, encoding="utf-8") as fh:
                    json.load(fh)
            except json.JSONDecodeError as exc:
                all_errors.append(f"{path}: invalid JSON — {exc}")
            continue
        all_errors.extend(validate_file(path, rules))

    if all_errors:
        for e in all_errors:
            print(f"::error::{e}" if _in_ci() else f"ERROR {e}")
        print(f"\nFAILED: {len(all_errors)} JSON-LD error(s).")
        return 1

    print(f"OK: {len(files)} JSON file(s) valid.")
    return 0


def _in_ci() -> bool:
    import os

    return os.environ.get("GITHUB_ACTIONS") == "true"


if __name__ == "__main__":
    sys.exit(main())
