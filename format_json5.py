#!/usr/bin/env python3

import argparse
import re
from pathlib import Path

INDENT = 2


TOKEN_RE = re.compile(
    r'''
    (?P<ws>\s+)
  | (?P<line>//[^\n]*)
  | (?P<block>/\*.*?\*/)
  | (?P<string>"(?:\\.|[^"\\])*")
  | (?P<number>-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)
  | (?P<word>true|false|null)
  | (?P<punc>[{}\[\]:,])
    ''',
    re.DOTALL | re.VERBOSE,
)


def tokenize(text):
    tokens = []
    pos = 0

    while pos < len(text):
        m = TOKEN_RE.match(text, pos)
        if not m:
            raise ValueError(f"Unexpected text near: {text[pos:pos+40]!r}")

        kind = m.lastgroup
        value = m.group()

        if kind != "ws":
            tokens.append((kind, value))

        pos = m.end()

    return tokens


class Parser:
    def __init__(self, tokens):
        self.tokens = tokens
        self.i = 0

    def peek(self):
        return self.tokens[self.i] if self.i < len(self.tokens) else None

    def pop(self):
        tok = self.peek()
        self.i += 1
        return tok

    def parse_value(self):
        leading = []

        while self.peek() and self.peek()[0] in ("line", "block"):
            leading.append(self.pop()[1])

        tok = self.peek()

        if tok is None:
            return {"type": "empty", "leading": leading}

        kind, val = tok

        if val == "{":
            node = self.parse_object()
        elif val == "[":
            node = self.parse_array()
        else:
            self.pop()
            node = {"type": "primitive", "value": val}

        node["leading"] = leading
        return node

    def parse_object(self):
        self.pop()  # {

        items = []

        while self.peek() and self.peek()[1] != "}":
            comments = []
            while self.peek() and self.peek()[0] in ("line", "block"):
                comments.append(self.pop()[1])

            key = self.pop()[1]
            self.pop()  # :

            value = self.parse_value()

            trailing = []
            while self.peek() and self.peek()[0] in ("line", "block"):
                trailing.append(self.pop()[1])

            if self.peek() and self.peek()[1] == ",":
                self.pop()

            items.append({
                "comments": comments,
                "key": key,
                "value": value,
                "trailing": trailing,
            })

        self.pop()  # }
        return {"type": "object", "items": items}

    def parse_array(self):
        self.pop()  # [

        items = []

        while self.peek() and self.peek()[1] != "]":
            value = self.parse_value()

            trailing = []
            while self.peek() and self.peek()[0] in ("line", "block"):
                trailing.append(self.pop()[1])

            if self.peek() and self.peek()[1] == ",":
                self.pop()

            items.append({
                "value": value,
                "trailing": trailing,
            })

        self.pop()  # ]
        return {"type": "array", "items": items}


def is_primitive_array(node):
    return (
        node["type"] == "array"
        and all(item["value"]["type"] == "primitive" for item in node["items"])
        and all(not item["value"].get("leading") for item in node["items"])
        and all(not item.get("trailing") for item in node["items"])
    )

def is_simple_object(obj):
    return (
        obj["type"] == "object"
        and all(
            item["value"]["type"] == "primitive"
            and not item["value"].get("leading")
            and not item.get("comments")
            and not item.get("trailing")
            for item in obj["items"]
        )
    )

def fmt(node, level=0):
    pad = " " * (level * INDENT)
    inner = " " * ((level + 1) * INDENT)

    leading = node.get("leading", [])
    prefix = ""
    if leading:
        prefix = "\n".join(pad + c for c in leading) + "\n"

    if node["type"] == "primitive":
        return prefix + node["value"]

    if node["type"] == "array":
        if not node["items"]:
            return prefix + "[]"

        if is_primitive_array(node):
            values = [item["value"]["value"] for item in node["items"]]
            return prefix + "[" + ", ".join(values) + "]"

        lines = []
        for idx, item in enumerate(node["items"]):
            line = inner + fmt(item["value"], level + 1)
            if idx < len(node["items"]) - 1:
                line += ","

            if item["trailing"]:
                line += " " + " ".join(item["trailing"])

            lines.append(line)

        return prefix + "[\n" + "\n".join(lines) + f"\n{pad}]"

    if node["type"] == "object":
        if not node["items"]:
            return prefix + "{}"

        # Inline simple objects
        if is_simple_object(node):
            parts = []

            for item in node["items"]:
                parts.append(
                    f'{item["key"]}: {item["value"]["value"]}'
                )

            return prefix + "{ " + ", ".join(parts) + " }"

        lines = []

        for idx, item in enumerate(node["items"]):
            for c in item["comments"]:
                lines.append(inner + c)

            line = inner + item["key"] + ": " + fmt(item["value"], level + 1)

            if idx < len(node["items"]) - 1:
                line += ","

            if item["trailing"]:
                line += " " + " ".join(item["trailing"])

            lines.append(line)

        return prefix + "{\n" + "\n".join(lines) + f"\n{pad}" + "}"

    return ""


def format_file(path: Path):
    text = path.read_text(encoding="utf-8")
    tokens = tokenize(text)
    tree = Parser(tokens).parse_value()
    path.write_text(fmt(tree) + "\n", encoding="utf-8")
    print(f"Formatted {path}")


def main():
    ap = argparse.ArgumentParser(
        description="Format JSONC/JSON5-ish files while preserving comments and keeping primitive arrays inline."
    )

    ap.add_argument("-d", "--dir", type=Path, help="Directory containing .json files")
    ap.add_argument("-f", "--file", type=Path, action="append", help="Specific file to format; may be used multiple times")

    args = ap.parse_args()

    files = []

    if args.dir:
        files.extend(sorted(args.dir.glob("*.json")))

    if args.file:
        files.extend(args.file)

    if not files:
        raise SystemExit("Use -d/--dir or -f/--file")

    for file in files:
        format_file(file)


if __name__ == "__main__":
    main()

