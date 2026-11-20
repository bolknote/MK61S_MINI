"""Make real post-review tool states and verify DeepSeek's next actions."""

import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache
import hashlib
import itertools
import random
from unittest.mock import patch

from transformers import AutoTokenizer

import bj_teacher
from aq_protocol import NO_BODY, END, header_ids, prompt_ids
from ar_spec import equivalent, infer, spec_text, verify
from av_deepseek import parse_expression
from ay_codec import encode, to_program
from ay_common import read, rows, save_rows, sha, write
from be_language import paths3
from bh_common import signature
from bj_runtime import Session
from bl_spec import install
from bl_vm import CachedVM
from bs_data import worker
from ce_data import reword
from ce_wording import editorial_question
from ck_data import local_pair
from ck_train import CURRENT, REPO
from cl_data import ROOT as PREVIOUS
from cn_runtime import CONTEXT, limit, shortened
from full_isa_protocol import REGISTERS
from ha_protocol import bytes_text, canonical


ROOT = PREVIOUS.with_name("kon-tiki-executor-prompt-distill-v1")
TEACHER_URL = "http://127.0.0.1:18119/v1/chat/completions"
SEED = 261114991
REVIEW_GROUPS = ("repair", "keep", "bad_spec_good_code", "bad_spec_bad_code", "run_missing")
SYSTEM = """Ты учитель исполнителя МК-61. Перед тобой независимые публичные состояния
после уже использованного пересмотра SPEC. Текст full_executor_prompt описывает
состояние и обычные правила исполнителя. Выбери действие строго по этим приоритетам.
1. Сначала из поля «Задача» получи требуемую формулу и место записи. Сравни их с
«Текущая гипотеза». Если гипотеза отличается по математическому смыслу, только
UNSURE. В этой ветке WRITE меняет программу, но не исправляет гипотезу проверки.
Например, задача «возведи 2.5 в степень 10», гипотеза pow10(2.5) — всегда UNSURE.
2. Если гипотеза верна, сравни вычисление текущей программы и публичные Факт 00/01
с задачей. stopped означает остановку, а не верность. Если есть неверный результат
или неверная запись в регистр — WRITE. Одного контрпримера достаточно.
3. Если код корректен, а в строке «не запускались» указан тест, выбери RUN этого
теста, даже если код выглядит правильным. После прохождения обоих тестов — DONE.
Никогда не выбирай WRITE для правильной программы. decoded_program — формула
фактического текущего HEX по символьному исполнению. Она не является ответом
на условие. Режим углов уже задан. Для каждого объекта заново пройди приоритеты.
Для WRITE заполни formula и store; store — явно требуемый R0..RE или пустая строка.
В formula допустимы исходные регистры R0..RE, числа из таблицы, pi, + - * / **,
sin cos tan asin acos atan sqrt square abs neg reciprocal exp pow10 ln log10 int frac sign,
pow(основание,показатель), скобки. Не заменяй Rn его значением в одном тесте.
Для RUN заполни case двумя HEX цифрами. Остальные строки пустые.
Соблюдай порядок и верни все предоставленные id. Только JSON."""
PROPS = {
    "id": {"type": "string"},
    "action": {"type": "string", "enum": ["write", "run", "done", "unsure"]},
    "formula": {"type": "string"},
    "store": {"type": "string", "enum": ["", *REGISTERS]},
    "case": {"type": "string", "enum": ["", "00", "01"]},
}


@lru_cache(maxsize=1)
def tokenizer():
    return AutoTokenizer.from_pretrained(CURRENT / "working/hf", local_files_only=True)


def tokenized(prompt, action, body):
    tok = tokenizer()
    x = prompt_ids(tok, prompt)
    header = [] if action in NO_BODY else header_ids(tok, action)
    y = [] if action in NO_BODY else tok.encode(bytes_text(body), add_special_tokens=False) + [END]
    return x + header + y, [-100] * (len(x) + len(header)) + y, len(x) - 1


def intent(goal):
    return (goal["spec"]["angle"], " ".join(goal["task"].casefold().replace("ё", "е").split()))


