#!/usr/bin/env python3

import argparse
import json
from pathlib import Path


def strip_json_comments(text: str) -> str:
    """Remove // comments while preserving quoted strings."""
    result = []
    in_string = False
    escape = False
    i = 0

    while i < len(text):
        char = text[i]

        if in_string:
            result.append(char)

            if escape:
                escape = False
            elif char == "\\":
                escape = True
            elif char == '"':
                in_string = False

            i += 1
            continue

        if char == '"':
            in_string = True
            result.append(char)
            i += 1
            continue

        if char == "/" and i + 1 < len(text) and text[i + 1] == "/":
            while i < len(text) and text[i] not in "\r\n":
                i += 1
            continue

        result.append(char)
        i += 1

    return "".join(result)


def format_arg(arg) -> str:
    if isinstance(arg, str):
        return arg

    return json.dumps(arg, ensure_ascii=False)


def print_compact(function_name: str, function_args: list) -> None:
    arg_text = ", ".join(format_arg(arg) for arg in function_args)

    print(f"{function_name}:")
    print(f"    ({arg_text})")
    print()


def print_multiline(function_name: str, function_args: list) -> None:
    print(f"{function_name}:")

    for arg in function_args:
        print(f"    {format_arg(arg)}")

    print()


def print_markdown(function_name: str, function_args: list) -> None:
    print(f"## {function_name}")
    print()

    if not function_args:
        print("_No args_")
    else:
        for arg in function_args:
            print(f"- `{format_arg(arg)}`")

    print()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="List DragnCards function names and required args."
    )

    parser.add_argument(
        "-i",
        "--input",
        required=True,
        help="Input JSON/JSONC file",
    )

    parser.add_argument(
        "-f",
        "--format",
        choices=["compact", "multiline", "markdown"],
        default="compact",
        help="Output format: compact, multiline, or markdown",
    )

    args = parser.parse_args()

    input_path = Path(args.input)

    if not input_path.exists():
        raise FileNotFoundError(f"Input file not found: {input_path}")

    text = input_path.read_text(encoding="utf-8")
    clean_text = strip_json_comments(text)
    data = json.loads(clean_text)

    functions = data.get("functions", {})

    if not functions:
        print("No functions found.")
        return

    for function_name in sorted(functions):
        function = functions[function_name]
        function_args = function.get("args", [])

        if args.format == "compact":
            print_compact(function_name, function_args)
        elif args.format == "multiline":
            print_multiline(function_name, function_args)
        elif args.format == "markdown":
            print_markdown(function_name, function_args)


if __name__ == "__main__":
    main()

