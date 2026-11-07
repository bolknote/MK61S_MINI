#!/usr/bin/env python3
"""Distill complete, short, varied dialogues instead of isolated reply templates."""
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
from common import core
from grade import grade
from prepare import fingerprint
from prepare_tagged import WORDS


PATTERNS = [
    'A natural friendly chat, moving from a statement to a related question, then a follow-up.',
    'The user asks for one simple idea, adds a constraint, then asks for a concrete detail.',
    'The user shares a little event, names an object or person, then asks about a stated fact.',
    'The user says a preference, changes their mind, then asks what they currently prefer.',
    'The user mentions two different objects with different attributes, then asks about one attribute.',
    'The user asks the bot a question, then asks the BOT to ask a different, relevant question.',
    'The user shares a pleasant or frustrating event and discusses it without a memory quiz.',
    'The user rejects an offered suggestion, then accepts a different concrete suggestion.',
    'A little conversation includes a greeting, topic change, or goodbye; follow the last message.',
    'The user asks about an unstated fact; the bot admits the missing information, without inventing it.',
    'The user asks a simple factual question about stated information, followed by a yes/no question.',
    'A short guessing or naming game has explicit rules and does not repeat earlier moves.',
]

SYSTEM = (
    'Write NEW natural English conversations between a person and TinyTalk, a friendly tiny text chatbot. '
    'Each conversation has exactly THREE user messages and THREE spoken bot answers. '
    'The supplied theme and example are inspiration, not text to copy. Invent different wording and details. '
    'Use short COMMON English words: each user message 2-10 words, each answer 2-12 words. '
    'Each answer must directly address its preceding user message using the entire conversation. '
    'Follow the supplied conversational pattern naturally. Vary question wording, names, objects, and sentence structures. '
    'Keep roles distinct: your name means the BOT name TinyTalk; my name means the USER name. '
    'Recall a fact only when stated. Keep name, color, count, location, person and object distinct. '
    'Use the newest corrected fact. Never invent missing context. Answer yes/no questions directly. '
    'Do not ask for a fact that the person just stated. Do not invent current weather or an object location. '
    'Give a real question if asked to ask a question; a concrete suggestion if requested. '
    'After the person adds a constraint, offer a concrete answer satisfying it, not merely acknowledge it. '
    'In turn-taking games, play YOUR next legal move after each user move; do not skip it or repeat an item. '
    'Respond socially to shared tastes rather than stating an unrelated trivial fact. '
    'TinyTalk has no body, family, personal job or physical experiences, but can discuss tastes conversationally. '
    'Avoid specialist advice, current events, medical, legal, financial, or complex technical subjects. '
    'A spoken answer is LITERAL text for the person to read; never a role name, topic or label. '
    'Fields user1, user2, user3 are the person; answer1, answer2, answer3 are TinyTalk. '
    'act1, act2, act3 classify the corresponding bot answer; choose from: ' + ', '.join(WORDS) + '.'
)


