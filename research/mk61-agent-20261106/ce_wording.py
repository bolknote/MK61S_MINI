"""Russian wording for the fixed exam trees, authored separately from the gate."""

from ay_common import read, rows, save_rows, sha
from ce_data import ROOT, reword


UNARY_NOUNS = {
    "abs": "модуль", "acos": "арккосинус", "asin": "арксинус", "atan": "арктангенс",
    "cos": "косинус", "sin": "синус", "tan": "тангенс", "ln": "натуральный логарифм",
    "log10": "десятичный логарифм", "sqrt": "квадратный корень", "square": "квадрат",
    "exp": "экспонента", "reciprocal": "обратная величина", "neg": "противоположное число",
    "sign": "знак", "int": "целая часть с отсечением к нулю",
    "frac": "дробная часть с исходным знаком", "pow10": "десять в степени",
}
ROOT_VERBS = (
    "Мне нужно вычислить это выражение: {expr}.",
    "Какое значение даст {expr}?",
    "Посчитай, пожалуйста: {expr}.",
    "Нужна программа МК-61 для следующего вычисления: {expr}.",
)


def bounded(expression):
    value = verbal(expression)
    return f"({value})" if isinstance(expression, list) else value


def verbal(expression):
    if isinstance(expression, str):
        return expression
    if isinstance(expression, dict):
        return "число пи" if "pi" in expression else expression["constant"]
    op, *args = expression
    if len(args) == 1:
        arg = bounded(args[0])
        if op == "neg":
            return f"{arg} с противоположным знаком"
        if op == "pow10":
            return f"десять в степени {arg}"
        return f"{UNARY_NOUNS[op]} от {arg}"
    left, right = map(bounded, args)
    if op == "pow":
        return f"степень с основанием {left} и показателем {right}"
    names = {"+": "сумма", "-": "разность", "*": "произведение", "/": "частное"}
    return f"{names[op]} значений {left} и {right}"


def editorial_question(spec, index):
    expression = spec["X"]
    op, *args = expression
    if len(args) == 2 and index % 3 == 0:
        left, right = map(bounded, args)
        prompts = {
            "+": f"К значению {left} добавь {right}.",
            "-": f"Вычти {right} из значения {left}.",
            "*": f"Значение {left} надо умножить на {right}.",
            "/": f"Числитель дроби равен {left}, знаменатель равен {right}. Вычисли дробь.",
            "pow": f"Найди степень. Основание равно {left}, показатель равен {right}.",
        }
        text = prompts[op]
    else:
        text = ROOT_VERBS[index % len(ROOT_VERBS)].format(expr=verbal(expression))
    if spec["writes"]:
        register = next(iter(spec["writes"]))
        tail = (f" Итог сохрани в {register}.", f" Ответ нужен в X и в регистре {register}.")
        text += tail[index % len(tail)]
    elif index % 3 == 1:
        text += " Результат должен остаться в X."
    return text


def main():
    assert not (ROOT / "frozen.json").exists()
    path = ROOT / "closed-asts.jsonl"
    assert sha(path) == read(ROOT / "ast-frozen.json")["sha256"]
    final = []
    for index, goal in enumerate(rows(path)):
        if goal["wording_cohort"] == "freeform":
            goal = reword(goal, editorial_question(goal["spec"], index), "local_editorial_templates")
        final.append(goal)
    assert len(final) == len({(g["task"], g["spec"]["angle"]) for g in final}) == 256
    save_rows(ROOT / "closed.jsonl", final)


if __name__ == "__main__":
    main()
