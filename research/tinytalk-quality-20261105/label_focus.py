#!/usr/bin/env python3
"""Extract short answer keywords from accepted targets, without rewriting speech."""
import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import json
from pathlib import Path
import re
import time
import urllib.request

from common import core
from reply_types import ANCHORS, SYSTEM as TYPE_SYSTEM


SYSTEM = TYPE_SYSTEM + (
    '\nFor each item also extract a short answer KEYWORD PHRASE. This is answer content, '
    'not a rationale, instruction, or explanation. Select a contiguous verbatim span from '
    'the supplied accepted answer, ideally 1-4 words and at most 8 words. '
    'Include the essential answer value: a corrected/current name or color, full title, '
    'named plant/genre, concrete action, game word, question subject, sympathy subject, '
    'or greeting/wish. Prefer Olivia over Your name is Olivia; mint over Try growing mint; '
    'The Little Prince over Try reading The Little Prince. Preserve full proper names and titles. '
    'For an unavailable personal fact use the literal keyword unknown. '
    'For social replies choose their essential phrase, e.g. good luck or sorry. '
    'Never invent, correct, extend or paraphrase the accepted answer. '
    'Choose a span from the answer even if a different reply might be better. '
    'Return an object mapping ids to {type: answer-form string, key: verbatim span}; no prose.'
)
COMPACT_SYSTEM = SYSTEM.replace(
    'Return an object mapping ids to {type: answer-form string, key: verbatim span}; no prose.',
    'Return one JSON object mapping each id to a SINGLE STRING: answer_type|keyword phrase. '
    'For example {"0":"name|Olivia","1":"color|blue","2":"unknown|unknown"}. '
    'Use the same named answer types above. No nested objects and no prose. '
    'The keyword after | MUST be copied from the supplied ANSWER, never merely from the context. '
    'For the answer That is a lovely name for your dog, use ack|lovely name, '
    'not a pet name from context. A name statement usually needs acknowledgment; '
    'the type name is for an actual requested name answer.')


