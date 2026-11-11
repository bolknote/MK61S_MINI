"""Optional table-order middleware: no task answer or model-weight access."""
import copy
from decimal import Decimal
from az_teacher import pool_for
from ba_pools import remap
from ay_codec import decode,encode
from ha_protocol import canonical


def canonical_pool(task,available):
    available=[canonical(v)for v in available]
    if len(set(available))!=len(available):raise ValueError('Unique constant values required')
    result=[v for v in pool_for(task)if v in available]
    result+=sorted(set(available)-set(result),key=Decimal)
    assert len(result)==len(available)and set(result)==set(available)
    return result


def constant_parameters(body):
    at=0;out=set()
    while at<len(body or[]):
        op=body[at];at+=1
        if op!=255:continue
        tag=body[at];at+=1
        if tag==0:continue
        if tag==1:out.add(at)
        at+=1
    return out


def remap_diag(body,current,old,new):
    result=list(body)
    if len(result)!=5:return result
    index=result[1]*256+result[2]
    if index in constant_parameters(current):
        for i in [3,4]:
            if result[i]<len(old):result[i]=new.index(old[result[i]])
    return result


def request_state(state):
    result=copy.deepcopy(state);old=state['pool'];new=canonical_pool(state['view']['task'],old)
    result['body']=remap(state['body'],old,new);result['pool']=new;result['view']['constants']=list(new)
    if result.get('diagnosis'):
        result['diagnosis']['body']=remap_diag(result['diagnosis']['body'],state['body'],old,new)
    return result


def response_body(action,body,state):
    old=state['pool'];new=canonical_pool(state['view']['task'],old)
    if action=='write':return encode(decode(body,new,state['view']['angle']),old)
    if action=='diag':return remap_diag(body,remap(state['body'],old,new),new,old)
    return list(body)
