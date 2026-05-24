#!/usr/bin/env python3
"""
Generate a DragnCards-style Arkham Horror LCG TSV from ArkhamDB, filtered to
one or more packs and/or encounter sets/scenarios.

This version deliberately uses Python's csv module for both reading and writing
TSV, so quoted multiline card text is treated as one record instead of being
split into bogus rows. It can also flatten card text to one physical line per
card if your downstream parser is line-oriented.

Examples:
  python generate_arkhamdb_filtered_tsv_fixed.py --list-packs
  python generate_arkhamdb_filtered_tsv_fixed.py --list-encounter-sets drowned
  python generate_arkhamdb_filtered_tsv_fixed.py --scenario "Dreams" -o dreams.tsv
  python generate_arkhamdb_filtered_tsv_fixed.py --pack-code tdcc -o drowned_city_campaign.tsv

  # Avoid physical continuation lines in the TSV text column:
  python generate_arkhamdb_filtered_tsv_fixed.py --scenario "Dreams" --one-line-text -o dreams.tsv

  # Append missing rows to an existing master TSV, preserving existing rows:
  python generate_arkhamdb_filtered_tsv_fixed.py --scenario "Dreams" --append-to-template arkhamhorrorlcg.tsv -o merged.tsv
"""
from __future__ import annotations

import argparse
import csv
import html
import json
import re
import sys
import urllib.request
from collections import OrderedDict, defaultdict
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

ARKHAMDB = "https://arkhamdb.com"
CARDS_URL = f"{ARKHAMDB}/api/public/cards/?encounter=1"
PACKS_URL = f"{ARKHAMDB}/api/public/packs/"

HEADER = [
    "databaseId", "name", "imageUrl", "cardBack", "type", "subtype", "packName",
    "deckbuilderQuantity", "setUuid", "numberInPack", "encounterSet", "encounterNumber",
    "unique", "permanent", "starting", "exceptional", "myriad", "faction", "traits",
    "side", "xp", "cost", "skillWillpower", "skillIntellect", "skillCombat", "skillAgility",
    "skillWild", "health", "healthPerInvestigator", "sanity", "uses", "enemyDamage", "enemyHorror",
    "enemyFight", "enemyEvade", "shroud", "doom", "clues", "cluesFixed", "victoryPoints",
    "vengeance", "stage", "parallelContent", "code", "tabooId", "tabooName", "tabooXp",
    "action", "reaction", "free", "hasBonded", "concealed", "concealedId", "text",
]

TYPE_DISPLAY = {
    "investigator": "Investigator", "asset": "Asset", "event": "Event", "skill": "Skill",
    "treachery": "Treachery", "enemy": "Enemy", "location": "Location", "act": "Act",
    "agenda": "Agenda", "scenario": "Scenario", "story": "Story", "key": "Key",
    "enemy_location": "Enemy-Location", "treachery_asset": "Treachery-Asset",
}

FACTION_DISPLAY = {
    "guardian": "Guardian.", "seeker": "Seeker.", "rogue": "Rogue.", "mystic": "Mystic.",
    "survivor": "Survivor.", "neutral": "Neutral.", "mythos": "Mythos.",
}

PLAYER_TYPES = {"investigator", "asset", "event", "skill"}
ENCOUNTER_TYPES = {"enemy", "treachery", "location", "act", "agenda", "scenario", "story", "key", "enemy_location", "treachery_asset"}


def fetch_json(url: str) -> Any:
    req = urllib.request.Request(url, headers={"User-Agent": "dragncards-arkhamdb-tsv/1.1"})
    with urllib.request.urlopen(req, timeout=60) as response:
        charset = response.headers.get_content_charset() or "utf-8"
        return json.loads(response.read().decode(charset))


def clean_text(value: Any, *, newline_mode: str = "actual") -> str:
    """Clean ArkhamDB HTML-ish text.

    newline_mode:
      actual  -> keep real newlines; csv writer quotes the field correctly.
      escaped -> replace real newlines with literal \\n, so every card is one physical TSV line.
      space   -> replace newlines with spaces.
    """
    if value is None:
        return ""
    text = html.unescape(str(value))
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.I)
    text = re.sub(r"</p>\s*<p>", "\n\n", text, flags=re.I)
    text = re.sub(r"<[^>]+>", "", text)
    text = text.replace("\r\n", "\n").replace("\r", "\n").strip()
    if newline_mode == "escaped":
        return text.replace("\n", r"\n")
    if newline_mode == "space":
        return re.sub(r"\s*\n\s*", " ", text)
    return text


