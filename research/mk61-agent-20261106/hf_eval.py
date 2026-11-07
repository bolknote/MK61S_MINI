"""Score raw DONE decisions separately from the non-oracle execution gate."""
import collections
import json

import torch

from hf_common import ROOT,ARMS,INITIAL,INITIAL_PACKET,allowed,compact_head,read,sha,write
from hf_runtime import Session,prompt
from ha_protocol import constants,encode,assemble,parse_call
from full_isa_common import HexProtocol
from full_isa_vm import FullVM,check_task
from codec_eval import generate_batch,language_nll


def generate(model,tokenizer,prompts):
    lengths=[len(tokenizer.encode(p,add_special_tokens=False))for p in prompts]
    result=[None]*len(prompts);valid=[i for i,n in enumerate(lengths)if n<1024]
    for i,n in enumerate(lengths):
        if n>=1024:result[i]={'reply':'','raw_reply':'','codec_error':'context_overflow','generated_token_ids':[],
                               'generated_tokens':0,'input_tokens':n,'batch_size':0,'batch_generation_seconds':0.}
    if valid:
        limit=min(512,1024-max(lengths[i]for i in valid))
        rows=generate_batch(model,tokenizer,[prompts[i]for i in valid],HexProtocol(),max_new=limit)
        for i,row in zip(valid,rows):
            own=min(512,1024-lengths[i])
            if row['generated_tokens']>=limit and own>limit:
                row=generate_batch(model,tokenizer,[prompts[i]],HexProtocol(),max_new=own)[0]
            result[i]=row
    return result


def stats(rows):
    return {'passed':sum(r['pass']for r in rows),'total':len(rows),
            'rate':sum(r['pass']for r in rows)/len(rows)if rows else 0.,'exact':sum(r.get('exact_reference',False)for r in rows)}


def evaluate(model,tokenizer,tasks,arm='asm',*,legacy_protocol=False):
    if legacy_protocol:
        import ha_eval
        return ha_eval.evaluate(model,tokenizer,tasks,arm)
    vm=FullVM();rows=[]
    for at in range(0,len(tasks),16):
        batch=tasks[at:at+16];texts=[prompt(t,arm)for t in batch]
        for task,text,row in zip(batch,texts,generate(model,tokenizer,texts)):
            pool=task.get('constants')or constants(task['task'])
            try:
                kind,body=parse_call(row['reply']);assert kind=='write'
                code=assemble(body,pool,arm);passed=check_task(vm,code,task)['pass'];valid=True
            except (ValueError,RuntimeError,ArithmeticError,AssertionError):body=None;code=None;passed=False;valid=False
            rows.append({'id':task['id'],'group':task['group'],'kind':task['kind'],'angle':task['angle'],
              'opcode':task.get('opcode'),'catalog_risk':task.get('catalog_risk'),'source_kind':task.get('source_kind'),
              'pass':bool(passed),'valid_call':valid,'body':body,'code':code,'exact_reference':code==task['reference_code'],
              'prompt':text,**row})
    groups=collections.defaultdict(list);opcodes=collections.defaultdict(list);kinds=collections.defaultdict(list)
    for row in rows:
        groups[row['group']].append(row);kinds[row['kind']].append(row)
        if row['opcode']is not None:opcodes[f'{row["opcode"]:02X}'].append(row)
    doc=[r for r in rows if r['kind']=='primitive'and r['catalog_risk']=='documented']
    return {**stats(rows),'valid_calls':sum(r['valid_call']for r in rows),'by_group':{k:stats(v)for k,v in groups.items()},
            'by_kind':{k:stats(v)for k,v in kinds.items()},'by_opcode':{k:stats(v)for k,v in opcodes.items()},
            'documented':stats(doc)if doc else None,'details':rows}


