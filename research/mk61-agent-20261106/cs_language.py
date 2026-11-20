"""Parse scope-explicit nested arithmetic without consulting the model."""

from functools import lru_cache
import re

from cf_language import (ANGLE_SUFFIX, BINARY_RULES, MODES, NAMES, PROGRAM_PREFIX,
                         QUESTION_PREFIX, UNARY, argument, register, remove_preposition)
from cq_language import PRESERVE, STORE, X_ONLY, independent_spec, normalize


EVALUATE = re.compile(r"^(?:(?:найди(?:те)?|вычисли(?:те)?|посчитай(?:те)?|определи(?:те)?):? +|"
                      r"(?:нужна программа мк-61 для следующего вычисления|мне нужно вычислить это выражение): +)")
STOP = re.compile(r"[.!?;] +(?:после вычисления )?остановись$")
NEGATE = re.compile(r"(.+) с противоположным знаком")
UNARY_EXTENDED = re.compile(r"(целая часть с отсечением к нулю|дробная часть с исходным знаком) от (.+)")
NAMED = {"сумма": "+", "разность": "-", "произведение": "*", "частное": "/"}
NAMED_BINARY = re.compile(r"(сумма|разность|произведение|частное) (?:значений |чисел )?(.+) и (.+)")
NAMED_POWER = re.compile(r"степень с основанием (.+) и показателем (.+)")
TEN_POWER = re.compile(r"(?:десять|10) в степени (.+)")
BINARY = tuple((op, re.compile(pattern), order) for op, pattern, order in (
    *BINARY_RULES,
    ("*", r"значение (.+?) (?:надо |нужно )?умножить на (.+)", (1, 2)),
    ("/", r"числитель дроби равен (.+), знаменатель равен (.+)\. вычисли дробь", (1, 2)),
    ("+", r"(.+) (?:плюс|\+) (.+)", (1, 2)),
    ("-", r"(.+) (?:минус|-) (.+)", (1, 2)),
    ("*", r"(.+) (?:умножить на|\*) (.+)", (1, 2)),
    ("/", r"(.+) (?:разделить на|/) (.+)", (1, 2)),
))


def groups(text):
    """Hide complete parenthesized operands from the enclosing operator."""
    depth = 0
    start = head = 0
    parts = []
    operands = {}
    for at, char in enumerate(text):
        if char == "(":
            if depth == 0:
                start = at
            depth += 1
        elif char == ")":
            depth -= 1
            if depth < 0:
                raise ValueError("unmatched closing parenthesis")
            if depth == 0:
                token = f"@{len(operands)}@"
                operands[token] = text[start + 1:at].strip()
                parts.extend((text[head:start], token))
                head = at + 1
    if depth:
        raise ValueError("unclosed operand")
    parts.append(text[head:])
    return "".join(parts), operands


def expression(text, depth=0):
    if depth >= 8:
        raise ValueError("expression is too deep")
    flat, contents = groups(text)

    def operand(fragment):
        fragment = fragment.strip()
        if fragment in contents:
            return expression(contents[fragment], depth + 1)
        if (match := re.fullmatch(r"(?:числ[оа]|значени[еяю]) (.+)", fragment)) and match[1] in contents:
            return expression(contents[match[1]], depth + 1)
        value = argument(fragment)
        if not isinstance(value, (dict, str)):
            raise ValueError("compound operand requires parentheses")
        return value

    if match := NEGATE.fullmatch(flat):
        return ["neg", operand(match[1])]
    if flat.startswith("минус ") and flat[6:] in contents:
        return ["neg", operand(flat[6:])]
    if match := NAMED_POWER.fullmatch(flat):
        return ["pow", operand(match[1]), operand(match[2])]
    if match := NAMED_BINARY.fullmatch(flat):
        return [NAMED[match[1]], operand(match[2]), operand(match[3])]
    if match := TEN_POWER.fullmatch(flat):
        return ["pow10", operand(match[1])]
    if match := UNARY_EXTENDED.fullmatch(flat):
        return ["int" if match[1].startswith("целая") else "frac", operand(match[2])]
    for operator, pattern, order in BINARY:
        if match := pattern.fullmatch(flat):
            try:
                return [operator, *(operand(match[index]) for index in order)]
            except (ValueError, ArithmeticError):
                continue
    if (match := UNARY.fullmatch(flat)) and match[2] is not None:
        operator = NAMES[match[1]]
        return [operator, operand(remove_preposition(match[2], operator))]
    return operand(flat)


def nested_spec(text, angle):
    if not 1 <= len(text) <= 640 or angle not in MODES.values() or "(" not in text or "@" in text:
        return None
    text = normalize(text)
    if match := ANGLE_SUFFIX.search(text):
        if MODES[match[1]] != angle:
            return None
        text = text[:match.start()].rstrip(" .!?;")
    text = STOP.sub("", PRESERVE.sub("", text)).rstrip(" .!?;")
    destination = None
    if match := STORE.search(text):
        destination = register(match["destination"])
        text = text[:match.start()]
    text = X_ONLY.sub("", text).rstrip(" .!?;")
    for prefix in (PROGRAM_PREFIX, QUESTION_PREFIX, EVALUATE):
        if match := prefix.match(text):
            text = text[match.end():]
            break
    value = expression(text)
    return {"X": value, "writes": {destination: value} if destination else {}, "angle": angle}


@lru_cache(maxsize=4096)
def parse_task(text, angle):
    if existing := independent_spec(text, angle):
        return existing
    try:
        return nested_spec(text, angle)
    except (ValueError, ArithmeticError):
        return None
