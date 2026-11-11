"""Four matched candidates per task; every wrong candidate fails a public ROM case."""
import collections
import copy
from decimal import Decimal
import hashlib
import json
import math
import random
import shutil
from ap_common import ROOT,PARENT,HERE,INITIAL,INITIAL_PACKET,ERROR_CLASSES as CLASSES,read,write,sha
from full_isa_math import UNARY,BINARY,value,compile_expr,literal
from full_isa_prepare import base_inputs
from full_isa_protocol import REGISTERS
from full_isa_vm import FullVM,state_match
from ha_protocol import constants,encode,assemble
from am_data import safe_view
from ap_runtime import render, diagnosis
from tasks import save_jsonl

NAMES={'neg':'смена знака','pow10':'десять в степени','exp':'экспонента','log10':'десятичный логарифм',
 'ln':'натуральный логарифм','asin':'арксинус','acos':'арккосинус','atan':'арктангенс','sin':'синус','cos':'косинус',
 'tan':'тангенс','sqrt':'квадратный корень','square':'квадрат','reciprocal':'обратное число','abs':'модуль',
 'sign':'знак по правилу МК-61','int':'целая часть','frac':'дробная часть'}
BIN={'-':'разность','/':'частное','+':'сумма','*':'произведение'}
FRAMES={'train':['Для {s} выполни по порядку: {a}; {b}.','Исходное значение — {s}. Сначала {a}, затем {b}.',
 'Порядок вычисления для {s}: {a}, после этого {b}.','Требуются два шага над {s}: {a}; далее {b}.'],
 'development':['Начни с {s}: первым преобразованием будет {a}, вторым — {b}.','Обработай {s} в последовательности {a} → {b}.'],
 'fresh':['Нужна программа для {s}: сперва получи {a}, а от результата — {b}.','Возьми {s}; вычисления должны идти так: {a}, потом {b}.']}


def partition(tag):
    n=int(hashlib.sha256(("ap-v1:"+tag).encode()).hexdigest()[:8],16)%10
    return 'novel-development'if n==0 else'novel-fresh'if n==1 else'known'


def pair_tag(family,a,b):
    return family+':'+':'.join(sorted([a,b]))


def finite_values(expr,states,angle):
    try:
        ys=[value(expr,s,angle)for s in states]
        return ys if all(not isinstance(y,complex)and math.isfinite(y)and abs(y)<1e6 for y in ys)else None
    except (ArithmeticError,ValueError,OverflowError,TypeError):return None


def changed(a,b):return any(not math.isclose(x,y,rel_tol=2e-6,abs_tol=2e-6)for x,y in zip(a,b))


def number(rng,split):
    end=rng.choice('1379'if split=='train'else'2468')
    return ('-'if rng.random()<.25 else'')+str(rng.randrange(0,4))+'.'+str(rng.randrange(10,99))+end


