"""Matched full-ISA, language, and oracle-free tool evaluation in 1024 tokens."""
import collections
import json

import torch

from ha_common import ROOT,read,write
from ha_protocol import prompt,constants,parse_call,assemble,encode
from ha_runtime import Session
from full_isa_common import HexProtocol
from full_isa_vm import FullVM,check_task
from codec_eval import generate_batch


def generate(model,tokenizer,prompts):
    encoded=[tokenizer.encode(x,add_special_tokens=False)for x in prompts]
    available=1024-max(map(len,encoded))
    if available<=0:raise ValueError('Context overflow; condition is never truncated')
    return generate_batch(model,tokenizer,prompts,HexProtocol(),max_new=min(512,available))


def evaluate(model,tokenizer,tasks,arm):
    vm=FullVM();rows=[]
    for at in range(0,len(tasks),16):
        batch=tasks[at:at+16];prompts=[prompt(t,arm)for t in batch]
        replies=generate(model,tokenizer,prompts)
        for task,text,row in zip(batch,prompts,replies):
            pool=task.get('constants')or constants(task['task'])
            try:
                kind,body=parse_call(row['reply']);assert kind=='write'
                code=assemble(body,pool,arm);passed=check_task(vm,code,task)['pass'];valid=True
            except (ValueError,RuntimeError,ArithmeticError,AssertionError):body=None;code=None;passed=False;valid=False
            rows.append({'id':task['id'],'group':task['group'],'kind':task['kind'],'angle':task['angle'],
              'opcode':task.get('opcode'),'catalog_risk':task.get('catalog_risk'),'source_kind':task.get('source_kind'),
              'pass':bool(passed),'valid_call':valid,'body':body,'code':code,'exact_reference':code==task['reference_code'],
              'prompt':text,**row})
    def stat(values):return {'passed':sum(x['pass']for x in values),'total':len(values),
      'rate':sum(x['pass']for x in values)/len(values)if values else None,'exact':sum(x['exact_reference']for x in values)}
    groups=collections.defaultdict(list);opcodes=collections.defaultdict(list);kinds=collections.defaultdict(list)
    for row in rows:
        groups[row['group']].append(row);kinds[row['kind']].append(row)
        if row['opcode']is not None:opcodes[f'{row["opcode"]:02X}'].append(row)
    documented=[r for r in rows if r['kind']=='primitive'and r['catalog_risk']=='documented']
    return {**stat(rows),'valid_calls':sum(r['valid_call']for r in rows),'by_group':{k:stat(v)for k,v in groups.items()},
      'by_kind':{k:stat(v)for k,v in kinds.items()},'by_opcode':{k:stat(v)for k,v in opcodes.items()},
      'documented':stat(documented)if documented else None,'details':rows}


def tool_panel(model,tokenizer,tasks,seeds,arm,max_turns=4):
    vm=FullVM();lookup={t['id']:t for t in tasks};rows=[]
    for item in seeds:
        task=lookup[item['task_id']];pool=task.get('constants')or constants(task['task'])
        session=Session(task,arm,encode(item['initial_code'],pool,arm),vm);session.run(0)
        for turn in range(max_turns):
            request=session.request()
            try:reply=generate(model,tokenizer,[request])[0]
            except ValueError:
                session.history.append({'kind':'context_overflow'});break
            session.apply(reply['reply']);session.history[-1].update(prompt=request,generated_token_ids=reply['generated_token_ids'])
            if session.finished:break
        try:code=assemble(session.body,pool,arm);passed=check_task(vm,code,task)['pass']
        except (ValueError,RuntimeError,ArithmeticError):code=None;passed=False
        rows.append({'id':task['id'],'initially_correct':item['intentionally_correct'],'pass':bool(passed and session.finished),'program_correct':bool(passed),
          'finished':session.finished,'code':code,'history':session.history})
    wrong=[r for r in rows if not r['initially_correct']]
    return {'passed':sum(r['pass']for r in rows),'total':len(rows),'initially_wrong':len(wrong),
      'repaired':sum(r['pass']for r in wrong),'false_accepts':sum(not r['pass']and r['finished']for r in wrong),
      'trace_requests':sum(h.get('kind')=='trace'for r in rows for h in r['history']),
      'patch_requests':sum(h.get('kind')=='patch'for r in rows for h in r['history']),
      'run_requests':sum(h.get('kind')=='run'for r in rows for h in r['history']),
      'observations_have_expected_outputs':False,'hidden_cases_available_to_model':False,'details':rows}


