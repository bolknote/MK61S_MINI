"""Separately frozen natural requests, real-source fragments and run policy."""
import collections
import json
import random
import shutil
import subprocess
from pathlib import Path

from full_isa_common import ROOT,read,sha,write
from full_isa_vm import FullVM,HERE,REPO
from full_isa_prepare import make_task,base_inputs
from full_isa_math import compile_expr,UNARY,WORDS
from tasks import BUILD,save_jsonl


NATURAL=[
 ('sin','Точка движется по единичной окружности. Её угол находится в {r}. Выдай вертикальную координату точки.'),
 ('cos','У единичного вектора угол задан в {r}. Найди горизонтальную составляющую.'),
 ('tan','Угол наклона линии записан в {r}. Нужен тангенс этого угла.'),
 ('asin','В {r} находится синус неизвестного угла. Восстанови главное значение угла.'),
 ('acos','Косинус угла лежит в {r}. Верни главный угол по этому значению.'),
 ('atan','Известен тангенс угла, он записан в {r}. Найди главное значение самого угла.'),
 ('ln','От положительного значения в {r} требуется логарифм с основанием e.'),
 ('log10','Какой десятичный логарифм у числа из {r}? Нужен код калькулятора.'),
 ('exp','Возведи число e в степень, заданную регистром {r}.'),
 ('pow10','В {r} указан показатель степени. Основание равно десяти. Выдай результат возведения.'),
 ('sqrt','Площадь квадрата задана в {r}. Определи длину стороны.'),
 ('reciprocal','В {r} дано ненулевое число. Найди число, произведение которого на данное равно единице.'),
 ('int','В {r} число со знаком. Отбрось дробные разряды без округления, оставив целую часть.'),
 ('frac','Целую часть числа {r} нужно отбросить. Сохрани оставшуюся дробь вместе с её знаком.'),
 ('square','Сторона квадрата хранится в {r}. Вычисли площадь.'),
 ('abs','Показание датчика {r} бывает отрицательным. Нужна его величина без знака.'),
 ('neg','Смещение задано регистром {r}. Найди смещение той же длины в противоположную сторону.')]


