#!/usr/bin/env python3

import argparse
import json
from collections import defaultdict
from pathlib import Path


def load_json(path: Path):
    """
    Load JSON files that may contain // comments.
    """

    text = path.read_text(encoding="utf-8")
    cleaned_lines = []

    for line in text.splitlines():
        if "//" in line:
            line = line.split("//", 1)[0]
        cleaned_lines.append(line)

    return json.loads("\n".join(cleaned_lines))


def main():
    parser = argparse.ArgumentParser(
        description="List named JSON entries and detect duplicates."
    )

    parser.add_argument(
        "-d",
        "--dir",
        default=".",
        help="Directory containing JSON files (default: current directory)",
    )

    parser.add_argument(
        "-t",
        "--type",
        action="append",
        help=(
            "Only process specific section types "
            "(example: -t actionLists -t functions)"
        ),
    )

    args = parser.parse_args()

    directory = Path(args.dir)

    if not directory.is_dir():
        raise SystemExit(f"Not a directory: {directory}")

    requested_types = set(args.type) if args.type else None

    lists = defaultdict(list)
    locations = defaultdict(lambda: defaultdict(list))

    json_files = sorted(directory.glob("*.json"))

    if not json_files:
        raise SystemExit(f"No .json files found in: {directory}")

    for json_file in json_files:
        try:
            data = load_json(json_file)
        except Exception as e:
            print(f"ERROR reading {json_file.name}: {e}")
            continue

        if not isinstance(data, dict):
            continue

        for section_name, section_value in data.items():

            # Skip unwanted section types
            if requested_types and section_name not in requested_types:
                continue

            if not isinstance(section_value, dict):
                continue

            for name in section_value.keys():
                lists[section_name].append(name)
                locations[section_name][name].append(json_file.name)

    if not lists:
        print("No matching section types found.")
        return

    #
    # Print sorted lists
    #
    for section_name in sorted(lists.keys(), key=str.lower):

        print()
        print(section_name)
        print("=" * len(section_name))

        for name in sorted(set(lists[section_name]), key=str.lower):
            print(name)

    #
    # Print duplicates
    #
    print()
    print("DUPLICATES")
    print("==========")

    found_duplicate = False

    for section_name in sorted(locations.keys(), key=str.lower):

        duplicates_in_section = False

        for name in sorted(locations[section_name].keys(), key=str.lower):

            files = locations[section_name][name]

            if len(files) > 1:

                if not duplicates_in_section:
                    print()
                    print(section_name)
                    print("-" * len(section_name))
                    duplicates_in_section = True

                found_duplicate = True

                print(name)

                for file_name in sorted(files):
                    print(f"  - {file_name}")

    if not found_duplicate:
        print("No duplicates found.")


if __name__ == "__main__":
    main()

