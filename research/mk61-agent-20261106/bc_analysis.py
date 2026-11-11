"""Reconstruct every one of the19 false self-check DONE episodes."""
import collections
import copy
from decimal import Decimal
from bc_common import ROOT,PARENT,HERE,read,rows,write,save_rows,sha
from az_runtime import Session,snapshot
from ba_lessons import wrong_program
from ar_spec import verify,spec_text,equivalent
from ha_protocol import canonical
from full_isa_vm import FullVM

def normal(expr):
    if not isinstance(expr,list):return expr
    op=expr[0];children=[normal(c)for c in expr[1:]]
    if op=='reciprocal':return ['/',{'constant':'1'},children[0]]
    if op=='pow10':return ['pow',{'constant':'10'},children[0]]
    if op=='neg'and isinstance(children[0],dict)and'constant'in children[0]:return {'constant':canonical(-Decimal(children[0]['constant']))}
    return [op,*children]

def shape(expr):
    if isinstance(expr,dict):return '#'
    if isinstance(expr,str):return expr
    return [expr[0],*[shape(x)for x in expr[1:]]]

def desired(s,correct):
    missing=[i for i in [0,1]if i not in s.runs]
    if missing:return 'run',[missing[0]],'public_runs'
    if not s.eligibility()[0]:return ('write',[],'public_failure')if 12-len(s.history)>=3 else('unsure',[],'budget')
    if not correct:return ('write',[],'task_error')if 12-len(s.history)>=3 else('unsure',[],'budget')
    if isinstance(s.observation,str)and s.observation.startswith('DONE_REJECTED'):return 'unsure',[],'visible_check_conflict'
    return 'done',[],'correct_task_program'

def main():
    ROOT.mkdir(parents=True,exist_ok=True)
    goals={g['id']:g for g in rows(PARENT/'closed-clean.jsonl')};report=read(PARENT/'spec/closed.json')
    failures=[r for r in report['self']['records']if r['finished']and not r['program_correct']];assert len(failures)==19
    vm=FullVM();cases=[];states=[];counts=collections.Counter()
    for record in failures:
        g=goals[record['task_id']];hyp=record['declared_spec'];assert not equivalent(hyp,g['spec'],g['audit_inputs'])['tested_equal']
        a,b=shape(normal(g['spec']['X'])),shape(normal(hyp['X']))
        category='literal_or_sign'if a==b else'operation_or_composition'
        from full_isa_math import registers
        if registers(g['spec']['X'])!=registers(hyp['X']):category='register'
        counts[category]+=1
        body=g['reference_body']if record['initially_correct']else wrong_program(g,vm,record['initial'])[0]
        s=Session(g,body,vm,'spec',hyp,True);correct_rejections=0;corruptions=0;first=True
        for h in record['history']:
            generated=h['generation'];assert not generated.get('codec_error')
            assert s.request()==h['prompt'],record['id']
            correct=verify(vm,s.body,s.pool,g['spec'],g['audit_inputs'])['status']=='TESTED'
            action,target,reason=desired(s,correct)
            if first or h['kind']in ['write','done','done_rejected']or reason=='visible_check_conflict':
                states.append({'episode_id':record['id'],'task_id':g['id'],'goal':g,'declared_spec':hyp,'state':snapshot(s),
                    'target_action':action,'target_body':target,'reason':reason,'program_correct':correct,'old_generation':generated})
            s.apply_action(generated['action'],generated['body'])
            assert s.history[-1]['kind']==h['kind']
            now=verify(vm,s.body,s.pool,g['spec'],g['audit_inputs'])['status']=='TESTED'
            if correct and not now:corruptions+=1
            if h['kind']=='done_rejected'and correct:correct_rejections+=1
            first=False
        assert s.finished and not verify(vm,s.body,s.pool,g['spec'],g['audit_inputs'])['status']=='TESTED'
        assert verify(vm,s.body,s.pool,hyp,g['audit_inputs'])['status']=='TESTED'
        cases.append({'episode_id':record['id'],'task_id':g['id'],'task':g['task'],'requested':g['spec'],'hypothesis':hyp,
            'category':category,'initially_correct':record['initially_correct'],'correct_code_rejections':correct_rejections,
            'correct_to_wrong_edits':corruptions,'all_prompts_reproduced':True})
    save_rows(ROOT/'retired19-states.jsonl',states);write(ROOT/'retired19-cases.json',cases)
    receipt={'episodes':19,'unique_conditions':len({r['task_id']for r in failures}),
       'initially_correct':sum(r['initially_correct']for r in failures),'all_final_codes_match_wrong_hypothesis':True,
       'with_any_gate_rejection':sum(any(h['kind']=='done_rejected'for h in r['history'])for r in failures),
       'with_correct_code_rejected':sum(r['correct_code_rejections']>0 for r in cases),'categories':dict(counts),
       'training_states':len(states),'files':{n:sha(ROOT/n)for n in ['retired19-states.jsonl','retired19-cases.json']}}
    write(ROOT/'analysis.json',receipt)
    lines=['# Разбор19 ложных DONE при самопроверке','',str(receipt),'',
       '| Условие | Требовалось | Гипотеза сети | Эпизодов | Отклонён правильный код |','|---|---|---|---:|---:|']
    for identifier in sorted({r['task_id']for r in cases}):
        group=[r for r in cases if r['task_id']==identifier];r=group[0]
        lines.append(f'| {r["task"]} | `{spec_text(r["requested"])}` | `{spec_text(r["hypothesis"])}` | {len(group)} | {sum(x["correct_code_rejections"]>0 for x in group)} |')
    lines += ['', 'Во всех19 эпизодах механическая проверка подтвердила неверную первоначальную гипотезу. '
       f'Отказ проверки был в {receipt["with_any_gate_rejection"]} эпизодах; в {receipt["with_correct_code_rejected"]} она отклоняла код, правильно решавший исходное условие. '
       'Протокол не даёт заменить первоначальную гипотезу отдельным действием: поэтому в таком конфликте правильный код нужно сохранить '
       'и завершить UNSURE, а не искажать его ради прохождения проверки. Это не считается успешным DONE.', '']
    (HERE/'SELF_CHECK_19_ANALYSIS.md').write_text('\n'.join(lines));print(receipt,flush=True)

if __name__=='__main__':main()
