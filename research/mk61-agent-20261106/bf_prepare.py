"""Freeze the natural-language course and final exam before either continuation."""
import collections
import json
import shutil
import time
import torch
from bf_common import ROOT,PARENT,PRIORS,SOURCES,HERE,read,rows,write,sha,signature,body_ids,DEV_NUMBERS,TEST_NUMBERS
from bf_spec import install
from bf_model import agent
from bf_course import Course,loss
from ay_course import encoded
from bc_pools import lesson_layout,goal_layout
from be_language import paths3
from native_export import packet
from full_isa_vm import FullVM
from ar_spec import verify
from transformers import AutoTokenizer
from decimal import Decimal
from ha_protocol import canonical

def main():
    install();assert not(ROOT/'frozen.json').exists()
    from be_common import check_frozen as previous
    previous()
    for arm in ['lora','full']:shutil.copyfile(PARENT/arm/'best.safetensors',ROOT/('initial-'+arm+'.safetensors'))
    teacher=read(ROOT/'teacher-frozen.json');lessons=read(ROOT/'lessons-frozen.json')
    for n,d in {**teacher['files'],**lessons['files']}.items():assert sha(ROOT/n)==d,n
    policy={'steps':6000,'checkpoints':[1000,3000,6000],'batch':32,'context':1024,
        'model_seed':261108120,'data_seed':261108121,'lr_lora':.0001,'lr_lora_actions':.0001,
        'lr_full':.00002,'lr_full_embeddings':.00001,'weight_decay':.01,
        'natural_pairs':12,'structured_pairs':2,'control_replay':4,'body_weight':2.,'goal_action_loss':False,
        'natural_draws':'3 original-clear pairs,2 minimally-edited pairs,7 general natural pairs',
        'first_simple_steps':200,'same_data_draws_for_both_branches':True,
        'continue_each_own_selected_BE_checkpoint':True,'both_initial_Q4_match_own_BE_parent':True,
        'Q4_every_forward':True,'compute_and_KV':'FP32','full_trainable':3022080,'lora_trainable':318208,
        'selection':'retain known short probes; structured and independently authored editorial development within5pp of own parent; then maximize natural accuracy, worst natural panel, fewer codec errors, raw success and fewer self falseDONE',
        'parent_step_zero_fallback':True,'one_selected_checkpoint_per_branch':True,'closed_used_for_selection':False,
        'checker':'relative2e-6 for nonzero; absolute1e-12 only for zero; ROM sign(0)=0',
        'checker_same_for_all_parent_and_trained_models':True,'same_six_actions_and_SPEC_codec':True,
        'no_new_neural_critic_DPO_or_DONE_penalty':True,'unix':time.time()}
    write(ROOT/'policy.json',policy);tokenizer=AutoTokenizer.from_pretrained(SOURCES['lora']/'hf',local_files_only=True)
    assert tokenizer.get_vocab()==AutoTokenizer.from_pretrained(SOURCES['full']/'hf',local_files_only=True).get_vocab()
    values=rows(ROOT/'lessons.jsonl');valid=[];dropped=collections.Counter()
    for i,r in enumerate(values):
        maximum=max(len(encoded(tokenizer,lesson_layout(r,m,f'bf:check:{i}:{m}'),'spec')[0])for m in ['default','full','distractors'])
        if maximum<=1000:valid.append(i)
        else:dropped[r['origin']]+=1
        if i%5000==0:print(json.dumps({'tokenized':i,'valid':len(valid)}),flush=True)
    assert len(valid)>.8*len(values);write(ROOT/'valid-ids.json',valid)
    c=Course(tokenizer);batch=c.batch(401,'cpu');indices=torch.cat([batch[-1].nonzero()[:,0],(~batch[-1]).nonzero()[:2,0]])
    batch=tuple(x.index_select(0,indices)for x in batch);head=torch.tensor(body_ids(tokenizer));initial={}
    for arm in ['lora','full']:
        model=agent(arm,'cpu');replica,_=model.packed(ROOT/('initial-'+arm+'.mkqb'));del replica
        a,b=packet(ROOT/('initial-'+arm+'.mkqb'))[1],packet(SOURCES[arm]/'model.mkqb')[1]
        with torch.nn.utils.parametrize.cached():v,parts=loss(model,batch,head)
        v.backward();assert torch.isfinite(v)and all(torch.isfinite(p.grad).all()for p in model.parameters()if p.grad is not None)
        if arm=='full':assert model.base.model.embed_tokens.parametrizations.weight.original.grad.abs().sum()>0
        else:assert model.get_input_embeddings().weight.grad is None
        initial[arm]={'trainable':model.trainable_count(),'CPU_Q4_byte_differences_from_own_parent':sum(x!=y for x,y in zip(a,b)),
            'finite_gradient':True,'loss':float(v.detach()),'parts':parts,'optimizer_updates':0}
        del model
    prior={signature(g['spec'])for p in PRIORS for s in ['train','development','closed']for g in rows(p/(s+'-clean.jsonl'))}
    training_keys={signature(r['target_spec'])for r in values};training_paths=set().union(*(paths3(r['target_spec']['X'])for r in values))
    ast=read(ROOT/'ast-frozen.json');held={tuple(x)for x in ast['dev_triples']+ast['test_triples']}
    assert not training_paths&held
    banned={canonical(abs(Decimal(x)))for x in DEV_NUMBERS+TEST_NUMBERS}
    assert not any(any(canonical(abs(Decimal(n)))in banned for n in r['state']['pool'])for r in values)
    for split in ['development','closed']:
        goals=rows(ROOT/(split+'-clean.jsonl'));keys={signature(g['spec'])for g in goals}
        assert not keys&prior and not keys&training_keys
        for g in goals:
            if g['panel']in ['known','novel']:assert g['blind_ambiguity_checked']and g['dual_blind_checked']
    vm=FullVM();checked=0
    for split in ['train','development','closed']:
        goals=rows(ROOT/(split+'-clean.jsonl'))
        for g in goals[::max(1,len(goals)//24)]:
            for mode in ['default','full','distractors']:
                h=goal_layout(g,mode);v=verify(vm,h['reference_body'],h['pool'],g['spec'],g['public_inputs']+g['checker_inputs']+g['audit_inputs'])
                assert v['status']=='TESTED',(g['id'],v);checked+=1
    write(ROOT/'checks.json',{'valid_lessons':len(valid),'dropped':dict(dropped),'initial':initial,
        'all_replay_targets_and_pools_holdout_checked':True,'literal_pool_leaks':0,'target_signature_leaks':0,
        'operator_triple_leaks':0,'sampled_permuted_ROM_checks':checked,'optimizer_updates':0})
    files=['ast-frozen.json','teacher-frozen.json','lessons-frozen.json','policy.json','valid-ids.json','checks.json',
        'lessons.jsonl','train-clean.jsonl','development-clean.jsonl','closed-clean.jsonl',
        'initial-lora.safetensors','initial-full.safetensors','initial-lora.mkqb','initial-full.mkqb','teacher-audit.jsonl']
    inherited=read(PARENT/'frozen.json')['sources']
    sources={**inherited,**{p.name:sha(p)for p in HERE.glob('bf_*.py')if not p.name.endswith(('_remote.py','_native.py','_report.py','_finish.py'))}}
    def assets(a):return {str(p.relative_to(SOURCES[a])):sha(p)for p in [SOURCES[a]/'model.mkqb',*sorted((SOURCES[a]/'hf').iterdir())]if p.is_file()}
    write(ROOT/'frozen.json',{'sources':sources,'files':{n:sha(ROOT/n)for n in files},'parents':{a:assets(a)for a in ['lora','full']},
        'SGD_started':False,'closed_model_generations_seen':False,'unix':time.time()})
    from bf_common import check_frozen
    check_frozen();write(ROOT/'prepared.json',{'complete':True,'valid_lessons':len(valid),'initial':initial,'optimizer_updates':0})
    print(json.dumps({'prepared':True,'initial':initial,'valid_lessons':len(valid)}),flush=True)

if __name__=='__main__':
    torch.set_num_threads(4);main()
