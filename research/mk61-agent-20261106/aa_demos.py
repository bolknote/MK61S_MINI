"""Post-selection reproductions of the user's failures and underspecified requests."""
import argparse
import json
from pathlib import Path
import torch
from transformers import AutoModelForCausalLM,AutoTokenizer
from aa_common import INITIAL,INITIAL_PACKET,SOURCE,compact_head,output_ids,write
from aa_eval import generate
from aa_runtime import Session
from aa_teacher import grade
from ha_protocol import constants,encode,assemble
from hf_runtime import Session as OldSession
from hf_eval import generate as old_generate
from full_isa_prepare import make_task
from full_isa_math import literal
from full_isa_vm import FullVM,check_task
from lowbit import load


def tasks(vm):
    result=[]
    for name,text,code,wrong,angle,n in [
      ('sin22','Подсчитай синус 22.',literal('22')+[0x1C,0x50],literal('22')+[0x1D,0x50],'DEG',1),
      ('zero','Выдай в X число 0.',literal('0')+[0x50],literal('1')+[0x50],'RAD',1),
      ('square_x','Вычисли квадрат текущего X.',[0x22,0x50],[0x22,0x22,0x50],'RAD',4),
      ('x_plus_one_squared','Вычисли (X+1)*(X+1).',literal('1')+[0x10,0x22,0x50],None,'RAD',2)]:
        inputs=[{'X':str(x)}for x in [-3,2.5,-1,0,1,7]]
        t=make_task(vm,code,text,'demo:'+name,'user_reproduction','demo',angle,inputs,kind='ha_task',check_names=['X'])
        cases=t['public_tests']+t['hidden_tests'];t['public_tests'],t['hidden_tests']=cases[:n],cases[n:]
        result.append((t,wrong))
    return result


def run_new(generator,task,wrong,vm):
    s=Session(task,'asm',body=encode(wrong,constants(task['task']),'asm')if wrong else None,vm=vm,gate=False)
    if wrong:s.run(0)
    for _ in range(10):
        row=generator(s.request())
        if row['codec_error']:s.history.append({'kind':'error','generation':row});break
        s.apply_action(row['action'],row['body'])
        if s.finished or s.abstained:break
    correct=grade(s);eligible=s.eligibility()[0]
    return {'task':task['task'],'public_cases':len(task['public_tests']),'initial_wrong_code':wrong,
            'program_correct':correct,'model_declared_done':s.finished,'model_abstained':s.abstained,
            'pass':correct and s.finished and eligible,'body':s.body,'history':s.history}


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--root',type=Path,required=True);a=ap.parse_args();root=a.root.resolve()
    torch.set_num_threads(4);vm=FullVM();items=tasks(vm);results={}
    for arm in ['sft','preference']:
        folder=root/'export'/arm
        model=AutoModelForCausalLM.from_pretrained(folder/'hf',local_files_only=True);load(model,folder/'model.mkqb');model.eval()
        tokenizer=AutoTokenizer.from_pretrained(folder/'hf',local_files_only=True);compact_head(model,output_ids(tokenizer))
        rows=[run_new(lambda p:generate(model,tokenizer,[p])[0],t,wrong,vm)for t,wrong in items]
        unknown=[]
        for text in ['Сделай расчёт по формуле, которую я ещё не сообщил.',
                     'Нужна обработка числа из X, но требуемую функцию пока не выбрали.',
                     'Реши мою задачу на МК-61. Условия пришлю следующим сообщением.',
                     'Найди результат для R2; само выражение пока отсутствует.',
                     'Вычисли значение функции при X=3. Какая функция, я забыл написать.',
                     'Нужно составить программу расчёта. Исходных данных и формулы ещё нет.',
                     'Рассчитай сумму. Какие числа складывать, пока не сказано.',
                     'Вычисли синус числа. Сам аргумент не задан.']:
            t={'id':'unknown','task':text,'angle':'RAD','public_tests':[{'segments':[{'inputs':{'X':'3'}}]}]}
            s=Session(t,'asm',vm=vm,gate=False);g=generate(model,tokenizer,[s.request()])[0]
            unknown.append({'task':text,'pass':g['action']=='unsure','generation':g})
        results[arm]={'reproductions':rows,'unknown':unknown,'unknown_passed':sum(r['pass']for r in unknown)}
        write(root/'user-reproductions.json',results)
    selected=json.loads((root/'preselected.json').read_text())['selected_arm']
    from aa_native import Native
    engine=Native(root/'export'/selected)
    results['native-selected']={'arm':selected,'reproductions':[run_new(engine.generate,t,w,vm)for t,w in items]}
    tokenizer=AutoTokenizer.from_pretrained(INITIAL,local_files_only=True)
    model=AutoModelForCausalLM.from_pretrained(INITIAL,local_files_only=True);load(model,INITIAL_PACKET);model.eval()
    compact_head(model,json.loads((SOURCE/'output-token-ids.json').read_text()));old=[]
    for t,wrong in items:
        s=OldSession(t,'asm',body=encode(wrong,constants(t['task']),'asm')if wrong else None,vm=vm,gate=False)
        if wrong:s.run(0)
        for _ in range(10):
            g=old_generate(model,tokenizer,[s.request()])[0]
            if g['codec_error']:break
            s.apply(g['reply'])
            if s.finished:break
        try:correct=bool(s.body and check_task(vm,assemble(s.body,s.pool,'asm'),t)['pass'])
        except (ValueError,ArithmeticError,RuntimeError):correct=False
        old.append({'task':t['task'],'program_correct':correct,'model_declared_done':s.finished,
                    'pass':correct and s.finished and s.eligibility()[0],'history':s.history})
    results['old-v3']={'reproductions':old};write(root/'user-reproductions.json',results)
    print(json.dumps({arm:{'reproductions':sum(r['pass']for r in result['reproductions']),
                           'unknown_passed':result.get('unknown_passed')}for arm,result in results.items()}),flush=True)


if __name__=='__main__':main()
