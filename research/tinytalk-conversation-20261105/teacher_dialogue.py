#!/usr/bin/env python3
"""Generate short multi-turn conversations using the user's local Qwen service."""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import json
from pathlib import Path
import re
import time
import urllib.request

TOPICS = [
    "books and stories", "drawing and colors", "music and songs", "a walk outdoors",
    "pets and animals", "a quiet evening", "a rainy afternoon", "a small success",
    "feeling bored", "feeling a little tired", "a simple hobby", "a friendly greeting",
    "sharing good news", "a small disappointment", "weekend plans", "making something by hand",
    "choosing a game", "trying something new", "a garden or houseplant", "a favorite snack",
    "a funny everyday moment", "a trip to a park", "looking at the sky", "a small daily routine",
    "a childhood story", "learning a new skill", "asking for company", "a cozy room",
    "a photograph", "a simple celebration", "finding a lost item", "a change of plans",
    "a gift for a friend", "organizing a shelf", "a short break", "something the user likes",
    "something the user dislikes", "a peaceful place", "a lighthearted joke", "ending a conversation",
]
INTENTS = ["share an experience", "ask for a simple idea", "chat about a preference",
           "ask a follow-up question", "express a mild feeling", "correct a small misunderstanding",
           "ask the bot a casual question", "continue an earlier topic"]
SYSTEM = (
    "Create training data for TinyTalk, a very small friendly English chatbot. "
    "Return ONLY a JSON array of SIX conversations. Each conversation is an array of SIX strings: "
    "user, bot, user, bot, user, bot. No role labels or Markdown. "
    "Use varied, everyday small talk. Most user messages are statements, not quiz questions. "
    "The bot should respond to the actual message, show interest, and keep the thread natural. "
    "A follow-up question is welcome when useful, but never force one into every reply. "
    "Each user turn: 2-14 words. Each bot turn: 4-18 words, one or two short sentences. "
    "Use easy, common words. Avoid long lists, lectures, facts quizzes and arithmetic. "
    "Make the later turns depend on earlier turns. Include different moods, preferences and tiny corrections. "
    "Vary openings and response wording; do not fill conversations with 'That sounds great' or other stock phrases. "
    "TinyTalk is a chat bot: it has no human job, family, age, hometown or physical experiences. "
    "It may talk about enjoying stories, music, ideas or conversation. Its name, if asked, is TinyTalk. "
    "The user can have personal experiences and a name. Keep the two speakers distinct. "
    "Do not use the names of other AI systems or claim to perform actions outside the chat."
)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default="teacher-dialogues.jsonl")
    parser.add_argument("--rounds", type=int, default=8)
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()
    path = Path(args.output)
    raw_dir = path.parent / "teacher-raw"
    raw_dir.mkdir(parents=True, exist_ok=True)

    def generate(task):
        topic_index, repeat = task
        topic = TOPICS[topic_index]
        name = f"{topic_index:02d}-{repeat:02d}.json"
        raw_path = raw_dir / name
        payload = {"model": "Qwen/Qwen3.8-Flash-Next-FP8", "temperature": 0.9,
                   "seed": 73133 + topic_index * 97 + repeat, "max_tokens": 2600,
                   "chat_template_kwargs": {"enable_thinking": False},
                   "messages": [{"role": "system", "content": SYSTEM},
                                {"role": "user", "content": f"Topic: {topic}. Focus: {INTENTS[repeat % len(INTENTS)]}. Variation {repeat + 1}. Write six different natural conversations."}]}
        if raw_path.exists():
            response = json.loads(raw_path.read_text())["response"]
        else:
            request = urllib.request.Request("http://127.0.0.1:8000/v1/chat/completions", json.dumps(payload).encode(),
                                             {"Content-Type": "application/json"})
            with urllib.request.urlopen(request, timeout=120) as stream:
                response = json.load(stream)
            raw_path.write_text(json.dumps({"request": payload, "response": response}, ensure_ascii=False) + "\n")
        text = response["choices"][0]["message"]["content"].strip()
        text = re.sub(r"```(?:json)?", "", text)
        # Qwen sometimes emits one valid array per line instead of an outer array.
        # Decode complete arrays only, without editing their strings or inventing turns.
        conversations, cursor = [], 0
        decoder = json.JSONDecoder()
        while cursor < len(text):
            start = text.find("[", cursor)
            if start < 0:
                break
            try:
                value, cursor = decoder.raw_decode(text, start)
            except ValueError:
                cursor = start + 1
                continue
            if isinstance(value, list) and all(isinstance(t, str) for t in value):
                if len(value) >= 6 and len(value) % 6 == 0:
                    conversations.extend(value[i:i+6] for i in range(0, len(value), 6))
            elif isinstance(value, list):
                conversations.extend(value)
        accepted = []
        for turns in conversations:
            if not isinstance(turns, list) or len(turns) != 6 or not all(isinstance(t, str) for t in turns):
                continue
            turns = [t.strip().replace("\u2019", "'") for t in turns]
            if any(not t or len(t.split()) > (20 if i % 2 == 0 else 24) for i, t in enumerate(turns)):
                continue
            if any(any(marker in t.lower() for marker in ["<|", "user:", "bot:", "qwen", "deepseek"]) for t in turns):
                continue
            identity = hashlib.sha256(json.dumps(turns, ensure_ascii=False).encode()).hexdigest()
            accepted.append({"id": identity, "source": "qwen_dialogue", "topic": topic,
                             "turns": turns, "raw_source": name})
        return accepted

    tasks = [(i, r) for i in range(len(TOPICS)) for r in range(args.rounds)]
    rows, errors = [], []
    started = time.monotonic()
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(generate, task): task for task in tasks}
        for completed, future in enumerate(as_completed(futures), 1):
            try:
                rows.extend(future.result())
            except Exception as error:
                errors.append({"task": futures[future], "error": str(error)[:200]})
            if completed % 16 == 0 or completed == len(tasks):
                print(json.dumps({"done": completed, "total": len(tasks), "accepted": len(rows), "failures": len(errors),
                                  "seconds": round(time.monotonic() - started, 1)}), flush=True)
    rows = list({row["id"]: row for row in rows}.values())
    rows.sort(key=lambda row: row["id"])
    path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows))
    report = {"teacher": "Qwen/Qwen3.8-Flash-Next-FP8", "topics": TOPICS, "arguments": vars(args),
              "conversations": len(rows), "failures": errors, "seconds": time.monotonic() - started,
              "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
              "limitations": "Synthetic conversations; format filtered, with later manual spot checks"}
    path.with_suffix(".report.json").write_text(json.dumps(report, indent=2) + "\n")
    if len(rows) < 1000:
        raise ValueError("Insufficient valid conversations")


if __name__ == "__main__":
    main()
