"""Executable full-command lessons, scientific synthesis and stateful programs."""
import collections
import hashlib
import json
import math
from pathlib import Path
import random
import re
import shutil
import time

from full_isa_protocol import REGISTERS,answer,prompt,linear_instructions
from full_isa_vm import ROOT,HERE,REPO,FullVM,STACK,check_task
from full_isa_math import UNARY,BINARY,WORDS,compile_expr,value,words,registers,literal
from tasks import BUILD,save_jsonl

DESCRIPTIONS={0x0A:'ввести десятичную точку',0x0B:'сменить знак X',0x0C:'выполнить ввод порядка ВП',0x0D:'очистить X',
 0x0E:'поднять стек командой В↑',0x0F:'вернуть прежнее X командой F Вx',0x10:'сложить Y и X',0x11:'вычесть X из Y',
 0x12:'умножить Y на X',0x13:'разделить Y на X',0x14:'поменять X и Y местами',0x15:'возвести десять в степень X',
 0x16:'вычислить экспоненту X',0x17:'найти десятичный логарифм X',0x18:'найти натуральный логарифм X',
 0x19:'получить арксинус X',0x1A:'получить арккосинус X',0x1B:'получить арктангенс X',0x1C:'вычислить синус X',
 0x1D:'вычислить косинус X',0x1E:'вычислить тангенс X',0x20:'ввести константу π',0x21:'извлечь квадратный корень из X',
 0x22:'возвести X в квадрат',0x23:'получить число, обратное X',0x24:'возвести X в степень Y командой F x^y',
 0x25:'циклически сдвинуть стек командой F ↻',0x26:'преобразовать число командой К °→′',0x2A:'преобразовать число командой К °→′″',
 0x30:'преобразовать минуты и секунды командой К °←′″',0x31:'взять модуль X',
 0x32:'выполнить К ЗН: для отрицательного X получить −1, для остальных +1',0x33:'преобразовать минуты командой К °←′',
 0x34:'оставить целую часть X, отбрасывая дробную к нулю',0x35:'оставить дробную часть X с её знаком',
 0x36:'выполнить К max по правилам МК-61, где ноль считается наибольшим',
 0x37:'выполнить логическое И мантисс командой К ∧',0x38:'выполнить логическое ИЛИ мантисс командой К ∨',
 0x39:'выполнить логическое исключающее ИЛИ мантисс командой К ⊕',0x3A:'инвертировать разряды мантиссы командой К ИНВ',
 0x3B:'получать новое псевдослучайное число К СЧ при каждом продолжении',0x50:'остановить программу командой С/П',
 0x54:'выполнить К НОП',0x55:'выполнить пустую команду К 1',0x56:'выполнить пустую команду К 2'}
PREFIXES={
 'train':['Требуется программа МК-61: ','Напиши код: ','Сделай на МК-61 следующее: ','Подготовь программу, которая должна ','МК-61. Нужно ','Составь короткую программу: '],
 'validation':['Для калькулятора требуется ','Сформируй программу со следующим действием: '],
 'audit':['Поручение для МК-61: ','Нужен исполняемый HEX для следующей операции: ','Пожалуйста, запрограммируй: ']}


def write(path,value):path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def base_inputs(rng):
    inputs={r:str(rng.choice([-7,-3,-1,0,2,5,11]))for r in REGISTERS}
    inputs.update(X=str(rng.choice([-3,-.5,0,.25,2,5])),Y=str(rng.choice([.5,2,3,7])),Z='13',T='17',X1='-19')
    return inputs


def fixtures(vm,code,inputs,angle,*,resume=False):
    result=[]
    for initial in inputs:
        state,context=vm.execute(code,initial,angle=angle,max_commands=128,max_frames=1024)
        if state['status']=='internal_error':raise ValueError('Core failure')
        segments=[{'inputs':initial,'expected':state}]
        if resume:
            for later in [{'X':'0','Y':'0'},{'X':'2','Y':'8'}]:
                state,context=vm.execute(None,later,context=context,max_commands=128,max_frames=1024)
                segments.append({'inputs':later,'expected':state})
        result.append({'segments':segments})
    return result