def main():
    if(ROOT/'run-policy-frozen.json').exists():print('Full run inputs already frozen');return
    vm=FullVM();rng=random.Random(6117040);natural=[]
    for index,(op,text)in enumerate(NATURAL):
        for angle in ['RAD','DEG','GRAD']:
            for variant in range(3):
                reg=rng.choice([f'R{i:X}'for i in range(15)]);inputs=[]
                for j in range(6):
                    values=base_inputs(rng)
                    candidates=[.1,.25,.5,1,2,3]if op in ['ln','log10','sqrt']else[-.75,-.5,-.25,.25,.5,.75]if op in ['asin','acos']else[-3,-1,-.5,.25,1,3]
                    values[reg]=str(candidates[j]);inputs.append(values)
                expr=[op,reg]
                if variant==1:expr=['+',[op,reg],{'constant':'1.5'}]
                elif variant==2:expr=['square',[op,reg]]
                wording=text.format(r=reg)
                if variant==1:wording+=' Увеличь полученный результат на 1.5.'
                elif variant==2:wording+=' Финальный показатель — квадрат найденной величины.'
                row=make_task(vm,compile_expr(expr)+[0x50],wording+' Результат нужен в X, регистры памяти не меняй.',
                  f'closed-natural:{index}:{angle}:{variant}','natural_transfer', 'closed-natural',angle,inputs,
                  kind='natural_transfer',targets=[UNARY[op]],check_names=['X',*[f'R{i:X}'for i in range(15)]])
                row['story_family']=index;natural.append(row)
    # User's sine-22 request is an observed reproduction, not new holdout.
    probes=[]
    for angle in ['RAD','DEG','GRAD']:
        for op,word in [('sin','синус'),('cos','косинус'),('tan','тангенс')]:
            for number in ['22','37.5','-30']:
                code=compile_expr([op,{'constant':number}])+[0x50]
                probes.append(make_task(vm,code,f'Подсчитай {word} {number}.',f'user-repro:{op}:{angle}:{number}',
                  'observed_user_reproduction','observed-repro',angle,[base_inputs(rng)for _ in range(6)],
                  kind='numeric_literal',targets=[UNARY[op]],check_names=['X',*[f'R{i:X}'for i in range(15)]]))
    save_jsonl(ROOT/'closed-natural.jsonl',natural);save_jsonl(ROOT/'observed-user-reproductions.jsonl',probes)
    catalog={r['code']:r for r in json.loads((ROOT/'catalog.json').read_text())}
    games=read(BUILD/'corpus/games-train.jsonl');fragments=[]
    for game in games:
        if not game.get('usable_for_code')or 'bytes'not in game:continue
        codes=game['bytes'];candidates=[]
        for at in range(max(0,len(codes)-4)):
            chunk=codes[at:at+4]
            if all(x in catalog and catalog[x]['risk']=='documented'and not catalog[x]['takes_address']and not(0x50<=x<=0x5F)and not(0x70<=x<=0xEF)for x in chunk):candidates.append((at,chunk))
        if not candidates:continue
        at,chunk=rng.choice(candidates);code=chunk+[0x50];inputs=[base_inputs(rng)for _ in range(6)]
        row=make_task(vm,code,'Выполни последовательно команды фрагмента МК-61: '+', '.join(catalog[x]['name']for x in chunk)+'. Затем С/П.',
          'game-fragment:'+str(len(fragments)), 'historical_game_fragments','train','RAD',inputs,kind='game_fragment',targets=chunk,
          check_names=None,raw=True)
        if any(c['segments'][0]['expected']['status']!='stopped'for c in row['public_tests']+row['hidden_tests']):continue
        row['source']='historical_game_fragment';row['source_game']=game.get('id',game.get('program'));row['source_span']=[at,at+4];row['is_complete_game']=False
        fragments.append(row)
        if len(fragments)>=160:break
    save_jsonl(ROOT/'historical-fragments.jsonl',fragments)
    # Freeze only actual core dependencies into this experiment's own directory.
    dep=subprocess.check_output(['c++','-std=c++17','-DMK61_CORE_STANDALONE=1','-DMK61_CORE_HOT_TABLES_IN_SRAM=0','-I',str(REPO/'code'),'-MM',str(HERE/'full_isa_bridge.cpp'),str(REPO/'code/mk61emu_core.cpp')],text=True)
    dependencies={Path(x)for x in dep.replace('\\\n',' ').split()if x.startswith(str(REPO/'code')+'/')}
    core=ROOT/'core-source';core.mkdir(exist_ok=True)
    for path in dependencies:
        target=core/path.relative_to(REPO/'code');target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(path,target)
    policy={'model':'3M HEX','arms':['full','protected'],'steps_each':8000,'validation_interval':500,'effective_batch':128,
      'lr':3e-5,'embedding_lr_factor':.5,'warmup_updates':150,'weight_decay':.01,'contexts':[512,1024,2048],
      'context_probabilities':[.85,.1,.05],'memory_fraction_each':.8,'qat':'Q4 from first update',
      'protected_variant':'Update embedding/readout rows used by the HEX head; keep other Russian input rows exactly unchanged.',
      'same_sampling_plan':True,'new_audit_used_for_selection':False,'native_context':1024,'configured_training_context':2048,
      'targets_not_guarantees':{'documented_instruction_encoding':.95,'numeric_synthesis':.8,'programming':.8,'stateful_interactions':.8},
      'input_domain':'All classic commands, all R0-RE, literals, complete visible stack, errors, three angle modes, true stop/resume',
      'historical_fragments_are_not_complete_games':True,'whole_core_dependencies_copied':True}
    write(ROOT/'policy.json',policy)
    frozen={'before_teacher_generation_and_gradients':True,'base_data_frozen_sha256':sha(ROOT/'data-frozen.json'),
      'files':{p.name:sha(p)for p in [ROOT/'policy.json',ROOT/'closed-natural.jsonl',ROOT/'observed-user-reproductions.jsonl',ROOT/'historical-fragments.jsonl']},
      'private_core_files':{str(p.relative_to(core)):sha(p)for p in core.rglob('*')if p.is_file()},
      'closed_natural_conditions':len(natural),'natural_story_families':len(NATURAL),'historical_game_fragments':len(fragments),
      'limitations':'Controlled synthetic instruction suite and separately authored natural transfer conditions, not independent human certification.'}
    write(ROOT/'run-policy-frozen.json',frozen);print(json.dumps({k:v for k,v in frozen.items()if k not in ['files','private_core_files']},ensure_ascii=False),flush=True)


if __name__=='__main__':main()
