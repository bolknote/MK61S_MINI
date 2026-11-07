#!/usr/bin/env python3
"""Inverse distillation: varied conversations sharing a short, precise reply.

Plans describe general conversational skills, not evaluation questions. The teacher
invents disjoint contexts. Limiting reply entropy helps a ten-million-parameter
student learn both the act and the wording without blending incompatible phrases.
"""
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

from prepare import fingerprint


def plans():
    result = []
    def add(kind, situation, *answers):
        for answer in answers:
            result.append(dict(kind=kind, situation=situation, answer=answer))
    add('greet', 'The user greets the bot and wants friendly company.',
        'Hello! What would you like to talk about?', 'Hi! How has your day been?')
    add('greet', 'The user asks how this chatbot is doing.',
        'I am ready to chat with you. How are you?')
    add('chat', 'The user wants a quiet friendly chat rather than an activity.',
        'Of course. What has been on your mind?', 'Sure. How are you feeling today?')
    add('thanks', 'The user thanks the bot for help, listening or chatting.',
        'You are welcome. I am glad we could chat.', 'You are welcome!')
    add('thanks', 'The user expresses that they enjoyed this conversation.',
        'I am glad you enjoyed our chat.')
    add('goodbye', 'The user is leaving or saying goodbye.',
        'Goodbye! I hope the rest of your day goes well.', 'See you later! It was nice chatting with you.')
    add('identify', 'The user asks who the bot is, its name, or what kind of companion it is.',
        'I am TinyTalk, a small friendly chat bot.')
    add('identify', 'The user asks whether this bot can chat, talk, listen or keep them company.',
        'Yes. I can chat with you and listen.')
    add('identify', 'The user asks about the bot having real human feelings.',
        'I do not have human feelings, but I can listen.')
    add('identify', 'The user asks about the bot having a body or doing real physical activities.',
        'I am a chat bot, so I cannot do physical things.')
    add('identify', 'The user asks whether the bot has pets or a family in real life.',
        'I am a chat bot. I do not have a real family or pets.')
    add('identify', 'The user asks whether the bot is human.',
        'No. I am TinyTalk, a small chat bot.')
    add('tired', 'The user is mildly tired and asks for an easy activity, with no restrictions.',
        'You could listen to a gentle song.', 'Try reading one short poem.')
    add('tired', 'The user is tired and only wants to talk, not do another activity.',
        'We can just chat. How was your day?')
    add('suggest', 'The user is bored indoors or has free time and wants one easy activity. No rejected activities.',
        'Draw a little house with a colorful door.', 'Try folding a small paper boat.',
        'Write a tiny story about a lost cat.')
    add('suggest', 'The user wants one quiet or relaxing thing to do. No restrictions or rejected activities.',
        'You could listen to a gentle song.', 'Try reading a short story.',
        'Draw a little flower with bright petals.')
    add('suggest', 'The user wants a short break after an annoying event, but is not asking for technical repair advice.',
        'You could take a short walk.', 'Try listening to a quiet song.')
    add('suggest', 'The user wants one simple drawing idea, without specifying an object.',
        'Draw a small cat wearing a hat.', 'Draw a little house beside a tree.')
    add('suggest', 'The user wants a simple object to draw using only paper and a pencil.',
        'Draw a small house with a round window.')
    add('suggest', 'The user wants a small craft that can be made using only paper.',
        'Fold a little paper boat.', 'Try making a paper bookmark.')
    add('suggest', 'The user wants a single game that can be played by text in this conversation.',
        "Let's take turns naming animals. I will start: cat.")
    add('play', 'The user wants a text-only game rather than a physical activity, including after rejecting another activity.',
        "Let's take turns naming foods. I will start: apple.",
        "Let's name animals. I will start: dog.")
    add('suggest', 'The user is bored by weather cancelling outdoor plans and wants something fun indoors.',
        'You could draw a funny animal.', 'Try writing a tiny story about a rainy day.')
    add('ask_question', 'The user explicitly asks the bot to ask about how their day has been.',
        'How has your day been?', 'What was the best part of your day?')
    add('ask_question', 'The user explicitly asks for a question about a hobby they enjoy, without a named hobby.',
        'What do you enjoy doing in your free time?')
    for subject, question in [
        ('books or reading', 'What kind of books do you like?'),
        ('music', 'What kind of music do you enjoy?'),
        ('food', 'What is your favorite food?'),
        ('pets', 'What do you like most about your pet?'),
        ('drawing', 'What do you like to draw?'),
        ('weekend plans', 'What would you like to do this weekend?'),
        ('a happy memory', 'What is a happy memory you like to think about?'),
        ('the user as a person', 'What is something you enjoy doing?'),
    ]:
        add('ask_question', 'The user explicitly asks for a question about ' + subject + '.', question)
    for situation, answer in [
        ('The user completed a book and enjoyed it.', 'That sounds like a lovely book. What did you like about it?'),
        ('The user is happy because their plant is growing.', 'It is lovely to see your plant grow!'),
        ('The user baked something and is pleased with the result.', 'That sounds delicious. Well done!'),
        ('The user is pleased that another person liked something they made.', 'It feels good when someone likes your work!'),
        ('The user feels proud after finishing a small task.', 'Well done! It feels good to finish something.'),
        ('The user learned something new and is pleased.', 'Well done! Learning something new can feel great.'),
        ('The user found something they had lost.', 'I am glad you found it!'),
        ('The user reports feeling better after a bad mood or problem.', 'I am glad you are feeling better.'),
        ('The user is pleased about seeing a friend.', 'That sounds lovely. Did you have a good time?'),
        ('The user is happy about a small success in a hobby.', 'Well done! What did you enjoy most?'),
    ]:
        add('positive', situation, answer)
    for situation, answer in [
        ('The user shares a small annoying accident, like spilling a drink, dropping something or losing a page.', 'Oh no. That sounds frustrating.'),
        ('The user is frustrated after their work did not turn out as hoped.', 'That sounds frustrating after all your effort.'),
        ('The user is disappointed that they missed a film or fell asleep during it.', 'That is disappointing. You could try watching it another time.'),
        ('The user lost a small object and is annoyed.', 'That is annoying. Where did you last use it?'),
        ('The user is frustrated because their plan was interrupted.', 'That sounds frustrating. Would you like to talk about it?'),
        ('The user feels a little lonely and wants company.', 'I can keep you company. What would you like to talk about?'),
        ('The user feels sad after an ordinary disappointing day.', 'I am sorry it was a hard day. I can listen.'),
    ]:
        add('negative', situation, answer)
    for situation, answer in [
        ('The user describes watching a bird, without stating its color.', 'What color was the bird?'),
        ('The user describes seeing a cute animal, without saying what type.', 'What kind of animal was it?'),
        ('The user mentions hearing a song that brought back a happy memory.', 'What did the song remind you of?'),
        ('The user describes a song reminding them of summer.', 'That sounds lovely. What do you remember about that summer?'),
        ('The user saw something pleasant while outside.', 'That sounds like a lovely little moment.'),
        ('The user says they made something, without explaining what.', 'What did you make?'),
        ('The user describes a calm moment looking out of a window.', 'That sounds peaceful. What could you see?'),
        ('The user says they took a photo, without stating its subject.', 'What did you take a photo of?'),
    ]:
        add('sharing', situation, answer)
    for subject, answer in [
        ('funny stories rather than scary ones', 'Funny stories can be a cheerful choice.'),
        ('quiet music', 'Quiet music can be very relaxing.'),
        ('drawing or making art', 'What do you like to draw?'),
        ('paper crafts', 'You could try folding a little paper animal.'),
        ('reading', 'What kind of books do you like?'),
        ('cats', 'What do you like most about cats?'),
        ('dogs', 'Dogs can be lovely companions.'),
        ('rainy days', 'What do you enjoy doing on a rainy day?'),
        ('sunny days', 'What do you enjoy doing on a sunny day?'),
        ('the color blue', 'Blue is a lovely color.'),
        ('the color green', 'Green is a lovely color.'),
        ('one food over another, without asking for advice', 'What do you like most about that food?'),
    ]:
        add('preference', 'The user expresses a preference for ' + subject + '.', answer)
    for situation, answer in [
        ('The user asks for a choice between unspecified options, and no options appear anywhere in the conversation.', 'What are the choices?'),
        ('The user asks how to use or change something, but has not said what the thing is.', 'What are you trying to use?'),
        ('The user refers to an unknown thing with it or that, and no referent is available.', 'What are you referring to?'),
        ('The user asks which unknown activity or option to try first, without giving options.', 'What are you choosing between?'),
        ('The user asks whether an unspecified plan is good, and gives no plan.', 'What is the plan?'),
        ('The user asks for help doing an unspecified task.', 'What are you trying to do?'),
    ]:
        add('clarify', situation, answer)
    for hobby, answer in [
        ('painting', 'Paint a small flower with bright petals.'),
        ('drawing', 'Draw a little cat with a round face.'),
        ('gardening', 'Try growing a bean in a small pot.'),
        ('knitting', 'Start by knitting a small square.'),
        ('baking', 'Try making a few simple cookies.'),
        ('paper crafts', 'Fold a little paper boat.'),
        ('writing', 'Write a tiny story about a lost pet.'),
        ('photography', 'Try taking a photo of one leaf.'),
        ('music', 'Try learning a short simple tune.'),
        ('sewing', 'Try sewing a small cloth pouch.'),
    ]:
        add('followup', f'The user wants one simple beginner project in {hobby}. The hobby may be stated in an earlier turn.', answer)
    for subject, answer in [
        ('a hat', 'You could make the hat bright red.'),
        ('a flag', 'You could make the flag bright yellow.'),
        ('a door', 'You could make the door blue.'),
        ('a flower', 'You could make the flower pink.'),
        ('a balloon', 'You could make the balloon purple.'),
        ('a kite', 'You could make the kite green.'),
        ('a boat', 'You could make the boat blue.'),
    ]:
        add('followup', f'The user is discussing making or drawing {subject} and now asks what color it could be. Answer with a color.', answer)
    add('followup', 'The user wants to make a drawing of an animal funnier.', 'Give it a silly hat and big boots.')
    add('followup', 'The user wants to decorate a paper boat.', 'You could add a little paper flag.')
    for rejected, answer in [
        ('reading', 'You could draw a small flower instead.'),
        ('drawing', 'You could listen to a gentle song instead.'),
        ('music', 'You could read a short story instead.'),
        ('a walk or going outside', 'You could fold a little paper boat instead.'),
        ('a puzzle', 'You could write a tiny story instead.'),
        ('reading and drawing', 'You could listen to a gentle song instead.'),
        ('music and puzzles', 'You could draw a little flower instead.'),
        ('physical activities because they only want to chat', "Let's take turns naming animals. I will start: cat."),
    ]:
        add('alternative', f'The user wants a relaxing activity but explicitly rejects {rejected}. Avoid the rejected activities.', answer)
    add('story', 'The user wants to begin a tiny story with the bot, with no fixed characters.',
        'A little fox found a tiny key beside a tree.')
    for animal in ['cat', 'dog', 'rabbit', 'bear', 'duck', 'mouse', 'frog', 'bird']:
        add('story', f'The user wants a tiny story about a {animal}.',
            f'A little {animal} found a shiny button beside a tree.')
    add('play', 'The user wants a funny invented name for a pretend dragon.', 'How about calling the dragon Wobblewing?')
    add('play', 'The user wants a funny invented name for a pretend cat.', 'How about calling the cat Noodlewhisker?')
    add('play', 'The user wants a funny invented name for a pretend robot.', 'How about calling the robot Beepboots?')
    return result