def proposal(rng,split,family):
    novel=split if split.startswith('novel-')else'known';word_split='development'if'development'in split else'fresh'if'fresh'in split else'train'
    angle=rng.choice(['RAD','DEG','GRAD']);ra,rb,rc,rd=rng.sample(REGISTERS,4)
    states=[base_inputs(rng)for _ in range(6)]
    grid=rng.choice([['.137','.283','.419','.567','.731','.893'],['1.137','1.283','1.419','1.567','1.731','1.893'],
      ['-.837','-.619','-.283','.137','.419','.731'],['-3.137','-1.619','.283','.837','1.419','2.731']])
    if split!='train':grid=[str(Decimal(x)+Decimal('.002'))for x in grid]
    for i,s in enumerate(states):
        for j,r in enumerate([ra,rb,rc,rd]):s[r]=grid[(i+2*j)%6]
    source_kind=rng.choice(['register','constant'])if family=='unary'else'register'
    leaf=ra if source_kind=='register'else{'constant':number(rng,split)}
    alt=rc if source_kind=='register'else{'constant':number(rng,split)}
    if leaf==alt:return None
    src=ra if source_kind=='register'else str(leaf['constant'])
    pool=None;operator_options=[];subtype='constant'if source_kind=='constant'else'load_register'
    if family=='unary':
        first,second=rng.sample(list(UNARY),2);tag=pair_tag(family,first,second)
        if partition(tag)!=novel:return None
        good=[second,[first,leaf]];order=[first,[second,leaf]];argument=[second,[first,alt]]
        code=compile_expr(good)+[0x50];order_code=compile_expr(order)+[0x50];arg_code=compile_expr(argument)+[0x50]
        prefix=len(compile_expr(leaf));text=rng.choice(FRAMES[word_split]).format(s=src,a=NAMES[first],b=NAMES[second])
        for where in [0,1]:
            for replacement in UNARY:
                pair=[first,second];old=pair[where]
                if replacement in pair:continue
                pair[where]=replacement
                if partition(pair_tag(family,*pair))!=novel:continue
                expr=[pair[1],[pair[0],leaf]];operator_options.append((prefix+where,UNARY[replacement],expr))
        preserve=True;store=None
    elif family=='binary':
        if novel!='known':return None
        op=rng.choice(['-','/']);tag='binary:'+op;good=[op,ra,rb];order=[op,rb,ra];argument=[op,rc,rb]
        code=compile_expr(good)+[0x50];order_code=compile_expr(order)+[0x50];arg_code=compile_expr(argument)+[0x50]
        text={'train':f'В X нужна {BIN[op]} {ra} и {rb}.','development':f'Найди {BIN[op]}: первое число в {ra}, второе в {rb}.',
          'fresh':f'Получи в X {BIN[op]} чисел из {ra} и {rb} в указанном порядке.'}[word_split]
        operator_options=[(2,BINARY[o],[o,ra,rb])for o in ['+','-','*','/']if o!=op];preserve=True;store=None
    elif family=='mixed':
        unary=rng.choice(list(UNARY));op=rng.choice(['+','-','*','/']);tag=pair_tag(family,unary,op)
        if partition(tag)!=novel:return None
        good=[unary,[op,ra,rb]];order=[op,[unary,ra],rb];argument=[unary,[op,rc,rb]]
        code=compile_expr(good)+[0x50];order_code=compile_expr(order)+[0x50];arg_code=compile_expr(argument)+[0x50]
        text={'train':f'Сначала {BIN[op]} {ra} и {rb}, затем {NAMES[unary]} результата.',
          'development':f'Для чисел {ra}, {rb} получи {BIN[op]}; к итогу примени {NAMES[unary]}.',
          'fresh':f'Нужно вычислить {NAMES[unary]} от результата: {BIN[op]} {ra} и {rb}.'}[word_split]
        operator_options=[(3,UNARY[o],[o,[op,ra,rb]])for o in UNARY if o!=unary and partition(pair_tag(family,o,op))==novel]
        operator_options += [(2,BINARY[o],[unary,[o,ra,rb]])for o in ['+','-','*','/']if o!=op and partition(pair_tag(family,unary,o))==novel]
        preserve=True;store=None
    else:
        if novel!='known':return None
        unary=rng.choice(list(UNARY));tag='memory:'+unary;good=[unary,ra];order=good;argument=[unary,rc]
        code=[0x60+int(ra[1:],16),UNARY[unary],0x40+int(rb[1:],16),0x50]
        order_code=[code[0],code[2],code[1],0x50]
        if rng.random()<.5:arg_code=[0x60+int(rc[1:],16),*code[1:]]
        else:arg_code=[code[0],code[1],0x40+int(rc[1:],16),0x50];argument=good;subtype='store_register'
        text={'train':f'Вычисли {NAMES[unary]} содержимого {ra}, запиши результат в {rb} и оставь его в X.',
          'development':f'Возьми число из {ra}. Требуется {NAMES[unary]}; итог помести в X и {rb}.',
          'fresh':f'Результат операции «{NAMES[unary]}» над {ra} должен оказаться в {rb} и в X.'}[word_split]
        operator_options=[(1,UNARY[o],[o,ra])for o in UNARY if o!=unary];preserve=False;store=rb
    text+=' Память R0–RE сохрани.'if preserve else f' Все регистры, кроме {store}, сохрани.'
    good_values=finite_values(good,states,angle);order_values=finite_values(order,states,angle);arg_values=finite_values(argument,states,angle)
    if good_values is None or order_values is None or arg_values is None:return None
    if family!='memory'and(not changed(good_values,order_values)or not changed(good_values,arg_values)):return None
    if family=='memory'and all(math.isclose(float(s[ra]),v,rel_tol=2e-6,abs_tol=2e-6)for s,v in zip(states,good_values)):return None
    rng.shuffle(operator_options);chosen=None
    for pc,opcode,expr in operator_options:
        ys=finite_values(expr,states,angle)
        if ys is not None and changed(good_values,ys):chosen=(pc,opcode);break
    if chosen is None:return None
    op_code=code[:];op_code[chosen[0]]=chosen[1]
    nop=[0x54]*rng.randrange(3);codes=[nop+op_code,nop+arg_code,nop+order_code,nop+code]
    assert collections.Counter(codes[2])==collections.Counter(codes[3])and codes[2]!=codes[3]
    assert len(codes[0])==len(codes[3])and sum(a!=b for a,b in zip(codes[0],codes[3]))==1
    if len({tuple(c)for c in codes})!=4:return None
    pool=constants(text)
    if source_kind=='constant':
        for x in [leaf['constant'],alt['constant']]:
            if str(x)not in pool:pool.append(str(x))
    rng.shuffle(pool)
    return {'task':text,'angle':angle,'codes':codes,'inputs':states,'pool':pool,'family':family,'pair_tag':tag,'argument_subtype':subtype}


