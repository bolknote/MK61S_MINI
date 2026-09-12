#!/usr/bin/env python3
"""Compile the 1966 CACM DOCTOR script into compact ELIZA.APP tables.

The generated include contains no parser and no editor. Keywords, pattern
operators, rule links, and captures are byte-coded; response text stays ASCII
so the final APP container can compress it efficiently with ZX0.
"""

from __future__ import annotations

import argparse
import hashlib
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE = ROOT / "examples/portable-apps/ELIZA/doctor-1966.txt"
DEFAULT_OUTPUT = ROOT / "examples/portable-apps/ELIZA/eliza_doctor_data.inc"

NO_ID = 0xFF
PAT_COUNT = 1
PAT_WORD = 2
PAT_ANY = 3
PAT_TAG = 4

REASSEMBLE_TEXT = 0
REASSEMBLE_LINK = 1
REASSEMBLE_NEWKEY = 2
REASSEMBLE_PRE = 3


@dataclass
class Transform:
    pattern: list
    reassemblies: list[list]


@dataclass
class Rule:
    keyword: str
    substitute: str | None = None
    rank: int = 0
    tags: list[str] = field(default_factory=list)
    transforms: list[Transform] = field(default_factory=list)
    link: str | None = None


class WordTable:
    def __init__(self) -> None:
        self.words: list[str] = []
        self.ids: dict[str, int] = {}

    def add(self, word: str) -> int:
        if word not in self.ids:
            if len(self.words) >= NO_ID:
                raise ValueError("ELIZA matcher vocabulary no longer fits in one byte")
            word.encode("ascii")
            self.ids[word] = len(self.words)
            self.words.append(word)
        return self.ids[word]

    def get(self, word: str) -> int:
        return self.ids[word]


def tokenize(text: str) -> list[str]:
    without_comments = "\n".join(line.split(";", 1)[0]
                                  for line in text.splitlines())
    return re.findall(r"\(|\)|=|[^\s()=]+", without_comments)


def parse_forms(tokens: list[str]) -> list:
    position = 0

    def expression():
        nonlocal position
        if position >= len(tokens):
            raise ValueError("unexpected end of DOCTOR script")
        token = tokens[position]
        position += 1
        if token != "(":
            if token == ")":
                raise ValueError("unexpected ')' in DOCTOR script")
            return token
        result = []
        while position < len(tokens) and tokens[position] != ")":
            result.append(expression())
        if position >= len(tokens):
            raise ValueError("unterminated list in DOCTOR script")
        position += 1
        return result

    forms = []
    while position < len(tokens):
        forms.append(expression())
    return forms


def group_items(group: list) -> tuple[str, list[str]]:
    if not isinstance(group, list) or not group or not isinstance(group[0], str):
        raise ValueError(f"invalid match group: {group!r}")
    head = group[0]
    if head in ("*", "/"):
        marker = head
        values = group[1:]
    elif head[0] in "*/":
        marker = head[0]
        values = ([head[1:]] if len(head) > 1 else []) + group[1:]
    else:
        raise ValueError(f"invalid match group: {group!r}")
    if not values or not all(isinstance(value, str) for value in values):
        raise ValueError(f"empty or invalid match group: {group!r}")
    return marker, values


def tag_items(group: list) -> list[str]:
    marker, values = group_items(group)
    if marker != "/":
        raise ValueError(f"expected DLIST tag group, got {group!r}")
    return values


def is_number(value) -> bool:
    return isinstance(value, str) and value.isdigit()


