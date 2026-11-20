"""Independent parsing of an explicit base and exponent in Russian."""

from functools import lru_cache
import re

from ce_short_path import NUMBER
from cf_language import (ANGLE_SUFFIX, ARGUMENT_REGISTER, MODES, REGISTER, RESULT,
                         STORE_VERB, argument, register)
from cg_language import parse_task as existing_parse


ATOM = rf"(?:{ARGUMENT_REGISTER}|(?:числ[оа] )?(?:(?:минус )?{NUMBER}|ноль|два|десять|единиц[ау]|пи|π))"
BASE = rf"(?P<base>{ATOM})"
POWER = rf"(?P<power>{ATOM})"
CALC = r"(?:найди(?:те)?|вычисли(?:те)?|посчитай(?:те)?|определи(?:те)?)"
QUERY = rf"(?:{CALC} степень|какой получится результат|что получится|чему равна степень)"
BASE_LABEL = r"основание(?: степени)?"
POWER_LABEL = r"показатель(?: степени)?"
VALUE = r"(?: рав(?:но|ен)| равняется|\s*[:=—–])? +"
SEPARATOR = r"(?:\s*[,.;] +| +и +)"
PREFIX = re.compile(
    rf"^(?:(?:{QUERY})[.!?:] +|(?:нужна программа мк-61 для следующего вычисления|"
    r"мне нужно вычислить это выражение|посчитай, пожалуйста): +)"
)
SUFFIX = re.compile(rf"{SEPARATOR}(?:{QUERY})$")
BOUNDARY = r"(?:[.!?;] +|, +(?:затем )?| +и +)"
STORE = re.compile(
    rf"{BOUNDARY}(?:(?:{RESULT} )?{STORE_VERB}(?: {RESULT})? в (?:регистр(?:е)? )?|"
    rf"(?:ответ|результат) (?:нужен|нужно получить) в [xх] и в регистре )(?P<destination>{REGISTER})$"
)
X_ONLY = re.compile(
    rf"{BOUNDARY}(?:(?:{RESULT} )?{STORE_VERB}(?: {RESULT})? в [xх]|"
    rf"(?:ответ|результат) (?:нужен в|должен остаться в) [xх])$"
)
PRESERVE = re.compile(r"[.!?;] +остальные регистры (?:памяти )?сохрани(?:те)?"
                      r"(?:[.;] +после вычисления остановись)?$")
RULES = tuple(map(re.compile, (
    rf"{BASE_LABEL}{VALUE}{BASE}{SEPARATOR}{POWER_LABEL}{VALUE}{POWER}",
    rf"{POWER_LABEL}{VALUE}{POWER}{SEPARATOR}{BASE_LABEL}{VALUE}{BASE}",
    rf"(?:(?:{CALC}|чему равна) )?степень с основанием {BASE} и показателем {POWER}",
    rf"(?:(?:{CALC}|чему равна) )?степень с показателем {POWER} и основанием {BASE}",
    rf"найди, чему равна степень с показателем {POWER} и основанием {BASE}",
    rf"(?:что получится, если )?(?:возведи(?:те)?|возвести) {BASE} в степень (?:равную )?{POWER}",
)))
TEN_TO_POWER = re.compile(rf"(?:(?:{CALC}) )?(?:10|десять) в степени {POWER}")
NAMED_POWER = re.compile(r"\bстепен(?:ь|и|ью)\b")
ROLES = re.compile(r"\b(?:основани(?:е|ем|я)|показател(?:ь|ем|я))\b")


def normalize(text):
    return " ".join(text.casefold().replace("ё", "е").replace("−", "-").split()).rstrip(".!?")


def named_power(text):
    text = normalize(text)
    return bool(NAMED_POWER.search(text) and ROLES.search(text))


def parse_power(text, angle):
    """Consume the whole task, including the destination and any angle clause."""
    if not 1 <= len(text) <= 640 or angle not in MODES.values():
        return None
    text = normalize(text)
    if match := ANGLE_SUFFIX.search(text):
        if MODES[match[1]] != angle:
            return None
        text = text[:match.start()].rstrip(" .!?;")
    text = PRESERVE.sub("", text)
    destination = None
    if match := STORE.search(text):
        destination = register(match["destination"])
        text = text[:match.start()]
    text = X_ONLY.sub("", text)
    text = SUFFIX.sub("", PREFIX.sub("", text, count=1), count=1)
    if match := TEN_TO_POWER.fullmatch(text):
        expr = ["pow10", argument(match["power"])]
        return {"X": expr, "writes": {destination: expr} if destination else {}, "angle": angle}
    for rule in RULES:
        if match := rule.fullmatch(text):
            base = argument(match["base"])
            power = argument(match["power"])
            expr = ["pow10", power] if base == {"constant": "10"} else ["pow", base, power]
            return {"X": expr, "writes": {destination: expr} if destination else {}, "angle": angle}
    return None


@lru_cache(maxsize=2048)
def independent_spec(text, angle):
    try:
        parsed = parse_power(text, angle)
    except (ValueError, ArithmeticError):
        parsed = None
    if parsed is not None or named_power(text):
        # Named roles must be consumed together, including any extra clauses.
        return parsed
    return existing_parse(text, angle)