def tool_panel(model,tokenizer,tasks,seeds,arm='asm',max_turns=6,*,gate=False,from_scratch=False):
    vm=FullVM();lookup={t['id']:t for t in tasks};rows=[]
    def grade(s):
        try:
            code=assemble(s.body,s.pool,arm)if s.body is not None else None
            return bool(code and check_task(vm,code,s.task)['pass']),code
        except (ValueError,ArithmeticError,RuntimeError):return False,None
    for at in range(0,len(seeds),16):
        items=seeds[at:at+16];sessions=[]
        for item in items:
            task=lookup[item['task_id']];pool=task.get('constants')or constants(task['task'])
            body=None if from_scratch else encode(item['initial_code'],pool,arm)
            s=Session(task,arm,body=body,vm=vm,gate=gate);s.exhausted=False
            if not from_scratch:
                s.run(0)
                if item.get('pre_run_all'):
                    for i in range(1,len(task['public_tests'])):s.run(i)
            sessions.append(s)
        for turn in range(max_turns):
            active=[s for s in sessions if not s.finished and not s.exhausted]
            if not active:break
            requests=[s.request()for s in active];replies=generate(model,tokenizer,requests)
            for s,request,row in zip(active,requests,replies):
                if row['codec_error']=='context_overflow':
                    s.history.append({'kind':'context_overflow','prompt':request});s.exhausted=True;continue
                kind=s.apply(row['reply']);entry=s.history[-1]
                entry.update(prompt=request,generated_token_ids=row['generated_token_ids'])
                if kind in ['done','done_rejected']:entry['grader_program_correct_at_attempt']=grade(s)[0]
        for item,s in zip(items,sessions):
            correct,code=grade(s)
            rows.append({'id':item['task_id'],'initially_correct':item['intentionally_correct']if not from_scratch else False,
                         'pass':bool(correct and s.finished),'program_correct':correct,'finished':s.finished,'code':code,
                         'history':s.history,'done_attempts':s.done_attempts,'done_rejections':s.done_rejections,
                         'origin':item.get('origin',{}),'from_scratch':from_scratch})
    wrong=[r for r in rows if not r['initially_correct']];controls=[r for r in rows if r['initially_correct']]
    return {'passed':sum(r['pass']for r in rows),'total':len(rows),'initially_wrong':len(wrong),
            'repaired':sum(r['pass']for r in wrong),'false_accepts':sum(r['finished']and not r['program_correct']for r in rows),
            'wrong_done_attempts':sum(h.get('grader_program_correct_at_attempt')is False for r in rows for h in r['history']),
            'premature_done_rejected':sum(r['done_rejections']for r in rows),
            'correct_controls_completed':sum(r['pass']for r in controls),'correct_controls':len(controls),
            'unfinished_correct':sum(r['program_correct']and not r['finished']for r in rows),
            'program_correct':sum(r['program_correct']for r in rows),
            'trace_requests':sum(h['kind']=='trace'for r in rows for h in r['history']),
            'patch_requests':sum(h['kind']=='patch'for r in rows for h in r['history']),
            'run_requests':sum(h['kind']=='run'for r in rows for h in r['history']),
            'context_overflows':sum(h['kind']=='context_overflow'for r in rows for h in r['history']),
            'gate_enabled':gate,'observations_have_expected_outputs':False,'hidden_cases_available_to_model':False,
            'max_turns':max_turns,'details':rows}


def development(model,tokenizer,strategy):
    return {'arm':strategy,'language':evaluate(model,tokenizer,read(ROOT/'development.jsonl')),
            'isa':evaluate(model,tokenizer,read(ROOT/'isa-development.jsonl')),
            'legacy':evaluate(model,tokenizer,read(ROOT/'legacy-development.jsonl')),
            'tools':tool_panel(model,tokenizer,read(ROOT/'validation.jsonl'),read(ROOT/'validation-tool-seeds.jsonl'),gate=False)}


