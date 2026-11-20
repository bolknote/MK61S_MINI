"""Recognize explicit repetition, replacement by sign, and absolute value clauses."""

import re

from cf_language import (
    DESTINATION, FUNCTION_NAME, NAMES, MODES, PREVIOUS_VALUE, RESULT,
    SEQUENCE, STORE_VERB, argument, expanded_parse, read_operation, register, resolve,
)


COUNT = r"(?:дважды(?: подряд)?|два раза(?: подряд)?)"
APPLY = r"(?:примени(?:те)?|применить)"
REPEAT = re.compile(
    rf"(?:{COUNT} {APPLY} ({FUNCTION_NAME})|{APPLY} ({FUNCTION_NAME}) {COUNT}|"
    rf"{APPLY} {COUNT} ({FUNCTION_NAME}))(?: к (.+))?"
)
REPLACE_SIGN = re.compile(
    r"(?:замени(?:те|ть)? (?:полученн(?:ый результат|ое значение|ое число)|результат) его знаком|"
    r"(?:полученн(?:ый результат|ое значение|ое число)|результат) замени(?:те|ть)? его знаком)"
)
ABSOLUTE = re.compile(r"(?:взяв |взять |возьми(?:те)? |вычисли(?:те|ть)? |найди(?:те)? )?(.+) по модулю")
EMPTY_ABSOLUTE = re.compile(r"(?:возьми(?:те)?|взять) по модулю")
STORE = re.compile(rf"(?:{RESULT} )?{STORE_VERB}(?: {RESULT})? {DESTINATION}")
RESULT_QUESTION = re.compile(r"[.;]\s*(?:какой результат|что (?:получится|выйдет|получилось))$")
CLAUSES = re.compile(r"[,.!?;] +(?:и +)?| +и +")


def read_clause(clause, previous):
    if match := REPEAT.fullmatch(clause):
        name = next(value for value in match.groups()[:3] if value is not None)
        operand = argument(match[4]) if match[4] else PREVIOUS_VALUE
        return [NAMES[name], [NAMES[name], operand]], True
    if REPLACE_SIGN.fullmatch(clause):
        return ["sign", PREVIOUS_VALUE], True
    if EMPTY_ABSOLUTE.fullmatch(clause):
        return ["abs", PREVIOUS_VALUE], True
    if match := ABSOLUTE.fullmatch(clause):
        operand = argument(match[1])
        if isinstance(operand, list):
            raise ValueError("unclear scope of absolute value")
        return ["abs", operand], True
    return read_operation(clause, previous), False


def parse_added_rules(text, angle):
    text = re.sub(r"\s+", " ", text.strip().lower()).replace("ё", "е").replace("−", "-")
    text = RESULT_QUESTION.sub("", text.rstrip(".!?"))
    clauses = CLAUSES.split(text)
    if not 1 <= len(clauses) <= 12:
        raise ValueError("unsupported clause count")
    previous = None
    destination = None
    used_new_rule = False
    for clause in clauses:
        clause = SEQUENCE.sub("", clause.strip())
        if destination is not None:
            raise ValueError("unexpected text after destination")
        if match := STORE.fullmatch(clause):
            if previous is None:
                raise ValueError("no result to store")
            destination = register(match[1])
            continue
        expression, is_new = read_clause(clause, previous)
        value, uses = resolve(expression, previous)
        if previous is not None and (uses != 1 or not isinstance(expression, list)):
            raise ValueError("ambiguous previous result")
        previous = value
        used_new_rule |= is_new
    if previous is None or not used_new_rule:
        return None
    return {"X": previous, "writes": {destination: previous} if destination else {}, "angle": angle}


def parse_task(text, angle):
    """Allow new syntax only after consuming the entire task."""
    established = expanded_parse(text, angle)
    if established is not None:
        return established
    if not 1 <= len(text) <= 640 or angle not in MODES.values() or "(" in text or ")" in text:
        return None
    try:
        return parse_added_rules(text, angle)
    except (ValueError, ArithmeticError, RecursionError):
        return None
