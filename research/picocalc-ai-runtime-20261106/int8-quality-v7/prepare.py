from pathlib import Path
from decimal import Decimal,localcontext
import json,hashlib,shutil,subprocess
ROOT=Path('/Users/bolk/Projects/MK61S_MINI');OUT=ROOT/'.build/mk61ai/int8-quality-v7';SRC=ROOT/'.build/mk61ai/swar-v5/source'
OPS={'+':0x10,'-':0x11,'*':0x12,'/':0x13,'abs':0x31,'neg':0x0b,'square':0x22}
def compile_expr(x):
 if isinstance(x,str):return [0x60+int(x[1:])]
 return [v for child in x[1:] for v in compile_expr(child)]+[OPS[x[0]]]
def value(x,reg):
 if isinstance(x,str):return reg[x]
 a=value(x[1],reg)
 if x[0]=='abs':return abs(a)
 if x[0]=='neg':return -a
 if x[0]=='square':return a*a
 b=value(x[2],reg)
 return {'+':lambda:a+b,'-':lambda:a-b,'*':lambda:a*b,'/':lambda:a/b}[x[0]]()
def n(x):return format(Decimal(x).normalize(),'f')
families=[
 ('sum',['+','R0','R1'],['Сложи значения R0 и R1; сумму выведи в X.','В R0 вчерашний остаток, в R1 сегодняшнее пополнение. Покажи общий итог в X.','Нужна программа для X=R0+R1.']),
 ('difference',['-','R0','R1'],['Из R0 вычти R1. Ответ нужен в X.','В R0 запас до расхода, расход записан в R1. Найди остаток в X.','Напиши код для X=R0-R1.']),
 ('product',['*','R0','R1'],['Перемножь R0 и R1, результат положи в X.','Цена записана в R0, количество в R1. Получи стоимость в X.','Требуется программа X=R0*R1.']),
 ('quotient',['/','R0','R1'],['Раздели значение R0 на ненулевое R1 и оставь частное в X.','R0 содержит путь, R1 время. Вычисли скорость как R0/R1 в X.','Нужен код для X=R0/R1. Нулевого делителя не будет.']),
 ('absolute',['abs','R0'],['Получить модуль содержимого R0 в X.','Отклонение задано в R0. Верни его величину без знака в X.','Напиши программу X=abs(R0).']),
 ('square',['square','R0'],['Возведи R0 во вторую степень; ответ в X.','Сторона квадрата задана в R0. Рассчитай площадь в X.','Программа должна вычислить X=R0*R0.']),
 ('negative',['neg','R0'],['Поменяй знак R0 и выведи новое значение в X.','Получи противоположное число к R0 в X.','Требуется X=-R0.']),
 ('cube',['*',['square','R0'],'R0'],['Возведи R0 в третью степень и выведи в X.','Найди куб числа в R0, результат оставь в X.','Нужна программа X=R0*R0*R0.']),
 ('sum3',['+',['+','R0','R1'],'R2'],['Сумму R0, R1 и R2 выведи в X.','Три слагаемых заданы регистрами R0, R1, R2. Покажи их итог в X.','Вычисли X=(R0+R1)+R2.']),
 ('muladd',['+',['*','R0','R1'],'R2'],['Умножь R0 на R1, затем прибавь R2. Ответ в X.','Площадь R0*R1 увеличь на величину R2 и покажи в X.','Составь программу X=R0*R1+R2.']),
 ('reverse',['-','R1','R0'],['Вычти R0 из R1 и выведи разность в X.','В R1 конечное показание, в R0 начальное. Найди приращение в X.','Получить X=R1-R0.']),
 ('sumsquares',['+',['square','R0'],['square','R1']],['Сложи квадраты R0 и R1; результат в X.','Нужна сумма второй степени R0 и второй степени R1 в X.','Вычисли X=R0*R0+R1*R1.']),
 ('mulsub',['-',['*','R0','R1'],'R2'],['Из произведения R0 и R1 вычти R2. Ответ в X.','Рассчитай R0*R1, уменьши на R2 и покажи в X.','Программа X=R0*R1-R2.']),
 ('absdiff',['abs',['-','R0','R1']],['Вычисли модуль разности R0 и R1 в X.','Найди расстояние между числами R0 и R1 на числовой прямой. Ответ в X.','Получить X=abs(R0-R1).']),
 ('squaresum',['square',['+','R0','R1']],['Квадрат суммы R0 и R1 выведи в X.','Сначала сложи R0 и R1, затем возведи результат во вторую степень. Вывод в X.','Нужна программа X=(R0+R1)*(R0+R1).']),
 ('sumratio',['/',['+','R0','R1'],'R2'],['Сумму R0 и R1 раздели на ненулевое R2. Ответ в X.','Сложи два значения из R0 и R1, найди отношение суммы к R2 в X.','Программа должна вычислить X=(R0+R1)/R2.'])]
