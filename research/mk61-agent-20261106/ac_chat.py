"""Public-only two-profile runner and post-selection user reproductions."""
import argparse
import json
from pathlib import Path
from ac_runtime import Session
from ha_protocol import constants,encode,parse_call,assemble
from hf_runtime import prompt as compiler_prompt


def rollout(task,tool,compiler,*,wrong=None,vm=None,gate=False,turns=10):
    body=encode(wrong,task.get('constants')or constants(task['task']),'asm')if wrong is not None else None
    s=Session(task,'asm',body=body,vm=vm,gate=gate,max_turns=turns);s.initial_history=0
    if wrong is not None:s.run(0);s.initial_history=len(s.history)
    else:
        row=compiler(compiler_prompt(task))
        if row.get('codec_error'):s.history.append({'kind':'compiler_error','generation':row});return s
        if row.get('action')!='write':s.history.append({'kind':'compiler_error','generation':row});return s
        s.apply_action('write',row['body']);s.history[-1]['generation']=row
    for _ in range(turns-(len(s.history)-s.initial_history)):
        row=tool(s.request())
        if row.get('codec_error'):s.history.append({'kind':'generation_error','generation':row});break
        s.apply_action(row['action'],row['body']);s.history[-1]['generation']=row
        if s.finished or s.abstained:break
    return s


def demos(root):
    import torch
    from transformers import AutoTokenizer,AutoModelForCausalLM
    from lowbit import load
    from ac_common import ARMS,output_ids,compact_head,write
    from ac_eval import generate
    from ac_teacher import grade
    from ac_native import Engine
    from full_isa_vm import FullVM
    from full_isa_prepare import make_task
    from full_isa_math import literal
    from ab_demos import tasks
    torch.set_num_threads(4);vm=FullVM();items=tasks(vm)
    for name,n,op,bad in [('sin37','37',0x1C,0x1D),('cos41','41',0x1D,0x1C)]:
        t=make_task(vm,literal(n)+[op,0x50],f'Рассчитай {"синус"if op==0x1C else"косинус"} числа {n}.',
            'demo:'+name,'user_reproduction','demo','DEG',[{'X':str(x)}for x in [-2,0,1,3,9,27]],kind='ha_task',check_names=['X'])
        bank=t['public_tests']+t['hidden_tests'];t['public_tests'],t['hidden_tests']=bank[:2],bank[2:]
        items.append((t,literal(n)+[bad,0x50]))
    tokenizer=AutoTokenizer.from_pretrained(root/'export/compiler/hf',local_files_only=True)
    compiler=AutoModelForCausalLM.from_pretrained(root/'export/compiler/hf',local_files_only=True);load(compiler,root/'export/compiler/model.mkqb');compiler.eval()
    compact_head(compiler,json.loads((root/'export/compiler/output-token-ids.json').read_text()))
    from hf_eval import generate as old_generate
    def initial(text):
        row=old_generate(compiler,tokenizer,[text])[0]
        try:action,body=parse_call(row['reply'])
        except ValueError:action=None;body=[]
        return {**row,'action':action,'body':body}
    results={};selected=json.loads((root/'preselected.json').read_text())['selected_arm']
    for arm in [*ARMS,'native-selected']:
        if arm=='native-selected':engine=Engine(root,selected);tool=engine.generate;first=engine.compile
        else:
            model=AutoModelForCausalLM.from_pretrained(root/'export'/arm/'hf',local_files_only=True);load(model,root/'export'/arm/'model.mkqb');model.eval();compact_head(model,output_ids(tokenizer))
            tool=lambda p:generate(model,tokenizer,[p])[0];first=initial
        rows=[]
        for task,wrong in items:
            s=rollout(task,tool,first,wrong=wrong,vm=vm);correct=grade(s);eligible=s.eligibility()[0]
            rows.append({'task':task['task'],'angle':task['angle'],'initial_wrong_code':wrong,'program_correct':correct,
                 'model_declared_done':s.finished,'model_abstained':s.abstained,'pass':correct and s.finished and eligible,
                 'body':s.body,'history':s.history})
        unknown=[]
        for text in ['Реши задачу на МК-61. Само условие пришлю позже.','Вычисли значение функции при X=3; формулу я не сообщил.',
                     'Нужно обработать число из R2. Требуемую операцию пока не выбрали.','Нужна программа, но исходных данных ещё нет.']:
            task={'id':'unknown','task':text,'angle':'RAD','public_tests':[{'segments':[{'inputs':{'X':'3'}}]}]}
            s=Session(task,'asm',vm=vm,gate=False);g=tool(s.request());unknown.append({'task':text,'pass':g.get('action')=='unsure','generation':g})
        results[arm]={'reproductions':rows,'unknown':unknown,'unknown_passed':sum(r['pass']for r in unknown)}
        write(root/'user-reproductions.json',results);print(json.dumps({'arm':arm,'reproductions':sum(r['pass']for r in rows),'unknown':results[arm]['unknown_passed']}),flush=True)


def main():
    ap=argparse.ArgumentParser();ap.add_argument('question',nargs='?');ap.add_argument('--root',type=Path,required=True)
    ap.add_argument('--arm',default='selected-research');ap.add_argument('--angle',choices=['RAD','DEG','GRAD']);ap.add_argument('--inputs',default='{}')
    ap.add_argument('--tests');ap.add_argument('--initial-hex');ap.add_argument('--demos',action='store_true');a=ap.parse_args();root=a.root.resolve()
    if a.demos:demos(root);return
    if not a.question or not a.angle:ap.error('question and --angle are required')
    from ac_native import Engine
    engine=Engine(root,a.arm);bank=json.loads(a.tests)if a.tests else[json.loads(a.inputs)]
    task={'id':'interactive','task':a.question,'angle':a.angle,'constants':constants(a.question),
          'public_tests':[{'segments':[{'inputs':x}]}for x in bank],'max_commands':128,'max_frames':1024}
    wrong=list(bytes.fromhex(a.initial_hex))if a.initial_hex else None
    s=rollout(task,engine.generate,engine.compile,wrong=wrong,gate=True)
    for row in s.history:print(json.dumps(row,ensure_ascii=False),flush=True)
    try:code=assemble(s.body,s.pool,'asm')if s.body else None
    except ValueError:code=None
    print(json.dumps({'model_declared_done':s.finished,'model_abstained':s.abstained,'verified_task_success':None,
         'independent_verification_available':False,'body':s.body,'expanded_program':code},ensure_ascii=False))


if __name__=='__main__':main()
