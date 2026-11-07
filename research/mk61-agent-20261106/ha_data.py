"""New paired tasks, a sealed language exam and full-ISA retention fixtures."""
import collections
from decimal import Decimal
import hashlib
import json
import math
import random
import shutil
import time

from ha_common import ROOT,PREVIOUS,INITIAL,INITIAL_PACKET,HERE,read,sha,write
from ha_protocol import constants,encode,assemble,address,write_call,patch_call
from full_isa_math import UNARY,BINARY,compile_expr,value,registers,literal
from full_isa_protocol import REGISTERS
from full_isa_prepare import base_inputs,make_task
from full_isa_vm import FullVM
from natural_data import NAMES,symbolic,describe
from tasks import BUILD,save_jsonl

CORE=BUILD/'full-isa-v1'
if(CORE/'server-results/development.jsonl').exists():CORE=CORE/'server-results'


def number(rng,split,small=False):
    """Same precision distribution; hash-partition exact decimal values."""
    while True:
        if rng.random()<(.8 if small else .55):
            n=rng.randrange(1,6);digits=''.join(str(rng.randrange(10))for _ in range(n));text='0.'+digits
        else:text=str(rng.randrange(1,97))
        if rng.random()<.35:text='-'+text
        value_=Decimal(text)
        if value_==0:continue
        if small and abs(value_)>=1:continue
        bucket=int(hashlib.sha256(str(value_.normalize()).encode()).hexdigest()[:8],16)%10
        if (split=='train'and bucket<6)or(split=='validation'and bucket in [6,7])or(split=='fresh'and bucket in [8,9]):return text


def verified(vm,expr,text,identity,group,split,angle,rng,*,code=None,source='R',raw=False):
    code=code or compile_expr(expr)+[0x50];inputs=[]
    used=registers(expr)if expr is not None else set()
    for attempt in range(100):
        state=base_inputs(rng)
        for r in used:state[r]=rng.choice(['-.75','-.5','-.25','.125','.25','.5','.75','1','2','3','4','7'])
        if source=='X':state['X']=rng.choice(['-.75','-.5','-.25','.125','.25','.5','.75','1','2','3'])
        try:
            expected=value(expr,{'R0':state['X']},angle)if source=='X'and expr is not None else value(expr,state,angle)if expr is not None else None
            if expected is not None and(isinstance(expected,complex)or not math.isfinite(expected)or abs(expected)>1e6):continue
        except (ValueError,OverflowError,ZeroDivisionError,TypeError):continue
        actual,_=vm.execute(code,state,angle=angle,max_commands=128,max_frames=1024)
        if actual['status']!='stopped':continue
        if expected is not None:
            try:
                if abs(float(actual['numeric']['X'])-expected)>max(2e-6,abs(expected)*2e-6):continue
            except (ValueError,TypeError):continue
        inputs.append(state)
        if len(inputs)==6:break
    if len(inputs)<6:return None
    task=make_task(vm,code,text,identity,group,split,angle,inputs,kind='ha_task',targets=[],check_names=['X',*REGISTERS],raw=raw)
    task.update(expression=expr,source_kind=source,constants=constants(text),source='paired_authored_real_core')
    for arm in ['direct','asm']:
        body=encode(code,task['constants'],arm)
        assert assemble(body,task['constants'],arm)==code
    return task