def training_goals():
    excluded = [*rows(PREVIOUS / "closed.jsonl"), *rows(PREVIOUS / "development.jsonl"),
                *rows(PREVIOUS / "recovery.jsonl")]
    held_text = {intent(g) for g in excluded}
    held_spec = {signature(g["spec"]) for g in excluded}
    held_paths = set().union(*(paths3(g["spec"]["X"]) for g in excluded if g["split"] in ("closed", "development")))
    result = {}
    full = {g["id"]: g for g in rows(PREVIOUS / "train-asts.jsonl")}
    for goal in rows(PREVIOUS / "train-compact.jsonl"):
        row = reword(full[goal["id"]], goal["task"], "composition_recovery_train")
        result[intent(row)] = row
    old = rows(PREVIOUS.parent / "kon-tiki-paired-compositions-v1" / "train.jsonl")
    old += rows(CURRENT.parent / "retired-train.jsonl")
    random.Random(SEED).shuffle(old)
    for row in old:
        if (intent(row) not in held_text and signature(row["spec"]) not in held_spec
                and not paths3(row["spec"]["X"]) & held_paths):
            result.setdefault(intent(row), row)
    assert not set(result) & held_text
    assert not {signature(row["spec"]) for row in result.values()} & held_spec
    return [{**row, "id": f"cn:train:{i:04}"} for i, row in enumerate(result.values())]


def lesson(goal, session, source, action, body=()):
    prompt = session.request()
    length = len(tokenized(prompt, action, body)[0])
    short = shortened(prompt, goal["task"], tokenizer()) if source in REVIEW_GROUPS else None
    if short is not None and len(prompt_ids(tokenizer(), short)) > limit(tokenizer()):
        return None
    if short is None and length > CONTEXT:
        return None
    identity = hashlib.sha256(prompt.encode()).hexdigest()[:20]
    return {"id": identity, "task_id": goal["id"], "full": prompt, "short": short,
            "group": source, "action": action, "body": list(body)}


def revised_session(goal, vm, code, hypothesis, writer):
    session = Session(goal, code, vm, "spec", hypothesis, True)
    if writer:
        session.apply_action("write", goal["spec_body"])
    session.apply_action("diag", [4, 255, 255, 0, 0])
    session.replan_attempted = True
    session.pending_replan = False
    session.apply_replan(encode(hypothesis, goal["pool"]))
    return session


def review_states(goal, vm):
    for group in REVIEW_GROUPS:
        good_spec = group in ("repair", "keep", "run_missing")
        good_code = group in ("keep", "bad_spec_good_code", "run_missing")
        hypothesis = goal["spec"] if good_spec else goal["bad_spec"]
        start = goal["reference_body"] if good_code else goal["bad_body"]
        session = revised_session(goal, vm, start, hypothesis, group == "run_missing")
        if group == "repair":
            yield lesson(goal, session, group, "write", goal["spec_body"])
        elif group == "keep":
            yield lesson(goal, session, group, "done")
        elif group == "run_missing":
            missing, = set(range(len(goal["public_inputs"]))) - session.runs.keys()
            yield lesson(goal, session, group, "run", [missing])
        else:
            yield lesson(goal, session, group, "unsure")


def replay_states(goal, vm):
    reference = goal["reference_body"]
    packet = goal["spec_body"]
    session = Session(goal, reference, vm, "spec", goal["spec"], True)
    yield lesson(goal, session, "old_done", "done")
    session = Session(goal, goal["bad_body"], vm, "spec", goal["spec"], True)
    yield lesson(goal, session, "old_write", "write", packet)
    session.apply_action("write", packet)
    missing, = set(range(len(goal["public_inputs"]))) - session.runs.keys()
    yield lesson(goal, session, "old_run", "run", [missing])
    session.apply_action("run", [missing])
    yield lesson(goal, session, "old_done", "done")
    session = Session(goal, reference, vm, "spec", goal["bad_spec"], True)
    yield lesson(goal, session, "old_diag", "diag", [4, 255, 255, 0, 0])