def primitive(row):
    op=row['code'];name=row['name'];check_pc=True;resume=False
    if op<=9:description='ввести цифру '+str(op)
    elif 0x40<=op<=0x4E:description='записать X в регистр R'+format(op%16,'X')
    elif 0x60<=op<=0x6E:description='вызвать в X значение регистра R'+format(op%16,'X')
    else:description=DESCRIPTIONS.get(op,'выполнить команду «'+name+'»')
    code=[op,0x50]
    if op in [0x51,0x53,0x52]:
        code=[0x51,0x04,0x50,0x54,0x50]if op==0x51 else[0x53,0x04,0x50,0x54,0x52]
        description=('перейти командой БП к адресу 04, где находится С/П'if op==0x51 else
          'вызвать подпрограмму по адресу 04 и после её немедленного возврата остановиться в ячейке 02; возврат стоит в ячейке 04')
    elif op in [0x57,0x59,0x5C,0x5E]:
        condition={0x57:'X не равно нулю',0x59:'X неотрицательно',0x5C:'X меньше нуля',0x5E:'X равно нулю'}[op]
        code=[op,0x04,0x50,0x54,0x50]
        description='проверить условие «'+condition+'»: при истине перейти к С/П в ячейке 02, иначе к С/П в ячейке 04'
    elif op in [0x58,0x5A,0x5B,0x5D]:
        n={0x58:2,0x5A:3,0x5B:1,0x5D:0}[op];code=[op,0x00,0x50]
        description=f'выполнять пустой цикл L{n} по адресу 00, используя штатный счётчик R{n}, и затем остановиться'
    elif 0x70<=op<=0xEF:
        reg=op%16 if op%16<15 else 0;base=op&0xF0
        if base==0xA0:
            code=[op,0x50]+[0x52]*16;description=f'вызвать подпрограмму косвенно через R{reg:X}; в ячейке 01 С/П, во всех ячейках 02–17 немедленный В/О'
        elif base in [0x70,0x80,0x90,0xC0,0xE0]:
            code=[op]+[0x50]*17
            description=('выполнить '+name+f'; все ячейки 01–17 содержат С/П. Адрес берётся по штатным правилам косвенной адресации МК-61 через R{reg:X}')
        else:description='выполнить '+name+' по штатным правилам косвенной адресации МК-61 и остановиться'
    elif op==0x3B:
        code=[0x3B,0x50,0x51,0x00];resume=True;description=DESCRIPTIONS[op]+'; после С/П программа должна возвращаться к адресу 00'
    if row['risk']!='documented'and not row['keyboard_enterable']:
        description=f'исполнить явно заданный сырой код {op:02X} в обычном режиме МК-61, затем С/П'
        if 0x70<=op<=0xEF:description+='; для переходов все ячейки 01–17 содержат С/П, для вызова — С/П в 01 и В/О в 02–17'
    return code,description,check_pc,resume


def primitive_inputs(op,rng,count=6):
    result=[]
    for i in range(count):
        x=base_inputs(rng)
        if op in [0x15,0x16]:x['X']=str([-1,-.5,0,.5,1,2][i])
        if op in [0x17,0x18,0x21,0x23]:x['X']=str([.25,1,2,5,0,-1][i])
        if op in [0x19,0x1A]:x['X']=str([-1,-.5,0,.5,1,2][i])
        if op in [0x1B,0x1C,0x1D,0x1E]:x['X']=str([-45,-1,0,22,45,90][i])
        if op==0x24:x.update(X=str([.5,2,3,4,-1,0][i]),Y=str([2,3,2,.5,2,2][i]))
        if op in [0x26,0x2A,0x30,0x33]:x['X']=[ '0','1.25','12.3','-5.15','0.75','23.5959'][i]
        if op in [0x34,0x35,0x32]:x['X']=['-2.75','-1','0','0.25','1.5','7'][i]
        if 0x37<=op<=0x3A:x.update(X=['8.010101','8.7','8.9','8.1234567','-8.010101','0'][i],Y=['8.1010101','8.8','8.6','8.7654321','8.1111111','0'][i])
        if op==0x36:x.update(X=['2','-2','0','3','5','-1'][i],Y=['3','0','7','-3','0','-2'][i])
        if op in [0x58,0x5A,0x5B,0x5D]:x['R'+str({0x58:2,0x5A:3,0x5B:1,0x5D:0}[op])]=str(i+1)
        if 0x70<=op<=0xEF:
            r=op%16 if op%16<15 else 0;x[f'R{r:X}']=str([4,5,6,7,8,9][i]);x['X']=str([-3,0,5,-1,0,7][i])
        result.append(x)
    return result


