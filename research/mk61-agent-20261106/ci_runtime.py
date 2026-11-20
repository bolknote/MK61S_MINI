"""Preserve equivalent programs and offer bounded edits to a rejected formula."""

from collections import Counter
from dataclasses import dataclass
from decimal import Decimal
import re

from ar_spec import expression_text, infer
from ay_codec import compile_spec, decode, encode
from ce_short_path import spec_key
from cf_language import NAMES, REGISTER, RESULT, STORE_VERB, register
from cf_runtime import checked_program
from cg_runtime import FormulaPreview
from full_isa_math import BINARY, UNARY
from ha_protocol import canonical


def power_key(spec):
    def normalize(tree):
        if not isinstance(tree, tuple) or tree[0] in ("constant", "pi"):
            return tree
        op, *children = tree
        children = tuple(map(normalize, children))
        if op == "pow10":
            return ("pow", ("constant", "10"), *children)
        return (op, *children)

    angle, expr, writes = spec_key(spec)
    return angle, normalize(expr), tuple((reg, normalize(value)) for reg, value in writes)


def preserve_power_alias(independent, declared, current, angle, pool, checks, vm, *, prefer_parser):
    result = checked_program(independent, declared, current, angle, pool, checks, vm, prefer_parser=prefer_parser)
    # The preceding path already ran the current program on all runtime inputs.
    if result[1] != "current_structure_differs":
        return result
    implied = infer(current, pool, angle)
    if power_key(independent) == power_key(implied):
        return current, "kept_program"
    return result


# Specific phrases precede individual names so that «сменить знак» is not sign(x).
PHRASES = (
    ("neg", r"(?:смени|сменить|поменяй|поменять) (?:его )?знак(?: результата)?|"
            r"(?:со знаком минус|с противоположным знаком|числ[оа] противоположн[а-я]+)"),
    ("abs", r"по модулю|отбрось знак|убери знак"),
    ("exp", r"(?:для|числа) [eе]|[eе] в (?:степень|степени)|в экспоненту"),
    ("pow10", r"(?:10|десять) в (?:степень|степени)"),
    ("reciprocal", r"(?:1|один|единиц[ауы]) (?:делится|деленн[а-я]+|поделенн[а-я]+) на"),
    ("+", r"плюс|сложи|сложить|прибавь|прибавить|сумм[ауы]"),
    ("-", r"вычти|вычесть|разност[ьи]"),
    ("*", r"умножь|умножить|произведени[ея]"),
    ("/", r"раздели|разделить|частно[ег][а-я]*"),
    ("pow", r"возведи|возвести|показател[ья]"),
    ("acos", r"arccos|acos"), ("asin", r"arcsin|asin"), ("atan", r"arctan|atan"),
    ("sign", r"sign"), ("neg", r"neg"), ("sqrt", r"sqrt"),
    ("log10", r"log10"), ("ln", r"ln"),
    ("sin", r"sin"), ("cos", r"cos"), ("tan", r"tan"), ("exp", r"exp"), ("abs", r"abs"),
)
WORDS = tuple(sorted(NAMES, key=len, reverse=True))
CUE_OPS = [op for op, _ in PHRASES] + [NAMES[name] for name in WORDS]
CUE_PATTERNS = [pattern for _, pattern in PHRASES] + [re.escape(name) for name in WORDS]
CUES = re.compile(r"\b(?:" + "|".join(f"({p})" for p in CUE_PATTERNS) + r")\b")
STORE = re.compile(rf"\b(?:(?:{RESULT} )?{STORE_VERB}(?: {RESULT})?|{RESULT}) в (?:регистр(?:е)? )?({REGISTER})\b")
REGISTERS = re.compile(rf"\b{REGISTER}\b")
NUMBERS = re.compile(r"(?<!\w)(?:(минус|плюс) )?([+-]?(?:\d+(?:[.,]\d+)?|[.,]\d+))(?!\w)")
NUMBER_WORD = re.compile(r"\b(?:один|единиц[ау]|ноль|два|десять)\b")
NUMBER_VALUE = {"один": "1", "единица": "1", "единицу": "1", "ноль": "0", "два": "2", "десять": "10"}
LIMIT = 3


@dataclass(frozen=True)
class FormulaEdit:
    path: tuple
    before: str
    after: str
    kind: str
    preview: FormulaPreview
    score: int


def nodes(expression, path=()):
    yield path, expression
    if isinstance(expression, list):
        for index, arg in enumerate(expression[1:], 1):
            yield from nodes(arg, (*path, index))


def replace_at(expression, path, replacement):
    if not path:
        return replacement
    index, *parent = path
    result = expression.copy()
    result[index] = replace_at(result[index], parent, replacement)
    return result