def accept_teacher(item, state, goal, vm):
    if item["action"] != state["action"]:
        raise ValueError("action disagrees with verified state")
    if state["action"] == "run":
        if int(item["case"], 16) != state["body"][0]:
            raise ValueError("wrong public test")
        return state
    if state["action"] != "write":
        return state

    expr = parse_expression(item["formula"])
    spec = {"X": expr, "angle": goal["spec"]["angle"],
            "writes": {item["store"]: expr} if item["store"] else {}}
    fixture = goal["public_inputs"] + goal["checker_inputs"] + goal["audit_inputs"]
    if not equivalent(spec, goal["spec"], fixture)["tested_equal"]:
        raise ValueError("teacher formula fails task oracle")
    try:
        body = encode(spec, goal["pool"])
        program, _ = to_program(body, goal["pool"], goal["spec"]["angle"], "spec")
    except ValueError:
        # A verified algebraic alias can contain folded numbers absent from the pool.
        body = state["body"]
        program, _ = to_program(body, goal["pool"], goal["spec"]["angle"], "spec")
    if verify(vm, program, goal["pool"], spec, fixture)["status"] != "TESTED":
        raise ValueError("encoded WRITE fails ROM verification")
    return {**state, "body": body}


def ask(client, batch, by_id):
    data = []
    for row in batch:
        goal = by_id[row["task_id"]]
        code = goal["reference_body"] if row["group"] in ("keep", "run_missing", "bad_spec_good_code") else goal["bad_body"]
        program = infer(code, goal["pool"], goal["spec"]["angle"])
        data.append({"id": row["id"], "full_executor_prompt": row["full"], "decoded_program": spec_text(program)})
    result = client.call(SYSTEM, data, bj_teacher.schema(PROPS), "mk61_executor_distill")
    return {item["id"]: item for item in result}


def collect(smoke=False):
    ROOT.mkdir(exist_ok=True)
    install()
    rng = random.Random(SEED)
    goals = training_goals()
    rng.shuffle(goals)
    by_id = {g["id"]: g for g in goals}
    assert len(by_id) == len(goals)
    vm = CachedVM(512)
    source = []
    balance = Counter()
    for goal in goals:
        is_power = goal.get("family") == "power"
        variant = balance["power" if is_power else "regular"] % len(REVIEW_GROUPS)
        schedule = ("bad_spec_good_code", "repair", "bad_spec_bad_code", "keep", "run_missing")
        index = REVIEW_GROUPS.index(schedule[variant])
        if is_power and balance["power"] >= 80:
            continue
        if not is_power and balance["regular"] >= 320:
            continue
        group = list(review_states(goal, vm))
        if group[index] is None:
            continue
        source.append(group[index])
        balance["power" if is_power else "regular"] += 1
        if smoke and len(source) == 12:
            break
    deepseek, audit = [], []
    batches = [source[i:i + 3] for i in range(0, len(source), 3)]
    with patch.multiple(bj_teacher, ROOT=ROOT, URL=TEACHER_URL):
        client = bj_teacher.Client()
        with ThreadPoolExecutor(max_workers=8) as pool:
            for i, (batch, answers) in enumerate(zip(batches, pool.map(lambda b: ask(client, b, by_id), batches), strict=True), 1):
                for state in batch:
                    answer = answers.get(state["id"])
                    error = None
                    try:
                        if answer is None:
                            raise ValueError("missing teacher answer")
                        deepseek.append(accept_teacher(answer, state, by_id[state["task_id"]], vm))
                    except (ValueError, KeyError, TypeError, SyntaxError, ArithmeticError) as exc:
                        error = str(exc)
                    audit.append({"id": state["id"], "task_id": state["task_id"], "group": state["group"],
                                  "target_action": state["action"], "teacher": answer, "rejected": error})
                if i % 5 == 0 or i == len(batches):
                    progress = {"batches": i, "total": len(batches), "accepted": len(deepseek)}
                    write(ROOT / "teacher-status.json", progress)
                    print(progress, flush=True)
    counts = Counter(row["group"] for row in deepseek)
    save_rows(ROOT / ("teacher-smoke.jsonl" if smoke else "teacher-audit.jsonl"), audit)
    print({"queried": balance, "accepted": counts})
    if smoke:
        assert len(deepseek) >= 5 and {r["action"] for r in deepseek} >= {"write", "unsure"}
        return
    assert len(deepseek) >= 70 and set(counts) == set(REVIEW_GROUPS), counts
    save_rows(ROOT / "teacher-lessons.jsonl", deepseek)
    # The verified synthetic pairs provide coverage where the teacher disagreed.
    # Retain the rest of the original protocol with ordinary-format replay.
    replay = []
    for goal in goals[:350]:
        replay.extend(r for r in [*review_states(goal, vm), *replay_states(goal, vm)] if r is not None)
    save_rows(ROOT / "replay-lessons.jsonl", replay)
    write(ROOT / "teacher-frozen.json", {"name": bj_teacher.MODEL, "queries": len(source), "training_only": True,
                                       "accepted": counts, "teacher_actions": Counter(r["action"] for r in deepseek),
                                       "replay": Counter(r["group"] for r in replay),
                                       "files": {name: sha(ROOT / name) for name in (
                                           "teacher-audit.jsonl", "teacher-lessons.jsonl", "replay-lessons.jsonl")}})


