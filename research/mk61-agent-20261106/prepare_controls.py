"""Verified branches, loops, state updates and natural Russian task wording."""
import hashlib
import json
import random

from emulator import Emulator
from harness import check_program, feedback, initial_prompt
from tasks import BUILD, compile_expr, expression_task, program_text, save_jsonl


def control_task(rng, index, split):
    kind = rng.choice(["branch", "loop", "state"])
    if kind == "branch":
        condition, opcode = rng.choice([("неотрицательно", 0x59), ("меньше нуля", 0x5C), ("равно нулю", 0x5E), ("не равно нулю", 0x57)])
        test_register = rng.randrange(4)
        a, b = rng.sample(range(4, 10), 2)
        code = [0x60 + test_register, opcode, 0x06, 0x60 + a, 0x50, 0x54, 0x60 + b, 0x50]
        text = f"МК-61: если число R{test_register} {condition}, выдай в X число из R{a}, иначе из R{b}. Заверши С/П."
        plan = f"проверить знак R{test_register}; выбрать R{a} или R{b}; остановиться"
        cases = []
        for value in [-5, 0, 3, -1, 7, 0, -2]:
            yes = {0x59: value >= 0, 0x5C: value < 0, 0x5E: value == 0, 0x57: value != 0}[opcode]
            ra, rb = rng.randint(1, 40), -rng.randint(1, 40)
            cases.append({"registers": {f"R{test_register}": value, f"R{a}": ra, f"R{b}": rb}, "expected_X": str(ra if yes else rb)})
    elif kind == "loop":
        # N is positive; FL0 repeats until the decremented counter reaches one.
        # R2 is the accumulator; no keyboard input occurs during this program.
        code = [0x0D, 0x42, 0x62, 0x61, 0x10, 0x42, 0x5D, 0x02, 0x62, 0x50]
        text = "МК-61: в R0 целое число повторений от 1 до 7, в R1 прибавляемое. Начни с нуля и прибавь R1 столько раз. Результат в X, R2 можно менять. Заверши С/П."
        plan = "обнулить R2; прибавлять R1 к R2; повторять по счётчику R0; выдать R2"
        deltas = list(range(-9, 10)) if split == "train" else [-13, -11, 12, 14] if split == "validation" else [-19, -17, 16, 18]
        cases = []
        for _ in range(7):
            n, delta = rng.randint(1, 7), rng.choice(deltas)
            cases.append({"registers": {"R0": n, "R1": delta}, "expected_X": str(n * delta)})
    else:
        first, second = rng.sample(range(4), 2)
        scratch = rng.randrange(4, 10)
        operation = rng.choice([("сложи", 0x10, lambda a, b: a + b), ("вычти второе из первого", 0x11, lambda a, b: a - b),
                                ("перемножь", 0x12, lambda a, b: a * b)])
        word, opcode, op = operation
        code = [0x60 + first, 0x60 + second, opcode, 0x40 + scratch, 0x50]
        text = f"МК-61: возьми R{first} и R{second}, {word}. Запиши результат и в R{scratch}, и в X. Остановись."
        plan = f"взять R{first} и R{second}; выполнить действие; сохранить в R{scratch}; остановиться"
        cases = []
        for _ in range(7):
            a, b = rng.randint(-9, 9), rng.randint(-9, 9)
            expected = str(op(a, b))
            cases.append({"registers": {f"R{first}": a, f"R{second}": b}, "expected_X": expected,
                          "expected_registers": {f"R{scratch}": expected}})
    return {"id": f"{split}:control:{index}", "kind": kind, "family": "control:" + kind,
            "task": text, "reference_code": code, "reference_plan": plan,
            "public_tests": cases[:2], "hidden_tests": cases[2:]}


def main():
    out = BUILD / "training"
    if (out / "control-v2-manifest.json").exists():
        raise SystemExit("Control dataset already frozen")
    rng = random.Random(61067)
    emulator = Emulator()
    rows = []
    for index in range(3500):
        task = control_task(rng, index, "train")
        checked = check_program(emulator, task["reference_code"], task["public_tests"] + task["hidden_tests"])
        if not checked["pass"]:
            raise ValueError(json.dumps({"task": task, "result": checked}, ensure_ascii=False))
        answer = "<plan>" + task["reference_plan"] + "</plan><write>" + program_text(task["reference_code"]) + "</write><run/>"
        rows.append({"kind": task["kind"], "family": task["family"], "source": "verified_control_generator", "split": "train",
                     "prompt": initial_prompt(task, examples=bool(index % 2)), "answer": answer})
    validation = [control_task(random.Random(62000 + i), i, "validation") for i in range(12)]
    test = [control_task(random.Random(63000 + i), i, "test") for i in range(18)]
    for split, additions in [("validation", validation), ("test", test)]:
        old = [json.loads(x) for x in (BUILD / f"tasks/{split}.jsonl").read_text().splitlines()]
        save_jsonl(BUILD / f"tasks/{split}-extended-v2.jsonl", old + additions)
    old = [json.loads(x) for x in (out / "sft-train.jsonl").read_text().splitlines()]
    save_jsonl(out / "control-v2-sft.jsonl", rows)
    combined = old + rows
    random.Random(61068).shuffle(combined)
    save_jsonl(out / "sft-combined-v2.jsonl", combined)
    report = {"control_rows": len(rows), "combined_rows": len(combined),
              "checks": "All seven inputs of every control-flow example checked on the microcode core",
              "validation_added": len(validation), "test_added": len(test),
              "split_note": "Expression families remain disjoint; control tasks test new inputs and register allocations of taught primitives. Loop increments have disjoint train/validation/test value ranges.",
              "files": {str(p.relative_to(BUILD)): hashlib.sha256(p.read_bytes()).hexdigest()
                        for p in [out / "control-v2-sft.jsonl", out / "sft-combined-v2.jsonl", BUILD / "tasks/validation-extended-v2.jsonl", BUILD / "tasks/test-extended-v2.jsonl"]}}
    (out / "control-v2-manifest.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