def text_evidence(text):
    text = " ".join(text.lower().replace("ё", "е").replace("−", "-").split())
    text = re.sub(r"мк[ -‑–]?61", "калькулятор", text)
    stores = list(STORE.finditer(text))
    dest = {register(match[1]) for match in stores}
    sources = [register(match[0]) for match in REGISTERS.finditer(STORE.sub("", text))]
    operations = [CUE_OPS[match.lastindex - 1] for match in CUES.finditer(text)]
    literals = []
    for match in NUMBERS.finditer(text):
        raw = match[2].replace(",", ".")
        if match[1] == "минус" and not raw.startswith("-"):
            raw = "-" + raw.lstrip("+")
        literals.append(canonical(raw))
    literals.extend(NUMBER_VALUE[match[0]] for match in NUMBER_WORD.finditer(text))
    return operations, list(dict.fromkeys(sources)), list(dict.fromkeys(literals)), dest


def collect_edits(task, refused, pool):
    spec = refused.spec()
    expression = spec["X"]
    ops, registers, numbers, destinations = text_evidence(task)
    evidence = Counter(ops)
    actual = Counter(value[0] for _, value in nodes(expression) if isinstance(value, list))
    original_key = power_key(spec)
    options = {}

    def propose(path, old, new, kind, score, writes=spec["writes"]):
        updated = replace_at(expression, path, new)
        revised = {"X": updated, "writes": {reg: updated for reg in writes}, "angle": spec["angle"]}
        key = power_key(revised)
        if key == original_key or (key in options and options[key].score >= score):
            return
        try:
            if decode(encode(revised, pool), pool, spec["angle"]) != revised:
                return
            compile_spec(revised, pool)
        except (ValueError, ArithmeticError, KeyError):
            return
        before, after = expression_text(old), expression_text(new)
        if kind == "destination":
            before, after = next(iter(spec["writes"]), "X"), next(iter(writes))
        options[key] = FormulaEdit(path, before, after, kind, FormulaPreview.from_spec(revised), score)

    for path, value in nodes(expression):
        if isinstance(value, list):
            op, *args = value
            family = UNARY if len(args) == 1 else BINARY
            for replacement in evidence.keys() & family.keys():
                if replacement != op and (actual[op] > evidence[op] or evidence[replacement] > actual[replacement]):
                    score = 80 + 15 * (not evidence[op]) + 10 * (evidence[replacement] > actual[replacement])
                    propose(path, value, [replacement, *args], "operator", score)
            if len(args) == 1:
                child = args[0]
                if evidence[op] < actual[op]:
                    propose(path, value, child, "extra_operator", 72 + 12 * (not evidence[op]))
                if isinstance(child, list) and len(child) == 2 and op != child[0] and evidence[op] and evidence[child[0]]:
                    propose(path, value, [child[0], [op, child[1]]], "order", 98)
            elif op in ("-", "/", "pow") and evidence[op]:
                propose(path, value, [op, args[1], args[0]], "order", 64)
        else:
            if isinstance(value, str) and value not in registers:
                for alternative in registers:
                    propose(path, value, alternative, "operand", 94)
            if not isinstance(value, str) or value not in registers:
                for number in numbers:
                    if number in pool:
                        opposite_sign = (isinstance(value, dict) and "constant" in value and
                                         canonical(value["constant"]) == canonical(-Decimal(number)))
                        propose(path, value, {"constant": number}, "operand", 70 + 25 * opposite_sign)
            if isinstance(value, dict) and value.get("constant") not in numbers:
                for alternative in registers:
                    propose(path, value, alternative, "operand", 86)
        for op in evidence.keys() & UNARY.keys():
            if evidence[op] > actual[op]:
                propose(path, value, [op, value], "missing_operator", 70)

    if len(destinations) == 1 and destinations != spec["writes"].keys():
        propose((), expression, expression, "destination", 110, destinations)
    return sorted(options.values(), key=lambda edit: (-edit.score, len(edit.path), edit.path, edit.preview.serialized_spec))[:LIMIT]


def question_text(refused, options):
    first = refused.text().rsplit("\n", 1)[0]
    lines = ["Отклонённая формула", first, "Какой вариант соответствует условию?"]
    for index, option in enumerate(options, 1):
        formula = option.preview.text().rsplit("\n", 1)[0]
        lines.extend([f"{index}. {option.before} → {option.after}", formula])
    lines.append("0. Ни один вариант")
    return "\n".join(lines)


def select_preview(options, response):
    if response is None:
        return None
    if type(response) is not int or not 0 <= response <= len(options):
        raise ValueError("Choose an option shown in this question")
    return options[response - 1].preview if response else None
