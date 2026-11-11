"""Truth labels come from compiler/ROM, including matched wrong/correct states."""
import collections
import random
from ay_common import ROOT,rows,save_rows,write,sha
from ay_runtime import Session,snapshot,goal_state
from full_isa_vm import FullVM
from full_isa_protocol import linear_instructions
from ha_protocol import assemble,encode
from full_isa_math import literal
from ar_spec import verify


def mutant(goal,vm,kind='operation'):
    raw=assemble(goal['reference_body'],goal['pool'],'asm');candidates=[]
    changes={0x22:0x21,0x21:0x22,0x1C:0x1D,0x1D:0x1C,0x10:0x11,0x11:0x10,
             0x12:0x13,0x13:0x12,0x31:0x0B,0x0B:0x31,0x18:0x17,0x35:0x34}
    for item in linear_instructions(raw):
        at=item['pc'];op=item['opcode']
        if op in changes:candidates.append(('operation',raw[:at]+[changes[op]]+raw[at+1:]))
        if 0x60<=op<=0x6E:candidates.append(('argument',raw[:at]+[0x60+(op-0x60+1)%15]+raw[at+1:]))
        if at+1<len(raw)and 0x60<=op<=0x6E and 0x60<=raw[at+1]<=0x6E:
            candidates.append(('order',raw[:at]+[raw[at+1],op]+raw[at+2:]))
    candidates.sort(key=lambda x:x[0]!=kind)
    for label,code in candidates:
        body=encode(code,goal['pool'],'asm');check=verify(vm,body,goal['pool'],goal['spec'],goal['public_inputs']+goal['audit_inputs'])
        if check['status']=='FAIL':return label,body
    # Expressions such as 1**R7 are constant functions: changing their register
    # cannot introduce an observable error. An extra +10 before STOP is an
    # explicit operation bug and differs beyond tolerance throughout our range.
    extra=encode(raw[:-1]+literal(10)+[0x10,0x50],goal['pool'],'asm')
    if verify(vm,extra,goal['pool'],goal['spec'],goal['public_inputs']+goal['audit_inputs'])['status']=='FAIL':
        return 'operation',extra
    raise ValueError('NO_NONTRIVIAL_MUTATION')


def prepare():
    assert not(ROOT/'frozen.json').exists()
    if(ROOT/'lessons-frozen.json').exists():return
    teacher=__import__('json').loads((ROOT/'teacher-frozen.json').read_text())
    for n,d in teacher['files'].items():assert sha(ROOT/n)==d,n
    vm=FullVM();lessons=[];counts=collections.Counter();rng=random.Random(26110803)
    def add(goal,state,action,origin,correctness):
        # Gold spec and target body are separate from the neural state.
        assert not set(state['view'])&{'expected','hidden_tests','reference_code','spec'}
        row={'id':f'ay:lesson:{len(lessons):07}','group_id':goal['id'],'state':state,'action':action,'origin':origin,
             'correctness':correctness,'reference_body':goal['reference_body'],'spec_body':goal['spec_body'],
             'body':[]if action in ['write','done','unsure']else[1],
             'simple':__import__('ay_data').op_count(goal['spec']['X'])<=2}
        assert action!='done'or correctness==1
        lessons.append(row);counts[origin]+=1
    assert(ROOT/'data-clean.json').exists()
    for i,g in enumerate(rows(ROOT/'train-clean.jsonl')):
        add(g,goal_state(g),'write','goal',-1)
        label,bad=mutant(g,vm,['operation','argument','order'][i%3])
        for correct,body in [(True,g['reference_body']),(False,bad)]:
            s=Session(g,body,vm,'hex')
            add(g,snapshot(s),'done'if correct else'write','done'if correct else'repair',int(correct))
            # A real WRITE and one real RUN are identical histories for both truth classes.
            t=Session(g,g['reference_body'],vm,'hex');t.apply_action('write',body)
            add(g,snapshot(t),'run','run',int(correct))
            t.apply_action('run',[1])
            add(g,snapshot(t),'done'if correct else'write','done'if correct else'repair',int(correct))
            # Eleven actual previous actions: remaining=1, without truth-correlated counters.
            for _ in range(11):s.apply_action('run',[0])
            add(g,snapshot(s),'done'if correct else'unsure','done'if correct else'unsure',int(correct))
        if i%300==0:print({'lesson_goals':i,'rows':len(lessons)},flush=True)
    save_rows(ROOT/'lessons.jsonl',lessons)
    write(ROOT/'lessons-frozen.json',{'rows':len(lessons),'counts':dict(counts),'sha256':sha(ROOT/'lessons.jsonl'),
                                    'no_teacher_DONE_opinions':True,'all_state_counters_come_from_live_sessions':True})


if __name__=='__main__':prepare()
