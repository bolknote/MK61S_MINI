"""Reviewable text tool protocol; every result comes from the real emulator."""
from __future__ import annotations

from decimal import Decimal
import re

from tasks import program_text

SYSTEM = ("Ты программируешь МК-61. Вход уже в регистрах. Код — байты HEX, максимум 105. "
          "Ответ: <plan>краткий план</plan><write>байты</write><run/>. "
          "Для диагностики текущего кода есть <trace/>. "
          "После результата эмулятора исправь код или ответь <done/>. "
          "Успех означает прохождение проверок, вычисления выполняет эмулятор.\n")
EXAMPLE = ("Задача: X = R0 + R1.\nАссистент: <plan>взять R0 и R1; сложить</plan>"
           "<write>60 61 10 50</write><run/>\nЭмулятор: PASS\nАссистент: <done/>\n")


def extract_code(reply):
    match = re.search(r"<write>\s*([0-9a-fA-F\s]+)\s*</write>", reply)
    if not match:
        return None
    words = match[1].split()
    if not words or len(words) > 105 or any(not re.fullmatch(r"[0-9A-Fa-f]{2}", x) for x in words):
        return None
    return [int(x, 16) for x in words]


def close_number(actual, expected):
    try:
        actual, expected = Decimal(actual), Decimal(expected)
        return actual.is_finite() and abs(actual - expected) <= max(Decimal("0.000002"), abs(expected) * Decimal("0.000002"))
    except (ValueError, ArithmeticError, TypeError):
        return False


def check_program(emulator, code, tests, *, trace=False):
    details = []
    for case in tests:
        result = emulator.run(code, case["registers"], max_commands=256, max_frames=2048, trace=trace,
                              memory=bool(case.get("expected_registers")))
        passed = result["status"] == "stopped" and close_number(result.get("X"), case["expected_X"])
        passed = passed and all(close_number(result.get(name), value) for name, value in case.get("expected_registers", {}).items())
        details.append({"input": case["registers"], "expected_X": case["expected_X"],
                        "expected_registers": case.get("expected_registers", {}), "actual": result, "pass": passed})
    return {"pass": bool(details) and all(x["pass"] for x in details), "details": details}


def feedback(result):
    if result["pass"]:
        return "PASS"
    failure = next(x for x in result["details"] if not x["pass"])
    inputs = ", ".join(f"{k}={v}" for k, v in failure["input"].items())
    actual = failure["actual"]
    registers = "; ".join(f"ожидалось {name}={value}, получено {actual.get(name, '?')}" for name, value in failure.get("expected_registers", {}).items())
    suffix = "; " + registers if registers else ""
    return f"FAIL {inputs}; ожидалось X={failure['expected_X']}; получено X={actual.get('X', '?')}; статус={actual['status']}" + suffix


def trace_feedback(emulator, code, case):
    actual = emulator.run(code, case["registers"], max_commands=64, max_frames=1024, trace=True)
    events = actual.get("trace", [])[-6:]
    rows = "; ".join(f"{row['pc']:02d}:{row['opcode']:02X} X={row['X']}" for row in events)
    return f"TRACE {rows}; итог X={actual.get('X', '?')}; ожидалось X={case['expected_X']}; статус={actual['status']}"


def initial_prompt(task, *, examples=True, observation=None):
    public = "; ".join(",".join(f"{k}={v}" for k, v in case["registers"].items()) + " => X=" + case["expected_X"]
                       for case in task["public_tests"][:2])
    prompt = SYSTEM + (EXAMPLE if examples else "") + "Задача: " + task["task"] + "\nПроверки: " + public + "\n"
    if task.get("initial_code"):
        prompt += "Исправь код: " + program_text(task["initial_code"]) + "\n"
    if observation:
        prompt += "Эмулятор: " + observation + "\n"
    return prompt + "Ассистент: "


def agent_run(task, generate, emulator, *, turns=3, examples=True):
    prompt = initial_prompt(task, examples=examples)
    history = []
    valid_calls = 0
    last_code = None
    current_code = task.get("initial_code")
    public_passed = False
    for turn in range(turns):
        reply = generate(prompt)
        code = extract_code(reply)
        entry = {"turn": turn, "prompt": prompt, "reply": reply, "code": code}
        if code is None and "<trace/>" in reply and current_code:
            valid_calls += 1
            entry["tool"] = "trace"
            entry["feedback"] = trace_feedback(emulator, current_code, task["public_tests"][0])
            history.append(entry)
            prompt = initial_prompt({**task, "initial_code": current_code}, examples=examples, observation=entry["feedback"])
            continue
        if code is None or "<run/>" not in reply:
            entry["feedback"] = "Неверный вызов. Нужны <write>байты HEX</write><run/>."
            history.append(entry)
            if "<done/>" in reply and not public_passed:
                entry["false_success_claim"] = True
            prompt = initial_prompt(task, examples=examples, observation=entry["feedback"])
            continue
        valid_calls += 1
        last_code = code
        current_code = code
        checked = check_program(emulator, code, task["public_tests"])
        public_passed = checked["pass"]
        entry["public_result"] = checked
        entry["feedback"] = feedback(checked)
        history.append(entry)
        if public_passed:
            hidden = check_program(emulator, code, task["hidden_tests"])
            return {"id": task["id"], "kind": task["kind"], "pass": hidden["pass"], "public_pass": True,
                    "valid_tool_calls": valid_calls, "code": code, "hidden_result": hidden, "history": history}
        prompt = initial_prompt({**task, "initial_code": code}, examples=examples, observation=entry["feedback"])
    return {"id": task["id"], "kind": task["kind"], "pass": False, "public_pass": public_passed,
            "valid_tool_calls": valid_calls, "code": last_code, "history": history}