def validate(item, row):
    assert set(item) == {'type', 'key'} and item['type'] in ANCHORS
    key = item['key']
    assert isinstance(key, str) and key == key.strip() and 0 < len(key) <= 100
    assert len(key.split()) <= 8 and re.search(r'\w', key) and '<|' not in key and '\n' not in key
    answer = row['plain_target']
    if key not in answer:
        match = re.search(re.escape(key), answer, flags=re.I)
        if match: key = match[0]
    assert key in answer or (key == 'unknown' and item['type'] == 'unknown'), (key, answer)
    return {'id': row['id'], 'answer_type': item['type'], 'focus': key}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data', default='base-data/train.jsonl')
    parser.add_argument('--output', default='focus-labels')
    parser.add_argument('--probe', type=int, default=0)
    parser.add_argument('--workers', type=int, default=12)
    parser.add_argument('--compact-wire', action='store_true', help='Shorter equivalent teacher response; reuse old cached batches')
    args = parser.parse_args()
    out = Path(args.output); raw = out / 'raw'; raw.mkdir(parents=True, exist_ok=True)
    all_rows = core.read_rows(args.data)
    automatic, rows = [], []
    for row in all_rows:
        if row['kind'] == 'replay':
            continue
        if row['kind'] == 'contrastive_facts':
            key = row['plain_target'].strip().rstrip('.!?') if row.get('known') else 'unknown'
            automatic.append({'id': row['id'], 'answer_type': row['answer_type'], 'focus': key})
        elif row['kind'] == 'grounded_qa':
            key = row['plain_target'].strip().rstrip('.!?')
            form = 'yes_no' if key.lower() in ['yes', 'no', 'maybe'] else 'fact'
            automatic.append({'id': row['id'], 'answer_type': form, 'focus': key})
        else:
            rows.append(row)
    if args.probe:
        # Stable balanced source sample; never read a development answer or closed audit.
        groups = {k: [] for k in sorted({r['kind'] for r in rows})}
        for row in sorted(rows, key=lambda r: hashlib.sha256(('focus-probe:' + r['id']).encode()).digest()):
            groups[row['kind']].append(row)
        rows = []
        while len(rows) < args.probe and any(groups.values()):
            for group in groups.values():
                if group and len(rows) < args.probe: rows.append(group.pop())
        automatic = []
    rows.sort(key=lambda r: r['id'])
    groups = [rows[i:i + 24] for i in range(0, len(rows), 24)]

    rejected_dir = out / 'rejected'; rejected_dir.mkdir(exist_ok=True)
    def reject(group, reason, key):
        (rejected_dir / (key + '.json')).write_text(json.dumps({'ids': [r['id'] for r in group], 'reason': reason}))
        return []
    def label(group, attempt=0):
        items = [{'id': str(i), 'context': r['messages'], 'answer': r['plain_target']}
                 for i, r in enumerate(group)]
        old_key = hashlib.sha256(json.dumps([SYSTEM, items, attempt], sort_keys=True).encode()).hexdigest()
        # Retain every old cached result. A compact response that fails the
        # span check retries with the more explicit object fields.
        compact = args.compact_wire and attempt == 0 and not (raw / (old_key + '.json')).exists()
        system = COMPACT_SYSTEM if compact else SYSTEM
        key = hashlib.sha256(json.dumps([system, items, attempt], sort_keys=True).encode()).hexdigest()
        path = raw / (key + '.json')
        entry = {'type': 'object', 'properties': {'type': {'type': 'string', 'enum': list(ANCHORS)},
                 'key': {'type': 'string'}}, 'required': ['type', 'key'], 'additionalProperties': False}
        if compact: entry = {'type': 'string', 'pattern': '^(' + '|'.join(ANCHORS) + ')\\|[^\\n]+$'}
        schema = {'type': 'object', 'properties': {str(i): entry for i in range(len(items))},
                  'required': [str(i) for i in range(len(items))], 'additionalProperties': False}
        if path.exists():
            response = json.loads(path.read_text())['response']
        else:
            payload = {'model': 'Qwen/Qwen3.8-Flash-Next-FP8', 'temperature': 0, 'max_tokens': 2400,
                'chat_template_kwargs': {'enable_thinking': False},
                'response_format': {'type': 'json_schema', 'json_schema': {'name': 'answer_keywords', 'strict': True, 'schema': schema}},
                'messages': [{'role': 'system', 'content': system}, {'role': 'user', 'content': json.dumps(items)}]}
            request = urllib.request.Request('http://127.0.0.1:8000/v1/chat/completions', json.dumps(payload).encode(),
                                             {'Content-Type': 'application/json'})
            with urllib.request.urlopen(request, timeout=240) as stream: response = json.load(stream)
            path.write_text(json.dumps({'request': payload, 'response': response}, ensure_ascii=False))
        try:
            parsed = json.loads(response['choices'][0]['message']['content'])
            assert response['choices'][0]['finish_reason'] != 'length'
            assert set(parsed) == {str(i) for i in range(len(items))}
        except (AssertionError, ValueError):
            if attempt >= 3: return reject(group, 'Invalid JSON/length after four attempts', key)
            return label(group, attempt + 1)
        accepted, rejected = [], []
        for i, row in enumerate(group):
            try:
                item = parsed[str(i)]
                if compact:
                    form, focus = item.split('|', 1); item = {'type': form, 'key': focus}
                accepted.append(validate(item, row))
            except (AssertionError, TypeError, KeyError, ValueError, AttributeError): rejected.append(row)
        if rejected:
            if attempt >= 3: reject(rejected, 'No valid short verbatim span after four attempts', key)
            else: accepted.extend(label(rejected, attempt + 1))
        return accepted

    labels = list(automatic); started = time.monotonic()
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = [pool.submit(label, group) for group in groups]
        for count, future in enumerate(as_completed(futures), 1):
            try: labels.extend(future.result())
            except BaseException:
                # Do not run thousands of queued requests after the first hard
                # infrastructure error while the context manager waits to exit.
                for pending in futures: pending.cancel()
                print(json.dumps({'failed_batch': count, 'queued_jobs_cancelled': True}), flush=True)
                raise
            if count % 100 == 0 or count == len(groups):
                print(json.dumps({'batches': count, 'total': len(groups), 'rows': len(labels),
                                  'seconds': round(time.monotonic() - started, 1)}), flush=True)
    labels.sort(key=lambda r: r['id'])
    excluded = sorted({r['id'] for r in rows} - {r['id'] for r in labels})
    assert len(labels) + len(excluded) == len(rows) + len(automatic)
    assert len(excluded) <= max(1, len(rows) * .005), 'Too many invalid labels; improve the labeling prompt'
    assert len({r['id'] for r in labels}) == len(labels)
    path = out / 'labels.jsonl'; path.write_text(''.join(json.dumps(r) + '\n' for r in labels))
    core.save(out / 'manifest.json', {'rows': len(labels), 'teacher_rows': len(rows),
        'automatic_grounded_rows': len(automatic), 'source_sha256': core.digest(args.data),
        'unlabelable_rows_excluded': excluded,
        'sha256': core.digest(path), 'types': dict(Counter(r['answer_type'] for r in labels)),
        'scope': 'Short answer-content spans only; no rationale; original spoken targets unchanged',
        'compact_wire_for_uncached_batches': args.compact_wire,
        'probe_only': bool(args.probe), 'reserved_audit3_opened': False})
    if args.probe:
        by_id = {r['id']: r for r in rows}
        core.save(out / 'probe-examples.json', [dict(by_id[r['id']], **r) for r in labels])


if __name__ == '__main__': main()
