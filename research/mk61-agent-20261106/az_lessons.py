"""Verified complete repair rollouts with both RUN indices and remaining=1."""
import collections
import copy
import random
from az_common import ROOT,rows,read,write,save_rows,sha
from az_runtime import Session,snapshot,goal_state
from ay_codec import compile_spec
from ay_data import op_count
from ay_lessons import mutant as fallback_mutant
from ar_spec import verify
from full_isa_vm import FullVM
from ha_protocol import assemble


def mutant(goal,vm,kind='operation'):
    source=goal['spec'];expr=source['X'];candidates=[]
    def changed(node,path):
        if isinstance(node,dict)and'constant'in node:
            old=node['constant']
            for value in goal['pool']:
                if value!=old:candidates.append(('argument',path,{'constant':value}))
        if isinstance(node,str):
            candidates.append(('argument',path,'R'+format((int(node[1:],16)+1)%15,'X')))
        if isinstance(node,list):
            replacements={'sin':'cos','cos':'sin','square':'sqrt','sqrt':'square','+':'-','-':'+','*':'/','/':'*','ln':'log10','frac':'int','abs':'neg'}
            if node[0]in replacements:candidates.append(('operation',path,[replacements[node[0]],*copy.deepcopy(node[1:])]))
            if node[0]in ['-','/','pow']:candidates.append(('order',path,[node[0],copy.deepcopy(node[2]),copy.deepcopy(node[1])]))
            for i,child in enumerate(node[1:],1):changed(child,path+[i])
    changed(expr,[]);candidates.sort(key=lambda x:x[0]!=kind)
    for label,path,replacement in candidates:
        new=copy.deepcopy(expr)
        if not path:new=replacement
        else:
            at=new
            for index in path[:-1]:at=at[index]
            at[path[-1]]=replacement
        spec={**source,'X':new,'writes':{r:new for r in source['writes']}}
        try:body=compile_spec(spec,goal['pool'])
        except (ValueError,ArithmeticError):continue
        if verify(vm,body,goal['pool'],source,goal['public_inputs']+goal['audit_inputs'])['status']=='FAIL':return label,body
    return fallback_mutant(goal,vm,kind)


def main():
    assert not(ROOT/'frozen.json').exists()
    if(ROOT/'lessons-frozen.json').exists():return
    teacher=read(ROOT/'teacher-frozen.json')
    for n,d in teacher['files'].items():assert sha(ROOT/n)==d,n
    vm=FullVM();output=[];counts=collections.Counter();run_counts=collections.Counter();positive_checked=0;certified=set()
    def add(g,s,action,origin,correct,body=None):
        nonlocal positive_checked
        state=goal_state(g)if s is None else snapshot(s)
        if action=='done':
            assert s is not None and s.eligibility()[0]
            key=(g['id'],tuple(assemble(s.body,s.pool,'asm')),g['spec']['angle'])
            if key not in certified:
                assert verify(vm,s.body,s.pool,g['spec'],g['audit_inputs'])['status']=='TESTED';certified.add(key)
            positive_checked+=1
        row={'id':f'az:lesson:{len(output):07}','group_id':g['id'],'state':state,'action':action,'origin':origin,
             'correctness':correct,'body':list(body or[]),'reference_body':g['reference_body'],'spec_body':g['spec_body'],
             'simple':op_count(g['spec']['X'])<=2,'family':g['family'],'curriculum':g.get('curriculum','new')}
        if action=='run':assert body in [[0],[1]];run_counts[str(body[0])]+=1
        assert not set(state['view'])&{'expected','reference_code','spec','hidden_tests'}
        output.append(row);counts[origin]+=1
    for i,g in enumerate(rows(ROOT/'train-clean.jsonl')):
        add(g,None,'write','goal',-1)
        label,bad=mutant(g,vm,['operation','argument','order'][i%3])
        for case in [0,1]:
            good=Session(g,g['reference_body'],vm,'hex',start_case=case)
            add(g,good,'done','done',1)
            # Complete initial repair: WRITE -> the missing RUN -> DONE.
            s=Session(g,bad,vm,'hex',start_case=case)
            add(g,s,'write','repair',0);s.apply_action('write',g['reference_body'])
            add(g,s,'run','run',1,[1-case]);s.apply_action('run',[1-case]);add(g,s,'done','done',1)
            # Failed prior edit, then a second edit while the other case is active.
            t=Session(g,g['reference_body'],vm,'hex',start_case=case);t.apply_action('write',bad)
            add(g,t,'run','run',0,[1-case]);t.apply_action('run',[1-case]);add(g,t,'write','repair',0)
            t.apply_action('write',g['reference_body']);add(g,t,'run','run',1,[case]);t.apply_action('run',[case])
            add(g,t,'done','done',1)
        for correct,body in [(True,g['reference_body']),(False,bad)]:
            s=Session(g,body,vm,'hex')
            for _ in range(11):s.apply_action('run',[s.case])
            add(g,s,'done'if correct else'unsure','done'if correct else'unsure',int(correct))
        if i%250==0:print({'goals':i,'lessons':len(output),'RUN':dict(run_counts)},flush=True)
    assert run_counts['0']==run_counts['1']>0
    save_rows(ROOT/'lessons.jsonl',output)
    write(ROOT/'lessons-frozen.json',{'rows':len(output),'counts':dict(counts),'RUN_counts':dict(run_counts),
      'positive_DONE_states_ROM_certified':positive_checked,'distinct_certified_programs':len(certified),'sha256':sha(ROOT/'lessons.jsonl'),
      'all_counters_and_cases_from_real_sessions':True,'complete_repair_and_repair_again_cycles':True,
      'LLM_DONE_opinions_not_used_as_truth':True})
    print({'lessons_complete':len(output),'RUN':dict(run_counts)},flush=True)


if __name__=='__main__':main()
