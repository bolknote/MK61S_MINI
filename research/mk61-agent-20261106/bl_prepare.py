"""Freeze parents, held-out test, observed-state exclusions and selection pre-SGD."""
import collections
import json
import shutil
import time
from decimal import Decimal
import torch
from transformers import AutoTokenizer
from bl_common import ROOT,PARENT,SOURCES,HERE,PRIORS,DEV_NUMBERS,TEST_NUMBERS,read,rows,write,sha,signature,check_previous,body_ids
from bl_model import agent
from bl_course import Course,encoded,loss
from bl_spec import install
from bl_own_errors import visible_code
from bc_pools import lesson_layout
from be_language import paths3
from ar_spec import infer
from ha_protocol import canonical
from native_export import packet


def main():
    install();check_previous();assert not(ROOT/'frozen.json').exists()
    for name in ['teacher-frozen.json','lessons-frozen.json','own-frozen.json']:
        for n,d in read(ROOT/name)['files'].items():assert sha(ROOT/n)==d,n
    for arm in ['lora','full']:
        p=PARENT/arm/'last.safetensors'
        assert sha(p)==read(SOURCES[arm]/'manifest.json')['selected_checkpoint_sha256']
        shutil.copyfile(p,ROOT/('initial-'+arm+'.safetensors'))
    policy={'steps':3000,'checkpoints':[1000,2000,3000],'batch':32,'context':1024,'reserve':160,
            'model_seed':261112120,'data_seed':261112121,'lr_lora':5e-5,'lr_lora_actions':5e-5,
            'lr_full':1e-5,'lr_full_embeddings':5e-6,'weight_decay':.01,
            'draws':'8 NL;2 wrong-own-SPEC reviews;2 exact correct-own-SPEC preservation;12 calibrated matched action decisions;8 mixed retained/on-policy repair/RUN/DONE/UNSURE',
            'wrong_hypothesis_action_prevalence':.15,'review_sees_prior_SPEC':True,'review_sees_code':False,
            'parent_runtime':'working BJ typed long prompt, latest trained step6000',
            'selection':'protect working parent accepted false DONE, corruptions, repairs, successful completions and false-claim episodes; NL within3pp, editorial/structured5pp. Also protect compact parent only if its completion coverage >=90% of working parent. Parent fallback; rank by repairs, completion, errors, language.',
            'closed_used_for_selection':False,'mandatory_fixed3000_audit':True,'Q4_every_forward':True,
            'same_data_draws':True,'compute_and_KV':'FP32','new_closed_generated_before_SGD':True,'unix':time.time()}
    write(ROOT/'policy.json',policy)
    tokenizer=AutoTokenizer.from_pretrained(SOURCES['lora']/'hf',local_files_only=True)
    assert tokenizer.get_vocab()==AutoTokenizer.from_pretrained(SOURCES['full']/'hf',local_files_only=True).get_vocab()
    values=rows(ROOT/'lessons.jsonl');valid=[];dropped=collections.Counter()
    ast=read(ROOT/'ast-frozen.json');held={tuple(x)for x in ast['dev_triples']+ast['test_triples']}
    banned={canonical(abs(Decimal(x)))for x in DEV_NUMBERS+TEST_NUMBERS}
    for i,row in enumerate(values):
        s=row['state'];specs=[row['target_spec'],s.get('declared_spec'),s.get('prior_spec')]
        try:
            code=visible_code(row['raw_prompt'],row['question']) if 'raw_prompt'in row else s['body']
            if code:specs.append(infer(code,s['pool'],s['view']['angle']))
        except (ValueError,ArithmeticError,KeyError):pass
        if any(paths3(sp['X'])&held for sp in specs if sp is not None):dropped['observed_operator_path']+=1;continue
        if any(canonical(abs(Decimal(n)))in banned for n in s['pool']):dropped['literal_pool']+=1;continue
        try:
            modes=['default']if 'raw_prompt'in row else['default','full','distractors']
            maximum=max(len(encoded(tokenizer,row if 'raw_prompt'in row else lesson_layout(row,m,f'bl:check:{i}:{m}'))[0])for m in modes)
            assert maximum<=1024
        except (ValueError,AssertionError,ArithmeticError):dropped[row['origin']]+=1;continue
        valid.append(i)
        if i%10000==0:print(json.dumps({'tokenized':i,'valid':len(valid)}),flush=True)
    assert len(valid)>.70*len(values)
    write(ROOT/'valid-ids.json',valid)
    course=Course(tokenizer);batch=course.batch(401,'cpu')
    indices=torch.cat([batch[-1].nonzero()[:3,0],(~batch[-1]).nonzero()[:2,0]])
    batch=tuple(x.index_select(0,indices)for x in batch);head=torch.tensor(body_ids(tokenizer));initial={}
    for arm in ['lora','full']:
        model=agent(arm,'cpu');replica,_=model.packed(ROOT/('initial-'+arm+'.mkqb'));del replica
        cpu=packet(ROOT/('initial-'+arm+'.mkqb'))[1];gpu=packet(SOURCES[arm]/'model.mkqb')[1]
        diffs=sum(a!=b for a,b in zip(cpu,gpu))
        if arm=='full':assert diffs==0
        pre=read(ROOT/'parent-b200-preflight.json')[arm]
        assert pre['B200_master_exact']and pre['B200_Q4_exact']
        with torch.nn.utils.parametrize.cached():v,parts=loss(model,batch,head)
        v.backward();assert torch.isfinite(v)and all(torch.isfinite(p.grad).all()for p in model.parameters()if p.grad is not None)
        initial[arm]={'trainable':model.trainable_count(),'CPU_Q4_differences':diffs,'B200_initial_exact':True,'finite_gradient':True,'loss':float(v.detach()),'parts':parts}
        del model
    train={signature(values[i]['target_spec'])for i in valid}
    prior={signature(g['spec'])for p in PRIORS for split in ['train','development','closed']for g in rows(p/(split+'-clean.jsonl'))}
    for split in ['development','closed']:
        keys={signature(g['spec'])for g in rows(ROOT/(split+'-clean.jsonl'))}
        assert not keys&train and not keys&prior
    write(ROOT/'preparation-checks.json',{'complete':True,'initial':initial,'valid_lessons':len(valid),'dropped':dict(dropped),
          'held_operator_paths_excluded_from_targets_hypotheses_and_inferable_visible_code':True,'optimizer_updates':0})
    files=['plan.json','parent-b200-preflight.json','ast-frozen.json','teacher-frozen.json','teacher-audit.jsonl','lessons-frozen.json','own-frozen.json','own-errors.jsonl','own-correct.jsonl','own-policy.jsonl',
           'policy.json','valid-ids.json','checks.json','runtime-checks.json','preparation-checks.json','lessons.jsonl','train-clean.jsonl','development-clean.jsonl','closed-clean.jsonl',
           'initial-lora.safetensors','initial-full.safetensors','initial-lora.mkqb','initial-full.mkqb']
    inherited=read(PARENT/'frozen.json')['sources']
    sources={**inherited,**{p.name:sha(p)for p in HERE.glob('bl_*.py')},'bk_independent_generate.py':sha(HERE/'bk_independent_generate.py')}
    def assets(a):
        folder=SOURCES[a];return{str(p.relative_to(folder)):sha(p)for p in[folder/'model.mkqb',*sorted((folder/'hf').iterdir())]if p.is_file()}
    write(ROOT/'frozen.json',{'sources':sources,'files':{n:sha(ROOT/n)for n in files},'parents':{a:assets(a)for a in ['lora','full']},'SGD_started':False,'closed_model_generations_seen':False,'unix':time.time()})
    write(ROOT/'prepared.json',{'complete':True,'initial':initial,'valid_lessons':len(valid),'optimizer_updates':0})
    print(json.dumps({'prepared':True,'valid':len(valid),'dropped':dict(dropped),'initial':initial}),flush=True)


if __name__=='__main__':torch.set_num_threads(4);main()