def basic_tasks(vm,split,count,seed):
    rng=random.Random(seed);out=[];ops=list(UNARY);seen=set();attempts=0
    while len(out)<count:
        attempts+=1
        if attempts>count*300:raise RuntimeError('Basic task generation exhausted')
        i=len(out);slot=i%20;kind=0 if slot<5 else 1;op=ops[(i//4)%len(ops)];angle=rng.choice(['RAD','DEG','GRAD'])
        source='constant'if slot<15 else'R'if slot<19 else'X'
        n=number(rng,split,small=op in ['asin','acos','exp','pow10'])if source=='constant'else rng.choice(REGISTERS)
        if kind==0:
            forms={'train':['Выдай в X число {n}.','Введи константу {n} и заверши программу.','Мне нужен код, загружающий {n} в X.','Запрограммируй ввод числа {n}.'],
              'validation':['Нужна программа, оставляющая в X константу {n}.','После запуска в X должно быть ровно {n}.'],
              'fresh':['Загрузи в X точное значение {n} и остановись.','Сделай так, чтобы итоговым числом в X стало {n}.']}
            text=rng.choice(forms[split]).format(n=n);expr={'constant':n};group='literal_copy';code=None;raw=True
        else:
            x=n if source!='X'else'текущего X'
            forms={'train':['Подсчитай {f} от {x}.','Вычисли {f} для {x}.','Найди {f}({x}).','Получи {f} значения {x}.','Мне нужен {f} от {x}.'],
              'validation':['Верни в X результат: {f} от {x}.','Как запрограммировать {f} для {x}?'],
              'fresh':['Для {x} требуется получить {f}.','Составь программу: аргумент {x}, функция — {f}.']}
            text=rng.choice(forms[split]).format(f=NAMES[op],x=x)
            expr=[op,'R0'if source=='X'else{'constant':n}if source=='constant'else n]
            code=[UNARY[op],0x50]if source=='X'else None
            group={'constant':'literal_function','R':'register_source','X':'stack_source'}[source];raw=False
        text+=' Память R0–RE сохрани.'
        if (angle,text)in seen:continue
        task=verified(vm,expr,text,f'ha-{split}:basic:{i:05}',group,split,angle,rng,code=code,source=source,raw=raw)
        if task:out.append(task);seen.add((angle,text))
    return out


def composite_tasks(vm,split,count,seed):
    rng=random.Random(seed);out=[];ops=list(UNARY)+list(BINARY);seen=set()
    while len(out)<count:
        i=len(out);op=ops[i%len(ops)];angle=rng.choice(['RAD','DEG','GRAD'])
        a={'constant':number(rng,split,small=op in ['asin','acos','exp','pow10'])}if i%2==0 else rng.choice(REGISTERS)
        b,c=rng.sample(REGISTERS,2)
        base=[op,a]if op in UNARY else[op,a,b]
        shape=(i//len(ops))%4
        if shape==0:expr=['+',base,{'constant':number(rng,split,small=True)}]
        elif shape==1:expr=['-',base,['square',c]]
        elif shape==2:expr=[rng.choice(['abs','square','neg']),['+',base,c]]
        else:expr=['+',base,[rng.choice(['abs','square','neg']),b]]
        text=describe(expr,split,rng)
        if i%3==0:
            starts={'train':['Вычисли выражение ','Нужен HEX для X = ','Составь программу: '],
              'validation':['Получить в X нужно следующее: '], 'fresh':['Запрограммируй расчёт X = ']}
            text=rng.choice(starts[split])+symbolic(expr)
        else:
            starts={'train':['Вычисли ','Получи в X ','Запиши программу для расчёта: '],
              'validation':['Результатом программы должно стать '], 'fresh':['Построй вычисление для величины: ']}
            text=rng.choice(starts[split])+text
        text+='. Регистры памяти оставь без изменений.'
        if (angle,text)in seen:continue
        task=verified(vm,expr,text,f'ha-{split}:composite:{i:05}','composition',split,angle,rng)
        if task:out.append(task);seen.add((angle,text))
    return out


class Program:
    def __init__(self):self.code=[];self.labels={};self.relocations=[]
    def add(self,*ops):self.code.extend(ops);return self
    def mark(self,name):self.labels[name]=len(self.code);return self
    def jump(self,opcode,name):self.code.append(opcode);self.relocations.append((len(self.code),name));self.code.append(0);return self
    def finish(self):
        for at,name in self.relocations:self.code[at]=address(self.labels[name])
        return self.code


def algorithm_tasks(vm,split,count,seed):
    rng=random.Random(seed);out=[]
    for i in range(count):
        r,s=rng.sample(REGISTERS,2);kind=i%3;angle=rng.choice(['RAD','DEG','GRAD'])
        if kind==0:
            low,high=sorted([Decimal(number(rng,split,small=True)),Decimal(number(rng,split,small=True))])
            if low==high:high=low+1
            lo,hi=str(low),str(high)
            p=Program().add(0x60+int(r[1:],16),*literal(lo),0x11).jump(0x59,'low')
            p.add(0x60+int(r[1:],16),*literal(hi),0x11).jump(0x5C,'high').add(0x60+int(r[1:],16),0x50)
            p.mark('low').add(*literal(lo),0x50).mark('high').add(*literal(hi),0x50);code=p.finish()
            text=f'Ограничь значение {r} интервалом от {lo} до {hi}: ниже верни {lo}, выше верни {hi}, внутри верни само значение. Итог в X; память сохрани.'
            inputs=[]
            for x in [low-1,low,(low+high)/2,high,high+1,Decimal(0)]:
                state=base_inputs(rng);state[r]=str(x);inputs.append(state)
            expected=[min(max(Decimal(x[r]),low),high)for x in inputs]
            group='algorithm_clamp'
        elif kind==1:
            op=rng.choice([0x22,0x31,0x1C,0x1D]);name={0x22:'квадрата',0x31:'модуля',0x1C:'синуса',0x1D:'косинуса'}[op]
            p=Program().add(0x60+int(r[1:],16)).jump(0x53,'function').add(0x60+int(s[1:],16),0x10,0x50)
            p.mark('function').add(op,0x52);code=p.finish()
            text=f'Вычисли сумму {name} {r} и {s}. Вычисление {name} оформи подпрограммой, которую основная программа вызывает с возвратом. Итог в X; память не меняй.'
            inputs=[base_inputs(rng)for _ in range(6)];opname={0x22:'square',0x31:'abs',0x1C:'sin',0x1D:'cos'}[op]
            expected=[value(['+',[opname,r],s],x,angle)for x in inputs];group='algorithm_subroutine'
        else:
            p=Program().add(0x60+int(r[1:],16)).jump(0x59,'negative')
            p.add(0x60+int(r[1:],16),0x60+int(s[1:],16),0x10,0x50)
            p.mark('negative').add(0x60+int(r[1:],16),0x0B,0x60+int(s[1:],16),0x11,0x50);code=p.finish()
            text=f'Если {r} неотрицателен, выдай сумму {r} и {s}; иначе выдай разность противоположного {r} и {s}. Память сохрани.'
            inputs=[base_inputs(rng)for _ in range(6)]
            for j,x in enumerate(inputs):x[r]=str([-3,-1,0,.25,1,3][j])
            expected=[float(x[r])+float(x[s])if float(x[r])>=0 else-float(x[r])-float(x[s])for x in inputs];group='algorithm_branch'
        if split=='validation':text='Новая программа: '+text
        elif split=='fresh':text='Реши на обычном МК-61 следующее задание. '+text
        task=make_task(vm,code,text,f'ha-{split}:algorithm:{i:04}',group,split,angle,inputs,kind='ha_task',check_names=['X',*REGISTERS])
        for case,target in zip(task['public_tests']+task['hidden_tests'],expected):
            actual=case['segments'][0]['expected'];assert actual['status']=='stopped'
            assert abs(float(actual['numeric']['X'])-float(target))<=max(2e-6,abs(float(target))*2e-6)
        task.update(constants=constants(text),source='authored_complete_algorithm',source_kind='R')
        assert assemble(encode(code,task['constants'],'asm'),task['constants'],'asm')==code
        out.append(task)
    return out


def main():
    ROOT.mkdir(exist_ok=True)
    if(ROOT/'data-frozen.json').exists():return
    vm=FullVM();sets={};seen=set();started=time.monotonic()
    for split,seed in [('train',6119201),('validation',6119202),('fresh',6119203)]:
        path=ROOT/(split+'.jsonl')
        if path.exists():rows=read(path)
        else:
            rows=basic_tasks(vm,split,4800 if split=='train'else 240,seed)
            print(json.dumps({'split':split,'basic':len(rows),'seconds':time.monotonic()-started}),flush=True)
            rows+=composite_tasks(vm,split,3000 if split=='train'else 240,seed+10)
            rows+=algorithm_tasks(vm,split,900 if split=='train'else 120,seed+20)
            unique={}
            for row in rows:unique.setdefault((row['angle'],row['task']),row)
            rows=list(unique.values())
            save_jsonl(path,rows)
        for row in rows:
            key=(row['angle'],row['task'])
            if key in seen:raise AssertionError('Duplicate task across frozen sets')
            seen.add(key)
        sets[split]=rows
        print(json.dumps({'split':split,'rows':len(rows),'seconds':time.monotonic()-started}),flush=True)
    # Retain all classic opcodes, old mathematical programs, and their exact fixtures.
    for old,new in [(CORE/'audit.jsonl','isa-audit.jsonl'),(CORE/'development.jsonl','isa-development.jsonl'),
      (CORE/'catalog.json','catalog.json'),(PREVIOUS/'fresh-language.jsonl','observed-previous-language.jsonl'),
      (PREVIOUS/'observed-user-reproductions.jsonl','observed-user-reproductions.jsonl')]:shutil.copyfile(old,ROOT/new)
    replay=[t for t in read(CORE/'train.jsonl')if t['kind']in ['primitive','programming','interactive_game','numeric_synthesis']]
    # Legacy expressions already have executable reference programs.
    legacy=read(PREVIOUS/'legacy-light.jsonl')
    light_keys=['id','task','angle','reference_code','kind','group','opcode','catalog_risk','source_kind','constants','source']
    light=[{k:t[k]for k in light_keys if k in t}for t in sets['train']+replay+legacy]
    save_jsonl(ROOT/'sft-light.jsonl',light)
    shutil.copytree(CORE/'core-source',ROOT/'core-source',dirs_exist_ok=True)
    from transformers import AutoTokenizer
    tokenizer=AutoTokenizer.from_pretrained(INITIAL,local_files_only=True,trust_remote_code=False)
    allowed={tokenizer.eos_token_id}
    for a in range(256):
        texts=[write_call([a,b])for b in range(256)]
        texts += ['<patch>00 00 '+f'{a:02X}'+'</patch><run/>',f'<run>{a:02X}</run>','<trace/>','<done/>']
        for ids in tokenizer(texts,add_special_tokens=False)['input_ids']:allowed.update(ids)
    write(ROOT/'output-token-ids.json',sorted(allowed))
    rng=random.Random(6119204)
    for split in ['validation','fresh']:
        groups=collections.defaultdict(list)
        for row in sets[split]:groups[row['group']].append(row)
        selected=[]
        for group,values in groups.items():rng.shuffle(values);selected+=values[:3 if split=='validation'else 12]
        write(ROOT/(split+'-tool-ids.json'),[t['id']for t in selected])
    policy={'arms':['direct','asm'],'steps_each':4000,'validation_interval':500,'effective_batch':128,'context':1024,
      'lr':2e-5,'embedding_lr_factor':.5,'warmup_updates':150,'weight_decay':.01,'memory_fraction_each':.8,
      'protect_non_output_embedding_rows':True,'qat':'Q4 from first update','max_new_tokens':512,
      'fresh_used_for_selection':False,'source_checkpoint':'full-isa-natural-v1/protected-best step2500',
      'goals':{'literal_accuracy':.90,'composition_accuracy':.80,'documented_instruction_accuracy':1.0},
      'tool_observations':'Actual status, IP, stack, memory changes and requested trace; no expected output or PASS/FAIL oracle',
      'numeric_values_hash_partitioned':True,'old_tests_are_observed_retests':True,'new_algorithms_are_authored_not_600_complete_games':True}
    write(ROOT/'policy.json',policy)
    files=['train.jsonl','validation.jsonl','fresh.jsonl','sft-light.jsonl','isa-audit.jsonl','isa-development.jsonl','catalog.json',
      'output-token-ids.json','observed-previous-language.jsonl','observed-user-reproductions.jsonl','validation-tool-ids.json','fresh-tool-ids.json','policy.json']
    frozen={'before_optimizer_updates':True,'initial_master_sha256':sha(INITIAL/'model.safetensors'),'initial_packet_sha256':sha(INITIAL_PACKET),
      'files':{name:sha(ROOT/name)for name in files},'private_core_files':{str(p.relative_to(ROOT/'core-source')):sha(p)for p in(ROOT/'core-source').rglob('*')if p.is_file()},
      'counts':{k:len(v)for k,v in sets.items()},'output_rows':len(allowed),'all_256_bytes_representable':True,
      'new_numeric_values_partitioned_by_hash':True,'fresh_labels_never_used_for_tool_feedback':True}
    write(ROOT/'data-frozen.json',frozen)
    print(json.dumps({k:v for k,v in frozen.items()if k not in ['files','private_core_files']}),flush=True)


if __name__=='__main__':main()