def parse_script(text: str) -> tuple[list[Rule], str, list[Transform]]:
    forms = parse_forms(tokenize(text))
    if len(forms) < 4 or not isinstance(forms[0], list) or forms[1] != "START":
        raise ValueError("unexpected DOCTOR script prologue")

    rules: list[Rule] = []
    memory_keyword: str | None = None
    memory_transforms: list[Transform] = []
    saw_end = False

    for form in forms[2:]:
        if form == []:
            saw_end = True
            break
        if not isinstance(form, list) or not form or not isinstance(form[0], str):
            raise ValueError(f"invalid top-level form: {form!r}")
        if form[0] == "MEMORY":
            if memory_keyword is not None or len(form) != 6:
                raise ValueError("DOCTOR must contain one four-way MEMORY rule")
            memory_keyword = form[1]
            for item in form[2:]:
                if not isinstance(item, list) or "=" not in item:
                    raise ValueError(f"invalid MEMORY transformation: {item!r}")
                equals = item.index("=")
                memory_transforms.append(
                    Transform(item[:equals], [item[equals + 1:]]))
            continue

        rule = Rule(form[0])
        index = 1
        while index < len(form):
            item = form[index]
            if item == "=":
                if index + 1 >= len(form) or not isinstance(form[index + 1], str):
                    raise ValueError(f"missing substitution in {rule.keyword}")
                rule.substitute = form[index + 1]
                index += 2
            elif is_number(item):
                rule.rank = int(item)
                if rule.rank > 255:
                    raise ValueError(f"rank does not fit byte in {rule.keyword}")
                index += 1
            elif item == "DLIST":
                if index + 1 >= len(form):
                    raise ValueError(f"missing DLIST in {rule.keyword}")
                rule.tags.extend(tag_items(form[index + 1]))
                index += 2
            elif isinstance(item, list) and item[:1] == ["="]:
                if len(item) != 2:
                    raise ValueError(f"invalid link in {rule.keyword}: {item!r}")
                rule.link = item[1]
                index += 1
            elif isinstance(item, list) and item and isinstance(item[0], list):
                if len(item) < 2 or not all(isinstance(value, list) for value in item):
                    raise ValueError(f"invalid transformation in {rule.keyword}")
                rule.transforms.append(Transform(item[0], item[1:]))
                index += 1
            else:
                raise ValueError(f"unexpected item in {rule.keyword}: {item!r}")
        rules.append(rule)

    if not saw_end or memory_keyword is None or len(memory_transforms) != 4:
        raise ValueError("incomplete DOCTOR script")
    if len({rule.keyword for rule in rules}) != len(rules):
        raise ValueError("duplicate keyword")
    return rules, memory_keyword, memory_transforms


def collect_pattern_words(pattern: list, words: WordTable) -> None:
    for term in pattern:
        if is_number(term):
            continue
        if isinstance(term, str):
            words.add(term)
            continue
        marker, values = group_items(term)
        if marker == "*":
            for value in values:
                words.add(value)


def collect_pre_words(reassembly: list, words: WordTable) -> None:
    if not reassembly or reassembly[0] != "PRE":
        return
    if len(reassembly) != 3 or not isinstance(reassembly[1], list):
        raise ValueError(f"invalid PRE reassembly: {reassembly!r}")
    for item in reassembly[1]:
        if not is_number(item):
            if not isinstance(item, str):
                raise ValueError(f"invalid PRE item: {item!r}")
            words.add(item)


def encode_pattern(pattern: list, words: WordTable,
                   tag_bits: dict[str, int]) -> bytes:
    encoded = bytearray()
    for term in pattern:
        if is_number(term):
            value = int(term)
            if value > 255:
                raise ValueError(f"pattern count does not fit byte: {term}")
            encoded.extend((PAT_COUNT, value))
        elif isinstance(term, str):
            encoded.extend((PAT_WORD, words.get(term)))
        else:
            marker, values = group_items(term)
            if marker == "*":
                if len(values) > 255:
                    raise ValueError("choice list does not fit byte")
                encoded.extend((PAT_ANY, len(values)))
                encoded.extend(words.get(value) for value in values)
            else:
                mask = 0
                for value in values:
                    mask |= 1 << tag_bits[value]
                encoded.extend((PAT_TAG, mask))
    return bytes(encoded)


def template_bytes(items: list) -> bytes:
    encoded: list[bytes] = []
    for item in items:
        if is_number(item):
            index = int(item)
            if not 1 <= index <= 9:
                raise ValueError(f"capture index outside 1..9: {item}")
            encoded.append(bytes((index,)))
        elif isinstance(item, str):
            encoded.append(item.encode("ascii"))
        else:
            raise ValueError(f"nested list in text template: {item!r}")
    return b" ".join(encoded) + b"\0"


def encode_reassembly(items: list, rule_ids: dict[str, int]) -> bytes:
    if items == ["NEWKEY"]:
        return bytes((REASSEMBLE_NEWKEY,))
    if items[:1] == ["="]:
        if len(items) != 2:
            raise ValueError(f"invalid linked reassembly: {items!r}")
        return bytes((REASSEMBLE_LINK, rule_ids[items[1]]))
    if items[:1] == ["PRE"]:
        if (len(items) != 3 or not isinstance(items[1], list) or
                not isinstance(items[2], list) or items[2][:1] != ["="] or
                len(items[2]) != 2):
            raise ValueError(f"invalid PRE reassembly: {items!r}")
        return bytes((REASSEMBLE_PRE, rule_ids[items[2][1]])) + \
            template_bytes(items[1])
    return bytes((REASSEMBLE_TEXT,)) + template_bytes(items)


