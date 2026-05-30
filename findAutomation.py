#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


def strip_jsonc(text: str) -> str:
    """Remove // and /* */ comments while preserving quoted strings."""
    result = []
    i = 0
    in_string = False
    escape = False

    while i < len(text):
        ch = text[i]
        nxt = text[i + 1] if i + 1 < len(text) else ""

        if in_string:
            result.append(ch)
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            i += 1
            continue

        if ch == '"':
            in_string = True
            result.append(ch)
            i += 1
            continue

        if ch == "/" and nxt == "/":
            while i < len(text) and text[i] not in "\r\n":
                i += 1
            continue

        if ch == "/" and nxt == "*":
            i += 2
            while i + 1 < len(text) and not (text[i] == "*" and text[i + 1] == "/"):
                i += 1
            i += 2
            continue

        result.append(ch)
        i += 1

    return "".join(result)


def remove_trailing_commas(text: str) -> str:
    """Remove trailing commas before } or ]."""
    return re.sub(r",\s*([}\]])", r"\1", text)


def load_jsonc(path: Path) -> Any:
    text = path.read_text(encoding="utf-8")
    text = strip_jsonc(text)
    text = remove_trailing_commas(text)
    return json.loads(text)


def walk_tree(value: Any, prefix: str = "") -> list[str]:
    lines: list[str] = []

    if isinstance(value, dict):
        for key, child in value.items():
            path = f"{prefix}.{key}" if prefix else str(key)
            lines.append(path)
            lines.extend(walk_tree(child, path))

    elif isinstance(value, list):
        for index, child in enumerate(value):
            path = f"{prefix}[{index}]"
            if isinstance(child, (dict, list)):
                lines.append(path)
                lines.extend(walk_tree(child, path))

    return lines


def find_automations(root: Path) -> None:

    EXCLUDE = [
        "starter",
        "generated",
        "backup",
    ]

    files = sorted(
        path
        for path in (
            list(root.rglob("*.json")) +
            list(root.rglob("*.jsonc"))
        )
        if not any(x in path.name.lower() for x in EXCLUDE)
    )
    
    for path in files:
        try:
            data = load_jsonc(path)
        except Exception as exc:
            print(f"\nERROR: {path}")
            print(f"  Could not parse: {exc}")
            continue

        automation = data.get("automation") if isinstance(data, dict) else None

        if automation is None:
            continue

        print(f"\n{path}")
        print("-" * len(str(path)))

        for line in walk_tree(automation, "automation"):
            print(f"  {line}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Find automation sections and child paths in DragnCards JSON/JSONC files."
    )
    parser.add_argument(
        "-d",
        "--directory",
        default=".",
        help="Directory to scan. Defaults to current directory.",
    )

    args = parser.parse_args()
    root = Path(args.directory).resolve()

    if not root.exists():
        raise SystemExit(f"Directory does not exist: {root}")

    if not root.is_dir():
        raise SystemExit(f"Not a directory: {root}")

    find_automations(root)


if __name__ == "__main__":
    main()

