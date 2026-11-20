"""Read explicit Russian arithmetic chains and result destinations."""

import re

from ce_short_path import OPERATIONS, NUMBER, PREVIOUS, parse_task as strict_parse
from ha_protocol import canonical


REGISTER = r"[rр] ?[0-9a-eавсе]"
ARGUMENT_REGISTER = rf"(?:(?:число|числа|значение|значения|содержимое|содержимого) (?:из |в )?)?(?:регистр(?:а|е)? )?({REGISTER})"
LATIN = str.maketrans("равсе", "rabce")
MODES = {"радианах": "RAD", "градусах": "DEG", "градах": "GRAD"}
ANGLE_SUFFIX = re.compile(r"\s*[,.;]?\s*(?:углы (?:заданы )?|режим |ответ (?:выдай|дай) )?в (радианах|градусах|градах)$")
PROGRAM_PREFIX = re.compile(r"^(?:(?:составь(?:те)?|напиши(?:те)?|сделай(?:те)?) программу|программа) (?:для )?мк-61: *")
QUESTION_PREFIX = re.compile(r"^(?:чему (?:равен|равна|равно|равняется) |сколько будет |какое значение даст |посчитай, пожалуйста: *|посчитай: *)")
QUESTION_SUFFIX = re.compile(r"(?:[.;]\s*| — )(?:что (?:получится|выйдет)|чему равно|сколько получится)$")
SEQUENCE = re.compile(r"^(?:(?:а )?(?:сначала|сперва|затем|потом|после этого|после чего|далее|а после) +)(?:— +)?")
RESULT = (r"(?:тот же результат|(?:полученн(?:ый|ое) )?(?:результат|ответ|число|значение)|итог|произведение|частное|разность|сумму|это)")
STORE_VERB = r"(?:запиши(?:те)?|записать|сохрани(?:те)?|сохранить|положи(?:те)?|положить|помести(?:те)?|поместить|оставь(?:те)?|оставить)"
DESTINATION = rf"(?:в (?:регистр(?:е)? )?)({REGISTER})"
STORE = re.compile(rf"(?:{RESULT} )?{STORE_VERB}(?: {RESULT})?(?: обратно)? {DESTINATION}$")
X_ONLY = re.compile(rf"(?:(?:{RESULT} )?{STORE_VERB}(?: {RESULT})? в [xх]|(?:покажи|показать|выведи|вывести|выдай) {RESULT}|результат оставь как ответ)")

NAMES = {
    **OPERATIONS,
    "экспонента": "exp", "экспоненты": "exp", "экспоненту": "exp",
    "абсолютная величина": "abs", "абсолютную величину": "abs", "абсолютной величины": "abs",
    "модуля": "abs", "арксинуса": "asin", "арккосинуса": "acos", "арктангенса": "atan",
    "синуса": "sin", "косинуса": "cos", "тангенса": "tan", "знака": "sign",
    "натурального логарифма": "ln", "десятичного логарифма": "log10",
    "корень": "sqrt", "корня": "sqrt", "квадратного корня": "sqrt", "квадрата": "square",
    "обратная величина": "reciprocal", "обратной величины": "reciprocal", "обратную величину": "reciprocal",
    "обратное число": "reciprocal", "обратного числа": "reciprocal", "обратное": "reciprocal",
    "целая часть": "int", "целую часть": "int", "целой части": "int",
    "дробная часть": "frac", "дробную часть": "frac", "дробной части": "frac",
}
FUNCTION_NAME = "|".join(re.escape(name) for name in sorted(NAMES, key=len, reverse=True))
UNARY = re.compile(rf"({FUNCTION_NAME})(?: +(.+))?$")
CALCULATE = re.compile(r"^(?:вычисли(?:те|ть)?|найди(?:те)?|найти|возьми(?:те)?|взять|посчитай(?:те)?|посчитать|определи(?:те|ть)?|извлеки(?:те)?|извлечь|получи(?:те|ть)?) +")
MOVE_SIGN = r"(?:смени(?:те|ть)?|поменяй(?:те)?|поменять) (?:его )?знак(?: на противоположный)?"
RESULT_REFS = PREVIOUS | {
    "его", "ее", "него", "нее", "полученное", "полученного", "это число", "это значение",
    "этого знака", "полученного угла", "этого угла", "этой суммы", "этой разности", "этого частного",
    "этого произведения", "полученной суммы", "полученной разности", "полученного частного",
    "полученного произведения", "от него", "того, что получилось",
}
PREVIOUS_VALUE = object()