def c_string(data: bytes) -> str:
    result = []
    for value in data:
        if value == ord('"'):
            result.append('\\"')
        elif value == ord('\\'):
            result.append('\\\\')
        elif 0x20 <= value <= 0x7E:
            result.append(chr(value))
        else:
            result.append(f"\\{value:03o}")
    return '"' + "".join(result) + '"'


def numeric_array(values: Iterable[int], per_line: int = 16,
                  formatter=lambda value: str(value)) -> str:
    values = list(values)
    lines = []
    for index in range(0, len(values), per_line):
        lines.append("  " + ", ".join(formatter(value)
                                      for value in values[index:index + per_line]))
    return ",\n".join(lines)


def compile_script(source: Path) -> str:
    source_bytes = source.read_bytes()
    text = source_bytes.decode("utf-8")
    rules, memory_keyword, memory_transforms = parse_script(text)
    if len(rules) >= NO_ID:
        raise ValueError("DOCTOR rule count does not fit one byte")
    rule_ids = {rule.keyword: index for index, rule in enumerate(rules)}
    if "NONE" not in rule_ids or memory_keyword not in rule_ids:
        raise ValueError("missing NONE or MEMORY keyword rule")

    tags: list[str] = []
    for rule in rules:
        for tag in rule.tags:
            if tag not in tags:
                tags.append(tag)
    if len(tags) > 8:
        raise ValueError("DOCTOR tag set does not fit one byte")
    tag_bits = {tag: index for index, tag in enumerate(tags)}

    words = WordTable()
    for rule in rules:
        if rule.keyword != "NONE":
            words.add(rule.keyword)
        if rule.substitute:
            words.add(rule.substitute)
        for transform in rule.transforms:
            collect_pattern_words(transform.pattern, words)
            for reassembly in transform.reassemblies:
                collect_pre_words(reassembly, words)
    for transform in memory_transforms:
        collect_pattern_words(transform.pattern, words)
    words.add("BUT")

    word_tags = [0] * len(words.words)
    word_rules = [NO_ID] * len(words.words)
    for rule_id, rule in enumerate(rules):
        if rule.keyword == "NONE":
            continue
        word_id = words.get(rule.keyword)
        word_rules[word_id] = rule_id
        for tag in rule.tags:
            word_tags[word_id] |= 1 << tag_bits[tag]

    pattern_blob = bytearray()
    pattern_offsets: dict[bytes, int] = {}
    reassembly_blob = bytearray()
    reassembly_offsets_by_data: dict[bytes, int] = {}
    reassembly_offsets: list[int] = []
    compiled_transforms: list[tuple[int, int, int, int]] = []

    def store_pattern(pattern: list) -> tuple[int, int]:
        encoded = encode_pattern(pattern, words, tag_bits)
        if encoded not in pattern_offsets:
            pattern_offsets[encoded] = len(pattern_blob)
            pattern_blob.extend(encoded)
        return pattern_offsets[encoded], len(encoded)

    def store_reassembly(reassembly: list) -> int:
        encoded = encode_reassembly(reassembly, rule_ids)
        if encoded not in reassembly_offsets_by_data:
            reassembly_offsets_by_data[encoded] = len(reassembly_blob)
            reassembly_blob.extend(encoded)
        return reassembly_offsets_by_data[encoded]

    def store_transform(transform: Transform) -> int:
        if len(transform.pattern) > 9 or len(transform.reassemblies) > 255:
            raise ValueError("DOCTOR transformation exceeds bytecode limits")
        pattern_offset, pattern_size = store_pattern(transform.pattern)
        first_reassembly = len(reassembly_offsets)
        for reassembly in transform.reassemblies:
            reassembly_offsets.append(store_reassembly(reassembly))
        compiled_transforms.append((pattern_offset, first_reassembly,
                                    pattern_size, len(transform.reassemblies)))
        return len(compiled_transforms) - 1

    compiled_rules = []
    for rule in rules:
        first_transform = len(compiled_transforms)
        for transform in rule.transforms:
            store_transform(transform)
        compiled_rules.append((
            words.get(rule.substitute) if rule.substitute else NO_ID,
            rule.rank,
            first_transform,
            len(rule.transforms),
            rule_ids[rule.link] if rule.link else NO_ID,
        ))

    memory_transform_ids = [store_transform(transform)
                            for transform in memory_transforms]

    word_pool = bytearray()
    word_offsets = []
    word_lengths = []
    for word in words.words:
        word_offsets.append(len(word_pool))
        encoded = word.encode("ascii")
        word_lengths.append(len(encoded))
        word_pool.extend(encoded)
        word_pool.append(0)

    if (len(word_pool) > 65535 or len(pattern_blob) > 65535 or
            len(reassembly_blob) > 65535 or len(reassembly_offsets) > 65535):
        raise ValueError("DOCTOR bytecode offsets no longer fit uint16_t")

    lines = [
        "/* Generated by tools/generate_eliza_doctor.py; do not edit. */",
        "/* Source: Anthony Hay's CC0 transcription of the 1966 CACM DOCTOR script. */",
        f"#define ELIZA_DOCTOR_SOURCE_SHA256 \"{hashlib.sha256(source_bytes).hexdigest()}\"",
        f"#define ELIZA_SCRIPT_WORD_COUNT {len(words.words)}U",
        f"#define ELIZA_SCRIPT_RULE_COUNT {len(rules)}U",
        f"#define ELIZA_SCRIPT_TRANSFORM_COUNT {len(compiled_transforms)}U",
        f"#define ELIZA_SCRIPT_NONE_RULE {rule_ids['NONE']}U",
        f"#define ELIZA_SCRIPT_MEMORY_RULE {rule_ids[memory_keyword]}U",
        f"#define ELIZA_SCRIPT_BUT_WORD {words.get('BUT')}U",
        "",
        f"static const char eliza_script_word_pool[{len(word_pool)}] =",
    ]
    for word in words.words:
        lines.append("  " + c_string(word.encode("ascii") + b"\0"))
    lines[-1] += ";"
    lines += [
        "",
        "static const uint16_t eliza_script_word_offsets[ELIZA_SCRIPT_WORD_COUNT] = {",
        numeric_array(word_offsets, 12),
        "};",
        "static const uint8_t eliza_script_word_lengths[ELIZA_SCRIPT_WORD_COUNT] = {",
        numeric_array(word_lengths, 16),
        "};",
        "static const uint8_t eliza_script_word_tags[ELIZA_SCRIPT_WORD_COUNT] = {",
        numeric_array(word_tags, 16),
        "};",
        "static const uint8_t eliza_script_word_rules[ELIZA_SCRIPT_WORD_COUNT] = {",
        numeric_array(word_rules, 16,
                      lambda value: "ELIZA_NO_ID" if value == NO_ID else str(value)),
        "};",
        "",
        "static const ElizaRuleData eliza_script_rules[ELIZA_SCRIPT_RULE_COUNT] = {",
    ]
    for rule, values in zip(rules, compiled_rules):
        substitute, rank, first_transform, transform_count, link = values
        sub_text = "ELIZA_NO_ID" if substitute == NO_ID else str(substitute)
        link_text = "ELIZA_NO_ID" if link == NO_ID else str(link)
        lines.append(f"  {{{sub_text}, {rank}, {first_transform}, "
                     f"{transform_count}, {link_text}}}, /* {rule.keyword} */")
    lines += [
        "};",
        "",
        "static const ElizaTransformData eliza_script_transforms[ELIZA_SCRIPT_TRANSFORM_COUNT] = {",
    ]
    for pattern_offset, first_reassembly, pattern_size, count in compiled_transforms:
        lines.append(f"  {{{pattern_offset}, {first_reassembly}, "
                     f"{pattern_size}, {count}}},")
    lines += [
        "};",
        "",
        f"static const uint8_t eliza_script_patterns[{len(pattern_blob)}] = {{",
        numeric_array(pattern_blob, 20, lambda value: f"0x{value:02x}"),
        "};",
        "",
        f"static const uint16_t eliza_script_reassembly_offsets[{len(reassembly_offsets)}] = {{",
        numeric_array(reassembly_offsets, 12),
        "};",
        "",
        f"static const unsigned char eliza_script_reassemblies[{len(reassembly_blob)}] =",
    ]
    for encoded, _offset in sorted(reassembly_offsets_by_data.items(),
                                   key=lambda item: item[1]):
        lines.append("  " + c_string(encoded))
    lines[-1] += ";"
    lines += [
        "",
        "static const uint8_t eliza_script_memory_transforms[4] = {",
        "  " + ", ".join(str(value) for value in memory_transform_ids),
        "};",
        "",
    ]
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--check", action="store_true",
                        help="fail if the checked-in generated include is stale")
    args = parser.parse_args()
    generated = compile_script(args.source)
    if args.check:
        current = args.output.read_text() if args.output.exists() else ""
        if current != generated:
            parser.exit(1, f"stale generated ELIZA data: {args.output}\n")
        return
    args.output.write_text(generated)


if __name__ == "__main__":
    main()