def make_task(vm,code,text,identity,group,split,angle,inputs,*,kind='primitive',targets=None,check_names=None,check_pc=False,raw=False,resume=False):
    cases=fixtures(vm,code,inputs,angle,resume=resume)
    return {'id':identity,'kind':kind,'group':group,'split':split,'angle':angle,'task':text,'reference_code':code,
      'public_tests':cases[:2],'hidden_tests':cases[2:],'target_opcodes':targets or[],
      'check_names':check_names,'check_pc':check_pc,'raw_compare':raw,'max_commands':128,'max_frames':1024,'source':'verified_full_core'}


def numeric_tasks(vm,split,seed,count):
    rng=random.Random(seed);out=[];ops=list(UNARY)+list(BINARY);pool=['-.5','-.25','.25','.5','1','2','3','4','5','7']
    names=list(REGISTERS)
    while len(out)<count:
        i=len(out);op=ops[i%len(ops)];r0,r1,r2=rng.sample(names,3);angle=rng.choice(['RAD','DEG','GRAD'])
        use_literal=i%3==0;leaf={'constant':rng.choice(['.25','.5','1','2','3','5','7','11','22','37'])}if use_literal else r0
        expr=[op,leaf]if op in UNARY else[op,leaf,r1]
        depth=1
        if i%4==1:expr=[rng.choice(['+','-','*','/']),expr,r2];depth=2
        elif i%4==2:expr=[rng.choice(['abs','square','sin','cos','atan']),['+',expr,r2]];depth=3
        elif i%4==3:expr=[op,['+',r0,r1]]if op in UNARY else[op,['+',r0,r1],r2];depth=2
        code=compile_expr(expr)+[0x50]
        if len(code)>80:continue
        inputs=[];attempts=0
        while len(inputs)<6 and attempts<180:
            attempts+=1;state=base_inputs(rng)
            for reg in registers(expr):state[reg]=rng.choice(pool)
            try:expected=value(expr,state,angle)
            except (ValueError,OverflowError,ZeroDivisionError,TypeError):continue
            if isinstance(expected,complex)or not math.isfinite(expected)or abs(expected)>1e6:continue
            actual,_=vm.execute(code,state,angle=angle,max_commands=128,max_frames=1024)
            try:good=actual['status']=='stopped'and abs(float(actual['numeric']['X'])-expected)<=max(2e-6,abs(expected)*2e-6)
            except (ValueError,TypeError):good=False
            if good:inputs.append(state)
        if len(inputs)<6:continue
        text=PREFIXES[split][i%len(PREFIXES[split])]+ 'вычислить '+words(expr)+'. Результат в X, память R0–RE не изменяй.'
        row=make_task(vm,code,text,f'{split}:numeric:{i:05}', 'scientific_synthesis',split,angle,inputs,
          kind='numeric_synthesis',targets=[UNARY.get(op,BINARY.get(op))],check_names=['X',*REGISTERS])
        row['expression']=expr;row['depth']=depth;row['has_literal']=use_literal;out.append(row)
    return out


