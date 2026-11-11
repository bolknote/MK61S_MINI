"""Freeze clean course, selection, source and independent final test before SGD."""
import collections
import json
import shutil
import time
import torch
from be_common import ROOT,PARENT,PRIORS,SOURCE,HERE,REPO,read,rows,write,sha,body_ids,DEV_NUMBERS,TEST_NUMBERS
from be_model import agent
from be_language import parse_question,paths3
from be_course import Course,loss
from ay_course import encoded
from bc_pools import lesson_layout,goal_layout
from ay_finalize import semantic_key
from full_isa_vm import FullVM
from ar_spec import verify
from native_export import packet
from transformers import AutoTokenizer

def main():
    assert not(ROOT/'frozen.json').exists()
    from bc_common import check_frozen as old_check
    old_check();shutil.copyfile(PARENT/'selected-adapters/spec.safetensors',ROOT/'initial-adapter.safetensors')
    data=read(ROOT/'data-frozen.json');lesson=read(ROOT/'lessons-frozen.json')
    for n,d in {**data['files'],**lesson['files']}.items():assert sha(ROOT/n)==d
    policy={'steps':4000,'checkpoints':[1000,2500,4000],'batch':32,'context':1024,'model_seed':26110898,'data_seed':26110899,
        'lr_lora':.0001,'lr_lora_actions':.0001,'lr_full':.00003,'lr_full_embeddings':.000015,'weight_decay':.01,
        'goal_pairs':14,'control_replay':4,'goal_action_loss':False,'body_weight':2.,'first_simple_steps':400,
        'action_replay':'balanced RUN00/01 alternating, DONE, repair WRITE, UNSURE; one each per batch',
        'same_example_draws_and_layouts_for_both_branches':True,'Q4_every_forward_from_first_step':True,
        'full_all_weights_including_input_embeddings':True,'same_starting_master_and_Q4_payload':True,
        'selection':'known sin regressions retained first; maximize mean(core accuracy,editorial accuracy), then min, total accuracy, fewer codec errors, raw success and fewer self falseDONE',
        'parent_step_zero_fallback':True,'closed_for_selection':False,'one_selected_checkpoint_per_branch':True,
        'old_development_and_exam_ASTs_retired_into_clean_training':True,'new_closed_model_generations_seen':False,
        'no_teacher_critic_DPO_or_DONE_penalty':True,'same_input_protocol_and_SPEC_codec':True,'unix':time.time()}
    write(ROOT/'policy.json',policy);tokenizer=AutoTokenizer.from_pretrained(SOURCE/'hf',local_files_only=True);valid=[];dropped=collections.Counter()
    values=rows(ROOT/'lessons.jsonl')
    for i,r in enumerate(values):
        assert parse_question(r['state']['view']['task'],r['target_spec']['angle'])==r['target_spec']
        maximum=max(len(encoded(tokenizer,lesson_layout(r,m,f'be:preflight:{i}:{m}'),'spec')[0])for m in ['default','full','distractors'])
        if maximum<=1000:valid.append(i)
        else:dropped[r['origin']]+=1
        if i%5000==0:print(json.dumps({'tokenized':i,'valid':len(valid)}),flush=True)
    assert len(valid)>.8*len(values);write(ROOT/'valid-ids.json',valid)
    initial={};gradients={};course=Course(tokenizer)
    # One identical batch, no optimizer updates; quantization and gradients checked on CPU.
    batch=course.batch(401,'cpu');chosen=torch.cat([batch[-1].nonzero()[:,0],(~batch[-1]).nonzero()[:2,0]])
    batch=tuple(x.index_select(0,chosen)for x in batch);head=torch.tensor(body_ids(tokenizer))
    for arm in ['lora','full']:
        torch.manual_seed(policy['model_seed']);model=agent(arm,'cpu');model.save_checkpoint(ROOT/('initial-'+arm+'.safetensors'))
        replica,_=model.packed(ROOT/('initial-'+arm+'.mkqb'));del replica
        a,b=packet(ROOT/('initial-'+arm+'.mkqb'))[1],packet(SOURCE/'model.mkqb')[1]
        initial[arm]={'trainable':model.trainable_count(),'CPU_Q4_byte_differences':sum(x!=y for x,y in zip(a,b)),'bytes':len(a)}
        with torch.nn.utils.parametrize.cached():value,parts=loss(model,batch,head)
        value.backward();assert torch.isfinite(value)and all(torch.isfinite(p.grad).all()for p in model.parameters()if p.grad is not None)
        embedding=model.base.model.embed_tokens
        if arm=='full':assert embedding.parametrizations.weight.original.grad is not None and embedding.parametrizations.weight.original.grad.abs().sum()>0
        else:assert embedding.weight.grad is None
        gradients[arm]={'loss':float(value.detach()),'parts':parts,'finite':True,'optimizer_updates':0}
        del model
    assert initial['lora']['trainable']==318208 and initial['full']['trainable']==3022080
    vm=FullVM();checks=0;seen=set();previous={semantic_key(g['spec'])for p in PRIORS for s in ['train','development','closed']for g in rows(p/(s+'-clean.jsonl'))}
    for split in ['train','development','closed']:
        goals=rows(ROOT/(split+'-clean.jsonl'));keys={semantic_key(g['spec'])for g in goals};assert not(seen&keys)
        if split!='train':assert not(previous&keys)
        seen.update(keys)
        for g in goals:
            if g['style']!='editorial':assert parse_question(g['task'],g['spec']['angle'])==g['spec']
        for g in goals[::max(1,len(goals)//32)]:
            for mode in ['default','full','distractors']:
                changed=goal_layout(g,mode)
                check=verify(vm,changed['reference_body'],changed['pool'],g['spec'],g['public_inputs']+g['checker_inputs']+g['audit_inputs'])
                assert check['status']=='TESTED',(g['id'],check);checks+=1
    write(ROOT/'checks.json',{'valid_lessons':len(valid),'dropped':dict(dropped),'initial':initial,'gradients':gradients,
        'independent_parser_all_controlled_wordings_checked':True,'new_dev_and_closed_prior_signatures_excluded':True,
        'sampled_permuted_reference_ROM_checks':checks,'optimizer_updates':0})
    files=['data-frozen.json','lessons-frozen.json','policy.json','valid-ids.json','checks.json','lessons.jsonl','initial-adapter.safetensors',
        'initial-lora.safetensors','initial-full.safetensors','initial-lora.mkqb','initial-full.mkqb','editorial-audit.jsonl',
        'train-clean.jsonl','development-clean.jsonl','closed-clean.jsonl']
    previous_sources=read(PARENT/'frozen.json')['sources']
    sources={**previous_sources,**{p.name:sha(p)for p in HERE.glob('be_*.py')if not p.name.endswith(('_remote.py','_report.py','_native.py','_finish.py'))}}
    model_files=[SOURCE/'model.mkqb',*sorted((SOURCE/'hf').iterdir())]
    write(ROOT/'frozen.json',{'sources':sources,'files':{n:sha(ROOT/n)for n in files},
        'parent_model':{str(p.relative_to(SOURCE)):sha(p)for p in model_files if p.is_file()},
        'SGD_started':False,'closed_generations_seen':False,'unix':time.time()})
    from be_common import check_frozen
    check_frozen();write(ROOT/'prepared.json',{'complete':True,'valid_lessons':len(valid),'initial':initial,'optimizer_updates':0})
    print(json.dumps({'prepared':True,'valid_lessons':len(valid),'initial':initial}),flush=True)

if __name__=='__main__':
    torch.set_num_threads(4);main()
