"""Independent task specifications, bytecode compiler and frozen evaluation sets."""
from __future__ import annotations

from decimal import Decimal, localcontext
import hashlib
import json
from pathlib import Path
import random

HERE = Path(__file__).resolve().parent
BUILD = HERE.parents[1] / ".build/mk61-agent-20261106"
OPS = {"+": 0x10, "-": 0x11, "*": 0x12, "/": 0x13, "abs": 0x31, "neg": 0x0B, "square": 0x22}


def program_text(code):
    return " ".join(f"{x:02X}" for x in code)


def compile_expr(expr):
    if isinstance(expr, str):
        return [0x60 + int(expr[1:], 16)]
    operator, *children = expr
    return [x for child in children for x in compile_expr(child)] + [OPS[operator]]


def expression_text(expr):
    if isinstance(expr, str):
        return expr
    operator, *children = expr
    if len(children) == 1:
        return {"abs": "abs", "neg": "neg", "square": "square"}[operator] + "(" + expression_text(children[0]) + ")"
    return "(" + expression_text(children[0]) + " " + operator + " " + expression_text(children[1]) + ")"


def plan_text(expr):
    if isinstance(expr, str):
        return f"взять {expr}"
    op, *children = expr
    word = {"+": "сложить", "-": "вычесть", "*": "умножить", "/": "разделить", "abs": "взять модуль",
            "neg": "сменить знак", "square": "возвести в квадрат"}[op]
    return "; ".join([*(plan_text(x) for x in children), word])


def value_of(expr, registers):
    if isinstance(expr, str):
        return Decimal(str(registers[expr]))
    op, *children = expr
    values = [value_of(child, registers) for child in children]
    a = values[0]
    with localcontext() as ctx:
        ctx.prec = 8
        if op == "abs": return abs(a)
        if op == "neg": return -a
        if op == "square": return a * a
        b = values[1]
        return {"+": lambda: a + b, "-": lambda: a - b, "*": lambda: a * b, "/": lambda: a / b}[op]()


def family_of(expr):
    # Register renamings, constants, inputs and commutative reorderings cannot
    # move an expression family between the generated train/test partitions.
    if isinstance(expr, str):
        return "v"
    op, *children = expr
    parts = [family_of(x) for x in children]
    if op in {"+", "*"}:
        parts.sort()
    return op + "(" + ",".join(parts) + ")"


def split_of(expr):
    family = family_of(expr)
    if len(compile_expr(expr)) <= 3:
        return "train"
    bucket = int(hashlib.sha256(("mk61-expr-v1:" + family).encode()).hexdigest()[:8], 16) % 10
    return "validation" if bucket == 0 else "test" if bucket == 1 else "train"


def random_expr(rng, depth):
    if depth == 0 or rng.random() < .23:
        return "R" + str(rng.randrange(4))
    op = rng.choice(["+", "-", "*", "/", "abs", "neg", "square"])
    return [op, random_expr(rng, depth - 1), *([] if op in {"abs", "neg", "square"} else [random_expr(rng, depth - 1)])]


def registers_used(expr):
    if isinstance(expr, str): return {expr}
    return set().union(*(registers_used(x) for x in expr[1:]))


def make_case(expr, rng):
    for _ in range(100):
        registers = {r: rng.choice([-9, -5, -2, -1, 0, 1, 2, 3, 5, 8, 11]) for r in sorted(registers_used(expr))}
        try:
            value = value_of(expr, registers)
        except ArithmeticError:
            continue
        if value.is_finite() and abs(value) < 1000000:
            return {"registers": registers, "expected_X": str(value.normalize())}
    raise ValueError("Cannot find safe arithmetic inputs")


def expression_task(expr, rng, index, *, split, kind="synthesis"):
    formula = expression_text(expr)
    wording = rng.choice([f"Напиши программу МК-61 для X = {formula}.",
                          f"МК-61. Вычисли {formula}, результат оставь в X.",
                          f"Нужен код МК-61: X = {formula}."])
    text = wording + " Входные значения уже в регистрах. Остановись командой С/П."
    code = compile_expr(expr) + [0x50]
    task = {"id": f"{split}:expr:{index:05d}", "family": family_of(expr), "kind": kind, "task": text,
            "expression": expr, "reference_code": code, "reference_plan": plan_text(expr) + "; остановиться",
            "public_tests": [make_case(expr, rng) for _ in range(2)],
            "hidden_tests": [make_case(expr, rng) for _ in range(5)]}
    if kind == "repair":
        broken = list(code)
        position = rng.randrange(len(broken) - 1)
        if 0x60 <= broken[position] <= 0x63:
            broken[position] = 0x60 + ((broken[position] - 0x60 + 1) % 4)
        else:
            broken[position] = rng.choice([x for x in [0x10, 0x11, 0x12, 0x31, 0x22] if x != broken[position]])
        task["initial_code"] = broken
    return task


def make_generated(split, count, *, seed):
    rng = random.Random(seed)
    tasks = []
    attempts = 0
    while len(tasks) < count:
        attempts += 1
        if attempts > count * 300:
            raise RuntimeError("Cannot fill independent task partition")
        expr = random_expr(rng, rng.choices([1, 2, 3], weights=[3, 5, 2])[0])
        if split_of(expr) != split or len(compile_expr(expr)) > 19:
            continue
        try:
            task = expression_task(expr, rng, len(tasks), split=split,
                                   kind="repair" if len(tasks) % 3 == 1 else "synthesis")
        except ValueError:
            continue
        tasks.append(task)
    return tasks


def elementary_tasks(seed=61061):
    rng = random.Random(seed)
    expressions = ["R0", "R2", ["+", "R0", "R1"], ["-", "R1", "R0"], ["*", "R2", "R3"],
                   ["/", "R0", "R1"], ["abs", "R0"], ["neg", "R1"], ["square", "R2"],
                   ["+", ["*", "R0", "R1"], "R2"], ["-", "R0", ["*", "R1", "R2"]],
                   ["/", ["+", "R0", "R1"], "R2"]]
    rows = []
    for i, expr in enumerate(expressions):
        task = expression_task(expr, rng, i, split="basic", kind="repair" if i % 3 == 1 else "synthesis")
        task["id"] = "basic:" + str(i)
        rows.append(task)
    return rows


def save_jsonl(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows))


def main():
    output = BUILD / "tasks"
    if (output / "frozen.json").exists():
        raise SystemExit("Evaluation sets already frozen; do not silently rewrite")
    sets = {"basic": elementary_tasks(), "validation": make_generated("validation", 60, seed=61062),
            "test": make_generated("test", 80, seed=61063)}
    hashes = {}
    for name, rows in sets.items():
        path = output / f"{name}.jsonl"
        save_jsonl(path, rows)
        hashes[name] = {"rows": len(rows), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
    train_families = {row["family"] for row in make_generated("train", 12000, seed=61064)}
    val_families = {row["family"] for row in sets["validation"]}
    test_families = {row["family"] for row in sets["test"]}
    assert not train_families & (val_families | test_families)
    assert not val_families & test_families
    (output / "frozen.json").write_text(json.dumps({"sets": hashes, "family_partition": "structural AST, register names removed",
                                                     "test_used_for_selection": False}, indent=2) + "\n")
    print(json.dumps(hashes, indent=2))


if __name__ == "__main__":
    main()
