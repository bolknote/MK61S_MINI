"""Executable ordinary Russian requests, constants and symbolic expressions."""
import collections
import json
import math
import random
import shutil
import time

from natural_common import ROOT,PREVIOUS,INITIAL,INITIAL_PACKET,read,sha,write
from full_isa_math import UNARY,BINARY,WORDS,compile_expr,value,registers
from full_isa_protocol import REGISTERS
from full_isa_prepare import base_inputs,make_task
from full_isa_vm import FullVM
from tasks import save_jsonl

NAMES={'neg':'противоположное число','pow10':'десять в степени','exp':'экспоненту','log10':'десятичный логарифм',
 'ln':'натуральный логарифм','asin':'арксинус','acos':'арккосинус','atan':'арктангенс','sin':'синус','cos':'косинус',
 'tan':'тангенс','sqrt':'квадратный корень','square':'квадрат','reciprocal':'обратное число','abs':'модуль',
 'sign':'знак по правилу МК-61','int':'целую часть','frac':'дробную часть'}
STORIES={
 'sin':['Угол {x} задаёт единичный радиус-вектор. Нужна его вертикальная составляющая.',
        'Для угла {x} получи вертикальную координату точки единичной окружности.',
        'Найди проекцию единичного вектора на вертикальную ось по углу {x}.',
        'Из угла {x} вычисли высоту точки на окружности радиуса один.'],
 'cos':['Из угла {x} найди горизонтальную координату точки на единичной окружности.',
        'Единичный радиус-вектор повёрнут на {x}. Нужна горизонтальная составляющая.',
        'Определи проекцию на горизонтальную ось единичного вектора с углом {x}.',
        'Для направления {x} вычисли горизонтальную координату на окружности радиуса один.'],
 'tan':['Линия наклонена на {x}. Нужен тангенс угла наклона.',
        'Угол склона равен {x}. Найди отношение вертикальной составляющей к горизонтальной.',
        'Определи тангенс для наклона {x}.', 'По углу {x} получи отношение синуса к косинусу.'],
 'asin':['Синус угла равен {x}. Восстанови главное значение угла.',
         'Задано значение синуса {x}. Найди главный угол.',
         'По синусу {x} вычисли соответствующий главный угол.',
         'У неизвестного угла синус {x}. Нужен сам угол на главной ветви.'],
 'acos':['Косинус угла равен {x}. Найди главный угол.',
         'Дано значение косинуса {x}. Восстанови соответствующий главный угол.',
         'Какой главный угол имеет косинус {x}?',
         'У неизвестного угла косинус {x}. Получи угол на главной ветви.'],
 'atan':['Тангенс угла равен {x}. Вычисли главный угол.',
         'Восстанови угол на главной ветви по тангенсу {x}.',
         'Какой главный угол соответствует тангенсу {x}?',
         'Известен тангенс {x}; требуется главное значение самого угла.'],
 'ln':['Найди логарифм {x} с основанием e.', 'Для числа {x} нужен логарифм по основанию числа Эйлера.',
       'Логарифмируй {x} по основанию e.', 'Возьми логарифм числа {x}, основание — e.'],
 'log10':['Нужен логарифм {x} с основанием десять.', 'Логарифмируй {x} по основанию 10.',
          'Основание логарифма равно 10, аргумент {x}. Найди результат.', 'Вычисли логарифм числа {x} при основании десять.'],
 'exp':['Возведи число e в степень {x}.', 'Основание — число Эйлера e, показатель {x}. Вычисли степень.',
        'Нужна степень числа e с показателем {x}.', 'Вычисли e в степени, заданной значением {x}.'],
 'pow10':['Возведи десять в степень {x}.', 'Основание равно 10, показатель {x}. Найди степень.',
          'Вычисли степень с основанием десять и показателем {x}.', 'Определи 10 в степени, заданной значением {x}.'],
 'sqrt':['Площадь квадрата равна {x}. Найди длину стороны.', 'По площади квадрата {x} получи его сторону.',
         'Из площади {x} восстанови неотрицательную сторону квадрата.', 'У квадрата площадь {x}; вычисли длину его стороны.'],
 'square':['Сторона квадрата равна {x}. Найди площадь.', 'Величина {x} задаёт сторону квадрата; вычисли его площадь.',
           'Определи площадь квадрата со стороной {x}.', 'Найди произведение числа {x} на само себя.'],
 'reciprocal':['Найди число, которое при умножении на {x} даёт единицу.', 'Раздели единицу на {x}.',
               'Какое число надо умножить на {x}, чтобы получить один?', 'Получи частное единицы и числа {x}.'],
 'abs':['Число {x} бывает отрицательным. Убери знак и оставь величину.', 'Нужна абсолютная величина числа {x}.',
        'Полученное значение {x} выдай без знака.', 'Возьми расстояние от числа {x} до нуля.'],
 'neg':['Смещение {x} нужно направить в противоположную сторону.', 'Смени знак числа {x}.',
        'У числа {x} поменяй положительный знак на отрицательный или наоборот.', 'Получи число той же величины, что {x}, но с противоположным знаком.'],
 'int':['Отбрось дробную часть {x} без округления, к нулю.', 'У числа {x} оставь целую часть с отсечением к нулю.',
        'Удали дробные разряды {x}, не округляя оставшееся.', 'От числа {x} нужна целая часть, округление запрещено.'],
 'frac':['Отбрось целую часть {x} и сохрани знак остатка.', 'В числе {x} оставь дробную часть с исходным знаком.',
         'Выдай дробный остаток числа {x} после отсечения целой части к нулю.', 'У числа {x} убери целую часть, сохранив знак дроби.'],
 'sign':['Если {x} отрицательно, выдай -1, иначе +1.', 'Получи -1 для отрицательного {x} и +1 для нуля или положительного.',
         'Результат должен быть -1 при {x}<0 и +1 во всех остальных случаях.', 'Примени правило знака МК-61 к {x}: ноль даёт +1.']}