def fresh_check():
    """Fresh compositions and paired base/exponent reversals, excluded from lessons."""
    install()
    rng = random.Random(SEED + 11)
    old = [*training_goals(), *rows(PREVIOUS / "development.jsonl"), *rows(PREVIOUS / "closed.jsonl")]
    held = {signature(g["spec"]) for g in old}
    occupied = set().union(*(paths3(g["spec"]["X"]) for g in old))
    goals = []
    triples = list(itertools.permutations(("square", "sqrt", "sin", "atan", "abs", "ln", "frac", "neg",
                                          "cos", "reciprocal", "int", "log10"), 3))
    rng.shuffle(triples)
    family = None
    n_family = 0
    for attempt in range(2400):
        is_power = len(goals) < 32
        store = REGISTERS[attempt % 15]
        angle = ("DEG", "RAD", "GRAD")[attempt % 3]
        value = {"constant": canonical(f"{2 + (attempt // 11) % 3}.{39127 + attempt}")}
        if is_power:
            literal = {"constant": "10"}
            expr = ["pow", value, literal] if len(goals) % 2 else ["pow10", value]
        else:
            if family is None or n_family == 4:
                family = next(t for t in iter(triples.pop, None) if t not in occupied)
                n_family = 0
            outer, middle, inner = family
            expr = [outer, [middle, [inner, rng.choice(REGISTERS)]]]
            if len(goals) % 3 == 1:
                expr = [rng.choice(("+", "-", "*")), expr, value]
        group = "power" if is_power else "composition"
        spec = {"X": expr, "angle": angle, "writes": {store: expr} if attempt % 5 else {}}
        key = signature(spec)
        if key in held:
            continue
        g = worker((spec, f"cn:fresh:{len(goals):03}", "closed", group, SEED + attempt, "bracket",
                    ("operation", "argument", "order")[attempt % 3], []))
        if g is None:
            continue
        text = local_pair(g, attempt) if is_power else editorial_question(spec, attempt)
        g = reword(g, text, "local_fresh")
        held.add(key)
        if not is_power:
            n_family += 1
        goals.append(g)
        if len(goals) == 96:
            break
    assert len(goals) == 96
    save_rows(ROOT / "fresh.jsonl", goals)
    write(ROOT / "fresh-frozen.json", {"sha256": sha(ROOT / "fresh.jsonl"), "tasks": len(goals),
                                      "families": Counter(g["family"] for g in goals), "seed": SEED + 11})


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("stage", choices=("smoke", "collect", "fresh"))
    stage = parser.parse_args().stage
    ROOT.mkdir(exist_ok=True)
    if stage == "fresh":
        fresh_check()
    else:
        collect(stage == "smoke")
