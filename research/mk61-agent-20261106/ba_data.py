"""Fresh held-out tasks plus explicitly retired previous-exam errors."""
import collections
import copy
from decimal import Decimal
import json
import random
import time
from ba_common import ROOT,PRIORS,PARENT,DEV_NUMBERS,TEST_NUMBERS,TRAIN_NUMBERS,read,rows,write,save_rows,sha
from az_data import tree,numbers
from ay_data import make,edges,op_count
from ay_finalize import semantic_key
from full_isa_math import UNARY,BINARY,registers
from full_isa_vm import FullVM
from ar_spec import expected,verify
from ay_codec import compile_spec


def mutated_specs(source):
    expr=source['X'];out=[]
    def visit(node,path):
        if isinstance(node,list):
            alternatives={'sin':'cos','cos':'sin','asin':'sin','square':'sqrt','sqrt':'square','+':'-','-':'+','*':'/','/':'*','ln':'log10','frac':'int','abs':'neg','exp':'pow10'}
            if node[0]in alternatives:out.append((path,[alternatives[node[0]],*copy.deepcopy(node[1:])]))
            if node[0]in ['-','/','pow']:out.append((path,[node[0],*copy.deepcopy(node[1:][::-1])]))
            if node[0]in UNARY:out.append((path,copy.deepcopy(node[1])))
            for i,c in enumerate(node[1:],1):visit(c,path+[i])
    visit(expr,[])
    for path,replacement in out:
        new=copy.deepcopy(expr)
        if not path:new=replacement
        else:
            at=new
            for i in path[:-1]:at=at[i]
            at[path[-1]]=replacement
        yield {**source,'X':new,'writes':{r:new for r in source['writes']}}


