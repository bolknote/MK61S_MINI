"""Verify an independently parsed arithmetic task before taking the short path."""

import re
from decimal import Decimal

from ar_spec import infer, verify
from ay_codec import compile_spec
from be_language import parse_question
from ha_protocol import canonical


# The natural-language subset is deliberately explicit about the accumulator.
# The structured syntax is handled by the existing full-consumption parser.
OPERATIONS = {
    "модуль": "abs",
    "арксинус": "asin",
    "арккосинус": "acos",
    "арктангенс": "atan",
    "синус": "sin",
    "косинус": "cos",
    "тангенс": "tan",
    "квадратный корень": "sqrt",
    "квадрат": "square",
    "натуральный логарифм": "ln",
    "десятичный логарифм": "log10",
    "экспоненту": "exp",
    "обратную величину": "reciprocal",
    "знак": "sign",
}
OPERATION_NAMES = "|".join(sorted(OPERATIONS, key=len, reverse=True))
PREVIOUS = {
    "это", "этого", "этого числа", "этого значения", "этого результата",
    "результат", "результата", "полученный результат", "полученного результата",
    "полученное число", "полученного числа", "полученное значение", "полученного значения",
}
REG = r"r[0-9a-e]"
NUMBER = r"-?(?:\d+(?:[.,]\d+)?|[.,]\d+)"
UNARY = re.compile(rf"(?:возьми|вычисли|найди|извлеки) ({OPERATION_NAMES})(?: (?:от |из )?(.+))?")
BINARY = (
    ("+", re.compile(r"прибавь (.+) к (.+)"), True),
    ("-", re.compile(r"из (.+) вычти (.+)"), False),
    ("*", re.compile(r"умножь (.+) на (.+)"), False),
    ("/", re.compile(r"раздели (.+) на (.+)"), False),
    ("pow", re.compile(r"возведи (.+) в степень (.+)"), False),
)
CONTINUE = re.compile(r"(прибавь|вычти|умножь на|раздели на|возведи в степень) (.+)")
CONTINUE_OPS = {"прибавь": "+", "вычти": "-", "умножь на": "*", "раздели на": "/", "возведи в степень": "pow"}
DESTINATION = re.compile(rf"(?:запиши|сохрани) (?:результат|ответ) в ({REG})|(?:результат|ответ) (?:запиши|сохрани) в ({REG})")
ACCUMULATOR = object()


def operand(text, previous):
    if previous is not None and text in PREVIOUS:
        return previous
    if re.fullmatch(REG, text):
        return text.upper()
    if text == "пи":
        return {"pi": True}
    if text.startswith("минус "):
        text = "-" + text.removeprefix("минус ")
    if re.fullmatch(NUMBER, text):
        return {"constant": canonical(text.replace(",", "."))}
    raise ValueError("unsupported operand")


def arithmetic_step(text, previous):
    if text == "смени знак" or text == "поменяй знак":
        if previous is not None:
            return ["neg", previous]
        raise ValueError("no previous result")
    if match := re.fullmatch(r"возьми (.+) с противоположным знаком", text):
        return ["neg", operand(match[1], previous)]
    if match := UNARY.fullmatch(text):
        value = operand(match[2], previous) if match[2] else previous
        if value is None:
            raise ValueError("missing unary operand")
        return [OPERATIONS[match[1]], value]
    for op, pattern, reverse in BINARY:
        if match := pattern.fullmatch(text):
            first, second = operand(match[1], previous), operand(match[2], previous)
            return [op, second, first] if reverse else [op, first, second]
    if previous is not None and (match := CONTINUE.fullmatch(text)):
        return [CONTINUE_OPS[match[1]], previous, operand(match[2], previous)]
    if match := re.fullmatch(r"возьми (.+)", text):
        return operand(match[1], previous)
    raise ValueError("unsupported arithmetic step")


def parse_steps(text, angle):
    text = re.sub(r"\s+", " ", text.strip().lower()).replace("−", "-")
    text = text.removesuffix(".").strip()
    parts = re.split(r"(?:[,.] +(?:и +)?| +и +)", text)
    if not 1 <= len(parts) <= 12:
        raise ValueError("unsupported chain length")
    expression = None
    destination = None
    final = False
    for index, part in enumerate(parts):
        prefix = r"^сначала +" if index == 0 else r"^(?:а +)?(?:затем|потом|после этого) +"
        part = re.sub(prefix, "", part)
        if match := DESTINATION.fullmatch(part):
            if expression is None or destination is not None:
                raise ValueError("unsupported store")
            destination = (match[1] or match[2]).upper()
            final = True
        elif part in ("оставь результат в x", "оставь ответ в x", "результат оставь в x", "ответ оставь в x"):
            if expression is None or final:
                raise ValueError("unsupported result clause")
            final = True
        elif final:
            raise ValueError("arithmetic after result clause")
        else:
            if expression is None:
                expression = arithmetic_step(part, None)
                continue
            step = arithmetic_step(part, ACCUMULATOR)
            if not isinstance(step, list) or not any(arg is ACCUMULATOR for arg in step[1:]):
                raise ValueError("step discards the previous result")
            expression = [step[0], *(expression if arg is ACCUMULATOR else arg for arg in step[1:])]
    if expression is None:
        raise ValueError("missing expression")
    return {"X": expression, "writes": {destination: expression} if destination else {}, "angle": angle}


def parse_task(text, angle):
    """Return a SPEC only when the entire instruction belongs to a supported grammar."""
    if angle not in {"RAD", "DEG", "GRAD"} or not 1 <= len(text) <= 640:
        return None
    if text.count("(") > 32:
        return None
    for parser in (parse_question, parse_steps):
        try:
            spec = parser(text, angle)
        except (ValueError, ArithmeticError, RecursionError):
            continue
        if len(spec["writes"]) <= 1:
            return spec
    return None


def expression_key(expression):
    if isinstance(expression, str):
        return expression
    if isinstance(expression, dict):
        return ("pi",) if "pi" in expression else ("constant", canonical(expression["constant"]))
    operator, *args = expression
    children = tuple(expression_key(arg) for arg in args)
    if operator == "neg" and isinstance(children[0], tuple) and children[0][0] == "constant":
        return ("constant", canonical(-Decimal(children[0][1])))
    return (operator, *children)


def spec_key(spec):
    return (
        spec["angle"],
        expression_key(spec["X"]),
        tuple(sorted((reg, expression_key(expr)) for reg, expr in spec["writes"].items())),
    )


def short_path(text, angle, pool, model_spec, current, checks, vm):
    """Return a checked program or a fallback reason using only runtime inputs."""
    independent = parse_task(text, angle)
    if independent is None:
        return None, "unsupported_text", None
    if model_spec is None or spec_key(independent) != spec_key(model_spec):
        return None, "spec_disagrees", independent
    if current is not None:
        result = verify(vm, current, pool, independent, checks)
        if result["status"] == "TESTED":
            try:
                implied = infer(current, pool, angle)
            except (ValueError, ArithmeticError, KeyError):
                return None, "current_structure_unknown", independent
            if spec_key(implied) == spec_key(independent):
                return current, "kept_program", independent
            return None, "current_structure_differs", independent
        if result["status"] != "FAIL":
            return None, "current_check_unknown", independent
    try:
        candidate = compile_spec(model_spec, pool)
    except (ValueError, ArithmeticError):
        return None, "compile_failed", independent
    if verify(vm, candidate, pool, independent, checks)["status"] != "TESTED":
        return None, "candidate_check_failed", independent
    return candidate, "compiled_program", independent
