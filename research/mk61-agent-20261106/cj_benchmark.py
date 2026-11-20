"""Compare hosted models with the frozen 3M outputs on the same MK-61 tasks."""

import argparse
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
import hashlib
import json
import re
import time
from urllib.error import HTTPError, URLError
from urllib.request import ProxyHandler, Request, build_opener
from unittest.mock import patch

import bj_eval
import cf_eval
import cg_eval
from ar_spec import verify
from au_teacher import REFERENCE
from av_deepseek import parse_expression
from ay_codec import UNARY_NAMES, compile_spec, decode, encode
from ay_common import read, rows, sha, write
from bj_runtime import render
from bl_spec import install
from bl_vm import CachedVM
from cg_language import parse_task
from ci_data import ROOT as SOURCE
from ci_eval import ARMS as PRIOR_ARMS, check_frozen, choice_from_auditor, clarify
from ci_runtime import preserve_power_alias
from full_isa_protocol import REGISTERS
from ha_protocol import canonical, parse_bytes


ROOT = SOURCE.parent / "hosted-model-comparison-v2"
TRANSLATION_CACHE = SOURCE.parent / "hosted-model-comparison-v1"
SERVICES = {
    "deepseek": ("deepseek-ai/DeepSeek-V4.1-Flash", 18128),
    "qwen": ("Qwen/Qwen3.8-Flash-Next-FP8", 18129),
}
ACTIONS = ["write", "run", "trace", "diag", "done", "unsure"]
SEED = 261114173
REPLY_LIMIT = 512
BATCH = 24

MANUAL = (
    'Ты управляешь программой МК-61. Верни один JSON с полями action, body и store. '
    'Для WRITE в body укажи математическое выражение через исходные регистры R0..RE, '
    'а в store укажи X или один явно запрошенный регистр для записи того же результата. '
    'Без просьбы о записи укажи X; вся память тогда сохраняется. '
    'Упряжь сама компилирует выражение и при WRITE запускает текущий открытый случай. '
    'Допустимы десятичные числа из списка «Константы» (сами значения, а не номера), pi, скобки, '
    '+, -, *, / и **. Унарные функции: ' + ', '.join(UNARY_NAMES) + '. '
    'int отсекает к нулю, frac сохраняет знак, sign(0)=0. '
    'Тригонометрия и обратные функции используют режим углов из состояния, включая GRAD. '
    'Пиши формулу для всех входов. Сохраняй запрошенные операции, даже при постоянном результате. '
    'Пример WRITE: {"action":"write","body":"square(R7)","store":"R8"}. '
    'Для остальных действий store должен быть X. RUN: body = номер случая "00" или "01". '
    'DIAG 04 FF FF 00 00 запрашивает пересмотр текущей гипотезы без замены программы. '
    'Другие DIAG используют пять байтов из состояния. TRACE, DONE, UNSURE принимают пустой body. '
    'В запросе на первичную формулу или пересмотр верни WRITE. '
    'В цикле сначала сравни фактические запуски с исходной задачей и текущей формулой. '
    'Если программа неверна, WRITE заменяет её. Если гипотеза неверна, запроси DIAG 04 FF FF 00 00. '
    'После WRITE можно запустить недостающий случай. DONE означает, что исходная задача решена. '
    'Если DONE отклонён, воспользуйся замечанием упряжи. stopped означает только останов. '
    'Если решения нет, верни UNSURE. В состоянии «WRITE с компактной SPEC» означает WRITE с выражением. '
    'Описание ниже нужно для чтения текущего HEX, в ответе его печатать не требуется.\n'
    + REFERENCE.split('WRITE —')[0]
)

ACTOR_MANUAL = (
    'Ты отлаживаешь загруженную программу МК-61. Верни ровно одно следующее действие в JSON action/body/store. '
    'Посмотри на строку «не запускались» у текущей версии: если там указан случай, сначала запусти его '
    'действием run с номером "00" или "01" в body. '
    'Когда все открытые случаи запускались, сопоставь факты и текущий код с исходным условием. '
    'При верной программе заверши: {"action":"done","body":"","store":"X"}. '
    'Если программа неверна, используй write, где body — формула для всех входов, а store — X или один регистр '
    'для записи того же результата, если это явно просят. Формулы используют исходные R0..RE, '
    'десятичные значения из таблицы констант, pi, скобки, +, -, *, /, ** и функции ' + ', '.join(UNARY_NAMES) + '. '
    'int отсекает к нулю, frac сохраняет знак, sign(0)=0. Режим углов устанавливает упряжь. '
    'WRITE сам запускает текущий случай; остальные случаи новой версии запускай отдельно. '
    'Повтор той же программы снова сбросит её проверки. Если ошибка в текущей гипотезе, '
    'запроси её пересмотр через diag с body "04 FF FF 00 00". При отказе DONE учти причину отказа. '
    'Для остальных действий store="X". TRACE, DONE и UNSURE имеют пустой body. '
    'Справочник ниже позволяет читать текущий HEX.\n' + REFERENCE.split('WRITE —')[0]
)