def register(text):
    return text.replace(" ", "").translate(LATIN).upper()


def literal(text):
    if text.startswith("минус "):
        text = "-" + text[6:]
    words = {"ноль": "0", "единица": "1", "единицу": "1", "два": "2", "десять": "10"}
    text = words.get(text, text)
    if re.fullmatch(NUMBER, text):
        value = canonical(text.replace(",", "."))
        return {"constant": value} if len(value) <= 18 else None
    return None


def argument(text, depth=0):
    """Read one entire operand. Nested unary phrases bind to the rest of it."""
    if depth >= 8:
        raise ValueError("expression is too deep")
    text = text.strip()
    if text in RESULT_REFS:
        return PREVIOUS_VALUE
    if match := re.fullmatch(ARGUMENT_REGISTER, text):
        return register(match[1])
    if text in ("пи", "число пи", "числа пи", "π"):
        return {"pi": True}
    if text.startswith(("число ", "числа ")):
        text = text.split(" ", 1)[1]
    if value := literal(text):
        return value
    if text.startswith("минус "):
        return ["neg", argument(text[6:], depth + 1)]
    if match := re.fullmatch(r"числ[оа] противоположн(?:ое|ого) (.+)", text):
        return ["neg", argument(match[1], depth + 1)]
    if match := re.fullmatch(r"(.+) с противоположным знаком", text):
        value = argument(match[1], depth + 1)
        if isinstance(value, list):
            raise ValueError("unclear scope of sign change")
        return ["neg", value]
    if match := re.fullmatch(r"(?:десять|10) в степени (.+)", text):
        return ["pow10", argument(match[1], depth + 1)]
    if match := UNARY.fullmatch(text):
        name, operand = match.groups()
        if operand is None:
            raise ValueError("function argument missing")
        return [NAMES[name], argument(remove_preposition(operand, NAMES[name]), depth + 1)]
    raise ValueError("unsupported operand")


def remove_preposition(text, operator):
    prefixes = ("от ", "из ", "к ") if operator == "reciprocal" else ("от ", "из ", "у ")
    for prefix in prefixes:
        if text.startswith(prefix):
            return text[len(prefix):]
    return text


BINARY_RULES = (
    ("+", r"(?:прибавь|добавь|прибавить|добавить) (.+) к (.+)", (2, 1)),
    ("+", r"(?:прибавь|добавь|прибавить|добавить) к (.+?) (?:число )?(.+)", (1, 2)),
    ("+", r"к (.+) (?:прибавь|добавь) (.+)", (1, 2)),
    ("+", r"(?:сложи|сложить) (.+) с (.+)", (1, 2)),
    ("-", r"(?:вычти|вычесть) (.+) из (.+)", (2, 1)),
    ("-", r"из (.+) (?:вычти|вычесть) (.+)", (1, 2)),
    ("*", r"(?:умножь|умножить|умножьте) (.+) на (.+)", (1, 2)),
    ("/", r"(?:раздели|разделить|разделите) (.+) на (.+)", (1, 2)),
    ("pow", r"(?:возведи|возвести|возведите) (.+) в степень (?:равную )?(.+)", (1, 2)),
    ("pow", r"(.+) возвести в степень (.+)", (1, 2)),
)
INFIX = re.compile(r"(.+) (плюс|минус) (.+)")
CONTINUATION = (
    ("+", re.compile(r"(?:прибавь|добавь|прибавить|добавить) (.+)")),
    ("-", re.compile(r"(?:вычти|вычесть) (.+)")),
    ("*", re.compile(r"(?:умножь|умножить) на (.+)")),
    ("/", re.compile(r"(?:раздели|разделить) на (.+)")),
    ("pow", re.compile(r"(?:возведи|возвести) в степень (.+)")),
)


def resolve(expression, previous):
    if expression is PREVIOUS_VALUE:
        if previous is None:
            raise ValueError("previous result missing")
        return previous, 1
    if not isinstance(expression, list):
        return expression, 0
    children = [resolve(arg, previous) for arg in expression[1:]]
    return [expression[0], *(child for child, _ in children)], sum(count for _, count in children)


