"""Matched action-level pilot. Model calls and every tool observation are saved."""
import argparse
import concurrent.futures
import hashlib
import json
import time
import urllib.request

from ar_common import ROOT, MODEL, MAX_TURNS, TEACHER, URL, read, write, check_frozen, sha
from ar_runtime import Session, view_of, goal_prompt
from ar_spec import infer, verify, equivalent, spec_text
from full_isa_vm import FullVM
from ha_protocol import parse_bytes


class Teacher:
    def __init__(self):
        self.pool=concurrent.futures.ThreadPoolExecutor(max_workers=4)
        self.cache=ROOT/'teacher-cache';self.cache.mkdir(exist_ok=True)

    def one(self, prompt, forced):
        schema={'type':'object','properties':{'action':{'type':'string','enum':[forced]if forced else['write','run','trace','done','unsure','diag']},
                  'body':{'type':'string'}},'required':['action','body'],'additionalProperties':False}
        system=('You operate the MK-61 tool harness. Return one JSON action with action and body. '
                'body is space-separated HEX bytes; empty for done/trace/unsure. '
                'run has one test-index byte, diag has five bytes. write replaces the whole program and runs the current public case. '
                'There are no additional tools. Obey the Russian task and facts in the user message. '
                'An unconfirmed formal hypothesis can be wrong; DONE claims the user task is solved.')
        payload={'model':TEACHER,'messages':[{'role':'system','content':system},{'role':'user','content':prompt}],
                 'temperature':0,'seed':260008,'max_tokens':512,
                 'chat_template_kwargs':{'enable_thinking':False},
                 'response_format':{'type':'json_schema','json_schema':{'name':'mk61_action','strict':True,'schema':schema}}}
        encoded=json.dumps(payload,ensure_ascii=False,sort_keys=True).encode()
        key=hashlib.sha256(encoded).hexdigest();path=self.cache/(key+'.json')
        if path.exists():return read(path)['generation']
        start=time.monotonic()
        request=urllib.request.Request(URL,encoded,headers={'Content-Type':'application/json'})
        error=None
        for attempt in range(3):
            try:
                with urllib.request.urlopen(request,timeout=150)as response:data=json.load(response)
                break
            except Exception as e:
                error=repr(e)
                if attempt==2:raise
                time.sleep(2)
        content=data['choices'][0]['message']['content']
        try:
            action=json.loads(content);name=action['action'];body=parse_bytes(action['body'],empty=True)
            if forced and name!=forced:raise ValueError('FORCED_ACTION')
            generation={'action':name,'body':body,'codec_error':None}
        except (ValueError,KeyError,TypeError)as e:
            generation={'action':None,'body':[],'codec_error':str(e)}
        generation.update(raw=content,usage=data.get('usage'),finish_reason=data['choices'][0]['finish_reason'],seconds=time.monotonic()-start)
        write(path,{'payload':payload,'response':data,'generation':generation})
        return generation

    def generate(self,prompts,forced_action=None):
        return list(self.pool.map(lambda p:self.one(p,forced_action),prompts))


class Small:
    def __init__(self):
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer
        from lowbit import load
        from codec_common import compact_head
        from aq_common import output_ids
        torch.set_num_threads(4);torch.manual_seed(260008);torch.backends.cuda.matmul.allow_tf32=False
        self.model=AutoModelForCausalLM.from_pretrained(MODEL/'hf',local_files_only=True)
        load(self.model,MODEL/'model.mkqb');self.model.cuda().eval().requires_grad_(False)
        self.tokenizer=AutoTokenizer.from_pretrained(MODEL/'hf',local_files_only=True)
        compact_head(self.model,output_ids(self.tokenizer))

    def generate(self,prompts,forced_action=None):
        from aq_eval import generate
        return generate(self.model,self.tokenizer,prompts,forced_action)


def plans(actor,goals,vm,out):
    path=out/'plans.json'
    if path.exists():return read(path)
    items=[(g,mode)for g in goals for mode in ['natural','formal']]
    rows=[]
    for at in range(0,len(items),16):
        chunk=items[at:at+16]
        prompts=[goal_prompt(view_of(g,mode),g['pool'])for g,mode in chunk]
        generations=actor.generate(prompts,'write')
        for(g,mode),prompt,generation in zip(chunk,prompts,generations):
            spec=None;error=None
            try:
                if generation.get('codec_error'):raise ValueError(generation['codec_error'])
                spec=infer(generation['body'],g['pool'],g['angle'])
                # Soundness preflight for the supported part of the symbolic decoder.
                check=verify(vm,generation['body'],g['pool'],spec,g['public_inputs']+g['checker_inputs'])
                if check['status']!='TESTED':raise ValueError('DECODER_VALIDATION '+json.dumps(check))
            except (ValueError,ArithmeticError,RuntimeError)as e:
                error=str(e);spec=None
            actual=verify(vm,generation.get('body',[]),g['pool'],g['spec'],g['audit_inputs'])
            rows.append({'id':g['id'],'mode':mode,'spec':spec,'spec_text':spec_text(spec),'inference_error':error,
                         'intent':equivalent(spec,g['spec'],g['audit_inputs']),
                         'program_to_task':actual,'generation':generation,'prompt':prompt})
        write(out/'status.json',{'phase':'goal_only_plans','completed':len(rows),'total':len(items)})
        print(json.dumps({'plans':len(rows),'total':len(items)}),flush=True)
    write(path,rows);return rows


