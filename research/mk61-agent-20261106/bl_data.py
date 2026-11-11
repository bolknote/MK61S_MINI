"""Natural candidates, targeted contrasts and fresh frozen expression holdouts."""
import collections
import concurrent.futures
import copy
from decimal import Decimal
import itertools
import json
import random
import time
from bl_common import ROOT,PARENT,PRIORS,DEV_NUMBERS,TEST_NUMBERS,read,write,rows,save_rows,sha,signature
from bh_spec import install
from bh_editorial import TEMPLATES
from be_data import clean_spec
from be_language import paths3
from bc_data import mutated_specs
from ay_data import make,op_count
from az_data import tree,numbers
from az_teacher import pool_for
from ay_codec import encode,compile_spec
from full_isa_vm import FullVM,build
from full_isa_math import UNARY,BINARY,registers
from ar_spec import verify,expected
from av_deepseek import parse_expression
from ha_protocol import canonical

def worker(item):
    install();return make(FullVM(),*item)

def main():
    ROOT.mkdir(parents=True,exist_ok=True);assert not(ROOT/'frozen.json').exists();assert(ROOT/'own-frozen.json').exists()
    if(ROOT/'ast-frozen.json').exists():return
    install();build();vm=FullVM();rng=random.Random(261112111);started=time.monotonic();seen=set();bank={};raw=collections.defaultdict(list)
    for p in PRIORS:
        for split in ['train','development','closed']:
            for g in rows(p/(split+'-clean.jsonl')):seen.add(signature(g['spec']))
    for split in ['train','development','closed']:
        for old in rows(PARENT/(split+'-clean.jsonl')):
            s=clean_spec(old['spec']);key=signature(s)
            if key in bank:continue
            g=copy.deepcopy(old);g.update(id=f'bl:train:retired:{len(bank):05}',source_id=old['id'],spec=s,split='train',panel='known',curriculum='retired')
            # BH used this exact strict checker and certified every frozen AST.
            # Reuse unchanged prior ASTs; only changed specifications need ROM rebuilding.
            if s != old['spec']:
                rebuilt=make(vm,s,g['id'],'train','known',g['family'],rng.randrange(2**31))
                if not rebuilt:continue
                g={**g,**rebuilt,'source_id':old['id'],'curriculum':'retired'}
            bank[key]=g
    # Keep existing natural wording as a candidate, unchanged until blind review.
    for p in reversed(PRIORS):
        for split in ['train','development','closed']:
            for old in rows(p/(split+'-clean.jsonl')):
                if old.get('style')in ['bracket','named','chain']:continue
                key=signature(old['spec'])
                if key in bank and old['task']not in raw[key]and len(raw[key])<2:raw[key].append(old['task'])
    banned={canonical(abs(Decimal(x)))for x in DEV_NUMBERS+TEST_NUMBERS}
    assert not any(numbers(g['spec']['X'])&banned for g in bank.values())
    literals=sorted({canonical(x)for g in bank.values()for x in numbers(g['spec']['X'])}|{'0.65','12.625','29.875','48.375','64.625','79.375'},key=Decimal)
    literals+=['-'+x for x in literals if Decimal(x)>0]
    # Exclude observed hypotheses and visible program ASTs, including wrong ones.
    observed=[]
    for name in ['own-errors.jsonl','own-correct.jsonl','own-policy.jsonl']:
        for item in rows(ROOT/name):
            h=item.get('hypothesis')
            if h is not None:observed.append(h);seen.add(signature(h))
    from bl_own_errors import visible_code
    from ar_spec import infer
    for item in rows(ROOT/'own-policy.jsonl'):
        try:observed.append(infer(visible_code(item['raw_prompt'],item['question']),item['pool'],item['goal']['spec']['angle']))
        except (ValueError,ArithmeticError):pass
    occupied=set().union(*(paths3(g['spec']['X'])for g in bank.values()),*(paths3(h['X'])for h in observed))
    safe=[op for op in UNARY if op not in ['exp','pow10','sign','int','frac']]
    held=rng.sample([t for t in itertools.product(safe,repeat=3)if t not in occupied and len(set(t))>=2],12)
    dev_held=set(held[:6]);test_held=set(held[6:]);all_held=set(held)
    output={'train':list(bank.values()),'development':[],'closed':[]};rejects=collections.Counter()
    quotas={'train':[],
        'development':[('known',{'constant':40,'numeric':48,'register':32}),('novel',{'constant':48,'numeric':40,'composition':32})],
        'closed':[('known',{'constant':120,'numeric':120,'register':80}),('novel',{'constant':120,'numeric':120,'composition':80})]}
    with concurrent.futures.ProcessPoolExecutor(4)as pool:
        for split,panels in quotas.items():
            for panel,families in panels:
                nums=DEV_NUMBERS if split=='development'and panel=='novel'else TEST_NUMBERS if split=='closed'and panel=='novel'else literals
                for family,n in families.items():
                    accepted=0;attempts=0
                    while accepted<n:
                        batch=[]
                        for _ in range(min(144,max(16,2*(n-accepted)))):
                            attempts+=1
                            if attempts>n*12000:raise RuntimeError((split,panel,family,accepted))
                            if family=='composition':
                                a,b,c=rng.choice(sorted(dev_held if split=='development'else test_held));expr=[a,[b,[c,rng.choice([f'R{x:X}'for x in range(15)])]]]
                                if rng.random()<.5:expr=['+',expr,{'constant':rng.choice(nums)}]
                            elif family=='numeric':
                                a=rng.choice([f'R{x:X}'for x in range(15)]);b={'constant':rng.choice(nums)}
                                if rng.random()<.4:a=[rng.choice(list(UNARY)),a]
                                if rng.random()<.5:a,b=b,a
                                expr=[rng.choice(list(BINARY)),a,b]
                            else:expr=tree(rng,nums,family=='constant',0,2 if family=='constant'else 3)
                            if op_count(expr)>5 or(family!='constant'and not registers(expr)):continue
                            if family in ['constant','numeric']and not numbers(expr):continue
                            es=paths3(expr)
                            if family!='composition'and es&all_held:continue
                            if family=='composition'and es&(test_held if split=='development'else dev_held):continue
                            spec={'X':expr,'writes':{rng.choice([f'R{x:X}'for x in range(15)]):expr}if rng.random()<.23 else{},'angle':rng.choice(['DEG','RAD','GRAD'])}
                            key=signature(spec)
                            if key in seen:continue
                            if not registers(expr):
                                try:
                                    if abs(expected(spec,{})['X'])>1e6:continue
                                except (ValueError,ArithmeticError,OverflowError):continue
                            seen.add(key);identifier=f'bl:{split}:{panel}:{family}:{attempts:06}'
                            batch.append((spec,identifier,split,panel,family,rng.randrange(2**31)))
                        for g in pool.map(worker,batch):
                            if g is None:rejects['reference_ROM_or_domain']+=1;continue
                            if accepted==n:continue
                            g['curriculum']='new';output[split].append(g);accepted+=1
                        if accepted==n:print(json.dumps({'split':split,'family':family,'accepted':accepted,'seconds':round(time.monotonic()-started,1)}),flush=True)
    # Teacher variants address actual on-policy misreadings, not random AST errors.
    own=rows(ROOT/'own-errors.jsonl');rng.shuffle(own);variants=[];seen_variants=set()
    for item in own:
        g=item['goal']
        if g['panel']=='structured' or item['hypothesis'] is None:continue
        identity=(g['task'],json.dumps(item['hypothesis'],sort_keys=True))
        if identity in seen_variants:continue
        seen_variants.add(identity)
        row=copy.deepcopy(g);row.update(id=f'bl:train:own-variant:{len(variants):04}',split='train',panel='known',
            curriculum='own_error_variant',source_id=g['id'],past_misread=item['hypothesis'],original_questions=[])
        variants.append(row)
        if len(variants)==240:break
    output['train']+=variants;contrast=len(variants)
    print(json.dumps({'own_error_teacher_variant_ASTs':contrast}),flush=True)
    # Additional structured probes test retention, not the headline natural metric.
    structured={};editorial={}
    for split,count,nums in [('development',80,DEV_NUMBERS),('closed',160,TEST_NUMBERS)]:
        values=[];accepted=0
        for turn in range(150):
            if accepted==count:break
            for i,(formula,text)in enumerate(TEMPLATES):
                a=nums[(i+turn)%len(nums)];b=nums[(i+turn+4)%len(nums)];expr=parse_expression(formula.format(a=a,b=b))
                spec={'X':expr,'writes':{f'R{(i+turn)%15:X}':expr}if i%4==0 else{},'angle':'DEG'if i%3 else'RAD'}
                key=signature(spec)
                if key in seen or paths3(expr)&all_held:continue
                g=make(vm,spec,f'bl:{split}:editorial:{accepted:03}',split,'editorial','editorial',rng.randrange(2**31))
                if not g:continue
                q=text.format(a=a,b=b)
                for r in spec['writes']:q+=' Запиши полученный результат в '+r+'.'
                g.update(task=q,pool=pool_for(q),style='editorial',curriculum='new_editorial',editorial_template=i)
                g['reference_body']=compile_spec(spec,g['pool']);g['spec_body']=encode(spec,g['pool'])
                values.append(g);seen.add(key);accepted+=1
                if accepted==count:break
        assert accepted==count;editorial[split]=values
        values=[];attempt=0
        while len(values)<count:
            attempt+=1;expr=tree(rng,nums,attempt%3==0,0,2)
            spec={'X':expr,'writes':{},'angle':rng.choice(['DEG','RAD','GRAD'])};key=signature(spec)
            if key in seen or paths3(expr)&all_held:continue
            g=make(vm,spec,f'bl:{split}:structured:{len(values):03}',split,'structured','structured',rng.randrange(2**31))
            if not g:continue
            values.append(g);seen.add(key)
        structured[split]=values
    # Preserve only candidate strings that correspond to the retained AST and angle.
    for g in output['train']:g['original_questions']=[]if g.get('curriculum')=='own_error_variant'else raw.get(signature(g['spec']),[]) or [g['task']]
    files=[]
    for split,values in output.items():
        name=split+'-asts.jsonl';save_rows(ROOT/name,values);files.append(name)
    for split in ['development','closed']:
        for kind,values in [('editorial',editorial[split]),('structured',structured[split])]:
            name=split+'-'+kind+'.jsonl';save_rows(ROOT/name,values);files.append(name)
    write(ROOT/'ast-frozen.json',{'files':{n:sha(ROOT/n)for n in files},'counts':{s:len(v)for s,v in output.items()},
        'retired_BE_development_and_closed':True,'original_natural_candidates':sum(len(g['original_questions'])for g in output['train']),
        'contrast_ASTs':contrast,'dev_triples':sorted(dev_held),'test_triples':sorted(test_held),
        'dev_numbers':DEV_NUMBERS,'test_numbers':TEST_NUMBERS,'normalized_prior_signatures_excluded':True,
        'verification':'relative2e-6 for nonzero, absolute1e-12 only for zero; ROM sign(0)=0',
        'rejections':dict(rejects),'closed_model_generations_seen':False,'SGD_started':False,'seconds':time.monotonic()-started})
    print(json.dumps({'AST_bank_complete':True,'counts':read(ROOT/'ast-frozen.json')['counts'],'natural_candidates':read(ROOT/'ast-frozen.json')['original_natural_candidates']}),flush=True)

if __name__=='__main__':main()
