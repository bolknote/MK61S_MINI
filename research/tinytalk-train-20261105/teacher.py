#!/usr/bin/env python3
"""Generate short English SFT examples through the user's local Qwen API.

No external API, keys, package installation or service configuration changes.
Teacher topic groups are fixed before generation and never cross dataset splits.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import json
from pathlib import Path
import re
import time
import urllib.request

TOPICS = [
    ["friendly greetings", "reading books", "drawing pictures", "listening to music",
     "playing outdoors", "making friends", "looking after pets", "growing plants",
     "simple school activities", "getting ready for bed", "describing colors", "recognizing shapes",
     "ordinary kitchen objects", "common household tools", "everyday materials", "walking to places",
     "observing wild animals", "simple sports", "family activities", "weather observations"],
    ["sharing toys", "tidying a room", "rainy day games", "asking for help"],
    ["finding lost objects", "planning a picnic", "waiting your turn", "learning a new word"],
]
SYSTEM = (
    "Write training examples for a tiny English chatbot. Use simple, natural English. "
    "Return ONLY a JSON array of 8 different objects with keys question and answer. "
    "Each question: 4 to 16 words. Each answer: 3 to 18 words, one or two sentences. "
    "Answers must respond directly, be correct, useful, friendly, and concise. "
    "Include ordinary questions, small talk, simple requests, and elementary explanations. "
    "Do not write arithmetic, name recall, or questions about a user's personal facts. "
    "Do not invent personal human experiences for the bot. Do not name any people or AI models. "
    "Avoid medical, legal, or financial advice. No Markdown, commentary, or reasoning traces."
)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8000/v1/chat/completions")
    parser.add_argument("--model", default="Qwen/Qwen3.8-Flash-Next-FP8")
    parser.add_argument("--output", default="teacher.jsonl")
    parser.add_argument("--rounds", type=int, default=4)
    parser.add_argument("--workers", type=int, default=2)
    args = parser.parse_args()
    path = Path(args.output)
    raw_dir = path.parent / "teacher-raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    tasks = [(split, topic, repeat) for split, topics in enumerate(TOPICS) for topic in topics for repeat in range(args.rounds)]

    def generate(task):
        split, topic, repeat = task
        name = f"{split}-{topic.replace(' ', '-')}-{repeat}.json"
        raw_path = raw_dir / name
        prompt = f"Topic: {topic}. Batch variation {repeat + 1}. Generate eight varied question-answer pairs."
        request = {"model": args.model, "temperature": 0.8, "seed": 14371 + split * 1000 + repeat,
                   "max_tokens": 1400, "chat_template_kwargs": {"enable_thinking": False},
                   "messages": [{"role": "system", "content": SYSTEM}, {"role": "user", "content": prompt}]}
        if raw_path.exists():
            raw = json.loads(raw_path.read_text())["response"]
        else:
            req = urllib.request.Request(args.url, json.dumps(request).encode(), {"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=120) as response:
                raw = json.load(response)
            raw_path.write_text(json.dumps({"request": request, "response": raw}, ensure_ascii=False, indent=2) + "\n")
        text = raw["choices"][0]["message"]["content"].strip()
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text)
        pairs = json.loads(text)
        if not isinstance(pairs, list):
            raise ValueError("Teacher response is not an array")
        rows = []
        for item in pairs:
            question = str(item["question"]).strip()
            answer = str(item["answer"]).strip()
            if not 4 <= len(question.split()) <= 20 or not 3 <= len(answer.split()) <= 20:
                continue
            if any(x in (question + answer).lower() for x in ["qwen", "deepseek", "<|", "user:", "bot:"]):
                continue
            rows.append({"question": question, "answer": answer, "split": split,
                         "topic": topic, "teacher": args.model, "source": name})
        return rows

    started = time.monotonic()
    rows, failures = [], []
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(generate, task): task for task in tasks}
        for done, future in enumerate(as_completed(futures), 1):
            try:
                rows.extend(future.result())
            except Exception as error:
                failures.append({"task": futures[future], "error": str(error)[:250]})
            if done % 8 == 0 or done == len(tasks):
                print(json.dumps({"done": done, "total": len(tasks), "accepted": len(rows),
                                  "failures": len(failures), "seconds": round(time.monotonic() - started, 1)}), flush=True)
    # Stable order independent of concurrent completion order.
    rows.sort(key=lambda row: (row["split"], row["topic"], row["source"], row["question"]))
    path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows))
    report = {"teacher": args.model, "endpoint": args.url, "topics": TOPICS, "arguments": vars(args),
              "accepted": len(rows), "failed_requests": failures, "seconds": time.monotonic() - started,
              "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
              "limitations": "Synthetic teacher answers are filtered for format and length; not manually fact-checked in full"}
    path.with_suffix(".report.json").write_text(json.dumps(report, indent=2) + "\n")
    if len(rows) < len(tasks) * 4:
        raise ValueError("Too few valid teacher examples")


if __name__ == "__main__":
    main()
