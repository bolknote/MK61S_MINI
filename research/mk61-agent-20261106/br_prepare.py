"""Freeze a finite capacity test, including its limits, before the first update."""
import collections
import json
import time
import torch
from br_common import ROOT,SOURCE,HERE,read,write,rows,sha,check_previous,body_ids
from br_model import Full
from br_course import Course,loss
from aq_course import pad
from bp_course import encoded


def main():
    check_previous();assert not(ROOT/'frozen.json').exists()
    policy={'steps':3000,'checkpoints':[500,1500,3000],'warmup':100,'lr':3e-5,'lr_embeddings':1.5e-5,
            'weight_decay':.01,'batch':32,'data_seed':261120113,'model_seed':261120114,'context':1024,'reserve':160,
            'max_actions':12,'Q4_from_first_forward':True,'same_optimizer_and_draws':True,
            'criterion':{'action_accuracy':.99,'teacher_forced_body_sequence_accuracy':.98,'gold_wrong_cycle_completion':.98,
                         'false_DONE':0,'correct_code_corruption':0},
            'selection':'best lexicographic training fit, earliest on exact ties; never held-out',
            'held_out':['wording','inputs','new_ast'],'held_out_final_audit_if_different':True,
            'limits':['one seed per architecture','depth only capacity change','finite training budget',
                      'training goals may overlap old parent tasks','gold/wrong SPEC are offline diagnostic controls',
                      'no claim that larger model fits a device at 1024 context','no deployment']}
    write(ROOT/'policy.json',policy)
    data=read(ROOT/'data-frozen.json');init=read(ROOT/'initialization.json')
    assert data['conflicting_prompt_labels']==0 and init['complete']
    for n,d in data['files'].items():assert sha(ROOT/n)==d,n
    grads={};counts={};digest=None
    for arm in ['small','large']:
        model=Full(arm,device='cpu');course=Course(model.tokenizer);head=torch.tensor(body_ids(model.tokenizer))
        selected=[next(r for r in course.rows if r['origin']==kind)for kind in ['goal','write']]
        batch=(*pad([encoded(model.tokenizer,r)for r in selected],'cpu'),torch.tensor([False,True]))
        with torch.nn.utils.parametrize.cached():value,parts=loss(model,batch,head)
        value.backward();assert torch.isfinite(value)
        assert all(torch.isfinite(p.grad).all()for p in model.parameters()if p.grad is not None)
        extra={n:float(p.grad.abs().max())for n,p in model.named_parameters()if arm=='large'and'base.model.layers.1.'in n and'.o_proj.'in n and p.grad is not None}
        if arm=='large':assert any(v>0 for v in extra.values()),'Added blocks receive no gradient'
        grads[arm]={'loss':float(value.detach()),'parts':parts,'all_gradients_finite':True,'added_output_gradient_maxima':extra}
        if arm=='small':
            for step in range(1,policy['steps']+1):course.batch(step,'cpu')
            digest=course.digest;counts=dict(course.counts)
        del model,course
    files={**data['files'],'data-frozen.json':sha(ROOT/'data-frozen.json'),'initialization.json':sha(ROOT/'initialization.json'),
           'initial-probes.json':sha(ROOT/'initial-probes.json'),'policy.json':sha(ROOT/'policy.json')}
    for p in sorted((ROOT/'initial').rglob('*')):
        if p.is_file():files[str(p.relative_to(ROOT))]=sha(p)
    previous=read(ROOT.parent/'spec-review-flag-fix-v1/frozen.json')['sources']
    sources={**previous,**{p.name:sha(p)for p in HERE.glob('br_*.py')}}
    parent={str(p.relative_to(SOURCE)):sha(p)for p in [SOURCE/'model.mkqb',*sorted((SOURCE/'hf').iterdir())]if p.is_file()}
    write(ROOT/'frozen.json',{'sources':sources,'files':files,'parent':parent,'SGD_started':False,'held_out_generations_seen':False,'unix':time.time()})
    write(ROOT/'prepared.json',{'complete':True,'optimizer_updates':0,'expected_draw_digest':digest,'expected_counts':counts,
          'training_goals':32,'training_rows':len(rows(ROOT/'lessons.jsonl')),'initial_Q4_function_matched':True,
          'gradient_checks':grads,'policy_sha256':sha(ROOT/'policy.json')})
    print(json.dumps(read(ROOT/'prepared.json')),flush=True)


if __name__=='__main__':torch.set_num_threads(4);main()