def control_tasks(vm,split,seed,count):
    rng=random.Random(seed);out=[]
    for i in range(count):
        mode=rng.choice(['RAD','DEG','GRAD']);inputs=[];kind=i%5;r0,r1,scratch=rng.sample(range(15),3)
        if kind==0:
            cond,word=rng.choice([(0x59,'неотрицателен'),(0x57,'не равен нулю'),(0x5C,'отрицателен'),(0x5E,'равен нулю')])
            code=[0x60+r0,cond,0x06,0x60+r1,0x50,0x54,0x60+scratch,0x50]
            text=f'Если R{r0:X} {word}, выдай R{r1:X}, иначе R{scratch:X}. Заверши С/П.';targets=[cond]
        elif kind==1:
            counter=i%4;op={0:0x5D,1:0x5B,2:0x58,3:0x5A}[counter]
            r1=rng.choice([x for x in range(4,15)]);scratch=rng.choice([x for x in range(4,15)if x!=r1])
            code=[0x0D,0x40+scratch,0x60+scratch,0x60+r1,0x10,0x40+scratch,op,0x02,0x60+scratch,0x50]
            text=f'Сложи R{r1:X} с собой столько раз, сколько задано положительным целым в R{counter}. Используй L{counter}; R{scratch:X} разрешён как накопитель. Итог в X.';targets=[op]
        elif kind==2:
            code=[0x60+r0,0x60+r1,0x10,0x40+scratch,0x50]
            text=f'Сумму R{r0:X} и R{r1:X} запиши в R{scratch:X} и выдай в X.';targets=[0x40+scratch]
        elif kind==3:
            op=rng.choice([0x1C,0x1D,0x21,0x31,0x22]);name={0x1C:'синус',0x1D:'косинус',0x21:'квадратный корень',0x31:'модуль',0x22:'квадрат'}[op]
            code=[0x60+r0,0x53,0x08,0x50,0x54,0x54,0x54,0x54,op,0x52]
            text=f'Вызови подпрограмму по адресу 08 для вычисления: {name} R{r0:X}. Основная программа должна вызывать её и завершаться после возврата. Итог в X.';targets=[0x53,0x52,op]
        else:
            code=[0x60+r0,0x60+r1,0x11,0x59,0x08,0x60+r0,0x50,0x54,0x60+r1,0x50]
            text=f'Выдай большее из R{r0:X} и R{r1:X}, корректно обрабатывая нулевые и отрицательные числа. Память не меняй.';targets=[0x59]
        for j in range(6):
            values=base_inputs(rng)
            if kind==1:values[f'R{counter}']=str(j+1)
            if kind==3 and op==0x21:values[f'R{r0:X}']=str(j+1)
            inputs.append(values)
        row=make_task(vm,code,PREFIXES[split][i%len(PREFIXES[split])]+text,f'{split}:control:{i:04}',
          ['branch_programs','loop_programs','memory_programs','subroutine_programs','branch_programs'][kind],split,mode,inputs,
          kind='programming',targets=targets,check_names=['X',*REGISTERS]if kind not in [1,2]else['X'])
        if kind==2:row['check_names']=['X',f'R{scratch:X}']
        out.append(row)
    return out


def interactive_tasks(vm,split,seed,count):
    rng=random.Random(seed);out=[]
    for i in range(count):
        acc=rng.randrange(4,15);code=[0x0D,0x40+acc,0x50,0x60+acc,0x10,0x40+acc,0x50,0x51,0x03]
        cases=[]
        for j in range(4):
            initial=base_inputs(rng);initial['X']='0';state,context=vm.execute(code,initial)
            segments=[{'inputs':initial,'expected':state}]
            for delta in [rng.choice([-7,-3,2,5]),rng.choice([-5,-1,3,8]),rng.choice([-2,1,4,9])]:
                later={'X':str(delta)};state,context=vm.execute(None,later,context=context)
                segments.append({'inputs':later,'expected':state})
            cases.append({'segments':segments})
        text=f'Счётчик очков игры: сначала обнули R{acc:X} и остановись. При каждом продолжении игрок вводит изменение счёта в X. Прибавь его к R{acc:X}, сохрани новый счёт там же и остановись. Повторяй без потери состояния.'
        out.append({'id':f'{split}:interactive:{i:03}','kind':'interactive_game','group':'stateful_interactions','split':split,'angle':'RAD',
          'task':PREFIXES[split][i%len(PREFIXES[split])]+text,'reference_code':code,'target_opcodes':[0x50,0x51,0x40+acc],
          'check_names':['X',f'R{acc:X}'],'check_pc':False,'raw_compare':False,'public_tests':cases[:1],'hidden_tests':cases[1:],
          'max_commands':128,'max_frames':1024,'source':'verified_game_mechanic'})
    return out