TRAIN_NUMBERS=[str(i)for i in range(100)if i not in [17,23,29,31,47,53,67,73,83,97]]+['-.5','.25','.5','1.5','2.75','-3','-12','-30']
HELD_NUMBERS=['17','23','29','31','47','53','67','73','83','97','-17','2.5','4.25','12.75',
 '.125','.375','.625','.875','-.125','-.375','-.625','-.875']
DIRECT={
 'train':['Подсчитай {f} {x}.','Вычисли {f} для {x}.','Нужен {f} от {x}.','Найди {f}({x}).','Дай программу: {f} от {x}.'],
 'validation':['Чему равен {f} числа {x}?','Запиши код, который находит {f} для {x}.'],
 'fresh':['Посчитай на МК-61 {f} для величины {x}.','Покажи, как вычислить {f} от {x}.']}


def symbolic(expr):
    if isinstance(expr,str):return expr
    if isinstance(expr,dict):return str(expr['constant'])
    op,*args=expr
    if op in UNARY:return op+'('+symbolic(args[0])+')'
    return '('+symbolic(args[0])+{'pow':'^'}.get(op,op)+symbolic(args[1])+')'


def leaf(rng,split,constant=False):
    if constant:return {'constant':rng.choice(TRAIN_NUMBERS if split=='train'else HELD_NUMBERS)}
    return rng.choice(REGISTERS)


def leaf_text(x):return x if isinstance(x,str)else str(x['constant'])


def describe(expr,split,rng):
    if isinstance(expr,(str,dict)):return leaf_text(expr)
    op,*args=expr
    xs=['('+describe(a,split,rng)+')'for a in args]
    if op in UNARY:return NAMES[op]+' от '+xs[0]
    if op=='pow':return xs[0]+' в степени '+xs[1]
    return xs[0]+{'+':' плюс ','-':' минус ','*':' умножить на ','/':' разделить на '}[op]+xs[1]


