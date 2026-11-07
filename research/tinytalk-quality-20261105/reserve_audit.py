#!/usr/bin/env python3
"""Reserve an independent next audit before further model selection; never grade the student here."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import urllib.request
from grade import grade
from prepare import fingerprint

FAMILIES = {
 'greeting':'Greeting and wanting a friendly chat.', 'identity':'Asking who this bot is, its name, or what to call it.',
 'idea':'Requesting one simple specific activity, craft or drawing idea.', 'ask':'Asking for a question on an everyday topic.',
 'good_news':'Sharing an ordinary happy event or small success.', 'bad_news':'Sharing an ordinary frustrating or disappointing event.',
 'company':'Wanting company or conversation, without requiring advice.', 'hobby':'Expressing an interest in an easy hobby.',
 'share':'Sharing an interesting ordinary observation.', 'preference':'Describing a preference and inviting a relevant response.',
 'clarify':'An ambiguous request with an essential detail missing everywhere in context.',
 'one_question':'Requesting exactly one question about a specific everyday subject.',
 'game':'Requesting a simple text game: word naming, guessing, rhyming or a very easy riddle.',
 'thanks':'Thanking the bot for chatting, listening or an idea.', 'bye':'Ending the conversation in varied natural ways.',
 'name':'A user gives a name, then asks the bot to recall it. Include a short earlier bot turn.',
 'pet':'A user gives their pet a name, then asks the bot to recall it. Include a short earlier bot turn.',
 'correct':'A user revises a preference then asks for the current value.',
 'reject':'A user rejects an earlier suggested activity and asks for a different one.',
 'project':'A user mentions a hobby, then asks for one concrete beginner project.',
}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', default='reserved-audit2')
    parser.add_argument('--training', required=True)
    parser.add_argument('--seed', type=int, default=301179)
    parser.add_argument('--strict-last-intent', action='store_true', help='Use fixed speaker fields and require the final turn to test the named family')
    args = parser.parse_args()
    output = Path(args.output);assert not (output/'manifest.json').exists();output.mkdir(parents=True, exist_ok=True)
    training = {fingerprint(json.loads(line)['messages']) for line in Path(args.training).read_text().splitlines()}
    def request(name, system, user, schema):
        cached = output/(name+'.raw.json')
        if cached.exists():
            try:return json.loads(json.loads(cached.read_text())['response']['choices'][0]['message']['content'])
            except (ValueError,KeyError):cached.rename(output/(name+'.invalid-cache.json'))
        payload = {'model':'Qwen/Qwen3.8-Flash-Next-FP8','temperature':.9,'seed':args.seed+int(hashlib.sha256(name.encode()).hexdigest()[:6],16),
          'max_tokens':1200 if args.strict_last_intent else 4000,'chat_template_kwargs':{'enable_thinking':False},
          'response_format':{'type':'json_schema','json_schema':{'name':'audit_cases','strict':True,'schema':schema}},
          'messages':[{'role':'system','content':system+' Use compact complete JSON. No formatting whitespace outside strings.'},{'role':'user','content':user}]}
        for attempt in range(4):
            payload['temperature']=0 if args.strict_last_intent else max(0,.9-attempt*.3)
            payload['seed']+=attempt
            req = urllib.request.Request('http://127.0.0.1:8000/v1/chat/completions',json.dumps(payload).encode(),{'Content-Type':'application/json'})
            with urllib.request.urlopen(req,timeout=180) as stream:response=json.load(stream)
            record={'request':payload,'response':response}
            try:
                parsed=json.loads(response['choices'][0]['message']['content'])
                assert isinstance(parsed,dict)and set(schema['required'])<=set(parsed)
            except (ValueError,AssertionError):
                (output/(name+f'.invalid{attempt}.json')).write_text(json.dumps(record))
                if attempt==3:raise
                continue
            cached.write_text(json.dumps(record));return parsed
    string = {'type':'string'}
    message = {'type':'object','properties':{'role':{'type':'string','enum':['user','assistant']},'content':string},'required':['role','content'],'additionalProperties':False}
    case = {'type':'object','properties':{'messages':{'type':'array','items':message,'minItems':1,'maxItems':5},'intent':string,'good_answer':string},
            'required':['messages','intent','good_answer'],'additionalProperties':False}
    schema = {'type':'object','properties':{'cases':{'type':'array','items':case,'minItems':5,'maxItems':5}},'required':['cases'],'additionalProperties':False}
    system = ('Create a held-out evaluation for a very small friendly English chatbot named TinyTalk. '
      'Write five diverse natural easy conversations for the supplied family. Each has 1,3 or 5 alternating user/assistant messages, ending with a user. '
      'The last user should be answerable by a short reply. Use common words and different situations. '
      'All facts needed for recall must be explicit in the USER messages. Keep each message under 14 words. '
      'intent is a precise fair criterion for the final answer; good_answer is one clearly correct short final reply for dataset quality assurance. '
      'No arithmetic, medical/financial advice, specialist facts or impossible physical bot abilities. '
      'Do not require lengthy explanations. Do not include anything about training, evaluation, or this instruction in the conversations.')
    def worker(item):
        family, description, suffix=item
        if args.strict_last_intent:
            result=[]
            for index in range(5):
                turns=3 if family in ['name','pet','correct','reject','project']else 1
                if index>=3:turns=5 if index==4 else 3
                keys=[('user'if i%2==0 else'assistant')+str(i//2)for i in range(turns)]
                properties={key:string for key in keys}
                properties.update(intent=string,good_answer=string)
                strict_schema={'type':'object','properties':properties,'required':list(properties),'additionalProperties':False}
                strict_system=('Create ONE independent ordinary-English conversation for a very small friendly text chatbot TinyTalk. '
                  'The LAST user utterance MUST exercise the specified family, not merely an earlier turn. '
                  'Use exactly the supplied speaker fields. Each utterance is under 12 words. '
                  'Use natural varied wording. All necessary recall facts must be in user utterances. '
                  'intent is a fair literal criterion for the last reply, and good_answer is one valid short reference answer. '
                  'Never require unstated restrictions, an invented bot preference, or a different speaker than the user actually asked about. '
                  'A brief relevant reply may be good. The bot has no physical body or human personal life. '
                  'No medicine, finance, arithmetic, specialist knowledge or impossible tasks. '
                  'For ask/one_question the final USER requests THE BOT to ask a question. '
                  'For name the final USER asks for their own stated name; for pet their pet\'s stated name. '
                  'For greeting the final turn itself is a greeting or opening a friendly chat.')
                parsed=request(family+suffix+'-strict'+str(index),strict_system,description+f' Variation {index}. Fields: '+', '.join(keys),strict_schema)
                messages=[{'role':'user'if i%2==0 else'assistant','content':parsed[key]}for i,key in enumerate(keys)]
                if fingerprint(messages)in training:continue
                result.append({'messages':messages,'intent':parsed['intent'],'good_answer':parsed['good_answer'],
                    'id':f'audit3:{family}:{index}{suffix}','family':family})
            return result
        parsed=request(family+suffix,system,description,schema)
        result=[]
        for index,row in enumerate(parsed['cases']):
            messages=row['messages']
            if len(messages) not in [1,3,5] or any(m['role']!=('user'if i%2==0 else'assistant')for i,m in enumerate(messages)):continue
            if fingerprint(messages) in training:continue
            result.append(dict(row,id=f'audit2:{family}:{index}{suffix}',family=family))
        return result
    with ThreadPoolExecutor(max_workers=8) as pool:rows=[row for group in pool.map(worker,[(k,v,'')for k,v in FAMILIES.items()]) for row in group]
    quality = grade(rows,[row['good_answer']for row in rows],output/'dataset-qa-cache')
    assert args.strict_last_intent or quality['pass_rate']>=.95, 'Independent audit inputs need better reference answers'
    rows=[row for row,g in zip(rows,quality['details'])if g['pass']]
    qa = [quality]
    for attempt in range(3):
        missing=[k for k in FAMILIES if sum(r['family']==k for r in rows)<5]
        if not missing:break
        tasks=[(k,FAMILIES[k]+' Use five different natural phrasings, avoiding very common two-word prompts.',f'-supplement{attempt}')for k in missing]
        with ThreadPoolExecutor(max_workers=8)as pool:extra=[row for group in pool.map(worker,tasks)for row in group]
        check=grade(extra,[r['good_answer']for r in extra],output/'dataset-qa-cache');qa.append(check)
        seen={fingerprint(row['messages'])for row in rows}
        for row,g in zip(extra,check['details']):
            identity=fingerprint(row['messages'])
            if g['pass']and identity not in seen:rows.append(row);seen.add(identity)
    selected=[]
    for family in FAMILIES:
        chosen=[r for r in rows if r['family']==family][:5]
        assert len(chosen)==5, family
        selected+=chosen
    rows=selected
    (output/'dataset-qa.json').write_text(json.dumps(qa,indent=2))
    path=output/'test.jsonl';path.write_text(''.join(json.dumps(row,ensure_ascii=False)+'\n'for row in rows))
    step={'type':'object','properties':{'user':string,'intent':string},'required':['user','intent'],'additionalProperties':False}
    scenario_schema={'type':'object','properties':{'steps':{'type':'array','items':step,'minItems':3,'maxItems':3}},'required':['steps'],'additionalProperties':False}
    topics=['Remember the user and a named pet with roles kept distinct.','Correct an everyday color preference, then recall the final value.',
      'Suggest a calm activity, respect rejected activities, then offer a text game.','Discuss making a small object, a decoration, then its color.',
      'React to an annoying event, offer a gentle break, then acknowledge relief.','Take turns naming foods without repeating an already used item.',
      'Discuss starting a hobby and concrete small next steps.','Recall a user name after an unrelated short topic.']
    def scenario(item):
        index,topic=item
        parsed=request('scenario'+str(index),
          'Create a three-turn user script for a small English text chatbot. Each step has a user utterance and a fair acceptance criterion. '
          'Keep user utterances under 12 words. All required facts must appear in user utterances. The actual bot will choose its own replies: '
          'do not assume it mentioned a particular object or fact. User follow-ups should explicitly name what they concern. '
          'Use common words and ordinary life, with no medicine, finance, specialist knowledge or arithmetic.',topic,scenario_schema)
        return [[step['user'],step['intent']]for step in parsed['steps']]
    with ThreadPoolExecutor(max_workers=4)as pool:scenarios=list(pool.map(scenario,enumerate(topics)))
    (output/'scenarios.json').write_text(json.dumps(scenarios,ensure_ascii=False,indent=2))
    digest=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    report={'policy':'New teacher-generated audit fixed after the first audit was opened; student never decoded or graded here',
      'rows':len(rows),'scenarios':len(scenarios),'seed':args.seed,'reference_answer_qa_pass_rate':quality['pass_rate'],
      'test_sha256':digest(path),'scenarios_sha256':digest(output/'scenarios.json'),
      'training_sha256_at_reservation':digest(Path(args.training)),'exact_training_context_overlap':0,'student_audit_opened':False}
    report['strict_final_intent']=args.strict_last_intent
    (output/'manifest.json').write_text(json.dumps(report,indent=2));print(json.dumps(report),flush=True)


if __name__=='__main__':main()
