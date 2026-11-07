"""Measure absolute reply quality and actual multi-turn conversations after Q4."""
from common import actual_q4, core, decode
from grade import grade

SCENARIOS = [
    [("I'd like a small drawing idea.", "Give a concrete drawing idea."),
     ("I think I'll draw a cat. What could make it funny?", "Give a simple cat-related drawing detail."),
     ("Maybe a silly hat would work. What color could it be?", "Suggest a color for the hat, staying on topic.")],
    [("I'd like something quiet to do.", "Give a concrete quiet activity."),
     ("I don't feel like reading or drawing. Another idea?", "Suggest a quiet activity other than reading or drawing."),
     ("Could we do something just by chatting?", "Suggest a concrete text-based activity.")],
    [("Hi, I'm Daisy. Nice to meet you.", "Greet Daisy without taking her name as the bot's name."),
     ("My little cat is named Biscuit.", "Respond relevantly to the user's cat."),
     ("What is my cat's name?", "The cat's name is Biscuit, not the bot's name or the user's name.")],
    [("I spilled tea on my notebook. I'm annoyed.", "Acknowledge a frustrating event, not celebrate it."),
     ("I might take a break. Any simple idea?", "Give an actual simple break activity."),
     ("Thanks. I'm feeling a bit better now.", "Acknowledge that the user feels better.")],
    [("I like blue best.", "Acknowledge the color preference."),
     ("Sorry, I meant green, not blue.", "Accept the corrected preference green."),
     ("What color do I like?", "The user's corrected favorite color is green.")],
    [("Let's take turns naming animals. You start.", "Name an animal to start the game."),
     ("I'll say fox. Your turn.", "Name another animal, not repeat fox."),
     ("Can you think of one more animal?", "Name another animal, different from ones already named.")],
]


TEST_SCENARIOS = [
    [("What could I make from one sheet of paper?", "Give a concrete paper craft."),
     ("I think I'll make a paper boat. How could I decorate it?", "Suggest a simple decoration for the paper boat."),
     ("A flag would be nice. What color could I choose?", "Suggest a color for the boat's flag.")],
    [("I want a calm activity for this evening.", "Give a concrete calm activity."),
     ("I don't want music or a puzzle. A different idea?", "Suggest something other than music or a puzzle."),
     ("Could we try a simple word game instead?", "Start or explain a concrete short word game.")],
    [("Hello, people call me Oscar.", "Greet Oscar; keep the bot's identity distinct."),
     ("My dog is called Maple.", "Reply relevantly about the user's dog."),
     ("What did I say my dog's name was?", "The dog's name is Maple, not Oscar or TinyTalk.")],
    [("My umbrella broke just as it started raining.", "Acknowledge an annoying event with an appropriate tone."),
     ("I'm home now and need to relax. One idea?", "Give one concrete relaxing activity."),
     ("That sounds better. Thank you for listening.", "Acknowledge thanks naturally.")],
    [("I'd choose red for the picture.", "Acknowledge the color choice."),
     ("Actually, change that to purple.", "Accept the updated choice purple."),
     ("Which color am I choosing now?", "The user's final choice is purple.")],
    [("Let's name foods. You go first.", "Name a food to start the game."),
     ("My turn: banana. Now you.", "Name a different food, not banana."),
     ("Another food, please.", "Name a food not already named.")],
]


def rollouts(model, tokenizer, device, scenarios, label, batched=True, cache_factory=None):
    histories = [[] for _ in scenarios]
    found = {}
    def current_case(scenario, turn):
        question, intent = scenarios[scenario][turn]
        messages = histories[scenario]
        messages.append({'role':'user', 'content':question})
        limit = getattr(model.config, 'tinytalk_runtime_context', 256)
        while len(tokenizer.encode(core.render(messages), add_special_tokens=False)) + 40 > limit:
            if len(messages) < 3:
                raise ValueError('Current conversation question does not fit')
            del messages[:2]
        return {'id':f'{label}:rollout:{scenario}:{turn}', 'messages':[dict(m) for m in messages], 'intent':intent}
    if batched:
        for turn in range(max(len(steps) for steps in scenarios)):
            active = [i for i, steps in enumerate(scenarios) if turn < len(steps)]
            cases = [current_case(i, turn) for i in active]
            replies = decode(model, tokenizer, cases, device, cache_factory=cache_factory)
            for scenario, case, reply in zip(active, cases, replies):
                found[scenario, turn] = (case, reply)
                histories[scenario].append({'role':'assistant', 'content':reply['reply']})
    else:
        for scenario, steps in enumerate(scenarios):
            for turn in range(len(steps)):
                case = current_case(scenario, turn)
                reply = decode(model, tokenizer, [case], device, cache_factory=cache_factory)[0]
                found[scenario, turn] = (case, reply)
                histories[scenario].append({'role':'assistant', 'content':reply['reply']})
    # Restore the original scenario-major order for the rubric, caches and partition gates.
    ordered = [found[i, turn] for i, steps in enumerate(scenarios) for turn in range(len(steps))]
    return [v[0] for v in ordered], [v[1] for v in ordered], histories


def assess(model, tokenizer, device, cases, qat_state, cache, label, scenarios=None, fp16_kv=False):
    from common import fp16_cache_factory
    cache_factory = fp16_cache_factory(model) if fp16_kv else None
    with actual_q4(model, qat_state):
        replies = decode(model, tokenizer, cases, device, cache_factory=cache_factory)
        rollout_cases, rollout_replies, transcripts = rollouts(model, tokenizer, device,
            scenarios if scenarios is not None else SCENARIOS, label, cache_factory=cache_factory)
    direct = grade(cases, replies, cache, workers=12)
    multi = grade(rollout_cases, rollout_replies, cache, workers=12)
    contextual = {"remember_name", "follow_hobby", "correction", "decline_idea", "follow_story", "name", "pet", "correct", "reject", "project"}
    context_grades = [g for c, g in zip(cases, direct["details"]) if c.get("family") in contextual]
    context_rate = sum(row["pass"] for row in context_grades) / len(context_grades) if context_grades else direct["pass_rate"]
    bad = sum(reply["bad"] for reply in replies + rollout_replies)
    target = direct["pass_rate"] >= 0.8 and context_rate >= 0.72 and multi["pass_rate"] >= 0.78 and bad <= 3
    return {"direct": direct, "multi_turn": multi, "context_pass_rate": context_rate, "malformed": bad,
            "cache_storage_precision":"FP16" if fp16_kv else "FP32", "attention_arithmetic":"host FP32",
            "conversation_execution":"Independent scenarios batched at each turn; original scenario order preserved",
            "grading_workers":12,
            "goal_met": target, "selection_score": 0.6 * direct["pass_rate"] + 0.4 * multi["pass_rate"],
            "replies": replies, "rollouts": transcripts, "rollout_cases": rollout_cases,
            "rollout_replies": rollout_replies}