def main():
    from transformers import AutoTokenizer
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', default='natural-data')
    p.add_argument('--source-data', default='base-data/train.jsonl')
    p.add_argument('--model', default='source-model')
    p.add_argument('--dialogues', type=int, default=12000)
    p.add_argument('--probe', action='store_true')
    p.add_argument('--full-audit', action='store_true', help='Grade every teacher target and exclude failures before training')
    p.add_argument('--qa-workers', type=int, default=12)
    args = p.parse_args()
    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=True)
    raw = out / 'raw'
    raw.mkdir(exist_ok=True)
    tokenizer = AutoTokenizer.from_pretrained(args.model, local_files_only=True, trust_remote_code=False)
    source = core.read_rows(args.source_data)
    seeds = [r for r in source if r['id'].startswith('everyday:') and not re.search(
        r'weather forecast|seasonal fashion|bank|budget|financ|insurance|medic|religion|politic|\bAI\b|software|factory|car repair',
        r.get('source_topic', ''), flags=re.I)]
    assert len(seeds) >= 1000
    excluded = set()
    for name in ['dev', 'test', 'opened-audit2']:
        excluded.update(fingerprint(r['messages']) for r in core.read_rows(Path('suite') / (name + '.jsonl')))
    # Hash exclusion only: no student replies, grades, selection or test contents are exposed.
    closed = Path('reserved-audit3/test.jsonl')
    if closed.exists():
        excluded.update(fingerprint(r['messages']) for r in core.read_rows(closed))
    rng = random.Random(912735)
    jobs = []
    for index in range(args.dialogues if not args.probe else 32):
        row = rng.choice(seeds)
        jobs.append({'index':index, 'theme':row.get('source_topic', 'everyday life'),
            'inspiration':row['messages'][0]['content'], 'pattern':PATTERNS[index % len(PATTERNS)],
            'variation':rng.randrange(1000000)})
    groups = [jobs[i:i + 4] for i in range(0, len(jobs), 4)]
    properties = {}
    for turn in range(1, 4):
        properties['user' + str(turn)] = {'type':'string'}
        properties['answer' + str(turn)] = {'type':'string'}
        properties['act' + str(turn)] = {'type':'string', 'enum':list(WORDS)}
    value = {'type':'object', 'properties':properties, 'required':list(properties), 'additionalProperties':False}
    def worker(group):
        key = hashlib.sha256(json.dumps([SYSTEM, group], sort_keys=True).encode()).hexdigest()
        path = raw / (key + '.json')
        schema = {'type':'object', 'properties':{str(i):value for i in range(len(group))},
            'required':[str(i) for i in range(len(group))], 'additionalProperties':False}
        for attempt in range(3):
            cache = path if attempt == 0 else path.with_name(path.stem + '-retry' + str(attempt) + '.json')
            if cache.exists():
                response = json.loads(cache.read_text())['response']
            else:
                payload = {'model':'Qwen/Qwen3.8-Flash-Next-FP8', 'temperature':.65, 'seed':group[0]['index'] + 47191 + attempt,
                    'max_tokens':2200, 'chat_template_kwargs':{'enable_thinking':False},
                    'response_format':{'type':'json_schema', 'json_schema':{'name':'natural_chat', 'strict':True, 'schema':schema}},
                    'messages':[{'role':'system', 'content':SYSTEM}, {'role':'user', 'content':json.dumps(group)}]}
                request = urllib.request.Request('http://127.0.0.1:8000/v1/chat/completions', json.dumps(payload).encode(),
                    {'Content-Type':'application/json'})
                with urllib.request.urlopen(request, timeout=180) as stream:
                    response = json.load(stream)
                cache.write_text(json.dumps({'request':payload, 'response':response}, ensure_ascii=False))
            try:
                parsed = json.loads(response['choices'][0]['message']['content'])
                assert response['choices'][0]['finish_reason'] != 'length'
                assert set(parsed) == {str(i) for i in range(len(group))}
                break
            except (ValueError, AssertionError, TypeError):
                if attempt == 2:
                    return [], Counter({'invalid_teacher_batch':1})
        rows = []
        skipped = Counter()
        for i, job in enumerate(group):
            dialogue = parsed[str(i)]
            messages = []
            for turn in range(1, 4):
                user = re.sub(r'\s+', ' ', dialogue['user' + str(turn)]).strip().replace('\u2019', "'")
                answer = re.sub(r'\s+', ' ', dialogue['answer' + str(turn)]).strip().replace('\u2019', "'")
                act = dialogue['act' + str(turn)]
                messages.append({'role':'user', 'content':user})
                kind = 'natural_dialogue'
                target = f'<|tt_intent:{act}|> ' + answer
                reason = None
                if not 1 <= len(answer.split()) <= 16 or not 1 <= len(user.split()) <= 16:
                    reason = 'length'
                elif '<|' in answer or '<|' in user or answer.lower() in ['user', 'assistant', 'bot', *WORDS]:
                    reason = 'bad_literal_answer'
                elif fingerprint(messages) in excluded:
                    reason = 'evaluation_context_overlap'
                elif len(tokenizer.encode(core.render(messages), add_special_tokens=False)) + 40 > 128:
                    reason = 'context_too_long'
                if reason:
                    skipped[reason] += 1
                else:
                    rows.append({'id':f'natural:{job["index"]}:{turn}', 'messages':[dict(m) for m in messages],
                        'kind':kind, 'intent_label':act, 'plain_target':answer, 'target':target,
                        'source':'teacher_complete_natural_dialogue', 'source_topic':job['theme'],
                        'pattern':job['pattern'], 'raw_response':cache.name})
                messages.append({'role':'assistant', 'content':answer})
        return rows, skipped
    rows = []
    skipped = Counter()
    started = time.monotonic()
    with ThreadPoolExecutor(max_workers=12) as pool:
        futures = [pool.submit(worker, group) for group in groups]
        for count, future in enumerate(as_completed(futures), 1):
            batch, misses = future.result()
            rows.extend(batch)
            skipped.update(misses)
            if count % 64 == 0 or count == len(groups):
                print(json.dumps({'done':count, 'batches':len(groups), 'rows':len(rows),
                    'seconds':round(time.monotonic() - started, 1)}), flush=True)
    unique = {}
    for row in sorted(rows, key=lambda r:r['id']):
        unique.setdefault(fingerprint(row['messages']), row)
    rows = list(unique.values())
    sample = sorted(rows, key=lambda r:hashlib.sha256(('qa-natural:' + r['id']).encode()).hexdigest())[:240]
    qa = grade(sample, [r['plain_target'] for r in sample], out / 'grade-cache', workers=args.qa_workers)
    core.save(out / 'teacher-audit.json', qa)
    if args.probe:
        core.save(out / 'probe.json', {'rows':len(rows), 'pass_rate':qa['pass_rate'], 'examples':rows, 'grades':qa})
        print(json.dumps({'probe_rows':len(rows), 'pass_rate':qa['pass_rate'], 'skipped':dict(skipped)}), flush=True)
        return
    sample_rate = qa['pass_rate']
    full_audit = args.full_audit or sample_rate < .95
    if full_audit:
        print(json.dumps({'phase':'full_teacher_answer_audit', 'rows':len(rows), 'sample_pass_rate':sample_rate}), flush=True)
        qa = grade(rows, [r['plain_target'] for r in rows], out / 'full-grade-cache', workers=args.qa_workers)
        core.save(out / 'full-teacher-audit.json', qa)
    bad = {g['id'] for g in qa['details'] if not g['pass']}
    rows = [r for r in rows if r['id'] not in bad]
    assert len(rows) >= args.dialogues
    path = out / 'train.jsonl'
    path.write_text(''.join(json.dumps(r, ensure_ascii=False) + '\n' for r in rows))
    report = {'rows':len(rows), 'planned_dialogues':args.dialogues, 'source_train_sha256':core.digest(args.source_data),
        'sha256':core.digest(path), 'acts':dict(Counter(r['intent_label'] for r in rows)), 'skipped':dict(skipped),
        'teacher_sample_pass_rate':sample_rate, 'source_seed_rows':len(seeds), 'new_reserved_audit_opened':False,
        'qa_workers':args.qa_workers, 'teacher_audit_method':qa['method'],
        'all_retained_targets_graded':full_audit, 'failed_targets_removed':len(bad),
        'whole_contexts_only':True, 'seconds':time.monotonic() - started}
    core.save(out / 'manifest.json', report)
    print(json.dumps(report), flush=True)


if __name__ == '__main__':
    main()
