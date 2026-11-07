#!/usr/bin/env python3
"""Blind validity check of observed rubrics, never looking at student answers or changing scores."""
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import urllib.request


SYSTEM = (
    'Audit evaluation instructions for short English conversations with TinyTalk, a friendly AI text bot. '
    'You see ONLY the conversation and proposed evaluation intent, never student replies or scores. '
    'Check whether that intent is justified by what the last user actually says and the prior context. '
    'An intent is invalid when it requires guessing a missing real-world fact, confuses my/your roles, '
    'misreads the last message, or unnecessarily excludes another clearly appropriate natural answer. '
    'Examples: a question asking where unstated bikes are cannot require garage; '
    'a friendly relevant follow-up to shared good news need not be an enthusiastic exclamation. '
    'The bot may express conversational preferences without claiming human physical experiences. '
    'A real request for a particular fact, concrete idea, question, correction or game move must still be fulfilled. '
    'Do not excuse vague filler, bad English, wrong stated facts or ignored explicit requests. '
    'Return valid, issue (none/unsupported_fact/role/over_specific/misread/ambiguous), reason (under 18 words), '
    'and grounded_intent, which describes an appropriate fair requirement based only on the conversation. '
    'This is a rubric audit, not model evaluation. Keep valid instructions just as strict.'
)


def main():
    out = Path('rubric-audit')
    out.mkdir(exist_ok=True)
    rows = []
    for name in ['dev', 'test', 'opened-audit2']:
        path = Path('suite') / (name + '.jsonl')
        for line in path.read_text().splitlines():
            row = json.loads(line)
            rows.append({'id':row['id'], 'partition':name, 'context':row['messages'], 'intent':row['intent']})
    def worker(items):
        key = hashlib.sha256(json.dumps([SYSTEM, items], sort_keys=True).encode()).hexdigest()
        path = out / (key + '.json')
        if path.exists():
            return json.loads(path.read_text())['results']
        value = {'type':'object', 'properties':{'valid':{'type':'boolean'},
            'issue':{'type':'string', 'enum':['none','unsupported_fact','role','over_specific','misread','ambiguous']},
            'reason':{'type':'string'}, 'grounded_intent':{'type':'string'}},
            'required':['valid','issue','reason','grounded_intent'], 'additionalProperties':False}
        schema = {'type':'object', 'properties':{str(i):value for i in range(len(items))},
            'required':[str(i) for i in range(len(items))], 'additionalProperties':False}
        wire = [dict(r, id=str(i)) for i, r in enumerate(items)]
        payload = {'model':'Qwen/Qwen3.8-Flash-Next-FP8', 'temperature':0, 'max_tokens':1800,
            'chat_template_kwargs':{'enable_thinking':False},
            'response_format':{'type':'json_schema','json_schema':{'name':'rubric_validity','strict':True,'schema':schema}},
            'messages':[{'role':'system','content':SYSTEM}, {'role':'user','content':json.dumps(wire)}]}
        request = urllib.request.Request('http://127.0.0.1:8000/v1/chat/completions', json.dumps(payload).encode(),
            {'Content-Type':'application/json'})
        with urllib.request.urlopen(request, timeout=180) as stream:
            response = json.load(stream)
        parsed = json.loads(response['choices'][0]['message']['content'])
        results = [dict(parsed[str(i)], id=r['id'], partition=r['partition']) for i, r in enumerate(items)]
        path.write_text(json.dumps({'request':payload,'response':response,'results':results}, ensure_ascii=False, indent=2))
        return results
    with ThreadPoolExecutor(max_workers=4) as pool:
        groups = list(pool.map(worker, [rows[i:i + 8] for i in range(0, len(rows), 8)]))
    results = [r for group in groups for r in group]
    report = {'purpose':'Blind rubric validity audit; original scores and suites remain unchanged',
        'student_answers_seen':False, 'reserved_audit_seen':False, 'total':len(results),
        'valid':sum(r['valid'] for r in results),
        'issues':dict(Counter(r['issue'] for r in results if not r['valid'])), 'results':results}
    (out / 'summary.json').write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print(json.dumps({k:v for k,v in report.items() if k != 'results'}), flush=True)


if __name__ == '__main__':
    main()
