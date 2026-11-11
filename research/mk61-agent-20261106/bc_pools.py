"""Counterfactual table views, preserving exact calculator program bytes."""
import copy
import hashlib
import random
from decimal import Decimal
from az_teacher import pool_for
from ay_codec import encode as encode_spec,compile_spec
from ha_protocol import assemble,canonical


def rng_for(identity):return random.Random(int(hashlib.sha256(identity.encode()).hexdigest()[:16],16))


def layout(pool,identity,mode):
    pool=list(pool);rng=rng_for(identity)
    if mode=='default':return pool
    if mode=='distractors':
        for value in ['6.25','14.5','3.5','-7.5']:
            if value not in pool:pool.append(value)
    if mode=='extras':
        base=pool_for('');assert pool[:len(base)]==base
        tail=pool[len(base):];rng.shuffle(tail);return base+tail
    assert mode in ['full','distractors'];rng.shuffle(pool);return pool


def remap(body,old,new):
    if body is None:return None
    result=list(body);at=0
    while at<len(result):
        op=result[at];at+=1
        if op!=255:continue
        tag=result[at];at+=1
        if tag==0:continue
        assert tag in [1,2,3]
        if tag==1:result[at]=new.index(canonical(old[result[at]]))
        at+=1
    assert assemble(body,old,'asm')==assemble(result,new,'asm')
    return result


def goal_layout(goal,mode,identity=None):
    g=copy.deepcopy(goal);g['pool']=layout(goal['pool'],identity or goal['id']+':'+mode,mode)
    g['reference_body']=compile_spec(g['spec'],g['pool']);g['spec_body']=encode_spec(g['spec'],g['pool'])
    g['pool_layout']=mode;return g


def lesson_layout(row,mode,identity):
    r=copy.deepcopy(row);state=r['state'];old=state['pool'];base=pool_for(state['view']['task'])
    for value in sorted(set(old)-set(base),key=Decimal):base.append(value)
    new=layout(base,identity,mode)
    state['body']=remap(state['body'],old,new);state['pool']=new;state['view']['constants']=list(new)
    r['reference_body']=compile_spec(r['target_spec'],new);r['spec_body']=encode_spec(r['target_spec'],new)
    if state.get('diagnosis')and new!=old:raise ValueError('Do not relabel an advisory diagnosis')
    r['pool_layout']=mode;return r
