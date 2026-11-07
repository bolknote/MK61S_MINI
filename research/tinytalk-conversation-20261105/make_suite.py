#!/usr/bin/env python3
"""Freeze ordinary conversation prompts before training or checkpoint selection.

Two variants per family are development prompts; three are reserved test prompts.
The notes describe conversational intent, not a required literal answer.
"""
import argparse
import hashlib
import json
from pathlib import Path

FAMILIES = [
 ("greeting", "Greet warmly and respond naturally without inventing a human identity.", [
  "Hi there. I felt like having a little chat.", "Hello! How is your day going?",
  "Hey, could I spend a few minutes talking with you?", "Good evening. I'd like some company.", "Hi! What shall we talk about today?"]),
 ("identity", "Answer about the bot's identity, not the user's name or an invented job.", [
  "I haven't met you before. What's your name?", "How would you describe yourself?",
  "Hello, little bot. What do you call yourself?", "Are you someone I can chat with?", "What kind of chat buddy are you?"]),
 ("hobby", "Discuss or suggest a hobby that fits the user's stated interest.", [
  "I want a quiet hobby for the evening. Any ideas?", "I enjoy making things with paper.",
  "I'd like to try drawing, but I don't know where to start.", "I like stories more than sports. What could I try?", "What could I make with just paper and a pencil?"]),
 ("mild_tiredness", "Offer low-effort company or a simple restful activity.", [
  "It's been a long day. I don't feel like doing much.", "I am tired and want something easy to do.",
  "I'm worn out from a busy afternoon. Can we just chat?", "My day was full. I'd enjoy a quiet little break.", "I only have energy for something very simple tonight."]),
 ("boredom", "Respond to boredom with a concrete simple idea or an engaging question.", [
  "I'm stuck indoors and feeling bored.", "There isn't much to do this afternoon. Any ideas?",
  "The rain cancelled my plans and now I'm restless.", "I've got half an hour to fill. Help me think of something fun.", "Nothing sounds interesting today. Could you help me pick an activity?"]),
 ("good_news", "Acknowledge the specific good news rather than switching topics.", [
  "I finished a book today and really enjoyed it.", "My little plant finally has a new leaf!",
  "I managed to fix my old lamp. I'm quite pleased.", "Someone liked the picture I drew today.", "I baked some cookies and they turned out nicely."]),
 ("mild_frustration", "Acknowledge a small disappointment without giving unrelated advice.", [
  "I spilled tea on my drawing. That was annoying.", "My puzzle is missing one piece.",
  "The cake I tried to bake came out flat.", "I forgot my umbrella and got wet on the way home.", "I spent ages choosing a film and then fell asleep."]),
 ("sharing", "Show interest in the specific event the user shared.", [
  "I saw a tiny bird taking a bath in a puddle.", "A cat followed me for part of my walk today.",
  "I found an old photo while clearing a drawer.", "I heard a song today that reminded me of summer.", "There was a beautiful orange sky on my way home."]),
 ("preference", "Discuss a preference naturally; do not give an irrelevant instruction.", [
  "I enjoy quiet mornings more than busy evenings.", "I usually pick funny stories over scary ones.",
  "I prefer little gardens to big crowded parks.", "I like soft music when I'm reading.", "I always choose a window seat if I can."]),
 ("ask_question", "Ask one relevant conversational question as requested.", [
  "Could you ask me about my day?", "Ask me something about what I like.",
  "I'd like to talk, but I don't know how to begin. Ask me a question.", "Can you ask me about my favorite story?", "Ask me a cheerful question, please."]),
 ("clarification", "Ask a clarification because the request has no clear referent.", [
  "Could you help me choose one?", "I'm not sure what to do with it.",
  "Do you think that would be a good idea?", "Can you suggest a better way to do it?", "Which one should I try first?"]),
 ("one_idea", "Respect the request for one short, concrete suggestion.", [
  "Give me just one idea for a quiet afternoon.", "Name one simple thing I could draw.",
  "Suggest a single little game we could play in this chat.", "Tell me one easy way to make my desk nicer.", "I want one tiny creative task, nothing more."]),
 ("closing", "End the conversation warmly instead of forcing another question.", [
  "I need to go now. Thanks for chatting.", "Good night. I'll talk to you another day.",
  "That's all for now. Have a nice evening!", "I have to leave, but this was nice.", "Time for me to get back to my book. Bye!"]),
 ("thanks", "Acknowledge thanks politely and naturally.", [
  "Thanks, that helped me think of something.", "I appreciate you keeping me company.",
  "That was a nice little chat. Thank you.", "You gave me a good idea. Thanks!", "I'm glad I stopped by to talk."]),
 ("play", "Accept or start a simple text game instead of claiming a physical action.", [
  "Want to play a little word game?", "Can we make up a tiny story together?",
  "Let's take turns naming animals. You start.", "Can you think of a simple guessing game for us?", "Let's invent a funny name for a pretend dragon."]),
]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    root = Path(args.output); root.mkdir(parents=True, exist_ok=True)
    splits = [[], []]
    for family, note, texts in FAMILIES:
        for index, text in enumerate(texts):
            splits[index >= 2].append({"id": f"{family}:{index}", "family": family, "intent": note,
                                       "messages": [{"role": "user", "content": text}]})
    for family, values, note in [
        ("remember_name", ["Nina", "Omar", "Lena", "Toby", "Mira"], "Use the user's given name without taking it as the bot's name."),
        ("follow_hobby", ["painting", "chess", "knitting", "gardening", "baking"], "Continue the stated hobby topic; a relevant idea or question is appropriate."),
        ("correction", ["green", "blue", "yellow", "purple", "orange"], "Accept the user's correction and retain the corrected preference."),
        ("follow_story", ["a fox", "a rabbit", "a little bear", "a kitten", "a duck"], "Continue the short story thread with a simple, consistent idea."),
        ("decline_idea", ["drawing", "reading", "music", "a puzzle", "a walk"], "Respect the user's rejection and suggest a different activity.")]:
        for index, value in enumerate(values):
            if family == "remember_name":
                turns = [f"I'm {value}. It's nice to meet you.", "Nice to meet you too.", "Do you remember what to call me?"]
            elif family == "follow_hobby":
                turns = [f"I've been thinking of trying {value}.", "That could be fun. What interests you about it?", "I'd like a small project to start with. Any ideas?"]
            elif family == "correction":
                turns = ["I like the red one.", "So red is your favorite?", f"Sorry, I meant {value}. Which color did I choose?"]
            elif family == "follow_story":
                turns = [f"Let's tell a story about {value}.", "Our little friend found a strange box beside a tree.", "What could be inside the box?"]
            else:
                turns = ["I want something relaxing to do.", f"You could try {value}.", f"I don't feel like {value} today. Something else?"]
            messages = [{"role": "user" if i % 2 == 0 else "assistant", "content": text} for i, text in enumerate(turns)]
            splits[index >= 2].append({"id": f"{family}:{index}", "family": family, "intent": note, "messages": messages})
    manifest = {"policy": "Frozen authored prompts; development variants 0-1, reserved test variants 2-4; not used as training examples", "files": {}}
    for name, rows in zip(["dev", "test"], splits):
        path = root / f"{name}.jsonl"
        path.write_text("".join(json.dumps(row) + "\n" for row in rows))
        manifest["files"][name] = {"rows": len(rows), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
    (root / "suite-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
