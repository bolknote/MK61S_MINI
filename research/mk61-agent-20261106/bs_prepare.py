"""Freeze data, protocol, retention gates, and shared-Qwen resource limits."""
import collections
import json
import time
import torch
from bs_common import ROOT,SOURCE,HERE,read,write,rows,sha,previous_check,body_ids
from br_common import ROOT as BR_ROOT
from bs_model import agent
from bs_course import Course,loss
from be_language import paths3
from az_data import numbers
from ar_spec import infer
from bs_data import DEV_NUMBERS,TEST_NUMBERS
from bl_spec import install


def main():
    previous_check();assert not(ROOT/'frozen.json').exists();install()
    policy={'steps':3000,'checkpoints':[1000,2000,3000],'lr':2e-5,'lr_embeddings':8e-6,'weight_decay':.01,
       'effective_batch':32,'microbatch':8,'accumulation':4,'data_seed':261121117,'model_seed':261121118,
       'context':1024,'reserve':160,'max_actions':12,'Q4_from_first_update':True,
       'old_translation_and_repair_fraction':.5,'GPU_duty_fraction':.5,'allocator_MiB':1536,'minimum_free_MiB':8192,
       'gpu':0,'host_gpu':1,'Qwen_service_changes':False,
       'selection':'development only; retain parent translations, correct completions and repairs; no false_DONE increase; also protect long working profile',
       'closed_primary_goals':256,'closed_own_episodes':512,'closed_wrong_SPEC_episodes':64,'closed_rejected_recovery_episodes':128,
       'main_profile_replacement':False,'device_access':False}
    write(ROOT/'policy.json',policy);data=read(ROOT/'data-frozen.json')
    for n,d in data['files'].items():assert sha(ROOT/n)==d,n
    held={tuple(x)for x in data['dev_triples']+data['test_triples']};values=rows(ROOT/'lessons.jsonl');valid=[];skipped=collections.Counter();cache={}
    for i,r in enumerate(values):
        visible=[r['target_spec']];s=r['state']
        for k in ['declared_spec','prior_spec']:
            if s.get(k)is not None:visible.append(s[k])
        if s.get('body'):
            key=(tuple(s['body']),tuple(s['pool']),s['view']['angle'])
            if key not in cache:
                try:cache[key]=infer(s['body'],s['pool'],s['view']['angle'])
                except (ValueError,ArithmeticError):cache[key]=None
            if cache[key]is not None:visible.append(cache[key])
        if any(paths3(v['X'])&held for v in visible):skipped['held_triplet_in_visible_state']+=1;continue
        if any(numbers(v['X'])&set(DEV_NUMBERS+TEST_NUMBERS)for v in visible):skipped['held_literal']+=1;continue
        valid.append(i)
    write(ROOT/'valid-ids.json',valid);write(ROOT/'leakage-checks.json',{'valid':len(valid),'excluded':dict(skipped),'target_hypothesis_and_inferable_visible_code_checked':True})
    model=agent('cpu');course=Course(model.tokenizer);batch=course.step(1,'cpu')[0];head=torch.tensor(body_ids(model.tokenizer))
    with torch.nn.utils.parametrize.cached():value,parts=loss(model,batch,head)
    value.backward();assert torch.isfinite(value)and all(torch.isfinite(p.grad).all()for p in model.parameters()if p.grad is not None)
    # Restart for the exact declared draw sequence; no GPU or optimizer step here.
    course=Course(model.tokenizer)
    for step in range(1,policy['steps']+1):course.step(step,'cpu')
    files={**data['files'],**{n:sha(ROOT/n)for n in ['data-frozen.json','valid-ids.json','leakage-checks.json','policy.json']}}
    sources={**read(BR_ROOT/'frozen.json')['sources'],**{p.name:sha(p)for p in HERE.glob('bs_*.py')}}
    parent={str(p.relative_to(SOURCE)):sha(p)for p in [SOURCE/'model.mkqb',*sorted((SOURCE/'hf').iterdir())]if p.is_file()}
    write(ROOT/'frozen.json',{'sources':sources,'files':files,'parent':parent,'SGD_started':False,'closed_generations_seen':False,'unix':time.time()})
    write(ROOT/'prepared.json',{'complete':True,'optimizer_updates':0,'valid_training_rows':len(valid),'expected_draw_digest':course.digest,
          'expected_counts':dict(course.counts),'finite_CPU_gradient_check':True,'CPU_loss':float(value.detach()),'parts':parts,
          'shared_Qwen_policy':{k:policy[k]for k in ['host_gpu','allocator_MiB','GPU_duty_fraction','minimum_free_MiB']}})
    print(json.dumps(read(ROOT/'prepared.json')),flush=True)


if __name__=='__main__':torch.set_num_threads(3);main()
