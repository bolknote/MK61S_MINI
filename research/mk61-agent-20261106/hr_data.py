"""Explicit 0/1/-1, stack inputs and independent deeper arithmetic families."""
import collections
import hashlib
import json
import random
import shutil
import time

from hr_common import ROOT,BASE,INITIAL,INITIAL_PACKET,HERE,read,sha,write
from ha_data import verified
from ha_protocol import constants
from ha_tools import seed,lessons
from full_isa_math import UNARY
from full_isa_protocol import REGISTERS
from full_isa_vm import FullVM
from natural_data import NAMES
from tasks import random_expr,expression_text,family_of,save_jsonl

NUMBERS=['0','1','-1','-0.0','.125','-.875','1.25','12.75','.0001','-.0001']


def operations(e):return 0 if isinstance(e,str)else 1+sum(operations(x)for x in e[1:])
def stack(e):
    if isinstance(e,str):return 1
    return stack(e[1])if len(e)==2 else max(stack(e[1]),1+stack(e[2]))


def replay_family(code):
    expressions=[];unary={0x0B:'neg',0x22:'square',0x31:'abs'};binary={0x10:'+',0x11:'-',0x12:'*',0x13:'/'}
    for op in code:
        if op==0x50:break
        if 0x60<=op<=0x6E:expressions.append('R'+format(op-0x60,'X'))
        elif op in unary and expressions:expressions.append([unary[op],expressions.pop()])
        elif op in binary and len(expressions)>=2:
            right=expressions.pop();left=expressions.pop();expressions.append([binary[op],left,right])
        else:return None
    return expressions[0]if len(expressions)==1 else None


def hard_tasks(vm,split,count,seed_):
    rng=random.Random(seed_);out=[];seen=set()
    while len(out)<count:
        expr=random_expr(rng,5);n=operations(expr)
        if not 4<=n<=8 or stack(expr)>4:continue
        family=family_of(expr);bucket=int(hashlib.sha256(('hr:'+family).encode()).hexdigest()[:8],16)%10
        if not((split=='train'and bucket<6)or(split=='validation'and bucket in [6,7])or(split=='fresh'and bucket in [8,9])):continue
        formula=expression_text(expr)
        if formula in seen:continue
        forms={'train':['Напиши программу МК-61 для X = {e}.','МК-61. Вычисли {e}, результат оставь в X.','Нужен код МК-61: X = {e}.'],
          'validation':['Получи значение X = {e}; составь программу.'],
          'fresh':['Рассчитай на МК-61 выражение {e}. Ответ оставь в X.']}
        text=rng.choice(forms[split]).format(e=formula)+' Входы уже в регистрах, память сохрани. Остановись С/П.'
        t=verified(vm,expr,text,f'hr-{split}:hard:{len(out):05}','composition',split,'RAD',rng)
        if t:t['repair_category']='hard';t['family']=family;out.append(t);seen.add(formula)
    return out


def boundary_tasks(vm,split,count,seed_):
    rng=random.Random(seed_);out=[];seen=set();ops=list(UNARY)
    while len(out)<count:
        identity=rng.random()<.18;op=rng.choice(ops);angle=rng.choice(['RAD','DEG','GRAD'])
        source='constant'if identity or rng.random()<.7 else rng.choice(['X','R'])
        if source=='constant':
            number=rng.choice(NUMBERS)
            if identity:
                forms={'train':['Выдай в X число {x}.','Загрузи константу {x} в X.','Введи число {x} и остановись.','Нужно получить ровно {x} в X.','Составь программу ввода {x}.'],
                  'validation':['Сделай результат X равным {x}.','Программа должна оставить в X значение {x}.'],
                  'fresh':['Положи в X точное число {x}, затем С/П.','После запуска требуется единственное значение {x} в X.']}
                text=rng.choice(forms[split]).format(x=number);expr={'constant':number};group='literal_copy'
            else:
                forms={'train':['Подсчитай {f} {x}.','Вычисли {f} от {x}.','Дай код: {f}({x}).','Мне нужен {f} для числа {x}.','Найди {f} числа {x}.'],
                  'validation':['Запрограммируй {f} значения {x}.','Для аргумента {x} найди {f}.'],
                  'fresh':['Получи {f}, аргументом служит число {x}.','Операция — {f}; исходное число равно {x}.']}
                text=rng.choice(forms[split]).format(f=NAMES[op],x=number);expr=[op,{'constant':number}];group='literal_function'
            code=None
        else:
            r=rng.choice(REGISTERS)if source=='R'else'X'
            if source=='X':
                forms={'train':['Вычисли {f} текущего X.','Аргумент уже в X. Найди {f}.','Обработай X: нужен {f}.','Найди {f} от значения в X.','Возьми {f} текущего значения X.'],
                  'validation':['В стеке X находится аргумент; вычисли {f} от него.'],
                  'fresh':['Примени к текущему X функцию: {f}.']}
                expr=[op,'R0'];code=[UNARY[op],0x50];group='stack_source'
            else:
                forms={'train':['Вычисли {f} {r}.','Аргумент находится в {r}. Получи {f}.','Найди {f} от {r}.'],
                  'validation':['Для числа из {r} вычисли {f}.'],
                  'fresh':['Возьми {r} как аргумент и получи {f}.']}
                expr=[op,r];code=None;group='register_source'
            text=rng.choice(forms[split]).format(f=NAMES[op],r=r)
        text+=' Итог в X, память сохрани.'
        if(angle,text)in seen:continue
        t=verified(vm,expr,text,f'hr-{split}:boundary:{len(out):05}',group,split,angle,rng,
          code=code,source=source,raw=identity)
        if t:t['repair_category']='boundary';out.append(t);seen.add((angle,text))
    return out