def development(model,tokenizer,arm):
    return {'arm':arm,'language':evaluate(model,tokenizer,read(ROOT/'development.jsonl'),arm),
      'isa':evaluate(model,tokenizer,read(ROOT/'isa-development.jsonl'),arm),
      'legacy':evaluate(model,tokenizer,read(ROOT/'legacy-development.jsonl'),arm),
      'tools':tool_panel(model,tokenizer,read(ROOT/'validation.jsonl'),read(ROOT/'validation-tool-seeds.jsonl'),arm)}


def selection(result):
    groups=result['language']['by_group'];doc=result['isa']['documented']['rate']
    literal=groups['literal_copy']['rate'];function=groups['literal_function']['rate'];composition=groups['composition']['rate']
    macro=sum(v['rate']for v in groups.values())/len(groups)
    tool=result['tools'];repair=tool['repaired']/tool['initially_wrong']if tool['initially_wrong']else 0
    legacy=result['legacy']['rate']
    # Coverage is a release condition; score still exposes promising incomplete candidates.
    score=.35*macro+.2*((literal+function)/2)+.2*composition+.15*repair+.1*legacy
    retention=True
    path=ROOT/'retention-floors.json'
    if path.exists():
        floors=json.loads(path.read_text());kinds=result['isa']['by_kind']
        retention=legacy>=floors['legacy']and kinds['numeric_synthesis']['rate']>=floors['scientific']and kinds['programming']['rate']>=floors['programming']
    return [doc==1. and retention,score,macro,literal,function,composition,repair,legacy]


def brief(result):
    return {'key':selection(result),'language':{k:v for k,v in result['language'].items()if k!='details'},
      'isa':{k:v for k,v in result['isa'].items()if k not in ['details','by_opcode']},
      'legacy':{k:result['legacy'][k]for k in ['passed','total','rate']},
      'tools':{k:v for k,v in result['tools'].items()if k!='details'}}


def audit(model,tokenizer,arm,label,packet):
    from ha_common import sha
    from codec_eval import language_nll
    language=evaluate(model,tokenizer,read(ROOT/'fresh.jsonl'),arm)
    isa=evaluate(model,tokenizer,read(ROOT/'isa-audit.jsonl'),arm)
    legacy=evaluate(model,tokenizer,read(ROOT/'legacy-development.jsonl'),arm)
    observed=evaluate(model,tokenizer,read(ROOT/'observed-previous-language.jsonl'),arm)
    user=evaluate(model,tokenizer,read(ROOT/'observed-user-reproductions.jsonl'),arm)
    tools=tool_panel(model,tokenizer,read(ROOT/'fresh.jsonl'),read(ROOT/'fresh-tool-seeds.jsonl'),arm)
    result={'label':label,'arm':arm,'packed_sha256':sha(packet),'language':language,'isa':isa,'legacy':legacy,
      'observed_previous_language':observed,'observed_user_reproductions':user,'tools':tools,'public_language':language_nll(model),
      'fresh_used_for_selection':False,'feedback_contains_expected_outputs':False,'physical_picocalc_measured':False}
    write(ROOT/'results'/(label+'.json'),result)
    print(json.dumps({'label':label,'language':[language['passed'],language['total']],'groups':language['by_group'],
      'doc':isa['documented'],'legacy':legacy['passed'],'tools':{k:v for k,v in tools.items()if k!='details'}}),flush=True)


def main():
    import argparse
    from transformers import AutoModelForCausalLM,AutoTokenizer
    from native_quant import attach,packed_copy
    from lowbit import load
    from ha_common import ARMS,INITIAL,INITIAL_PACKET,allowed,compact_head
    ap=argparse.ArgumentParser();ap.add_argument('--arm',choices=ARMS,required=True);a=ap.parse_args()
    assert(ROOT/'preselected.json').exists()
    torch.set_num_threads(4);torch.cuda.set_per_process_memory_fraction(.2)
    paths=[(a.arm+'-baseline',INITIAL,INITIAL_PACKET),(a.arm+'-best',ROOT/a.arm/'best',None),(a.arm+'-endpoint',ROOT/a.arm/'last',None)]
    for label,path,source in paths:
        if(ROOT/'results'/(label+'.json')).exists():continue
        model=AutoModelForCausalLM.from_pretrained(path,local_files_only=True,trust_remote_code=False)
        tokenizer=AutoTokenizer.from_pretrained(path,local_files_only=True,trust_remote_code=False)
        packet=ROOT/'results'/(label+'.mkqb');packet.parent.mkdir(exist_ok=True)
        if source:
            import shutil
            shutil.copyfile(source,packet);load(model,packet)
        else:attach(model,'q4');model,_=packed_copy(model,packet,'q4')
        model.to('cuda').eval();compact_head(model,allowed());audit(model,tokenizer,a.arm,label,packet);del model


if __name__=='__main__':main()