def selection(result):
    lang=result['language'];tool=result['tools'];doc=result['isa']['documented']['rate'];legacy=result['legacy']['rate']
    macro=sum(v['rate']for v in lang['by_group'].values())/len(lang['by_group'])
    repair=tool['repaired']/max(1,tool['initially_wrong']);success=tool['passed']/max(1,tool['total'])
    false=tool['false_accepts']/max(1,tool['total']);unfinished=tool['unfinished_correct']/max(1,tool['total'])
    floors=json.loads((ROOT/'retention-floors.json').read_text());kinds=result['isa']['by_kind']
    guard=doc==1. and legacy>=floors['legacy']and kinds['numeric_synthesis']['rate']>=floors['scientific']and kinds['programming']['rate']>=floors['programming']
    score=.45*success+.35*repair+.1*macro+.1*legacy-.3*false-.1*unfinished
    return [guard,score,-false,repair,success,macro,legacy]


def brief(r):
    return {'key':selection(r),'language':{k:v for k,v in r['language'].items()if k!='details'},
            'isa':{k:v for k,v in r['isa'].items()if k not in ['details','by_opcode']},
            'legacy':{k:r['legacy'][k]for k in ['passed','total','rate']},
            'tools':{k:v for k,v in r['tools'].items()if k!='details'}}


def audit(model,tokenizer,label,packet):
    tasks=read(ROOT/'fresh.jsonl');items=read(ROOT/'fresh-tool-seeds.jsonl')
    result={'label':label,'arm':'asm','packed_sha256':sha(packet),'language':evaluate(model,tokenizer,tasks),
      'isa':evaluate(model,tokenizer,read(ROOT/'isa-audit.jsonl')),'legacy':evaluate(model,tokenizer,read(ROOT/'legacy-development.jsonl')),
      'observed_retention':evaluate(model,tokenizer,read(ROOT/'observed-retention.jsonl')),
      'observed_ablation':evaluate(model,tokenizer,read(ROOT/'observed-ablation.jsonl')),
      'observed_previous_language':evaluate(model,tokenizer,read(ROOT/'observed-previous-language.jsonl')),
      'observed_user_reproductions':evaluate(model,tokenizer,read(ROOT/'observed-user-reproductions.jsonl')),
      'tools':tool_panel(model,tokenizer,tasks,items,gate=False),'tools_gated':tool_panel(model,tokenizer,tasks,items,gate=True),
      'from_scratch':tool_panel(model,tokenizer,tasks,items[:48],gate=True,from_scratch=True),
      'public_language':language_nll(model),'fresh_used_for_selection':False,'feedback_contains_expected_outputs':False,
      'physical_picocalc_measured':False}
    write(ROOT/'results'/(label+'.json'),result)
    print(json.dumps({'label':label,'language':[result['language']['passed'],result['language']['total']],
      'doc':result['isa']['documented'],'legacy':result['legacy']['passed'],
      'tools':{k:v for k,v in result['tools'].items()if k!='details'},'tools_gated':{k:v for k,v in result['tools_gated'].items()if k!='details'}}),flush=True)


def main():
    import argparse
    import shutil
    from transformers import AutoModelForCausalLM,AutoTokenizer
    from native_quant import attach,packed_copy
    from lowbit import load
    ap=argparse.ArgumentParser();ap.add_argument('--arm',choices=ARMS,required=True);a=ap.parse_args()
    assert(ROOT/'preselected.json').exists();torch.set_num_threads(4);torch.cuda.set_per_process_memory_fraction(.2)
    paths=[(a.arm+'-best',ROOT/a.arm/'best',None)]
    if a.arm=='safe':paths.insert(0,('asm-baseline',INITIAL,INITIAL_PACKET))
    for label,path,source in paths:
        if(ROOT/'results'/(label+'.json')).exists():continue
        model=AutoModelForCausalLM.from_pretrained(path,local_files_only=True,trust_remote_code=False)
        tokenizer=AutoTokenizer.from_pretrained(path,local_files_only=True,trust_remote_code=False)
        packet=ROOT/'results'/(label+'.mkqb');packet.parent.mkdir(exist_ok=True)
        if source:shutil.copyfile(source,packet);load(model,packet)
        else:attach(model,'q4');model,_=packed_copy(model,packet,'q4')
        model.to('cuda').eval();compact_head(model,allowed());audit(model,tokenizer,label,packet);del model


if __name__=='__main__':main()
