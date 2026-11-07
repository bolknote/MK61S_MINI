"""Freeze 300 controlled Russian conditions, grouped by 60 scenario families."""
import collections
import json
import random

from semantic_common import ROOT,INITIAL_MASTER_SHA,INITIAL_PACKET_SHA,write_json,sha
from compose_common import make_task,substitute,read
from emulator import Emulator,build
from tasks import BUILD,save_jsonl

# New independently authored scenario seeds, never provided to the teacher.
# Five related questions per family are clustered in reporting; these are not
# 300 independent human-written stories or a broad human benchmark.
SEEDS=[
 ('полярный архив','число оцифрованных листов','число новых листов','число забракованных листов','число архивистов'),
 ('подводная база','объём запаса воды','объём пополнения','объём израсходованной воды','число отсеков'),
 ('реставрационная мастерская','число исходных деталей','число полученных деталей','число утраченных деталей','число наборов'),
 ('лесная обсерватория','объём первого массива наблюдений','объём второго массива','объём удалённых записей','число ночей'),
 ('мобильная библиотека','число книг до остановки','число принятых книг','число выданных книг','число маршрутов'),
 ('керамическая студия','масса первой партии глины','масса второй партии','масса отходов','число заготовок'),
 ('музей механики','число принятых экспонатов','число дополнительных экспонатов','число исключённых экспонатов','число залов'),
 ('оранжерея на крыше','объём воды в баке','объём долитой воды','объём использованной воды','число грядок'),
 ('радиокружок','число годных деталей в первой коробке','число деталей во второй','число выбракованных деталей','число участников'),
 ('экспедиционный склад','масса начального груза','масса довезённого груза','масса списанного груза','число саней'),
 ('кукольный театр','число мест первой зоны','число мест второй зоны','число закрытых мест','число секций'),
 ('школьная типография','число листов в первом стопе','число листов во втором стопе','число испорченных листов','число комплектов'),
 ('сборочная станция','число готовых модулей','число добавленных модулей','число неисправных модулей','число платформ'),
 ('мастерская витражей','площадь первого стекла','площадь второго стекла','площадь обрезков','число панелей'),
 ('пещерный лагерь','объём первой ёмкости','объём второй ёмкости','объём потерь','число групп'),
 ('шахматный фестиваль','число заявок первой волны','число заявок второй волны','число отменённых заявок','число турнирных залов'),
 ('парк роботов','число исходных аккумуляторов','число заряженных дополнительно','число снятых аккумуляторов','число роботов'),
 ('звуковая лаборатория','объём первой записи','объём второй записи','объём вырезанных фрагментов','число носителей'),
 ('питомник редких растений','число сеянцев первой партии','число сеянцев второй партии','число погибших сеянцев','число лотков'),
 ('геологическая коллекция','масса первого образца','масса второго образца','масса удалённых включений','число проб'),
]


