#!/usr/bin/env python3
"""Old prompts become development regressions; reserve new prompts for the final audit."""
import argparse
import hashlib
import json
from pathlib import Path

TEST = [
 ("greeting", "Reply warmly and naturally.", ["Hello there, little chat friend.", "Could we talk for a while? I have a quiet moment.", "I've just sat down with some tea. Hello!"]),
 ("identity", "Identify the bot consistently, without taking the user's identity.", ["Who is answering me right now?", "Tell me what I should call this little bot.", "Are you a human or a chat bot?"]),
 ("idea", "Give one concrete small activity.", ["I'm home with a free evening. Suggest something quiet.", "What is one small thing I could make from paper?", "I have a pencil and ten minutes. What could I draw?"]),
 ("ask", "Ask an actual relevant question as requested.", ["Please ask which games I enjoy.", "Your turn to ask about my afternoon.", "Ask me a question about my hobbies."]),
 ("good_news", "Recognize the positive event.", ["My friend sent me a lovely postcard today.", "I finally solved the little puzzle on my desk.", "The seeds I planted have started growing!"]),
 ("bad_news", "Recognize the negative event without a happy unrelated reaction.", ["My favorite cup fell and broke.", "I missed the bus and stood in the rain.", "The wind blew away the picture I was drawing."]),
 ("company", "Offer friendly company and a relevant response.", ["I'm a bit lonely this evening. Can we chat?", "I'm not looking for advice, just some company.", "It's very quiet here. I'd enjoy a little conversation."]),
 ("hobby", "Respond to the stated hobby and interests.", ["I might learn to knit a little scarf.", "I'd like to grow a plant on my windowsill.", "I want to write a very short story."]),
 ("share", "Show interest in the user's actual event.", ["A small dog sat beside me in the park today.", "I saw a rainbow over the roofs this afternoon.", "I found a drawing I made years ago."]),
 ("preference", "Acknowledge or discuss the stated preference.", ["I like gentle songs more than noisy ones.", "Funny books cheer me up more than scary ones.", "I enjoy walking slowly and looking at trees."]),
 ("clarify", "Ask a useful clarification when an essential detail is absent.", ["Can you help me fix this?", "I have two choices but I can't decide.", "I want to make it nicer. Any thoughts?"]),
 ("one_question", "Ask only one appropriate question.", ["Ask me just one thing about my day.", "Give me one cheerful question to answer.", "Could you ask about a place I like?"]),
 ("game", "Suggest or start a concrete text-based game.", ["Let's play something with words. Can you start?", "Name an animal and I'll name another.", "Give me a simple riddle for fun."]),
 ("thanks", "Acknowledge thanks appropriately.", ["That made my evening nicer. Thank you.", "I liked your little idea. Thanks!", "Thanks for listening to me today."]),
 ("bye", "Close warmly rather than starting an unrelated topic.", ["I must go and eat dinner. Bye for now.", "I'm heading to bed. Thanks for the company.", "My break is over. Let's chat another time."]),
]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--previous-suite", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    root = Path(args.output); root.mkdir(parents=True, exist_ok=True)
    development = []
    for name in ["dev", "test"]:
        for line in (Path(args.previous_suite) / f"{name}.jsonl").read_text().splitlines():
            row = json.loads(line); row["id"] = "regression:" + row["id"]; development.append(row)
    test = []
    for kind, intent, questions in TEST:
        for index, question in enumerate(questions):
            test.append({"id": f"fresh:{kind}:{index}", "family": kind, "intent": intent,
                         "messages": [{"role": "user", "content": question}]})
    for kind, values in [("name", ["Erin", "Robin", "Dora"]), ("pet", ["Pip", "Ash", "Sunny"]),
                         ("correct", ["white", "pink", "brown"]), ("reject", ["reading", "drawing", "a puzzle"]),
                         ("project", ["gardening", "baking", "painting"])]:
        for index, value in enumerate(values):
            if kind == "name":
                turns = [f"People call me {value}.", "Hello! It's nice to meet you.", "Which name did I give you?"]
                intent = f"The user's name is {value}; do not give the bot's name."
            elif kind == "pet":
                turns = [f"I have a little cat named {value}.", "A cat can be lovely company.", "Can you tell me my cat's name?"]
                intent = f"The cat is named {value}."
            elif kind == "correct":
                turns = ["I think I'll choose blue.", "Blue can be a nice choice.", f"Actually, make it {value}. What is my choice now?"]
                intent = f"Use the corrected choice {value}."
            elif kind == "reject":
                turns = ["I want a quiet activity.", f"Maybe try {value}.", "No, that doesn't appeal to me. A different idea, please."]
                intent = f"Suggest a concrete activity other than {value}."
            else:
                turns = [f"I want to start {value}.", "That could be a nice hobby.", "What would be an easy first project?"]
                intent = f"Suggest a concrete beginner project relevant to {value}."
            test.append({"id": f"fresh:{kind}:{index}", "family": kind, "intent": intent,
                         "messages": [{"role": "user" if i % 2 == 0 else "assistant", "content": text} for i, text in enumerate(turns)]})
    manifest = {"goal": "At least 80% acceptable short replies after Q4, with context use and useful responses; not just relative preference",
                "old_test_is_now_development": True, "fresh_test_used_for_training_or_selection": False, "files": {}}
    for name, rows in [("dev", development), ("test", test)]:
        path = root / f"{name}.jsonl";path.write_text("".join(json.dumps(row) + "\n" for row in rows))
        manifest["files"][name] = {"rows": len(rows), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
    (root / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