inputs=[('-7','2','2'),('9','-4','-4'),('0','8','5'),('0.75','-2','0.5'),('-3','-0.5','4'),('5','0.25','-8')]
tasks=[]
for family,expr,wordings in families:
 reference=compile_expr(expr)+[0x50]
 for variant in range(4):
  cases=[]
  for index,values in enumerate(inputs):
   reg={f'R{i}':Decimal(v) for i,v in enumerate(values)}
   with localcontext() as c:c.prec=20;expected=value(expr,reg)
   cases.append(' '.join(k+'='+n(v) for k,v in reg.items())+' => X='+n(expected)+(' PUBLIC=0' if index>=2 else ''))
  broken=list(reference);broken[0]=0x63
  tasks.append(dict(id=f'fresh-{family}-{variant+1}',family=family,task=(wordings[variant] if variant<3 else 'Исправь программу. '+wordings[0]),code=(''.join(f'{x:02X}' for x in broken) if variant==3 else ''),cases=cases,reference_code=''.join(f'{x:02X}' for x in reference)))
old=[json.loads(x) for x in (ROOT/'tests/data/mk61_ai_holdout_v2.jsonl').read_text().splitlines() if x.strip()]
assert len(tasks)==64 and not ({x['task'] for x in tasks}&{x['task'] for x in old})
for label,data in [('fresh64',tasks),('regression20',old)]:
 (OUT/(label+'.jsonl')).write_text(''.join(json.dumps(x,ensure_ascii=False)+'\n' for x in data))
 (OUT/(label+'.tsv')).write_text(''.join('\t'.join([x['id'],x['task'],x.get('code',''),*x['cases']])+'\n' for x in data))
# Validate every fresh specification against a fixed correct program through the same real emulator.
(OUT/'oracle64.tsv').write_text(''.join('\t'.join([x['id'],x['task'],x['reference_code'],*x['cases']])+'\n' for x in tasks))
shutil.copyfile(ROOT/'tests/mk61_ai_eval.cpp',OUT/'eval.cpp')
t=(OUT/'eval.cpp').read_text();t=t.replace('    const auto started = micros(nullptr);','    const auto started = micros(nullptr);\n    if (std::getenv("MK61_QUALITY_ORACLE")) { agent.run_tests(); }\n    else')
t=t.replace('#include <cassert>','#include <cassert>\n#include <cstdlib>');(OUT/'eval.cpp').write_text(t)
sources=['mk61_ai_model.cpp','mk61_ai_linear.cpp','mk61_ai_tokenizer.cpp','mk61_ai_harness.cpp','mk61_ai_tools.cpp','mk61_ai_agent.cpp','mk61_ai_grammar.cpp','mk61emu_core.cpp']
subprocess.run(['clang','-std=c11','-O2','-c',str(SRC/'code/mk61_ai_kernels.c'),'-o',str(OUT/'kernels.o')],check=True)
subprocess.run(['clang++','-std=c++17','-O2','-ffp-contract=off','-DMK61_CORE_STANDALONE=1','-DMK61_CORE_HOT_TABLES_IN_SRAM=0','-I'+str(SRC/'code'),*[str(SRC/'code'/s) for s in sources],str(OUT/'kernels.o'),str(OUT/'eval.cpp'),'-o',str(OUT/'evaluator')],check=True)
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
manifest=dict(status='FROZEN_BEFORE_FRESH_RUN',scope='existingQ4 model used in hardware; host same native C++; no training or device I/O',model_lut_sha256=sha(ROOT/'.build/mk61ai/v3/models/full-lut/MODEL.MKA'),model_int8_sha256=sha(ROOT/'.build/mk61ai/swar-v5/MODEL-NIBBLE.MKA'),evaluation_sha256=sha(OUT/'evaluator'),fresh_sha256=sha(OUT/'fresh64.jsonl'),regression_sha256=sha(OUT/'regression20.jsonl'),cases=dict(fresh_tasks=64,regression_tasks=20,fresh_public=128,fresh_hidden=256),source_pins={str(SRC/'code'/s):sha(SRC/'code'/s) for s in sources},criteria=['all declared cases count, no retries or best-of','same prompts/planning/budget/greedy/SRAM/fullhead for both modes','each task must pass public and hidden cases','retain every baseline-solved regression task','fresh solved count must not decrease','valid tool replies and runtime error rates must not worsen','do not infer noninferiority from zero successes or numerical closeness','switch default and reclaim LUT only if gate passes'])
(OUT/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n');print(json.dumps({k:manifest[k] for k in ['status','cases','criteria']},indent=2))