def actual_record(actual,inputs):
    changes={r:actual['numeric'][r]if actual['numeric'][r]is not None else actual['raw'][r]for r in REGISTERS
      if actual['numeric'][r]is None or Decimal(actual['numeric'][r])!=Decimal(str(inputs[r]))}
    r={'status':actual['status'],'IP':actual['pc'],'X':actual['numeric']['X']or actual['raw']['X'],'Y':actual['numeric']['Y']or actual['raw']['Y']}
    if changes:r['memory']=changes
    return r


def label(vm,p,identity,split):
    outcomes=[]
    for code in p['codes']:
        vals=[]
        for inputs in p['inputs']:
            a,_=vm.execute(code,inputs,angle=p['angle'],max_commands=128,max_frames=1024)
            if a['status']!='stopped':return None
            vals.append(a)
        outcomes.append(vals)
    good=outcomes[3];names=['X',*REGISTERS]
    if any(all(state_match(a,b,names=names)for a,b in zip(vals[:3],good[:3]))for vals in outcomes[:3]):return None
    task={'id':identity,'task':p['task'],'angle':p['angle'],'constants':p['pool'],'reference_code':p['codes'][3],
      'public_tests':[{'segments':[{'inputs':s,'expected':g}]}for s,g in zip(p['inputs'][:3],good[:3])],
      'hidden_tests':[{'segments':[{'inputs':s,'expected':g}]}for s,g in zip(p['inputs'][3:],good[3:])],
      'check_names':names,'max_commands':128,'max_frames':1024}
    view=safe_view(task,p['pool']);rows=[]
    for target,code in enumerate(p['codes']):
        body=encode(code,p['pool'],'asm');assert assemble(body,p['pool'],'asm')==code
        runs={i:[actual_record(a,s)]for i,(a,s)in enumerate(zip(outcomes[target][:3],p['inputs'][:3]))}
        state={'view':view,'pool':p['pool'],'body':body,'runs':runs,'case':0,'revision':0,'remaining':10,'observation':None}
        rows.append({'id':identity+':'+CLASSES[target],'group_id':identity,'label':target,'class':CLASSES[target],
          'prompt':render(state),'code':code,'body':body,'state':state,'family':p['family'],'pair_tag':p['pair_tag'],
          'argument_subtype':p['argument_subtype'],'all_public_stopped':True,'public_counterexample':target!=3})
    return {'id':identity,'rows':rows,'task':task,'family':p['family'],'pair_tag':p['pair_tag']}