def main():
    ROOT.mkdir(parents=True,exist_ok=True)
    if(ROOT/'ast-frozen.json').exists():return
    vm=FullVM();rng=random.Random(26110841);seen=set()
    for prior in PRIORS:
        for split in ['train','development','closed']:seen.update(semantic_key(g['spec'])for g in rows(prior/(split+'-clean.jsonl')))
    previous={g['id']:g for g in rows(PARENT/'closed-clean.jsonl')};exam=read(PARENT/'spec/closed.json')
    retired_ids={r['task_id']for gate in ['raw','self']for r in exam[gate]['records']if r['finished']and not r['program_correct']}
    retired_ids|={r['id']for r in exam['pool_stress']['records']if not r['program_correct']}
    retired=[]
    for identifier in sorted(retired_ids):
        g=copy.deepcopy(previous[identifier]);g.update(id='ba:retired:'+identifier,source_id=identifier,split='train',panel='known',curriculum='retired_exam_error')
        retired.append(g)
    # No old development questions are training data; opened exam mistakes are explicitly retired.
    grouped=collections.defaultdict(list)
    for g in rows(PARENT/'train-clean.jsonl'):grouped[g['id']].append(g)
    replay=[]
    from ba_teacher import clean_wording
    eligible=[k for k,v in grouped.items()if all(clean_wording(x['task'])for x in v)
              and not(numbers(v[0]['spec']['X'])&set(DEV_NUMBERS+TEST_NUMBERS))]
    for identifier in rng.sample(sorted(eligible),400):
        for g in grouped[identifier]:
            g=copy.deepcopy(g);g.update(id='ba:replay:'+identifier,source_id=identifier,split='train',panel='known',curriculum='replay')
            replay.append(g)
    occupied=set().union(*(edges(g['spec']['X'])for g in replay+retired))
    candidates=[(a,b)for a in list(UNARY)+list(BINARY)for b in UNARY if(a,b)not in occupied and a not in ['pow','exp','pow10']and b not in ['exp','pow10']]
    held=rng.sample(sorted(candidates),12);dev_edges=set(held[:6]);test_edges=set(held[6:]);all_held=set(held)
    save_rows(ROOT/'replay-goals.jsonl',replay);save_rows(ROOT/'retired-goals.jsonl',retired)
    output={};started=time.monotonic()
    quotas={'train':[('known',{'constant':320,'numeric':320,'register':160})],
      'development':[('known',{'constant':32,'numeric':32,'register':16}),('novel',{'constant':32,'numeric':32,'composition':16})],
      'closed':[('known',{'constant':80,'numeric':80,'register':40}),('novel',{'constant':80,'numeric':80,'composition':40})]}
    for split,panels in quotas.items():
        values=list(retired)if split=='train'else[]
        for panel,families in panels:
            literals=DEV_NUMBERS if split=='development'and panel=='novel'else TEST_NUMBERS if split=='closed'and panel=='novel'else TRAIN_NUMBERS
            for family,n in families.items():
                accepted=0;attempts=0
                while accepted<n:
                    attempts+=1
                    if attempts>n*10000:raise RuntimeError((split,family,accepted))
                    if family=='composition':
                        parent,child=rng.choice(sorted(dev_edges if split=='development'else test_edges))
                        sub=[child,tree(rng,literals,False,1,2)]
                        expr=[parent,sub]if parent in UNARY else[parent,sub,tree(rng,literals,False,1,2)]
                    elif family=='numeric':
                        a=tree(rng,literals,False,1,2)if rng.random()<.4 else rng.choice([f'R{x:X}'for x in range(15)])
                        b={'constant':rng.choice(literals)};expr=[rng.choice(list(BINARY)),a,b]
                        if rng.random()<.4:expr=[expr[0],b,a]
                    else:expr=tree(rng,literals,family=='constant',0,2 if family=='constant'else 3)
                    if op_count(expr)>5 or(family!='constant'and not registers(expr)):continue
                    if family in ['numeric','constant']and not numbers(expr):continue
                    es=edges(expr)
                    if family!='composition'and es&all_held:continue
                    if family=='composition'and es&(test_edges if split=='development'else dev_edges):continue
                    spec={'X':expr,'writes':{rng.choice([f'R{x:X}'for x in range(15)]):expr}if rng.random()<.2 else{},'angle':rng.choice(['RAD','DEG','GRAD'])}
                    if semantic_key(spec)in seen:continue
                    if not registers(expr):
                        try:
                            if abs(expected(spec,{})['X'])>1e6:continue
                        except (ValueError,ArithmeticError):continue
                    g=make(vm,spec,f'ba:{split}:{panel}:{family}:{accepted:04}',split,panel,family,rng.randrange(2**31))
                    if not g:continue
                    g['curriculum']='new';values.append(g);seen.add(semantic_key(spec));accepted+=1
        # Near-neighbour conditions give the same observed program both positive and negative labels.
        if split=='train':
            bases=[g for g in values if g['curriculum']=='new'];rng.shuffle(bases);pairs=0
            for base in bases:
                for spec in mutated_specs(base['spec']):
                    if semantic_key(spec)in seen or edges(spec['X'])&all_held:continue
                    partner=make(vm,spec,f'ba:train:contrast:{pairs:04}',split,'known',base['family'],rng.randrange(2**31))
                    if not partner:continue
                    try:
                        body=compile_spec(spec,base['pool'])
                        if verify(vm,body,base['pool'],spec,base['public_inputs']+base['checker_inputs']+base['audit_inputs'])['status']!='TESTED':continue
                        if verify(vm,base['reference_body'],base['pool'],spec,base['audit_inputs'])['status']!='FAIL':continue
                    except (ValueError,ArithmeticError):continue
                    partner.update(public_inputs=base['public_inputs'],checker_inputs=base['checker_inputs'],audit_inputs=base['audit_inputs'],
                        curriculum='contrast',contrast_base=base['id'])
                    base['contrast_partner']=partner['id'];values.append(partner);seen.add(semantic_key(spec));pairs+=1;break
                if pairs==200:break
            assert pairs>=160,pairs
        save_rows(ROOT/(split+'-asts.jsonl'),values);output[split]=len(values)
        print(json.dumps({'split':split,'ASTs':len(values),'seconds':time.monotonic()-started}),flush=True)
    names=[s+'-asts.jsonl'for s in output]+['replay-goals.jsonl','retired-goals.jsonl']
    write(ROOT/'ast-frozen.json',{'files':{n:sha(ROOT/n)for n in names},'sizes':output,'replay_questions':len(replay),
      'retired_previous_exam_tasks':len(retired),'previous_exam_no_longer_a_holdout':True,
      'dev_edges':sorted(dev_edges),'test_edges':sorted(test_edges),'DEV_numbers':DEV_NUMBERS,'TEST_numbers':TEST_NUMBERS,
      'new_closed_prior_signatures_excluded':True,'closed_model_generations_seen':False,'SGD_started':False})


if __name__=='__main__':main()