def episode_record(goal,mode,initial,gate,session,declared,plan):
    task_check=verify(session.vm,session.body,session.pool,goal['spec'],goal['audit_inputs'])
    spec_check=verify(session.vm,session.body,session.pool,declared,goal['audit_inputs'])
    intent=equivalent(declared,goal['spec'],goal['audit_inputs'])
    eligible=session.eligibility()[0]
    return {'id':f'{goal["id"]}:{mode}:{initial}:{gate}','task_id':goal['id'],'family':goal['family'],
            'input_mode':mode,'initial':initial,'gate':gate,'task':view_of(goal,mode)['task'],
            'declared_spec':declared,'declared_intent':intent,'spec_available':declared is not None,
            'plan_program_correct':plan['program_to_task']['status']=='TESTED',
            'finished':session.finished,'abstained':session.abstained,'eligible':eligible,
            'task_correct':task_check['status']=='TESTED','spec_consistent':spec_check['status']=='TESTED',
            'task_audit':task_check,'spec_audit':spec_check,'body':session.body,
            'gate_checks':session.gate_checks,'history':session.history,
            'pass':session.finished and eligible and task_check['status']=='TESTED'}


def run(label):
    frozen=check_frozen();goals=read(ROOT/'goals.json');out=ROOT/label;out.mkdir(exist_ok=True)
    assert not(out/'results.json').exists(),'Results already finalized'
    actor=Small()if label=='small'else Teacher();vm=FullVM();started=time.monotonic()
    plan_rows=plans(actor,goals,vm,out);plan_index={(r['id'],r['mode']):r for r in plan_rows}
    jobs=[(g,mode,initial,gate)for g in goals for mode in ['natural','formal']
          for initial in ['correct','wrong']for gate in ['raw','mechanical']]
    records=[];record_path=out/'episodes.jsonl'
    if record_path.exists():records=[json.loads(x)for x in record_path.read_text().splitlines()]
    completed={r['id']for r in records}
    jobs=[j for j in jobs if ':'.join([j[0]['id'],*j[1:]])not in completed]
    for at in range(0,len(jobs),16):
        chunk=jobs[at:at+16];sessions=[];declareds=[]
        for g,mode,initial,gate in chunk:
            plan=plan_index[(g['id'],mode)]
            declared=g['spec']if mode=='formal'else plan['spec']
            declareds.append(declared)
            sessions.append(Session(view_of(g,mode),g['reference_body']if initial=='correct'else g['wrong_body'],
                                    vm,declared,g['checker_inputs'],gate=='mechanical'))
        for turn in range(MAX_TURNS):
            active=[s for s in sessions if not s.finished and not s.abstained and not getattr(s,'exhausted',False)]
            if not active:break
            prompts=[s.request()for s in active];generated=actor.generate(prompts)
            for s,p,v in zip(active,prompts,generated):
                if v.get('codec_error'):
                    s.history.append({'kind':'generation_error','prompt':p,'generation':v});s.exhausted=True;continue
                try:s.apply_action(v['action'],v['body'])
                except (ValueError,ArithmeticError,RuntimeError)as error:
                    s.observation='ERROR '+str(error);s.history.append({'kind':'error','observation':s.observation})
                s.history[-1].update(prompt=p,generation=v)
        for(g,mode,initial,gate),s,declared in zip(chunk,sessions,declareds):
            row=episode_record(g,mode,initial,gate,s,declared,plan_index[(g['id'],mode)])
            records.append(row)
            with record_path.open('a')as stream:stream.write(json.dumps(row,ensure_ascii=False)+'\n')
        write(out/'status.json',{'phase':'episodes','completed':len(records),'total':256,'seconds':time.monotonic()-started})
        print(json.dumps({'episodes':len(records),'seconds':round(time.monotonic()-started,1)}),flush=True)
    check_frozen()
    write(out/'results.json',{'label':label,'records':records,'plans':plan_rows,'seconds':time.monotonic()-started,
                             'source_frozen_sha256':sha(ROOT/'frozen.json'),'training_updates':0})
    write(out/'status.json',{'phase':'complete','episodes':len(records),'seconds':time.monotonic()-started})


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('model',choices=['small','teacher']);args=p.parse_args();run(args.model)