def closed_data():
    manifest = check_frozen()
    dataset = SOURCE / "closed.jsonl"
    assert sha(dataset) == read(SOURCE / "wording-frozen.json")["closed_sha256"]
    assert read(SOURCE / "complete.json")["complete"]
    return rows(dataset), manifest


def policy():
    return {
        "driver_sha256": sha(__file__), "dataset_sha256": sha(SOURCE / "closed.jsonl"),
        "source_manifest_sha256": sha(SOURCE / "frozen.json"),
        "q4_results_sha256": {arm: sha(SOURCE / (arm.replace("_", "-") + ".json")) for arm in PRIOR_ARMS},
        "models": {role: model for role, (model, _) in SERVICES.items()},
        "thinking": False, "temperature": 0, "seed": SEED,
        "reply_tokens": REPLY_LIMIT, "turns": bj_eval.MAX_TURNS,
        "tasks": 256, "starts_per_task": 2,
        "separate_runtime_prompt": True, "uses_cached_translation_responses_by_full_request_hash": True,
        "gold_only_for_scoring_and_simulated_confirmation": True,
        "deepseek_helped_author_160_wordings_in_separate_calls": True,
    }


def context_from_prompt(prompt):
    # The frozen snapshot is the only input available to the hosted adapter.
    angle = re.match(r"МК-61: (DEG|RAD|GRAD);", prompt)[1]
    line = next(line for line in prompt.splitlines() if line.startswith("Константы: "))
    pool = []
    for item in line.removeprefix("Константы: ").split(";"):
        index, value = item.split("=", 1)
        assert int(index, 16) == len(pool)
        pool.append(value)
    return angle, pool


def tool_prompt(snapshot):
    lines = []
    for line in snapshot.splitlines():
        if line.startswith(("Вызовы:", "Заметки:", "Ассистент:")):
            continue
        if line.startswith("Осталось действий:"):
            line = line.split(". Исправление:", 1)[0] + "."
        lines.append(line)
    return "\n".join([*lines, "По этому состоянию выбери одно следующее действие."])


def normalize_literals(expression, pool):
    if not isinstance(expression, list):
        return expression
    operator, *parts = expression
    parts = [normalize_literals(part, pool) for part in parts]
    if operator == "neg" and isinstance(parts[0], dict) and "constant" in parts[0]:
        candidate = canonical(-Decimal(parts[0]["constant"]))
        if candidate in pool:
            return {"constant": candidate}
    return [operator, *parts]


def decode_output(content, forced, angle, pool):
    answer = json.loads(content)
    if not isinstance(answer, dict) or set(answer) != {"action", "body", "store"}:
        raise ValueError("ACTION_OBJECT")
    action, body, store = answer["action"], answer["body"], answer["store"]
    if action not in ([forced] if forced else ACTIONS) or type(body) is not str or len(body) > 512:
        raise ValueError("ACTION_BODY")
    if action == "write":
        if store not in ["X", *REGISTERS]:
            raise ValueError("STORE_REGISTER")
        body = body.replace("^", "**").replace("−", "-").replace("π", "pi").strip()
        expr = normalize_literals(parse_expression(body), pool)
        spec = {"angle": angle, "X": expr, "writes": {} if store == "X" else {store: expr}}
        encoded = encode(spec, pool)
        if decode(encoded, pool, angle) != spec:
            raise ValueError("SPEC_ROUND_TRIP")
        compile_spec(spec, pool)
        return action, encoded
    if store != "X":
        raise ValueError("STORE_REQUIRES_WRITE")
    encoded = parse_bytes(body, empty=True)
    expected = {"run": 1, "diag": 5}.get(action, 0)
    if len(encoded) != expected or (action == "run" and encoded[0] not in (0, 1)):
        raise ValueError("ACTION_BODY_LENGTH")
    return action, encoded