def generate(vm,split,number,seed,seen):
    rng=random.Random(seed);rows=[];ops=list(UNARY)+list(BINARY);started=time.monotonic();attempt=0
    while len(rows)<number:
        attempt+=1
        if attempt>number*100:raise RuntimeError('Cannot generate natural tasks')
        index=len(rows);op=ops[index%len(ops)];shape=(index//len(ops))%6;angle=rng.choice(['RAD','DEG','GRAD'])
        left=leaf(rng,split,constant=shape in [0,3]or rng.random()<.25);right=leaf(rng,split,constant=rng.random()<.2)
        expr=[op,left]if op in UNARY else[op,left,right];base_expr=expr;depth=1
        style=(index//(len(ops)*6))%4
        if op in UNARY:
            if style==1:
                story_index=rng.choice([0,1])if split=='train'else 2 if split=='validation'else 3
                text=STORIES[op][story_index].format(x=leaf_text(left));group='semantic_story'
            else:text=rng.choice(DIRECT[split]).format(f=NAMES[op],x=leaf_text(left));group='literal_request'if isinstance(left,dict)else'direct_function'
        else:
            labels={'+':'сумму','-':'разность','*':'произведение','/':'частное','pow':'степень'}
            if op=='pow':text=f'Возведи {leaf_text(left)} в степень {leaf_text(right)}.'
            else:text=f'Найди {labels[op]} {leaf_text(left)} и {leaf_text(right)}.'
            if split=='validation':text='Для вычисления нужно получить '+describe(expr,split,rng)+'.'
            elif split=='fresh':text='Выполни расчёт: '+describe(expr,split,rng)+'.'
            group='literal_request'if isinstance(left,dict)else'direct_function'
        if shape==3:
            other=leaf(rng,split);expr=['+',expr,other];depth=2;text+=' К полученному прибавь '+leaf_text(other)+'.';group='composition'
        elif shape==4:
            outer=rng.choice(['square','abs','neg']);expr=[outer,expr];depth=2
            text+=' Затем вычисли '+NAMES[outer]+' результата.';group='composition'
        elif shape==5:
            other=leaf(rng,split);expr=['-',expr,['square',other]];depth=3
            text+=' Из результата вычти квадрат '+leaf_text(other)+'.';group='composition'
        if style==3:
            prefix=rng.choice(['Напиши программу для X = ','Вычисли выражение ','Нужен код: '])if split=='train'else'Составь HEX для формулы: 'if split=='validation'else'Рассчитай на калькуляторе X = '
            text=prefix+symbolic(expr)+'.';group='symbolic_expression'
        if rng.random()<.5:text+=' Итог оставь в X. Регистры памяти сохрани.'
        key=(angle,text)
        if key in seen:continue
        code=compile_expr(expr)+[0x50]
        inputs=[];used=registers(expr)
        for trial in range(60):
            state=base_inputs(rng)
            for r in used:state[r]=rng.choice(['-.75','-.5','-.25','.125','.25','.5','.75','1','2','3','4','7'])
            try:expected=value(expr,state,angle)
            except (ValueError,OverflowError,ZeroDivisionError,TypeError):continue
            if isinstance(expected,complex)or not math.isfinite(expected)or abs(expected)>1e6:continue
            actual,_=vm.execute(code,state,angle=angle,max_commands=128,max_frames=1024)
            try:good=actual['status']=='stopped'and abs(float(actual['numeric']['X'])-expected)<=max(2e-6,abs(expected)*2e-6)
            except (ValueError,TypeError):good=False
            if good:inputs.append(state)
            if len(inputs)==6:break
        if len(inputs)<6:continue
        row=make_task(vm,code,text,f'natural-{split}:{index:05}','natural_'+group,split,angle,inputs,
          kind='natural_request',targets=[UNARY.get(op,BINARY.get(op))],check_names=['X',*REGISTERS])
        row.update(expression=expr,depth=depth,root_operation=op,language_style=style,has_literal=isinstance(left,dict),
          source='authored_russian_grammar_real_core',fresh_template_family=split)
        seen.add(key);rows.append(row)
        if len(rows)%1000==0:print(json.dumps({'split':split,'rows':len(rows),'seconds':time.monotonic()-started}),flush=True)
    return rows


def main():
    ROOT.mkdir(exist_ok=True)
    if(ROOT/'data-frozen.json').exists():print('Natural inputs already frozen');return
    vm=FullVM();seen=set();sets={}
    for split,n,seed in [('train',7200,6118101),('validation',552,6118102),('fresh',552,6118103)]:
        cached=ROOT/(split+'-language.jsonl')
        if cached.exists():
            sets[split]=read(cached);seen.update((t['angle'],t['task'])for t in sets[split]);continue
        sets[split]=generate(vm,split,n,seed,seen)
        rng=random.Random(seed+100)
        for op in UNARY:
            for angle in ['RAD','DEG','GRAD']:
                forms=['Подсчитай {f} X. Число уже находится в стеке X.','Возьми {f} текущего значения X.']if split=='train'else['В X уже задан аргумент. Вычисли его {f}.']if split=='validation'else['Обработай текущее число в X: требуется {f}.']
                for form in forms:
                    inputs=[]
                    for _ in range(100):
                        state=base_inputs(rng);state['X']=rng.choice(['-.75','-.5','-.25','.125','.25','.5','.75','1','2','3'])
                        try:expected=value([op,'R0'],{'R0':state['X']},angle)
                        except (ValueError,OverflowError,ZeroDivisionError):continue
                        actual=vm.execute([UNARY[op],0x50],state,angle=angle)[0]
                        if actual['status']!='stopped' or abs(float(actual['numeric']['X'])-expected)>max(2e-6,abs(expected)*2e-6):continue
                        inputs.append(state)
                        if len(inputs)==6:break
                    assert len(inputs)==6
                    task=make_task(vm,[UNARY[op],0x50],form.format(f=NAMES[op]),f'natural-{split}:stack:{op}:{angle}:{len(sets[split])}',
                      'natural_stack_input',split,angle,inputs,kind='natural_request',targets=[UNARY[op]],check_names=['X',*REGISTERS])
                    task.update(depth=1,source='authored_russian_grammar_real_core');sets[split].append(task)
        save_jsonl(ROOT/(split+'-language.jsonl'),sets[split])
    names=['catalog.json','output-token-ids.json','audit.jsonl','development.jsonl','observed-user-reproductions.jsonl',
      'closed-natural.jsonl','sft-light.jsonl','legacy-light.jsonl','repair-examples.jsonl']
    for name in names:shutil.copyfile(PREVIOUS/name,ROOT/name)
    shutil.copytree(PREVIOUS/'core-source',ROOT/'core-source',dirs_exist_ok=True)
    original=read(ROOT/'sft-light.jsonl')
    light_keys=['id','task','angle','reference_code','group','kind','opcode','catalog_risk','target_opcodes','source','depth']
    light=original+[{k:t[k]for k in light_keys if k in t}for t in sets['train']]
    save_jsonl(ROOT/'sft-light.jsonl',light)
    rng=random.Random(6118104);toolset=list(sets['fresh']);rng.shuffle(toolset)
    write(ROOT/'tool-probe-ids.json',[t['id']for t in toolset[:100]])
    policy={'steps_each':3000,'validation_interval':500,'effective_batch':128,'lr':2e-5,'embedding_lr_factor':.5,
      'warmup_updates':100,'weight_decay':.01,'contexts':[512,1024,2048],'context_probabilities':[.85,.1,.05],
      'memory_fraction_each':.8,'arms':['full','protected'],'starting_model':'full-isa-v1/protected-best step2000',
      'old_audit_is_observed_regression':True,'fresh_language_used_for_selection':False,
      'teacher_for_this_stage':'Authored deterministic Russian language grammar; previous neural teacher rows replayed.'}
    write(ROOT/'policy.json',policy)
    files=names+['train-language.jsonl','validation-language.jsonl','fresh-language.jsonl','policy.json','tool-probe-ids.json']
    source=ROOT/'frozen-source';source.mkdir(exist_ok=True)
    for p in __import__('pathlib').Path(__file__).parent.glob('natural_*.py'):shutil.copyfile(p,source/p.name)
    frozen={'before_new_optimizer_updates':True,'initial_master_sha256':sha(INITIAL/'model.safetensors'),
      'initial_packet_sha256':sha(INITIAL_PACKET),'files':{name:sha(ROOT/name)for name in files},
      'new_training_rows':len(sets['train']),'validation_language_rows':len(sets['validation']),'fresh_language_rows':len(sets['fresh']),
      'source_hashes':{p.name:sha(p)for p in source.iterdir()},'private_core_files':{str(p.relative_to(ROOT/'core-source')):sha(p)for p in(ROOT/'core-source').rglob('*')if p.is_file()},
      'seen_old_natural_153_used_only_as_observed_retest':True,'current_stage_has_no_fresh_teacher_api_calls':True,
      'independent_math_and_real_core_crosscheck':True,'template_synthetic_not_human_benchmark':True}
    write(ROOT/'data-frozen.json',frozen)
    write(ROOT/'run-policy-frozen.json',{'files':frozen['files'],'private_core_files':frozen['private_core_files']})
    print(json.dumps({k:v for k,v in frozen.items()if k not in ['files','source_hashes','private_core_files']}),flush=True)


if __name__=='__main__':main()