def lessons(groups):
    result=[]
    def add(g,state,action,body,truth,origin,**extra):
        result.append({'id':f'ap:lesson:{len(result):07}', 'group_id':g['id'], 'state':copy.deepcopy(state),
          'action':action,'body':body,'correctness':truth,'origin':origin,'family':g['family'],
          'pair_tag':g['pair_tag'],**extra})
    for g in groups:
        good=g['rows'][3];reference=good['body']
        goal={**copy.deepcopy(good['state']),'body':None,'runs':{},'diagnosis':None}
        add(g,goal,'write',reference,-1,'goal_program')
        for r in g['rows']:
            state=copy.deepcopy(r['state']);state['remaining']=12;state['diagnosis']=None
            d=diagnosis(r['body'],reference,r['class']);truth=int(r['class']=='correct')
            add(g,state,'diag',d,truth,'localized_diagnosis',error_kind=r['class'])
            if truth:
                add(g,state,'done',[],1,'correct_completed')
                state['diagnosis']={'body':d,'revision':0};state['remaining']=11
                add(g,state,'done',[],1,'correct_after_diagnosis')
                continue
            state['diagnosis']={'body':d,'revision':0};state['remaining']=11
            add(g,state,'write',reference,0,'diagnosis_to_repair',before_body=r['body'])
            # The first attempted repair can still be wrong. Its observed
            # state gets a fresh diagnosis, never a supervised incorrect WRITE.
            other=g['rows'][(r['label']+1)%3]
            recovery=copy.deepcopy(other['state']);recovery.update(revision=1,remaining=9,diagnosis=None,
              observation='Предыдущая правка выполнена; проверка нового кода продолжается.')
            add(g,recovery,'diag',diagnosis(other['body'],reference,other['class']),0,'failed_repair_rediagnosis',error_kind=other['class'])
            recovery['diagnosis']={'body':[0,255,255,0,0],'revision':1};recovery['remaining']=8
            add(g,recovery,'write',reference,0,'false_claim_recovery',before_body=other['body'])
            fixed=copy.deepcopy(good['state']);fixed.update(revision=2,remaining=8,diagnosis=None)
            all_runs=fixed['runs'];fixed['runs']={0:all_runs[0]}
            add(g,fixed,'run',[1],1,'verify_after_repair')
            fixed['runs'][1]=all_runs[1];fixed['case']=1;fixed['remaining']=7
            add(g,fixed,'run',[2],1,'verify_second_case')
            fixed['runs'][2]=all_runs[2];fixed['case']=2;fixed['remaining']=6
            add(g,fixed,'done',[],1,'verified_repair_done')
    return result