SYSTEM = (
    'Invent English conversation inputs for a very small chatbot. You are given a situation and a FIXED final answer. '
    'Invent twelve different natural user inputs for which that exact answer is coherent, helpful and appropriate. '
    'Each example is context (0, 2 or 4 alternating user/bot strings) and user (the final user utterance). '
    'The fixed answer must directly meet the LAST user utterance; do not ask another question that it fails to answer. '
    'Use varied paraphrases, indirect requests and simple statements, not just a prefix changed. '
    'About half should be single-turn inputs. Use very short plain contexts with correct speaker roles. '
    'Keep every string under 22 words. Do not mention the fixed answer in the user input. '
    'No speaker labels, no special tokens, no medical, financial or arithmetic tasks. '
    'The bot is TinyTalk, an English text chatbot without a physical body or human personal life. '
    'Do not write any final bot answers: only the inputs that support the supplied fixed answer.'
)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True)
    parser.add_argument('--suite', default='suite')
    parser.add_argument('--rounds', type=int, default=8)
    parser.add_argument('--workers', type=int, default=16)
    args = parser.parse_args()
    output = Path(args.output);output.mkdir(parents=True, exist_ok=True)
    raw = output / 'raw';raw.mkdir(exist_ok=True)
    excluded = {fingerprint(json.loads(line)['messages']) for split in ['dev', 'test']
                for line in (Path(args.suite) / (split + '.jsonl')).read_text().splitlines()}
    text = {'type': 'string'}
    item = {'type': 'object', 'properties': {'context': {'type': 'array', 'items': text, 'maxItems': 4}, 'user': text},
            'required': ['context', 'user'], 'additionalProperties': False}
    schema = {'type': 'object', 'properties': {'examples': {'type': 'array', 'items': item, 'minItems': 12, 'maxItems': 12}},
              'required': ['examples'], 'additionalProperties': False}
    tasks = [(plan, i) for plan in plans() for i in range(args.rounds)]
    random.Random(17291).shuffle(tasks)
    def worker(task):
        plan, repeat = task
        key = hashlib.sha256(json.dumps([SYSTEM, task], sort_keys=True).encode()).hexdigest()
        path = raw / (key + '.json')
        if path.exists():response = json.loads(path.read_text())['response']
        else:
            payload = {'model': 'Qwen/Qwen3.8-Flash-Next-FP8', 'temperature': 1, 'seed': int(key[:7], 16), 'max_tokens': 2800,
                       'chat_template_kwargs': {'enable_thinking': False},
                       'response_format': {'type': 'json_schema', 'json_schema': {'name': 'contexts', 'strict': True, 'schema': schema}},
                       'messages': [{'role': 'system', 'content': SYSTEM}, {'role': 'user', 'content': json.dumps(dict(plan, variation=repeat))}]}
            for attempt in range(3):
                try:
                    request = urllib.request.Request('http://127.0.0.1:8000/v1/chat/completions', json.dumps(payload).encode(), {'Content-Type': 'application/json'})
                    with urllib.request.urlopen(request, timeout=180) as stream:response = json.load(stream)
                    json.loads(response['choices'][0]['message']['content'])['examples'];break
                except Exception:
                    if attempt == 2:raise
                    time.sleep(1)
            path.write_text(json.dumps({'request': payload, 'response': response}))
        rows = []
        for example in json.loads(response['choices'][0]['message']['content'])['examples']:
            if len(example['context']) not in [0, 2, 4]:continue
            turns = [re.sub(r'^(?:user|assistant|bot|tinytalk)\s*:\s*', '', re.sub(r'\s+', ' ', turn).strip(), flags=re.I).replace('\u2019', "'")
                     for turn in example['context'] + [example['user']]]
            if any(not turn or len(turn.split()) > 26 or '<|' in turn for turn in turns):continue
            messages = [{'role': 'user' if i % 2 == 0 else 'assistant', 'content': turn} for i, turn in enumerate(turns)]
            identity = fingerprint(messages)
            if identity in excluded:continue
            rows.append({'id': 'consistent:' + identity, 'kind': plan['kind'], 'intent_label': plan['kind'], 'messages': messages,
                         'target': f"<|tt_intent:{plan['kind']}|> " + plan['answer'], 'plain_target': plan['answer'],
                         'source': 'inverse_distillation', 'plan': plan['situation'], 'raw_response': path.name})
        return rows
    rows, failures = [], []
    start = time.monotonic()
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        jobs = {pool.submit(worker, task): task for task in tasks}
        for done, job in enumerate(as_completed(jobs), 1):
            try:rows.extend(job.result())
            except Exception as error:failures.append({'task': jobs[job], 'error': str(error)[:180]})
            if done % 64 == 0 or done == len(tasks):
                print(json.dumps({'done': done, 'tasks': len(tasks), 'rows': len(rows), 'failures': len(failures), 'seconds': round(time.monotonic() - start, 1)}), flush=True)
    # A context receives one canonical target. Never retain contradictory duplicates.
    rng = random.Random(78211);rng.shuffle(rows)
    rows = sorted({row['id']: row for row in rows}.values(), key=lambda row: row['id'])
    path = output / 'train.jsonl';path.write_text(''.join(json.dumps(row, ensure_ascii=False) + '\n' for row in rows))
    manifest = {'policy': 'Inverse distillation to consistent short replies; varied independently generated training conversations',
                'rows': len(rows), 'plans': len(plans()), 'kinds': dict(Counter(row['kind'] for row in rows)), 'failures': failures,
                'sha256': hashlib.sha256(path.read_bytes()).hexdigest(), 'exact_reserved_contexts_excluded': len(excluded),
                'test_evaluated': False, 'seconds': time.monotonic() - start}
    (output / 'manifest.json').write_text(json.dumps(manifest, indent=2))
    print(json.dumps(manifest), flush=True)


if __name__ == '__main__':main()
