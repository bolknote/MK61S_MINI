"""Paired diagnostic lessons and deterministic, oracle-free repair seeds."""
import hashlib
import random

from ha_protocol import constants,encode,write_call,patch_call,suffix_patch
from ha_runtime import Session
from full_isa_protocol import linear_instructions
from full_isa_vm import FullVM,check_task


def corrupt(task,vm=None,salt=0):
    vm=vm or FullVM();rng=random.Random(int(hashlib.sha256((task['id']+str(salt)).encode()).hexdigest()[:12],16))
    code=task['reference_code'];positions=list(range(len(code)-1));rng.shuffle(positions)
    for at in positions:
        old=code[at];candidates=list(range(10))if old<=9 else list(range(0x60,0x6F))if 0x60<=old<=0x6E else[0x10,0x11,0x12,0x13,0x0B,0x22,0x31,0x1C,0x1D,0x54]
        rng.shuffle(candidates)
        for new in candidates[:5]:
            if new==old:continue
            wrong=list(code);wrong[at]=new
            if not check_task(vm,wrong,task,public=True)['pass']:
                return wrong,{'position':at,'original':old,'replacement':new,'source':'deterministic_mutation'}
    wrong=[0x54,0x50]
    if check_task(vm,wrong,task,public=True)['pass']:wrong=[0x0D,0x50]
    assert not check_task(vm,wrong,task,public=True)['pass']
    return wrong,{'source':'empty_program_mutation'}


def seed(task,*,correct=False,vm=None,salt=0,wrong=None):
    pool=task.get('constants')or constants(task['task'])
    if correct:code=task['reference_code'];origin={'source':'correct_reference'}
    elif wrong is not None:code=wrong;origin={'source':'actual_pretrained_error'}
    else:code,origin=corrupt(task,vm,salt)
    return {'task_id':task['id'],'initial_code':code,'intentionally_correct':correct,'origin':origin}


def lessons(task,item,vm=None):
    pool=task.get('constants')or constants(task['task']);pairs=[]
    sessions={arm:Session(task,arm,encode(item['initial_code'],pool,arm),vm)for arm in ['direct','asm']}
    for arm,s in sessions.items():s.run(0)
    def add(kind,answers):
        pairs.append({'id':task['id']+':'+kind,'task_id':task['id'],'kind':kind,'pair':{
          arm:{'prompt':s.request(),'answer':answers[arm]}for arm,s in sessions.items()},
          'observation_has_expected_answer':False,'origin':item['origin']})
    if not item['intentionally_correct']:
        add('inspect',{arm:'<trace/>'for arm in sessions})
        for s in sessions.values():s.trace()
        targets={}
        for arm,s in sessions.items():
            wanted=encode(task['reference_code'],pool,arm)
            patch=suffix_patch(s.body,wanted);offset=patch[0]*256+patch[1]
            targets[arm]=patch_call(s.body,wanted)if offset>=4 else write_call(wanted)
        add('repair',targets)
        for arm,s in sessions.items():s.apply(targets[arm])
    # Correct code is checked on a second supplied input before DONE.
    if len(task['public_tests'])>1:
        add('verify',{arm:'<run>01</run>'for arm in sessions})
        for s in sessions.values():s.apply('<run>01</run>')
    add('done',{arm:'<done/>'for arm in sessions})
    return pairs

