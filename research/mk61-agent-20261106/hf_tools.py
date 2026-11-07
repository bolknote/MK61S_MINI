"""Counterfactual wrong/correct states and executable suffix-patch lessons."""
import hashlib

from ha_protocol import constants,encode,assemble,write_call,patch_call
from ha_tools import corrupt
from hf_runtime import Session
from full_isa_vm import check_task


def seed(task,vm,index,*,wrong=None,correct=False,origin=None):
    if correct:code=task['reference_code'];source={'source':'correct_control'}
    elif wrong is not None:code=wrong;source={'source':'actual_student_error',**(origin or{})}
    else:code,source=corrupt(task,vm,salt=6120700+index)
    actual=check_task(vm,code,task)['pass']
    if correct:assert actual
    else:assert not actual
    return {'task_id':task['id'],'initial_code':code,'intentionally_correct':bool(actual),'origin':source,
            'pre_run_all':bool(index%3==0),'inspect_first':bool(index%4!=0)}


def lessons(task,item,vm):
    pool=task.get('constants')or constants(task['task'])
    session=Session(task,'asm',body=encode(item['initial_code'],pool,'asm'),vm=vm);session.run(0)
    if item['pre_run_all']:
        for i in range(1,len(task['public_tests'])):session.run(i)
    out=[]
    def add(kind,answer,suffix=''):
        request=session.request();out.append({'id':task['id']+':'+kind+suffix,'task_id':task['id'],'kind':kind,
           'pair':{'asm':{'prompt':request,'answer':answer}},'origin':item['origin'],
           'intentionally_correct':item['intentionally_correct'],'observation_has_expected_answer':False})
    if item['inspect_first']:
        add('inspect','<trace/>');session.apply('<trace/>')
    if not item['intentionally_correct']:
        target=encode(task['reference_code'],pool,'asm')
        # Learn PATCH even when the first changed byte is at offset zero.
        answer=patch_call(session.body,target)
        if int(hashlib.sha256(task['id'].encode()).hexdigest()[:4],16)%5==0:answer=write_call(target)
        add('repair',answer);assert session.apply(answer)in ['patch','write']
        assert check_task(vm,assemble(session.body,pool,'asm'),task)['pass']
    missing=[i for i in range(len(task['public_tests']))if i not in session.runs]
    for i in missing:
        add('verify',f'<run>{i:02X}</run>',f':{i}');session.apply(f'<run>{i:02X}</run>')
    assert session.eligibility()[0]
    add('done','<done/>')
    # Correct code after TRACE is still ready for DONE; do not teach an endless trace loop.
    session.apply('<trace/>');add('done','<done/>',':after-trace')
    return out
