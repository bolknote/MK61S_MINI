#!/usr/bin/env python3
"""Distill a larger varied, simple conversational corpus from the user's local teacher."""
import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import json
from pathlib import Path
import random
import re
import time
import urllib.request

from generate import INTENTS, TOPICS

BEHAVIORS = dict(INTENTS, **{
    "greeting": "Greetings, thanks, farewells and asking how the bot is. Give a natural brief social reply. The bot has no physical daily life.",
    "identity": "The user asks about the bot's identity, feelings, abilities or experience. It is TinyTalk, a small chat bot. No invented human life or names.",
    "sharing": "The user shares a specific ordinary observation or small achievement. Acknowledge it with the appropriate tone and a relevant comment or question. No unrelated subject.",
    "preference": "The user describes a preference or asks about their preference already in context. Refer to the actual topic; don't ask them to repeat information already given.",
    "game": "The user starts or continues a simple chat game: naming animals, foods, colors, rhyming or making a tiny story. ACTUALLY play with a valid specific example. Don't merely agree to play. Don't repeat an item already used.",
})
SUBJECTS = TOPICS + ["paper crafts", "a rainy afternoon", "a new pet", "a simple drawing", "a small plant", "favorite colors",
                     "weekend plans", "a tired day", "a lost object", "a silly animal", "a peaceful moment", "a new skill"]
SYSTEM = (
    "Create training examples for TinyTalk, a very small friendly English chat bot. "
    "Use easy common words. Each object has context (0,2,4 alternating user and bot strings), user, answer. "
    "Use varied natural user phrasing: indirect requests, simple statements, questions and short follow-ups. "
    "Each final answer must be coherent, SPECIFIC to the conversation, and only 2-12 words. "
    "A request for an idea needs an actual action. A request to ask a question needs an actual relevant question. "
    "A game needs a valid move, not agreement to play. Facts and corrections must match the context and speakers. "
    "Ambiguous requests need clarification. If enough information was given, answer directly. "
    "Respond appropriately to positive or negative feelings. Avoid generic empty filler. "
    "Keep identity distinct: the bot is TinyTalk. It has no human job, body, family or physical personal experiences. "
    "Earlier bot replies in context must ALSO be useful, coherent and specific. "
    "All strings contain ONLY the spoken words. Never prefix a string with User:, Bot:, TinyTalk: or Assistant:. "
    "Avoid medicine, finance, arithmetic, specialized facts, long explanations and role labels. "
    "Give twelve DIFFERENT situations and answers, not merely names changed in the same template. "
    "Use context in about half the examples, including several with four earlier turns."
)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default="large-gold.jsonl")
    parser.add_argument("--rounds", type=int, default=8)
    parser.add_argument("--workers", type=int, default=16)
    args = parser.parse_args()
    output = Path(args.output);raw = output.parent / "large-raw";raw.mkdir(parents=True, exist_ok=True)
    text_schema = {"type": "string"}
    item_schema = {"type": "object", "properties": {"context": {"type": "array", "items": text_schema, "maxItems": 4},
                                                   "user": text_schema, "answer": text_schema},
                   "required": ["context", "user", "answer"], "additionalProperties": False}
    schema = {"type": "object", "properties": {"examples": {"type": "array", "items": item_schema, "minItems": 12, "maxItems": 12}},
              "required": ["examples"], "additionalProperties": False}
    tasks = [(kind, topic, repeat) for kind in BEHAVIORS for topic in SUBJECTS for repeat in range(args.rounds)]
    random.Random(24983).shuffle(tasks)

    def generate(task):
        kind, topic, repeat = task
        # Keep cache identities stable while fixing surface normalization.
        cache_system = SYSTEM.replace("All strings contain ONLY the spoken words. Never prefix a string with User:, Bot:, TinyTalk: or Assistant:. ", "")
        key = hashlib.sha256(json.dumps(["large-v1", task, cache_system]).encode()).hexdigest()
        path = raw / (key + ".json")
        if path.exists():
            response = json.loads(path.read_text())["response"]
        else:
            payload = {"model": "Qwen/Qwen3.8-Flash-Next-FP8", "temperature": 0.95, "seed": int(key[:7], 16), "max_tokens": 4400,
                       "chat_template_kwargs": {"enable_thinking": False},
                       "response_format": {"type": "json_schema", "json_schema": {"name": "chat_examples", "strict": True, "schema": schema}},
                       "messages": [{"role": "system", "content": SYSTEM},
                                    {"role": "user", "content": f"Behavior: {BEHAVIORS[kind]} Topic inspiration: {topic}. Variation set {repeat + 1}. The behavior matters more than the topic. Write twelve varied examples."}]}
            request = urllib.request.Request("http://127.0.0.1:8000/v1/chat/completions", json.dumps(payload).encode(), {"Content-Type": "application/json"})
            for attempt in range(3):
                try:
                    with urllib.request.urlopen(request, timeout=180) as stream:
                        response = json.load(stream)
                    # Only cache complete structured responses.
                    json.loads(response["choices"][0]["message"]["content"])["examples"]
                    break
                except Exception:
                    if attempt == 2:raise
                    time.sleep(1)
            path.write_text(json.dumps({"request": payload, "response": response}, ensure_ascii=False))
        result = []
        for row in json.loads(response["choices"][0]["message"]["content"])["examples"]:
            context = row["context"]
            if len(context) not in (0, 2, 4):continue
            turns = [re.sub(r"^(?:user|bot|assistant|tinytalk)\s*:\s*", "", re.sub(r"\s+", " ", t).strip().replace("\u2019", "'"), flags=re.I)
                     for t in context + [row["user"], row["answer"]]]
            if any(not t or len(t.split()) > 27 for t in turns) or not 1 <= len(turns[-1].split()) <= 15:continue
            if len(" ".join(turns)) > 900 or any(t in " ".join(turns).lower() for t in ("<|", "user:", "bot:", "qwen", "deepseek")):continue
            messages = [{"role": "user" if i % 2 == 0 else "assistant", "content": t} for i, t in enumerate(turns[:-1])]
            identity = hashlib.sha256(json.dumps(messages, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
            bucket = int(identity[:8], 16) % 100
            split = "validation" if bucket < 5 else "test" if bucket < 10 else "train"
            result.append({"id": identity, "kind": kind, "topic": topic, "messages": messages, "target": turns[-1],
                           "intent": BEHAVIORS[kind], "source": path.name, "split": split})
        return result

    rows, failures = [], []
    started = time.monotonic()
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        jobs = {pool.submit(generate, task): task for task in tasks}
        for done, job in enumerate(as_completed(jobs), 1):
            try:rows.extend(job.result())
            except Exception as error:failures.append({"task": jobs[job], "error": str(error)[:180]})
            if done % 64 == 0 or done == len(tasks):
                print(json.dumps({"done": done, "total": len(tasks), "rows": len(rows), "failures": len(failures), "seconds": round(time.monotonic() - started, 1)}), flush=True)
    rows = sorted({row["id"]: row for row in rows}.values(), key=lambda row: row["id"])
    output.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows))
    report = {"rows": len(rows), "kinds": dict(Counter(row["kind"] for row in rows)), "failures": failures,
              "seconds": time.monotonic() - started, "sha256": hashlib.sha256(output.read_bytes()).hexdigest(), "teacher": "Qwen/Qwen3.8-Flash-Next-FP8"}
    output.with_suffix(".report.json").write_text(json.dumps(report, indent=2) + "\n")
    if len(rows) < 20000:raise ValueError("Insufficient larger conversational corpus")


if __name__ == "__main__":
    main()