class Actor:
    def __init__(self, model, port, folder, parallel):
        self.model = model
        self.url = f"http://127.0.0.1:{port}/v1"
        self.cache = folder / "cache"
        self.translation_cache = TRANSLATION_CACHE / folder.name / "cache"
        self.pool = parallel
        self.opener = build_opener(ProxyHandler({}))

    def check_model(self):
        with self.opener.open(self.url + "/models", timeout=10) as response:
            live = json.load(response)
        if not any(row["id"] == self.model for row in live["data"]):
            raise RuntimeError(f"The configured service does not expose {self.model}")

    def request(self, prompt, forced):
        schema = {
            "type": "object", "additionalProperties": False, "required": ["action", "body", "store"],
            "properties": {
                "action": {"type": "string", "enum": [forced] if forced else ACTIONS},
                "body": {"type": "string"}, "store": {"type": "string", "enum": ["X", *REGISTERS]},
            },
        }
        payload = {
            "model": self.model, "messages": [
                {"role": "system", "content": MANUAL if forced else ACTOR_MANUAL},
                {"role": "user", "content": prompt if forced else tool_prompt(prompt)},
            ],
            "temperature": 0, "seed": SEED, "max_tokens": REPLY_LIMIT,
            "chat_template_kwargs": {"thinking": False, "enable_thinking": False},
            "response_format": {"type": "json_schema", "json_schema": {"name": "mk61_action", "strict": True, "schema": schema}},
        }
        data = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode()
        path = self.cache / (hashlib.sha256(data).hexdigest() + ".json")
        if path.exists():
            return read(path)
        cached_translation = self.translation_cache / path.name
        if forced == "write" and cached_translation.exists():
            return read(cached_translation)
        request = Request(self.url + "/chat/completions", data, {"Content-Type": "application/json"})
        start = time.monotonic()
        for attempt in range(4):
            try:
                with self.opener.open(request, timeout=65) as stream:
                    response = json.load(stream)
                choice = response["choices"][0]
                result = {"model": response.get("model"), "content": choice["message"].get("content") or "",
                          "usage": response.get("usage"), "finish_reason": choice.get("finish_reason"),
                          "reasoning_sent": bool(choice["message"].get("reasoning_content") or choice["message"].get("reasoning")),
                          "seconds": time.monotonic() - start}
                # The snapshots and their hashes are also kept in the scored histories.
                write(path, result)
                return result
            except HTTPError as error:
                if error.code not in (408, 429, 500, 502, 503, 504) or attempt == 3:
                    raise RuntimeError(f"{self.model}: HTTP {error.code}: {error.read(800).decode(errors='replace')}") from error
            except (TimeoutError, URLError, ConnectionError):
                if attempt == 3:
                    raise
            time.sleep(2 ** attempt)

    def one(self, prompt, forced=None):
        angle, pool = context_from_prompt(prompt)
        result = self.request(prompt, forced)
        try:
            action, encoded = decode_output(result["content"], forced, angle, pool)
            error = None
        except (ValueError, ArithmeticError, TypeError, KeyError, SyntaxError) as exc:
            action, encoded, error = None, [], str(exc)
        usage = result["usage"] or {}
        return {**result, "action": action, "body": encoded, "codec_error": error,
                "input_tokens": usage.get("prompt_tokens"), "completion_tokens": usage.get("completion_tokens")}

    def generate(self, model, tokenizer, prompts, forced_action=None):
        # Identical RUN states may share a request, including across batch boundaries.
        unique = dict.fromkeys(prompts)
        values = self.pool.map(lambda prompt: self.one(prompt, forced_action), unique)
        output = dict(zip(unique, values, strict=True))
        return [output[prompt].copy() for prompt in prompts]


def progress(folder, stage, count, total):
    status = {"stage": stage, "done": count, "total": total}
    write(folder / "progress.json", status)
    print(folder.name, status, flush=True)


def batches(folder, stage, goals, run):
    result = []
    for start in range(0, len(goals), BATCH):
        group = goals[start:start + BATCH]
        path = folder / stage / f"{start:03}.json"
        if path.exists():
            chunk = read(path)
        else:
            chunk = run(group)
            write(path, chunk)
        actual = {row.get("task_id", row["id"]) for row in chunk}
        assert actual == {g["id"] for g in group}, path
        result.extend(chunk)
        progress(folder, stage, start + len(group), len(goals))
    return result


