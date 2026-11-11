"""Same ROM expert, with explicit metadata for the few erroneous payload tokens."""
import difflib
import re
from af_teacher import correct,make_session,expert
from ag_common import MAX_TURNS
from ha_protocol import bytes_text


def changed_indexes(old,new):
    important=[]
    for tag,a,b,c,d in difflib.SequenceMatcher(a=old,b=new,autojunk=False).get_opcodes():
        if tag!='equal':important.extend(range(max(0,c-1),min(len(new),max(c+1,d))))
    return sorted(set(important))


def row(s,t,origin,**extra):
    action,body=expert(s,t);r={'task_id':t['id'],'prompt':s.request(),'action':action,'body':body,
      'correctness':int(correct(s.vm,t,s.body,s.pool)),'level':t.get('level',1),'group':t.get('group'),
      'origin':origin,'eligible_for_DONE':s.eligibility()[0],'runtime_has_expected':False,**extra}
    if action=='write'and s.body:
        # Payload offsets only label the loss; they never enter the prompt.
        r['changed_byte_indexes']=changed_indexes(bytes_text(s.body).split(),bytes_text(body).split())
    return r


def follow(s,t,origin='generalized_error',**extra):
    values=[]
    for _ in range(MAX_TURNS):
        r=row(s,t,origin,**extra);values.append(r);kind=s.apply_action(r['action'],r['body'])
        if kind in ['done','unsure']:break
    return values

