#!/usr/bin/env python3
"""Combine concrete conversational supervision with a small natural-language replay pool."""
from collections import Counter
import argparse
import hashlib
import json
from pathlib import Path
import re


def fingerprint(messages):
    return hashlib.sha256(json.dumps(messages, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def normalize_teacher(row):
    """Recover flat speaker/content arrays and reject obvious false bot capabilities."""
    row = dict(row)
    messages = row["messages"]
    if len(messages) == 5 and messages[0]["content"].strip().lower() == "user" and messages[2]["content"].strip().lower() in ("bot", "assistant", "tinytalk"):
        messages = [{"role": "user", "content": messages[1]["content"]},
                    {"role": "assistant", "content": messages[3]["content"]}, messages[4]]
        row["messages"] = messages
    if any(m["content"].strip().lower() in ("user", "bot", "assistant") for m in messages):
        return None
    bot_turns = [m["content"] for m in messages if m["role"] == "assistant"] + [row["target"]]
    physical = re.compile(r"\bI (?:will |can |am going to )?(?:draw|paint|wear|cook|bake|eat|drink|drive|walk|touch|see|smell|taste)\b|\bmy (?:shirt|job|office|mother|father|hands|eyes|home|cat|dog|car)\b", re.I)
    if any(physical.search(text) for text in bot_turns):
        return None
    row["id"] = fingerprint(messages)
    return row


def handcrafted():
    rows = []
    def add(kind, user, answer, context=()):
        turns = list(context) + [user]
        messages = [{"role": "user" if i % 2 == 0 else "assistant", "content": text} for i, text in enumerate(turns)]
        identity = fingerprint(messages)
        bucket = int(identity[:8], 16) % 100
        rows.append({"id": identity, "kind": kind, "messages": messages, "target": answer,
                     "intent": "Give a useful, relevant short reply.", "source": "authored_curriculum",
                     "split": "validation" if bucket < 5 else "test" if bucket < 10 else "train"})
    activities = {
        "a quiet evening": ["Read a short story.", "Try drawing a little picture.", "Listen to a calm song."],
        "paper": ["Fold a paper boat.", "Make a little paper bookmark.", "Draw a small animal on it."],
        "drawing": ["Try drawing a flower.", "Draw a little house.", "Draw a funny cat."],
        "a chat game": ["Let's take turns naming animals. Cat!", "Let's name things that are blue. Sky!", "I'll say a word; you find a rhyme. Cat!"],
        "gardening": ["Try growing beans in a small pot.", "Plant a few seeds in a cup.", "Grow a small herb on your windowsill."],
        "baking": ["Try making a few simple cookies.", "Start with a small batch of cookies.", "Try a simple little cake."],
        "reading": ["Try a short funny story.", "Pick a book with a cheerful cover.", "Read one short poem."],
        "music": ["Try listening to one calm song.", "Choose a gentle song you enjoy.", "Make a small list of favorite songs."],
        "a hobby": ["Try drawing with a pencil.", "You could fold paper animals.", "Try writing a tiny story."],
        "my room": ["Put one favorite picture on your wall.", "Tidy one small corner.", "Put a small plant by the window."],
    }
    forms = ["Give me one idea for {}.", "Suggest something simple for {}.", "Can you give me a small idea about {}?",
             "I'd like an easy idea for {}.", "What is one thing I could try with {}?", "Help me think of something for {}."]
    for topic, answers in activities.items():
        for i, form in enumerate(forms):
            add("idea", form.format(topic), answers[i % len(answers)])
        for i, answer in enumerate(answers):
            for opening in ["I'd like to try this.", "I'm just starting.", "I want an easy first step."]:
                add("followup", opening + " What could I do first?", answer,
                    [f"I'm interested in {topic}.", "That could be fun."])
    questions = {"my day": "What did you do today?",
                 "my hobbies": "What do you like to do for fun?", "my favorite book": "What is your favorite book?",
                 "my favorite game": "What is your favorite game?", "my music": "What music do you like?",
                 "my pet": "What is your pet like?", "my weekend": "What did you do this weekend?",
                 "my favorite place": "What place do you like best?", "my drawing": "What did you draw?"}
    for topic, answer in questions.items():
        for form in ["Ask me about {}.", "Could you ask a question about {}?", "Please ask me one thing about {}.",
                     "I want you to ask about {}.", "Your turn: ask about {}."]:
            add("ask", form.format(topic), answer)
    names = "Alice Ben Clara Dan Emma Finn Grace Hugo Iris Jack Kate Leo Mia Nora Owen Paul Rosa Sam Tina Will".split()
    for name in names:
        for intro in [f"My name is {name}.", f"I'm {name}.", f"Please call me {name}."]:
            for question in ["What is my name?", "Do you remember my name?", "What should you call me?"]:
                add("role", question, f"Your name is {name}.", [intro, "Nice to meet you."])
        for question in ["What is my cat's name?", "What did I call my cat?", "Can you remember my cat's name?"]:
            add("role", question, f"Your cat's name is {name}.", [f"My cat is called {name}.", "A cat can be nice company."])
    colors = "red blue green yellow orange purple pink white black brown".split()
    for old in colors:
        for new in colors:
            if old == new:
                continue
            for form in ["Actually, I meant {}. Which color did I choose?", "Sorry, change it to {}. What's my choice now?"]:
                add("correction", form.format(new), f"You chose {new}.", [f"I'll choose {old}.", f"So {old} is your choice."])
    for rejected in ["drawing", "reading", "music", "a walk", "a puzzle", "baking"]:
        for answer in ["You could fold a paper boat.", "Try writing a tiny story.", "You could name animals with me."]:
            for form in ["I'd rather not do that. Any other idea?", "No, something different please.", "I don't feel like that today. Something else?"]:
                add("followup", form, answer, ["I'd like something fun to do.", f"You could try {rejected}."])
    for question, answer in [
        ("Can you help me with it?", "What would you like help with?"),
        ("Which one should I choose?", "What are the choices?"),
        ("Can you fix this?", "What seems to be wrong?"),
        ("Do you like that?", "What are you asking about?"),
        ("How should I do it?", "What are you trying to do?"),
        ("What's your name?", "I'm TinyTalk, a little chat bot."),
        ("Who are you?", "I'm TinyTalk. I'm here to chat with you."),
        ("Are you a person?", "I'm a little chat bot called TinyTalk."),
    ]:
        add("clarify" if "help" in answer or "?" in answer else "role", question, answer)
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gold", default="gold.jsonl")
    parser.add_argument("--replay", default="/replay")
    parser.add_argument("--suite", default="suite")
    parser.add_argument("--output", default="data")
    parser.add_argument("--supervise-context", action="store_true")
    parser.add_argument("--context-quality-report", default="teacher-audit/audit.json")
    args = parser.parse_args()
    root = Path(args.output); root.mkdir(parents=True, exist_ok=True)
    excluded = set()
    for name in ["dev", "test"]:
        for line in (Path(args.suite) / f"{name}.jsonl").read_text().splitlines():
            excluded.add(fingerprint(json.loads(line)["messages"]))
    raw_generated = [json.loads(line) for line in Path(args.gold).read_text().splitlines()]
    generated = [normalized for row in raw_generated if (normalized := normalize_teacher(row)) is not None]
    rows = list(generated) + handcrafted()
    context_quality = None
    if args.supervise_context:
        audit = json.loads(Path(args.context_quality_report).read_text())
        context_quality = audit["context"]["grades"]["pass_rate"]
    supervise_context = args.supervise_context and context_quality >= 0.95
    if supervise_context:
        for row in generated:
            for index in range(1, len(row["messages"]), 2):
                messages = row["messages"][:index]
                rows.append(dict(row, id=fingerprint(messages), messages=messages,
                                 target=row["messages"][index]["content"],
                                 intent="Reply relevantly and naturally to the conversation.",
                                 source="context:" + row["source"]))
    by_split = {name: [] for name in ["train", "validation", "test"]}
    seen = set(excluded)
    for row in rows:
        identity = fingerprint(row["messages"])
        if identity in seen:
            continue
        seen.add(identity); by_split[row["split"]].append(row)
    manifest = {"suite_contexts_excluded_from_training": len(excluded), "files": {},
                "teacher_rows_before_curation": len(raw_generated), "teacher_rows_after_curation": len(generated),
                "context_supervision": {"requested": args.supervise_context, "enabled": supervise_context,
                                        "sample_pass_rate": context_quality, "minimum_sample_pass_rate": 0.95},
                "policy": "Concrete conversational intents, short direct replies, no generic filler targets; exact evaluation contexts excluded"}
    for name in by_split:
        for line in (Path(args.replay) / f"{name}.jsonl").read_text().splitlines():
            row = json.loads(line)
            if row["kind"] != "soda" or fingerprint(row["messages"]) in seen:
                continue
            row["kind"] = "replay"; by_split[name].append(row); seen.add(fingerprint(row["messages"]))
        path = root / f"{name}.jsonl"
        path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in by_split[name]))
        manifest["files"][name] = {"rows": len(by_split[name]), "kinds": dict(Counter(row["kind"] for row in by_split[name])),
                                    "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
    (root / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