def preflight(actor, vm, folder):
    cases = [
        ("Посчитай квадрат R7 и запиши результат в R8.", ["square", "R7"], "R8"),
        ("Вычти 1.25 из R7, оставь результат в X.", ["-", "R7", {"constant": "1.25"}], "X"),
    ]
    values = []
    for task, expression, store in cases:
        pool = ["0", "1", "1.25"]
        prompt = f"МК-61: DEG; 105 ячеек.\nКонстанты: 00=0;01=1;02=1.25\nЗадача: {task}"
        output = actor.one(prompt, "write")
        spec = {"X": expression, "writes": {} if store == "X" else {store: expression}, "angle": "DEG"}
        good = not output["codec_error"] and verify(
            vm, compile_spec(decode(output["body"], pool, "DEG"), pool), pool, spec,
            [{"R7": "2.25", "R8": "-1.5"}, {"R7": "-3.25", "R8": "0.875"}],
        )["status"] == "TESTED"
        values.append({"task": task, "output": output, "pass": good})
    write(folder / "preflight.json", values)
    if not all(item["pass"] for item in values):
        raise RuntimeError(f"Preflight failed for {actor.model}; see {folder / 'preflight.json'}")

    spec = {"X": ["square", "R7"], "writes": {}, "angle": "DEG"}
    wrong = {**spec, "X": ["abs", "R7"]}
    goal = {"id": "comparison:probe", "task": cases[0][0].replace("запиши результат в R8", "оставь результат в X"),
            "spec": spec, "pool": pool, "public_inputs": [{"R7": "2.25"}, {"R7": "-3.25"}],
            "checker_inputs": [{"R7": "1.25"}]}
    correct = bj_eval.Session(goal, compile_spec(spec, pool), vm, "spec", spec, True)
    start = correct.request()
    correct.apply_action("write", encode(spec, pool))
    incorrect = bj_eval.Session(goal, compile_spec(wrong, pool), vm, "spec", spec, True)
    states = {"correct": start, "missing_case": correct.request(), "wrong": incorrect.request()}
    trial = {name: actor.one(state) for name, state in states.items()}
    write(folder / "runtime-preflight.json", trial)
    if trial["correct"]["action"] != "done" or trial["missing_case"]["action"] != "run":
        raise RuntimeError(f"RUN/DONE transport preflight failed for {actor.model}; see {folder / 'runtime-preflight.json'}")


def benchmark(role, workers):
    goals, source_manifest = closed_data()
    assert len(goals) == 256 and bj_eval.MAX_TURNS == 12
    frozen = policy()
    path = ROOT / "policy.json"
    if path.exists():
        assert read(path) == frozen
    else:
        write(path, frozen)
    folder = ROOT / role
    install()
    vm = CachedVM()
    with ThreadPoolExecutor(max_workers=workers) as executor:
        actor = Actor(*SERVICES[role], folder, executor)
        actor.check_model()
        preflight(actor, vm, folder)
        with patch.object(bj_eval.core, "generate", actor.generate), patch.object(bj_eval.core, "render", render), \
             patch.object(bj_eval, "generate", actor.generate), patch.object(cg_eval, "ROOT", folder), \
             patch.object(bj_eval.core, "mutant", lambda g, vm, kind: (g["error_kind"], g["bad_body"])):
            primary = batches(folder, "translation", goals, lambda group: bj_eval.core.primary(None, None, group, "spec", vm))
            write(folder / "translation.json", primary)
            plans = {row["id"]: row for row in primary}
            full = batches(folder, "cycle", goals, lambda group: bj_eval.episodes(None, None, group, plans, vm, "self"))
            write(folder / "cycle.json", full)
            progress(folder, "independent_SPEC", 0, len(goals))
            with patch.object(cf_eval, "checked_program", preserve_power_alias):
                automatic = cf_eval.run_variant(goals, plans, full, parse_task, True, vm)
            _, confirmed = cg_eval.confirmation_arms(goals, primary, automatic, actor.generate, vm)
            rejected = [row for row in confirmed if row.get("confirmation") is False]
            picked, attempts = clarify(goals, rejected, vm, answer=choice_from_auditor)
            write(folder / "assisted.json", {"records": [picked.get(row["id"], row) for row in confirmed], "attempts": attempts})
    assert check_frozen() == source_manifest and policy() == frozen
    assert len(primary) == 256 and len(full) == 512
    write(folder / "complete.json", {"model": actor.model, "tasks": len(primary), "episodes": len(full)})
    progress(folder, "complete", len(goals), len(goals))


if __name__ == "__main__":
    cli = argparse.ArgumentParser()
    cli.add_argument("role", choices=SERVICES)
    cli.add_argument("--workers", type=int, default=8)
    args = cli.parse_args()
    benchmark(args.role, args.workers)