def main():
    if(ROOT/'data-frozen.json').exists():print('Full ISA data already frozen');return
    started=time.monotonic();vm=FullVM();catalog=json.loads((ROOT/'catalog.json').read_text());sets={};reference_coverage=collections.Counter()
    for split,seed in [('train',6117001),('validation',6117002),('audit',6117003)]:
        rng=random.Random(seed);rows=[]
        for row in catalog:
            code,description,check_pc,resume=primitive(row)
            for angle in ['RAD','DEG','GRAD']:
                inputs=primitive_inputs(row['code'],rng)
                base=make_task(vm,code,'',f'{split}:op{row["hex"]}:{angle}',row['group'],split,angle,inputs,
                  targets=[row['code']],check_pc=check_pc,raw=True,resume=resume)
                base['opcode']=row['code'];base['catalog_risk']=row['risk']
                variants=PREFIXES[split]
                for k,prefix in enumerate(variants):
                    suffix='; затем остановиться С/П.'if not resume else'.'
                    task={**base,'id':base['id']+f':wording{k}','task':prefix+description+suffix,
                      'language_family':f'{split}:primitive-phrasing-{k}'};rows.append(task)
                if split=='train':
                    executed={s['opcode']for c in base['public_tests']+base['hidden_tests']for part in c['segments']for s in part['expected']['trace']}
                    if row['code']not in executed:raise ValueError('Target opcode not executed: '+row['hex'])
                    reference_coverage[row['code']]+=1
        rows+=numeric_tasks(vm,split,seed+10,2200 if split=='train'else 192 if split=='validation'else 288)
        rows+=control_tasks(vm,split,seed+20,900 if split=='train'else 90 if split=='validation'else 135)
        rows+=interactive_tasks(vm,split,seed+30,60 if split=='train'else 10)
        if split!='train':
            # One wording per opcode/mode is the exhaustive instruction panel;
            # the remaining held-out phrasings are available as a separate panel.
            exhaustive=[r for r in rows if r['kind']=='primitive'and':wording0'in r['id']]
            other=[r for r in rows if r['kind']!='primitive'];main_rows=exhaustive+other
            save_jsonl(ROOT/(split+'-all-wordings.jsonl'),rows);rows=main_rows
        sets[split]=rows;save_jsonl(ROOT/(split+'.jsonl'),rows)
        print(json.dumps({'prepared':split,'rows':len(rows),'seconds':time.monotonic()-started}),flush=True)
    assert set(reference_coverage)==set(range(256))
    manifest={'version':'full-isa-v1','reference_all_256_opcodes_executed':True,
      'documented_opcode_reference_coverage':1.,'all_three_angle_modes':True,'all_fifteen_registers':True,
      'raw_stack_and_memory':True,'real_stop_resume_cases':True,'no_seven_operation_output_ast':True,
      'counts':{s:len(rows)for s,rows in sets.items()},'by_kind':{s:dict(collections.Counter(r['kind']for r in rows))for s,rows in sets.items()},
      'files':{name:sha(ROOT/name)for name in ['train.jsonl','validation.jsonl','audit.jsonl','catalog.json','output-token-ids.json']},
      'new_audit_used_for_selection':False,'before_new_teacher_and_optimizer_updates':True,
      'source_sha256':{p.name:sha(p)for p in [HERE/'full_isa_prepare.py',HERE/'full_isa_math.py',HERE/'full_isa_vm.py',HERE/'full_isa_bridge.cpp',HERE/'core_bridge.cpp',HERE/'full_isa_protocol.py']},
      'seconds':time.monotonic()-started}
    write(ROOT/'data-frozen.json',manifest);print(json.dumps(manifest,ensure_ascii=False),flush=True)


if __name__=='__main__':main()
