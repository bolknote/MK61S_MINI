#!/usr/bin/env python3
"""Strict score-only training-data screen; conversational model evaluation still uses grade.py unchanged."""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import urllib.request
from grade import SYSTEM as EVALUATION_SYSTEM


SYSTEM = EVALUATION_SYSTEM.split('Return ONE JSON object')[0] + (
    'Return ONE JSON object whose keys are input ids and whose values are integer scores only. '
    'Score 4=good, 3=acceptable, 2=partly relevant but fails the request, 1=irrelevant, 0=empty or incoherent. '
    'Apply all the above criteria. Do not output explanations or extra fields. '
    'This screens training targets; keep score 4 for a clearly good relevant answer.'
)


def screen(cases, replies, cache, workers=12):
    cache = Path(cache)
    cache.mkdir(parents=True, exist_ok=True)
    inputs = [{'id':case['id'], 'context':case['messages'],
        'intent':case.get('intent', "Reply naturally and usefully to the user's last message."),
        'reply':reply['reply'] if isinstance(reply, dict) else reply} for case, reply in zip(cases, replies)]
    def worker(items):
        key = hashlib.sha256(json.dumps([SYSTEM, items], sort_keys=True).encode()).hexdigest()
        path = cache / (key + '.json')
        if path.exists():
            return json.loads(path.read_text())['grades']
        schema = {'type':'object', 'properties':{str(i):{'type':'integer', 'minimum':0, 'maximum':4} for i in range(len(items))},
            'required':[str(i) for i in range(len(items))], 'additionalProperties':False}
        payload = {'model':'Qwen/Qwen3.8-Flash-Next-FP8', 'temperature':0, 'max_tokens':512,
            'chat_template_kwargs':{'enable_thinking':False},
            'response_format':{'type':'json_schema','json_schema':{'name':'target_scores','strict':True,'schema':schema}},
            'messages':[{'role':'system','content':SYSTEM},
                        {'role':'user','content':json.dumps([dict(r, id=str(i)) for i,r in enumerate(items)])}]}
        for attempt in range(3):
            request = urllib.request.Request('http://127.0.0.1:8000/v1/chat/completions', json.dumps(payload).encode(),
                {'Content-Type':'application/json'})
            with urllib.request.urlopen(request, timeout=180) as stream:
                response = json.load(stream)
            path.with_name(path.stem + f'-attempt{attempt}.raw.json').write_text(json.dumps({'request':payload,'response':response}))
            try:
                scores = json.loads(response['choices'][0]['message']['content'])
                assert set(scores) == {str(i) for i in range(len(items))}
                assert all(type(v) is int and 0 <= v <= 4 for v in scores.values())
                break
            except (ValueError, AssertionError, TypeError):
                if attempt == 2:
                    raise
        results = [{'id':row['id'], 'score':scores[str(i)], 'pass':scores[str(i)] == 4} for i,row in enumerate(items)]
        path.write_text(json.dumps({'inputs':items,'grades':results,'request':payload,'response':response}))
        return results
    with ThreadPoolExecutor(max_workers=workers) as pool:
        groups = list(pool.map(worker, [inputs[i:i + 24] for i in range(0, len(inputs), 24)]))
    details = [g for group in groups for g in group]
    return {'total':len(details), 'passed':sum(g['pass'] for g in details),
        'pass_rate':sum(g['pass'] for g in details) / len(details) if details else 0,
        'mean_score':sum(g['score'] for g in details) / len(details) if details else 0,
        'method':'Qwen training-data screen, same acceptability criteria, score-only JSON, accept only score 4',
        'model_evaluation_grader_changed':False, 'details':details}


def main():
    p = Path('natural-probe/probe.json')
    probe = json.loads(p.read_text())
    rows = probe['examples']
    screened = screen(rows, [r['plain_target'] for r in rows], 'target-screen-calibration-cache')
    previous = {g['id']:g for g in probe['grades']['details']}
    bad = [g for g in screened['details'] if not previous[g['id']]['pass']]
    false_accepts = [g for g in bad if g['pass']]
    report = {'known_bad_targets':len(bad), 'known_bad_rejected':len(bad) - len(false_accepts),
        'false_accepts':false_accepts, 'retained':screened['passed'], 'total':screened['total'], 'screen':screened}
    assert len(bad) >= 5
    Path('target-screen-calibration.json').write_text(json.dumps(report, indent=2))
    print(json.dumps({k:v for k,v in report.items() if k != 'screen'}), flush=True)


if __name__ == '__main__':
    main()