def main():
    ROOT.mkdir(exist_ok=True)
    if(ROOT/'data-frozen.json').exists():return
    vm=FullVM();sets={};started=time.monotonic()
    for split,nb,nh,s in [('train',1080,1600,6120101),('validation',120,120,6120102),('fresh',160,200,6120103)]:
        p=ROOT/(split+'.jsonl')
        if p.exists():rows=read(p)
        else:
            rows=boundary_tasks(vm,split,nb,s)+hard_tasks(vm,split,nh,s+10);save_jsonl(p,rows)
        sets[split]=rows;print(json.dumps({'split':split,'rows':len(rows),'seconds':time.monotonic()-started}),flush=True)
    names=['catalog.json','output-token-ids.json','isa-audit.jsonl','isa-development.jsonl','legacy-development.jsonl',
      'observed-user-reproductions.jsonl','observed-previous-language.jsonl','retention-floors.json']
    for name in names:shutil.copyfile(BASE/name,ROOT/name)
    shutil.copyfile(BASE/'fresh.jsonl',ROOT/'observed-ablation.jsonl');shutil.copytree(BASE/'core-source',ROOT/'core-source',dirs_exist_ok=True)
    keys=['id','task','angle','reference_code','kind','group','opcode','catalog_risk','source_kind','constants','source','repair_category']
    replay=[];excluded=0
    for t in read(BASE/'sft-light.jsonl'):
        expression=replay_family(t['reference_code'])
        if expression is not None and operations(expression)>=4:
            bucket=int(hashlib.sha256(('hr:'+family_of(expression)).encode()).hexdigest()[:8],16)%10
            if bucket>=6:excluded+=1;continue
        replay.append(t)
    light=replay+[{k:t[k]for k in keys if k in t}for t in sets['train']]
    save_jsonl(ROOT/'sft-light.jsonl',light)
    lessons_=read(BASE/'tool-lessons.jsonl')
    for i,t in enumerate([t for t in sets['train']if t['repair_category']=='boundary'][:64]):lessons_+=lessons(t,seed(t,correct=i%5==0,vm=vm,salt=6120110),vm)
    save_jsonl(ROOT/'tool-lessons.jsonl',lessons_)
    rng=random.Random(6120111)
    for split in ['validation','fresh']:
        grouped=collections.defaultdict(list)
        for t in sets[split]:grouped[t['group']].append(t)
        chosen=[]
        for values in grouped.values():rng.shuffle(values);chosen+=values[:3 if split=='validation'else 8]
        seeds=[seed(t,correct=i%4==0,vm=vm,salt=6120112)for i,t in enumerate(chosen)]
        save_jsonl(ROOT/(split+'-tool-seeds.jsonl'),seeds)
    # Keep the same original retention floors, strengthen the legacy target to 64/98.
    floors=json.loads((ROOT/'retention-floors.json').read_text());floors['legacy']=64/98;write(ROOT/'retention-floors.json',floors)
    policy={'steps_each':1200,'validation_interval':300,'effective_batch':128,'context':1024,'lr':1e-5,'embedding_lr_factor':.5,
      'warmup_updates':80,'weight_decay':.01,'learning_rate_scale':{'slow':.25,'fast':1.},'fresh_used_for_selection':False,
      'format':'asm','source':'harness-ablation-v1/asm-best step2500','quotas':{'hard':72,'boundary':24,'primitive':12,'algorithm':8,'tool':8,'language':4},
      'goal':'repair 0/1/-1 and source X/R, restore at least64/98 legacy without losing full ISA; preserve original ablation results'}
    write(ROOT/'policy.json',policy)
    files=names+['train.jsonl','validation.jsonl','fresh.jsonl','sft-light.jsonl','tool-lessons.jsonl','observed-ablation.jsonl',
      'validation-tool-seeds.jsonl','fresh-tool-seeds.jsonl','policy.json']
    frozen={'before_optimizer_updates':True,'initial_master_sha256':sha(INITIAL/'model.safetensors'),'initial_packet_sha256':sha(INITIAL_PACKET),
      'files':{n:sha(ROOT/n)for n in files},'private_core_files':{str(p.relative_to(ROOT/'core-source')):sha(p)for p in(ROOT/'core-source').rglob('*')if p.is_file()},
      'counts':{k:len(v)for k,v in sets.items()},'new_hard_families_hash_partitioned':True,'excluded_replay_rows_of_held_families':excluded,
      'old_ablation_is_observed_retest':True,'initial_checkpoint_may_have_prior_exposure_to_families':True}
    write(ROOT/'data-frozen.json',frozen);print(json.dumps({k:v for k,v in frozen.items()if k not in ['files','private_core_files']}),flush=True)


if __name__=='__main__':main()