def s(card: Dict[str, Any], key: str, default: str = "") -> str:
    value = card.get(key, default)
    return "" if value is None else str(value)


def n(card: Dict[str, Any], key: str) -> str:
    value = card.get(key)
    return "" if value is None else str(value)


def bool01(card: Dict[str, Any], key: str) -> str:
    return "1" if bool(card.get(key)) else "0"


def image_url(path: Optional[str]) -> str:
    if not path:
        return ""
    if path.startswith(("http://", "https://")):
        return path
    return ARKHAMDB + path


def has_b_side(card: Dict[str, Any]) -> bool:
    return bool(card.get("backimagesrc") or card.get("back_text") or card.get("back_name"))


def card_back(card: Dict[str, Any]) -> str:
    if has_b_side(card) or card.get("hidden") or card.get("double_sided"):
        return "multi_sided"
    t = s(card, "type_code")
    if t in PLAYER_TYPES:
        return "Player Card"
    if t in ENCOUNTER_TYPES:
        return "Encounter Card"
    return "Player Card"


def display_type(type_code: str) -> str:
    return TYPE_DISPLAY.get(type_code, type_code.replace("_", " ").title())


def display_faction(code: str) -> str:
    parts = [p.strip() for p in code.split(".") if p.strip()] or ([code] if code else [])
    return " ".join(FACTION_DISPLAY.get(p, p.title() + ".") for p in parts)


def quantity(card: Dict[str, Any]) -> str:
    for key in ("quantity", "deck_limit"):
        if card.get(key) is not None:
            return str(card[key])
    return "1"


def build_row(card: Dict[str, Any], *, side: str, image_key: str, newline_mode: str,
              name_key: str = "name", text_key: str = "text", traits_key: str = "traits") -> Dict[str, str]:
    type_code = s(card, "type_code")
    real_traits = clean_text(card.get("real_traits") or card.get("traits") or "", newline_mode=newline_mode)
    raw_text_for_icons = s(card, text_key) or s(card, "text")
    row = {h: "" for h in HEADER}
    row.update({
        "databaseId": s(card, "code"),
        "name": clean_text(card.get(name_key) or card.get("name"), newline_mode=newline_mode),
        "imageUrl": image_url(card.get(image_key)),
        "cardBack": card_back(card),
        "type": display_type(type_code),
        "subtype": clean_text(card.get("subtype_name") or card.get("subtype_code") or "", newline_mode=newline_mode),
        "packName": clean_text(card.get("pack_name") or card.get("pack_code") or "", newline_mode=newline_mode),
        "deckbuilderQuantity": quantity(card),
        "setUuid": s(card, "pack_code"),
        "numberInPack": s(card, "position"),
        "encounterSet": clean_text(card.get("encounter_name") or card.get("encounter_code") or "", newline_mode=newline_mode),
        "encounterNumber": s(card, "encounter_position"),
        "unique": bool01(card, "is_unique"),
        "permanent": "1" if "Permanent." in real_traits or card.get("permanent") else "0",
        "starting": "1" if card.get("real_slot") == "Permanent" else "0",
        "exceptional": "1" if "Exceptional." in real_traits or card.get("exceptional") else "0",
        "myriad": "1" if "Myriad." in real_traits or card.get("myriad") else "0",
        "faction": display_faction(s(card, "faction_code")),
        "traits": clean_text(card.get(traits_key) or card.get("real_traits") or "", newline_mode=newline_mode),
        "side": side,
        "xp": n(card, "xp"),
        "cost": n(card, "cost"),
        "skillWillpower": n(card, "skill_willpower"),
        "skillIntellect": n(card, "skill_intellect"),
        "skillCombat": n(card, "skill_combat"),
        "skillAgility": n(card, "skill_agility"),
        "skillWild": n(card, "skill_wild"),
        "health": n(card, "health"),
        "healthPerInvestigator": "1" if card.get("health_per_investigator") else "0",
        "sanity": n(card, "sanity"),
        "uses": clean_text(card.get("uses") or "", newline_mode=newline_mode),
        "enemyDamage": n(card, "enemy_damage"),
        "enemyHorror": n(card, "enemy_horror"),
        "enemyFight": n(card, "enemy_fight"),
        "enemyEvade": n(card, "enemy_evade"),
        "shroud": n(card, "shroud"),
        "doom": n(card, "doom"),
        "clues": n(card, "clues"),
        "cluesFixed": "1" if card.get("clues_fixed") else "0",
        "victoryPoints": n(card, "victory"),
        "vengeance": n(card, "vengeance"),
        "stage": n(card, "stage"),
        "parallelContent": "1" if card.get("parallel") else "0",
        "code": s(card, "code"),
        "tabooId": s(card, "taboo_id", "0") or "0",
        "tabooName": clean_text(card.get("taboo_set_name") or "None", newline_mode=newline_mode),
        "tabooXp": s(card, "taboo_xp", "0") or "0",
        "action": "1" if "[action]" in raw_text_for_icons else "0",
        "reaction": "1" if "[reaction]" in raw_text_for_icons else "0",
        "free": "1" if "[free]" in raw_text_for_icons else "0",
        "hasBonded": "1" if card.get("bonded_to") else "0",
        "concealed": "1" if card.get("concealed") else "0",
        "concealedId": s(card, "concealed_id"),
        "text": clean_text(card.get(text_key) or "", newline_mode=newline_mode),
    })
    return row