def main():
    ROOT.mkdir(exist_ok=True)
    if(ROOT/'data-frozen.json').exists():return
    vm=FullVM();seen=set();corpus={};rng=random.Random(171301)
    # Exclude every old AO task text, including its already-opened exams.
    for split in ['train','development','novel-development','fresh','novel-fresh']:
        for g in read(PARENT/(split+'.jsonl')):seen.add((g['task']['angle'],g['task']['task']))
    specs=[('train',{'unary':480,'binary':240,'mixed':240,'memory':240}),
      ('development',{'unary':32,'binary':16,'mixed':16,'memory':16}),
      ('novel-development',{'unary':24,'mixed':16}),
      ('fresh',{'unary':64,'binary':32,'mixed':32,'memory':32}),
      ('novel-fresh',{'unary':48,'mixed':32})]
    for split,quotas in specs:
        path=ROOT/(split+'.jsonl')
        if path.exists():
            corpus[split]=read(path);seen.update((g['task']['angle'],g['task']['task'])for g in corpus[split]);continue
        values=[]
        for family,n in quotas.items():
            accepted=0;attempts=0
            while accepted<n:
                attempts+=1
                if attempts>n*2000:raise RuntimeError(('Generation exhausted',split,family,accepted,attempts))
                p=proposal(rng,split,family)
                if p is None or(p['angle'],p['task'])in seen:continue
                g=label(vm,p,f'ap:{split}:{family}:{accepted:04}',split)
                if g is None:continue
                seen.add((p['angle'],p['task']));values.append(g);accepted+=1
                if accepted%40==0:print(json.dumps({'split':split,'family':family,'groups':accepted,'attempts':attempts}),flush=True)
        rng.shuffle(values);save_jsonl(path,values);corpus[split]=values
        print(json.dumps({'split':split,'groups':len(values),'episodes':4*len(values)}),flush=True)
    train_pairs={g['pair_tag']for g in corpus['train']}
    for split in ['novel-development','novel-fresh']:assert not train_pairs&{g['pair_tag']for g in corpus[split]}
    assert not{g['pair_tag']for g in corpus['novel-development']}&{g['pair_tag']for g in corpus['novel-fresh']}
    course=lessons(corpus['train']);save_jsonl(ROOT/'lessons.jsonl',course)
    shutil.copytree(PARENT/'core-source',ROOT/'core-source',dirs_exist_ok=True)
    policy={'arms':['full','short'],'steps':2500,'checkpoints':[500,1250,2500],'batch':32,
      'lr_lora':.00015,'lr_heads':.0003,'curriculum_steps':500,'Q4_every_forward':True,'fp32_training':True,'context':1024,
      'stage1':{'goal_program':8,'localized_diagnosis':8,'write':6,'run':4,'done':6},
      'stage2':{'goal_program':4,'localized_diagnosis':6,'write':10,'run':6,'done':6},
      'body_weight':2.,'changed_token_weight':3.,'semantic_weight':.3,'risk_weight':.5,'distill_weight':.1,
      'selection':'lexicographic: eligibility, minimum utility on known/novel development, overall success, -false DONE',
      'utility':'(success - 4*false_DONE)/episodes','release':{'minimum_panel_success':.8,'maximum_false_DONE_rate':.05,
      'minimum_correct_start_completion':.8},'source_profile':'released AJ lr10-terminal','max_turns':12,
      'runtime_no_gold_or_expected':True,'raw_DONE_not_vetoed':True,'old_actor_unchanged':True,
      'large_LLM_teacher_called':False,'teacher':'fixture compiler, actual ROM trajectories; frozen source full-prompt KL filtered by gold tokens'}
    write(ROOT/'policy.json',policy)
    files={p.name:sha(p)for p in ROOT.iterdir()if p.suffix in ['.json','.jsonl']and p.name not in ['data-frozen.json','start-launch.json']}
    write(ROOT/'data-frozen.json',{'files':files,'group_counts':{s:len(v)for s,v in corpus.items()},
      'episode_counts':{s:len(v)*4 for s,v in corpus.items()},'lesson_count':len(course),
      'lesson_actions':dict(collections.Counter(r['action']for r in course)),
      'unique_novel_pairs':{s:len({g['pair_tag']for g in corpus[s]})for s in ['novel-development','novel-fresh']},
      'source_master_sha256':sha(INITIAL/'model.safetensors'),'source_packet_sha256':sha(INITIAL_PACKET),
      'all_bad_have_public_counterexamples':True,'all_candidates_stopped':True,'order_preserves_raw_command_multiset':True,
      'new_texts_disjoint_across_splits_and_AO':True,'frozen_before_SGD':True})
    print(json.dumps({'frozen':True,'lessons':len(course),'episodes':{s:len(v)*4 for s,v in corpus.items()}}),flush=True)


if __name__=='__main__':main()

