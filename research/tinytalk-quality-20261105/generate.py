#!/usr/bin/env python3
"""Generate short, intent-directed chat examples for the user's local TinyTalk experiment."""
from concurrent.futures import ThreadPoolExecutor, as_completed
from collections import Counter
import argparse
import hashlib
import json
from pathlib import Path
import re
import time
import urllib.request

TOPICS = ["reading", "drawing", "music", "pets", "a quiet evening", "a rainy day", "a garden",
          "making a gift", "a small success", "a small annoyance", "a simple game", "a short walk",
          "a favorite snack", "a picture", "a story", "a hobby"]
INTENTS = {
    "idea": "The user asks for ONE concrete idea. The answer must give an actual simple action, not praise the request or ask what it is.",
    "ask": "The user asks the bot to ask a question. The answer must ask one real, relevant question about the user's day or interests.",
    "emotion": "The user shares a small good or bad event. Respond with the correct emotional tone and a relevant short comment or follow-up.",
    "chat": "Natural everyday small talk. The reply should refer to the user's actual topic and not be a stock phrase that fits anything.",
    "followup": "There are 2 or 4 earlier turns. The user asks a follow-up. Answer using the topic and details already present, without asking for information already given.",
    "correction": "There are 2 earlier turns. The user corrects a name, color, choice or preference. The answer must accept and use the corrected detail.",
    "clarify": "The request genuinely lacks a necessary detail. Ask one specific clarification instead of inventing the missing thing.",
    "role": "The user asks about a name or a personal fact already in the context. Keep the user, their friend/pet and the bot distinct. The bot's name is TinyTalk.",
}
SYSTEM = (
    "Write examples for a VERY SMALL English chat bot called TinyTalk. Use common, easy words. "
    "Output EIGHT JSON objects, one per line, with keys context, user, answer. "
    "context is an array of 0, 2, or 4 strings alternating user,bot; user is the final user's message; answer is the bot's ideal reply. "
    "User messages should sound natural, with varied phrasing. Answers must directly fulfill the requested behavior. "
    "Each answer is 4-12 words and one or two short sentences. Never include role labels or special tokens. "
    "Do not answer a request for an idea with 'Great idea' or 'What is it?'. "
    "Do not ask a vague question when enough information was already given. "
    "For a correction, use the new detail and do not repeat the wrong one. "
    "For a question request, ASK the requested question. "
    "Keep the bot's identity distinct from the user's. The bot has no human job, family, or physical life. "
    "Avoid arithmetic, specialized advice, and long factual explanations. "
    "Different objects must use different situations and answers; avoid repeating generic stock phrases."
)


def objects(text):
    decoder = json.JSONDecoder(); cursor = 0
    while cursor < len(text):
        start = text.find("{", cursor)
        if start < 0:
            return
        try:
            value, cursor = decoder.raw_decode(text, start)
        except ValueError:
            cursor = start + 1; continue
        if isinstance(value, dict):
            yield value


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default="gold.jsonl")
    parser.add_argument("--rounds", type=int, default=4)
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()
    path = Path(args.output); raw = path.parent / "gold-raw"; raw.mkdir(parents=True, exist_ok=True)
    tasks = [(kind, topic, repeat) for kind in INTENTS for topic in TOPICS for repeat in range(args.rounds)]

    def generate(task):
        kind, topic, repeat = task
        identity = hashlib.sha256(json.dumps(task).encode()).hexdigest()
        cached = raw / f"{identity}.json"
        if cached.exists():
            result = json.loads(cached.read_text())
        else:
            payload = {"model": "Qwen/Qwen3.8-Flash-Next-FP8", "temperature": 0.9,
                       "seed": int(identity[:7], 16), "max_tokens": 2200,
                       "chat_template_kwargs": {"enable_thinking": False},
                       "messages": [{"role": "system", "content": SYSTEM},
                                    {"role": "user", "content": f"Behavior: {INTENTS[kind]} Topic: {topic}. Variation {repeat + 1}. Write eight varied examples."}]}
            req = urllib.request.Request("http://127.0.0.1:8000/v1/chat/completions", json.dumps(payload).encode(), {"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=120) as stream:
                response = json.load(stream)
            result = {"request": payload, "response": response}
            cached.write_text(json.dumps(result, ensure_ascii=False) + "\n")
        text = result["response"]["choices"][0]["message"]["content"] or ""
        rows = []
        for row in objects(text):
            context, question, answer = row.get("context", []), row.get("user"), row.get("answer")
            if not isinstance(context, list) or len(context) not in [0, 2, 4]:
                continue
            if not isinstance(question, str) or not isinstance(answer, str) or not all(isinstance(t, str) for t in context):
                continue
            turns = [re.sub(r"\s+", " ", t).strip().replace("\u2019", "'") for t in context + [question, answer]]
            if any(not t or len(t.split()) > 24 for t in turns) or not 2 <= len(turns[-1].split()) <= 16:
                continue
            if len(" ".join(turns)) > 700 or any(marker in " ".join(turns).lower() for marker in ["<|", "user:", "bot:", "qwen", "deepseek"]):
                continue
            messages = [{"role": "user" if i % 2 == 0 else "assistant", "content": t} for i, t in enumerate(turns[:-1])]
            row_id = hashlib.sha256(json.dumps(messages, ensure_ascii=False).encode()).hexdigest()
            bucket = int(row_id[:8], 16) % 100
            split = "validation" if bucket < 5 else "test" if bucket < 10 else "train"
            rows.append({"id": row_id, "kind": kind, "topic": topic, "messages": messages,
                         "target": turns[-1], "intent": INTENTS[kind], "split": split, "source": cached.name})
        return rows

    started = time.monotonic(); rows, failures = [], []
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(generate, task): task for task in tasks}
        for done, future in enumerate(as_completed(futures), 1):
            try:
                rows.extend(future.result())
            except Exception as error:
                failures.append({"task": futures[future], "error": str(error)[:200]})
            if done % 32 == 0 or done == len(tasks):
                print(json.dumps({"done": done, "total": len(tasks), "accepted": len(rows), "failures": len(failures),
                                  "seconds": round(time.monotonic() - started, 1)}), flush=True)
    rows = list({row["id"]: row for row in rows}.values()); rows.sort(key=lambda row: row["id"])
    path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows))
    report = {"rows": len(rows), "kinds": dict(Counter(row["kind"] for row in rows)), "failures": failures,
              "seconds": time.monotonic() - started, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
    path.with_suffix(".report.json").write_text(json.dumps(report, indent=2) + "\n")
    if len(rows) < 2500:
        raise ValueError("Insufficient intent-directed examples")


if __name__ == "__main__":
    main()