def main():
    ROOT.mkdir(exist_ok=True)
    if(ROOT/'audit-frozen.json').exists():
        frozen=json.loads((ROOT/'audit-frozen.json').read_text())
        assert all(sha(ROOT/name)==item['sha256']for name,item in frozen['files'].items());print('Audit already frozen');return
    # Semantic groups use three distinct question sets, not register renamings.
    groups=[
      [(['-','A','C'],'Сколько останется от первоначального запаса, если убрать списанную часть, не учитывая пополнение?'),
       (['-',['+','A','B'],'C'],'Всё пополнение присоединили к исходному запасу и затем списали указанную часть. Нужен конечный остаток.'),
       (['-','A',['+','B','C']],'Считай вторую величину дополнительным расходом. Из исходной величины убери и этот расход, и списанную часть.'),
       (['/',['-',['+','A','B'],'C'],'D'],'После объединения исходного запаса с пополнением и списания потерь остаток поровну разделили между получателями. Найди долю одного.'),
       (['-','A',['/',['+','B','C'],'D']],'Сложи вторую и третью величины, раздели их сумму на число получателей. На полученную долю уменьши первую величину.')],
      [(['/','A','D'],'Исходный запас без изменений делят между получателями поровну. Какая доля у одного?'),
       (['/',['+','A','B'],'D'],'Объедини первый запас с пополнением и распредели всё поровну между получателями. Потери здесь не учитываются.'),
       (['+','A',['/','B','D']],'Первый запас остаётся целиком, а из пополнения берут только долю одного получателя. Сколько будет вместе?'),
       (['+',['/','A','D'],['/','B','D']],'Первый запас и пополнение поделили между теми же получателями отдельно. Сложи две доли, доставшиеся одному.'),
       (['-',['/','A','D'],['/','C','D']],'Для одного получателя найди его долю исходного запаса за вычетом его доли списанной части. Обе доли считают для одинакового числа получателей.')],
      [(['abs','C'],'Третья величина может иметь знак. Найди её размер, не учитывая знак.'),
       (['abs',['-','A','B']],'На сколько первый запас отличается от второго по абсолютной величине? Направление разницы не нужно.'),
       (['square',['-','A','B']],'Мера расхождения определена как квадрат разности первого и второго запасов. Вычисли эту меру.'),
       (['/',['square',['-','A','B']],'D'],'Для показателя найди квадрат расхождения между первым и вторым запасами и раздели его на число получателей.'),
       (['+',['abs',['-','A','B']],'C'],'Сначала узнай абсолютное расхождение первого и второго запасов. Затем прибавь третью величину с её исходным знаком.')],
    ]
    em=Emulator(build(ROOT/'libaudit-reference.so'));rng=random.Random(6116001);rows=[]
    for index,(topic,a,b,c,d)in enumerate(SEEDS):
        for kind,questions in enumerate(groups):
            names=rng.sample(['R0','R1','R2','R3'],4);mapping=dict(zip('ABCD',names));family=f'audit-family-{index:02d}-{kind}'
            roles={names[0]:a,names[1]:b,names[2]:c,names[3]:d}
            legend='; '.join(k+' — '+v for k,v in roles.items())+'.'
            for q,(expr,text)in enumerate(questions):
                # Explicitly fix the role of D in questions mentioning recipients.
                if 'получател' in text:legend_for_question=legend+' Под получателями здесь понимается количество '+names[3]+'.'
                else:legend_for_question=legend
                task=make_task('Ситуация «'+topic+'». '+legend_for_question+' '+text,substitute(expr,mapping),rng,
                  family+f':{q}',split='closed-audit',emulator=em)
                rows.append({**task,'language_family':family,'story_seed':index,'audit_style':'controlled_narrative_with_explicit_register_roles'})
    assert len(rows)==300
    save_jsonl(ROOT/'audit.jsonl',rows)
    policy={'arms':['direct','auxiliary'],'steps_each':2000,'validation_interval':250,'effective_batch':128,
      'lr':1e-5,'embedding_lr_factor':.5,'weight_decay':.01,'warmup_updates':100,
      'contexts':[512,1024,2048],'context_probabilities':[.8,.1,.1],'quantization':'Q4 from first update',
      'primary_selection':'validation-best; freeze before audit; include original baseline',
      'targets_not_guarantees':{'two_operations':.5,'three_operations':.25,'formal':.95},
      'auxiliary_task_fraction':.2,'same_core_examples_both_arms':True,'inference_output':'unchanged calc+HEX+tools',
      'no_formula_warmup':True,'repair_feedback':'training cases only','teacher_endpoint':'http://127.0.0.1:8001/v1/chat/completions'}
    write_json(ROOT/'policy.json',policy)
    write_json(ROOT/'audit-frozen.json',{'before_teacher_generation_and_gradients':True,
      'files':{p.name:{'sha256':sha(p),'rows':len(rows)if p.suffix=='.jsonl'else None}for p in [ROOT/'audit.jsonl',ROOT/'policy.json']},
      'source_master_sha256':INITIAL_MASTER_SHA,'source_packed_sha256':INITIAL_PACKET_SHA,
      'new_conditions':len(rows),'language_families':60,'story_seeds':20,
      'levels':dict(collections.Counter(t['level']for t in rows)),
      'limitations':'Controlled Codex-authored questions: 20 scenarios, 3 question sets, 5 related tasks per family. Not independent human authored stories. Use clustered uncertainty.',
      'teacher_never_receives_audit_conditions':True,'physical_picocalc_measured':False})
    print(json.dumps({'frozen':300,'levels':dict(collections.Counter(t['level']for t in rows))}))


if __name__=='__main__':main()