def read_operation(text, previous):
    if re.fullmatch(MOVE_SIGN, text):
        return ["neg", PREVIOUS_VALUE]
    if match := re.fullmatch(rf"(?:{MOVE_SIGN}) (?:у |для )?(.+)", text):
        return ["neg", argument(match[1])]
    if match := re.fullmatch(r"(?:поменяй|смени) у (.+) знак(?: на противоположный)?", text):
        return ["neg", argument(match[1])]
    if text in ("отбрось знак", "убери знак", "возьми по модулю"):
        return ["abs", PREVIOUS_VALUE]
    if match := re.fullmatch(r"(?:возведи|возвести|возведите) (?:(.+) )?в квадрат", text):
        return ["square", argument(match[1]) if match[1] else PREVIOUS_VALUE]
    if match := re.fullmatch(r"(.+) возвести в квадрат", text):
        return ["square", argument(match[1])]
    if re.fullmatch(r"(?:возведи|возвести) e в (?:эту|полученную) степень", text):
        return ["exp", PREVIOUS_VALUE]
    if match := re.fullmatch(r"от (.+) (?:найди|вычисли|возьми) (.+)", text):
        if match[2] in NAMES:
            return [NAMES[match[2]], argument(match[1])]
    if match := re.fullmatch(r"какой знак у (.+)", text):
        return ["sign", argument(match[1])]
    for operator, pattern, order in BINARY_RULES:
        if match := re.fullmatch(pattern, text):
            try:
                return [operator, *(argument(match[index]) for index in order)]
            except ValueError:
                continue
    if previous is not None:
        for operator, pattern in CONTINUATION:
            if match := pattern.fullmatch(text):
                return [operator, PREVIOUS_VALUE, argument(match[1])]
    text = CALCULATE.sub("", text)
    if match := INFIX.fullmatch(text):
        left, right = argument(match[1]), argument(match[3])
        if isinstance(left, list) or isinstance(right, list):
            raise ValueError("unclear scope of arithmetic")
        return ["+" if match[2] == "плюс" else "-", left, right]
    if text in NAMES:
        return [NAMES[text], PREVIOUS_VALUE]
    return argument(text)


def read_natural(text, angle):
    text = re.sub(r"\s+", " ", text.strip().lower()).replace("ё", "е").replace("−", "-")
    text = PROGRAM_PREFIX.sub("", text).rstrip(".!?")
    if match := ANGLE_SUFFIX.search(text):
        if MODES[match[1]] != angle:
            raise ValueError("angle conflict")
        text = text[:match.start()].rstrip(" .,;")
    text = QUESTION_SUFFIX.sub("", text).rstrip(".!?")
    text = QUESTION_PREFIX.sub("", text)
    text = text.replace("того, что получилось", "полученного результата")
    text = re.sub(r" +[—–] +и +", " и ", text)
    # A decimal separator is part of the operand. Commas followed by a space
    # and sentences separate explicit clauses.
    clauses = re.split(r"(?:[,.!?;] +(?:и +)?| +и +)", text)
    if not 1 <= len(clauses) <= 12:
        raise ValueError("too many clauses")
    previous = None
    destination = None
    finished = False
    for clause in clauses:
        clause = SEQUENCE.sub("", clause.strip().rstrip(".!?"))
        clause = re.sub(r"^а +", "", clause)
        if match := STORE.fullmatch(clause):
            if previous is None or destination is not None:
                raise ValueError("invalid destination")
            destination = register(match[1])
            finished = True
            continue
        if X_ONLY.fullmatch(clause):
            if previous is None or finished:
                raise ValueError("invalid result clause")
            finished = True
            continue
        if finished:
            raise ValueError("calculation after result")
        expression = read_operation(clause, previous)
        value, uses = resolve(expression, previous)
        if previous is not None and (uses != 1 or not isinstance(expression, list)):
            raise ValueError("ambiguous accumulator")
        previous = value
    if previous is None:
        raise ValueError("empty calculation")
    return {"X": previous, "writes": {destination: previous} if destination else {}, "angle": angle}


def expanded_parse(text, angle):
    """Retain the strict parser and accept fully consumed natural clauses."""
    original = strict_parse(text, angle)
    if original is not None:
        return original
    if not 1 <= len(text) <= 640 or angle not in MODES.values() or "(" in text or ")" in text:
        return None
    try:
        return read_natural(text, angle)
    except (ValueError, ArithmeticError, RecursionError):
        return None
