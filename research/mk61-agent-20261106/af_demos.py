"""Post-selection real user failures and new underspecified Russian requests."""
import argparse
import json
from pathlib import Path
import torch
from transformers import AutoModelForCausalLM,AutoTokenizer
from af_common import ARMS,output_ids,compact_head,write
from af_eval import generate
from af_native import Engine
from af_teacher import correct
from ac_runtime import Session
from ha_protocol import encode,constants
from full_isa_vm import FullVM
from lowbit import load
from ab_demos import tasks as user_tasks


def run(task,wrong,tool,threshold,vm,compiler,repeat_writes=0):
    pool=task.get('constants')or constants(task['task']);s=Session(task,'asm',body=encode(wrong,pool,'asm')if wrong is not None else None,vm=vm,gate=threshold is not None)
    s.initial_history=0
    if wrong is not None:s.run(0)
    else:
        g=compiler(task)
        if g.get('action')=='write':s.apply_action('write',g['body']);s.history[-1]['profile']='compiler'
        else:return {'task':task['task'],'pass':False,'history':[g]}
    if repeat_writes:
        for _ in range(repeat_writes):
            s.apply_action('write',s.body)
            for j in range(1,len(task['public_tests'])):s.apply_action('run',[j])
    for _ in range(10-len(s.history)):
        g=tool(s.request())
        if g.get('codec_error'):s.history.append({'kind':'generation_error','generation':g});break
        if g['action']=='done'and threshold is not None and s.eligibility()[0]and g['correctness_margin']<threshold:
            s.observation='Оценка решения не подтвердила соответствие условию. Проверь операцию, аргумент и требования задачи; при неуверенности выбери UNSURE.'
            s.history.append({'kind':'semantic_DONE_rejected','generation':g,'observation':s.observation});continue
        s.apply_action(g['action'],g['body']);s.history[-1]['generation']=g
        if s.finished or s.abstained:break
    ok=correct(vm,task,s.body,s.pool)
    return {'task':task['task'],'angle':task['angle'],'initial_wrong_code':wrong,'program_correct':ok,'finished':s.finished,
        'abstained':s.abstained,'pass':ok and s.finished and s.eligibility()[0],'body':s.body,'history':s.history}


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--root',type=Path,required=True);a=ap.parse_args();root=a.root.resolve();torch.set_num_threads(4)
    tokenizer=AutoTokenizer.from_pretrained(root/'export/compiler/hf',local_files_only=True)
    compiler=AutoModelForCausalLM.from_pretrained(root/'export/compiler/hf',local_files_only=True);load(compiler,root/'export/compiler/model.mkqb');compiler.eval()
    compact_head(compiler,json.loads((root/'export/compiler/output-token-ids.json').read_text()))
    from hf_eval import generate as compile_generate
    from hf_runtime import prompt
    from ha_protocol import parse_call
    def compile_task(t):
        g=compile_generate(compiler,tokenizer,[prompt(t)])[0]
        try:a,b=parse_call(g['reply'])
        except ValueError:a=None;b=[]
        return {**g,'action':a,'body':b}
    vm=FullVM();items=user_tasks(vm);results={};pre=json.loads((root/'preselected.json').read_text())
    for arm in [*ARMS,'native-selected']:
        selected=pre['selected_arm']if arm=='native-selected'else arm;threshold=pre['choices'][selected]['threshold']
        if arm=='native-selected':engine=Engine(root,selected);tool=engine.generate
        else:
            folder=root/'export'/arm;model=AutoModelForCausalLM.from_pretrained(folder/'hf',local_files_only=True);load(model,folder/'model.mkqb');model.eval();compact_head(model,output_ids(tokenizer))
            tool=lambda text:generate(model,tokenizer,[text])[0]
        value={}
        for mode,cut in [('raw',None),('calibrated',threshold)]:value[mode]=[run(t,w,tool,cut,vm,compile_task)for t,w in items]
        value['already_correct']=[{**run(t,t['reference_code'],tool,None,vm,compile_task,repeat_writes=n),'prefilled_repeated_writes':n}
            for t,w in items for n in [0,1]]
        unknown=[]
        for i,text in enumerate(['Условие расчёта ещё не готово. Нужна программа для МК-61.',
            'Придумай код для значения X. Какой результат нужен, я пока не сказал.',
            'Аргумент лежит в R3, но функцию уточню в следующем сообщении.',
            'Нужно вычисление. Исходное выражение я забыл приложить.',
            'Программа должна обработать X. Способ обработки пока неизвестен.',
            'Хочу получить результат на калькуляторе. Условий пока нет.',
            'Для числа 37 нужна функция, но её название я не указал.',
            'Составь программу по моему заданию. Само задание ещё не прислал.']):
            task={'id':'new-unknown:'+str(i),'task':text,'angle':'RAD','public_tests':[{'segments':[{'inputs':{'X':'3'}}]}]}
            s=Session(task,'asm',vm=vm,gate=False);g=tool(s.request());unknown.append({'task':text,'correct_UNSURE':g.get('action')=='unsure','generation':g})
        value['unknown']=unknown;value['unknown_correct']=sum(r['correct_UNSURE']for r in unknown);results[arm]=value
        write(root/'user-reproductions.json',results)
        print(json.dumps({'arm':arm,'raw':sum(r['pass']for r in value['raw']),'calibrated':sum(r['pass']for r in value['calibrated']),'unknown':value['unknown_correct']}),flush=True)


if __name__=='__main__':main()