def normalize(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.lower())


def any_match(card: Dict[str, Any], needles: Sequence[str], keys: Sequence[str]) -> bool:
    if not needles:
        return False
    hay = [normalize(s(card, k)) for k in keys]
    for needle in needles:
        nrm = normalize(needle)
        if any(nrm and nrm in h for h in hay):
            return True
    return False


def filter_cards(cards: List[Dict[str, Any]], args: argparse.Namespace) -> List[Dict[str, Any]]:
    filters_used = bool(args.pack_code or args.pack_name or args.scenario or args.encounter_set)
    if not filters_used:
        raise SystemExit("Refusing to generate the entire card pool. Use --pack-code, --pack-name, --scenario, or --encounter-set.")

    scenario_terms = list(args.scenario or []) + list(args.encounter_set or [])
    wanted = []
    for card in cards:
        ok = False
        if args.pack_code and any_match(card, args.pack_code, ["pack_code"]):
            ok = True
        if args.pack_name and any_match(card, args.pack_name, ["pack_name"]):
            ok = True
        if scenario_terms and any_match(card, scenario_terms, ["encounter_code", "encounter_name"]):
            ok = True
        if ok:
            wanted.append(card)
    return wanted


def dedupe_cards(cards: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    by_code: "OrderedDict[str, Dict[str, Any]]" = OrderedDict()
    for card in cards:
        code = s(card, "code")
        if code:
            by_code.setdefault(code, card)
    return list(by_code.values())


def rows_for_card(card: Dict[str, Any], *, newline_mode: str) -> List[Dict[str, str]]:
    if has_b_side(card):
        return [
            build_row(card, side="A", image_key="imagesrc", newline_mode=newline_mode),
            build_row(card, side="B", image_key="backimagesrc", name_key="back_name", text_key="back_text", traits_key="back_traits", newline_mode=newline_mode),
        ]
    return [build_row(card, side="", image_key="imagesrc", newline_mode=newline_mode)]


def row_key(row: Dict[str, str]) -> Tuple[str, str]:
    # side is blank for normal cards; A/B for multi-sided cards.
    return (row.get("databaseId", ""), row.get("side", ""))


def validate_rows(rows: List[Dict[str, str]]) -> None:
    seen: Dict[Tuple[str, str], int] = {}
    by_id: Dict[str, List[Dict[str, str]]] = defaultdict(list)
    for idx, row in enumerate(rows, start=2):  # +1 for header
        key = row_key(row)
        if key in seen:
            raise SystemExit(f"Duplicate TSV row for databaseId={key[0]!r}, side={key[1]!r} at output rows {seen[key]} and {idx}.")
        seen[key] = idx
        if row.get("databaseId"):
            by_id[row["databaseId"]].append(row)

    for dbid, group in by_id.items():
        if len(group) <= 1:
            continue
        sides = sorted(r.get("side", "") for r in group)
        backs = {r.get("cardBack", "") for r in group}
        if sides != ["A", "B"] or backs != {"multi_sided"}:
            raise SystemExit(
                f"databaseId {dbid} appears {len(group)} times but is not a clean multi_sided A/B pair "
                f"(sides={sides}, cardBacks={sorted(backs)})."
            )


def read_template_rows(path: str) -> Tuple[List[str], List[Dict[str, str]]]:
    with open(path, "r", newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f, delimiter="\t")
        if reader.fieldnames is None:
            raise SystemExit(f"Template {path!r} has no header row.")
        rows = [{h: (row.get(h) or "") for h in reader.fieldnames} for row in reader]
    return list(reader.fieldnames), rows


def write_tsv(rows: List[Dict[str, str]], output: str, *, header: Sequence[str]) -> None:
    validate_rows(rows)
    with open(output, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=list(header),
            delimiter="\t",
            extrasaction="ignore",
            lineterminator="\n",
            quoting=csv.QUOTE_MINIMAL,
            doublequote=True,
        )
        writer.writeheader()
        writer.writerows(rows)


def list_packs() -> None:
    packs = fetch_json(PACKS_URL)
    for p in packs:
        print(f"{p.get('code',''):<8} {p.get('name','')}")


def list_encounter_sets(cards: List[Dict[str, Any]], term: Optional[str]) -> None:
    seen: "OrderedDict[Tuple[str, str], int]" = OrderedDict()
    for c in cards:
        code = s(c, "encounter_code")
        name = s(c, "encounter_name")
        if code or name:
            seen[(code, name)] = seen.get((code, name), 0) + 1
    term_n = normalize(term or "")
    for (code, name), count in sorted(seen.items(), key=lambda item: (item[0][1], item[0][0])):
        if term_n and term_n not in normalize(code) and term_n not in normalize(name):
            continue
        print(f"{code:<30} {name:<50} {count:>4} cards")


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Generate selected DragnCards-style TSV rows from ArkhamDB.")
    p.add_argument("-o", "--output", default="arkhamhorrorlcg.filtered.tsv", help="Output TSV path")
    p.add_argument("--pack-code", action="append", help="ArkhamDB pack code to include, e.g. tdcc. May be repeated.")
    p.add_argument("--pack-name", action="append", help="Pack name substring to include. May be repeated.")
    p.add_argument("--scenario", action="append", help="Scenario/encounter set code or name substring to include. May be repeated.")
    p.add_argument("--encounter-set", action="append", help="Alias for --scenario. May be repeated.")
    p.add_argument("--append-to-template", metavar="TSV", help="Read an existing master TSV and append only missing generated rows.")
    p.add_argument("--text-newlines", choices=("actual", "escaped", "space"), default="actual", help="How to write newlines inside card text. Default: actual quoted newlines.")
    p.add_argument("--one-line-text", action="store_true", help="Shortcut for --text-newlines escaped; keeps every card on one physical line.")
    p.add_argument("--list-packs", action="store_true", help="List ArkhamDB pack codes and exit")
    p.add_argument("--list-encounter-sets", nargs="?", const="", metavar="FILTER", help="List encounter set codes/names, optionally filtered")
    return p.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    if args.one_line_text:
        args.text_newlines = "escaped"

    if args.list_packs:
        list_packs()
        return 0

    cards = fetch_json(CARDS_URL)

    if args.list_encounter_sets is not None:
        list_encounter_sets(cards, args.list_encounter_sets)
        return 0

    selected = dedupe_cards(filter_cards(cards, args))
    if not selected:
        raise SystemExit("No cards matched. Try --list-packs or --list-encounter-sets to find the exact code/name.")

    generated_rows: List[Dict[str, str]] = []
    for card in selected:
        generated_rows.extend(rows_for_card(card, newline_mode=args.text_newlines))

    if args.append_to_template:
        header, template_rows = read_template_rows(args.append_to_template)
        existing = {row_key(r) for r in template_rows}
        new_rows = []
        for r in generated_rows:
            # If the template header differs, still preserve the template schema.
            normalized = {h: r.get(h, "") for h in header}
            if row_key(normalized) not in existing:
                new_rows.append(normalized)
                existing.add(row_key(normalized))
        output_rows = template_rows + new_rows
        write_tsv(output_rows, args.output, header=header)
        print(f"Wrote {args.output} with {len(template_rows)} existing row(s) + {len(new_rows)} new row(s).")
    else:
        write_tsv(generated_rows, args.output, header=HEADER)
        print(f"Wrote {args.output} with {len(generated_rows)} TSV row(s) from {len(selected)} ArkhamDB card record(s).")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
