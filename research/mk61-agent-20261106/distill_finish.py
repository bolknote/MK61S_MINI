"""Export teacher-trained checkpoints and report executed Russian tasks honestly."""
import hashlib
import json
from pathlib import Path
import shutil

from tasks import BUILD,HERE


def read(path):return json.loads(path.read_text())


def short(value):
    return {k:value[k]for k in ['passed','total','pass_rate','valid_tool_tasks','by_kind']if k in value}


def main():
    root=BUILD/'distill-v1';source=root/'server-results'
    state=read(source/'status.json')
    if state['phase']!='teacher_round_complete':raise ValueError('Round is not complete')
    selected=read(source/'preselected.json')
    report={'preselected':selected,'frozen_probes':read(root/'frozen-v2.json'),
            'policy':read(source/'policy.json'),'teacher':read(source/'teacher-manifest.json'),
            'training':read(source/'own-error-clean-manifest.json'),'models':{},'baselines':{},
            'host_activations_and_kv':'FP32; real Q4 weight packing and reload',
            'native_picocalc_runtime_implemented':False}
    for name in ['original','previous-plan','previous-direct']:
        report['baselines'][name]=short(read(source/'results'/f'baseline-{name}-q4-fresh-russian-v2.json'))
    broad=BUILD/'distill-broad/server-results'
    if(broad/'teacher-manifest.json').exists():report['broad_teacher']=read(broad/'teacher-manifest.json')
    if(broad/'data-manifest.json').exists():report['broad_data']=read(broad/'data-manifest.json')
    for arm in ['structured','direct']:
        name=arm+'-clean';export=root/'export'/arm;hf=export/'hf';hf.mkdir(parents=True,exist_ok=True)
        scores={}
        for fmt in ['q4','fp32']:
            for split in ['fresh-russian-v2','formal','opened-diagnostic']:
                scores[fmt+':'+split]=short(read(source/'results'/f'{name}-{fmt}-{split}.json'))
        scores['q4:validation']=short(read(source/'results'/f'{name}-q4-validation.json'))
        scores['q4:semantic']=short(read(source/'results'/f'{name}-semantic-q4.json'))
        details=read(source/'results'/f'{name}-q4-fresh-russian-v2.json')['details']
        tool_stats={'trace_tasks':sum(any(h.get('tool')=='trace'for h in d['history'])for d in details),
                    'passed_after_failed_run':sum(d['pass']and any(h.get('public_result',{}).get('pass')is False for h in d['history'][:-1])for d in details),
                    'public_pass_hidden_fail':sum(d.get('public_pass',False)and not d['pass']for d in details)}
        for p in(source/name/'best').iterdir():
            if p.is_file():shutil.copy2(p,hf/p.name)
        q4=export/'model.mkq4';shutil.copy2(source/'results'/f'{name}-q4-fresh-russian-v2.mkq4',q4)
        manifest={'arm':arm,'parameters':3017984,'context':512,'q4_file':str(q4),'q4_bytes':q4.stat().st_size,
                  'q4_sha256':hashlib.sha256(q4.read_bytes()).hexdigest(),'hf_directory':str(hf),
                  'hf_sha256':hashlib.sha256((hf/'model.safetensors').read_bytes()).hexdigest(),
                  'tokenizer_bytes':(hf/'tokenizer.json').stat().st_size,'scores':scores,'tool_behavior':tool_stats,
                  'initial_teacher_training':read(source/arm/'training.json'),
                  'clean_teacher_training':read(source/name/'training.json')}
        (export/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n');report['models'][arm]=manifest
    chosen=selected['arm'].removesuffix('-clean');report['selected']=chosen
    scores=report['models'][chosen]['scores'];natural=scores['q4:fresh-russian-v2'];formal=scores['q4:formal']
    achieved=natural['passed']/natural['total']>=.8 and formal['passed']/formal['total']>=.95
    report['declared_quality_target_met']=achieved
    (root/'final-report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    lines=['# Flourish-3M после обучения с учителем','',
           '**'+('Заданный порог на новых русских задачах достигнут.'if achieved else'Заданный порог качества пока не достигнут.')+'**',
           'Результаты относятся к коротким арифметическим программам и отдельной проверке управления. '
           'Это не проверка генерации полноценных исторических игр.','',
           '| Вариант | Новые русские условия, Q4 | Формальная регрессия, Q4 |','| --- | ---: | ---: |']
    for name,label in [('original','Исходная Flourish'),('previous-plan','Предыдущая с планом'),('previous-direct','Предыдущая без плана')]:
        v=report['baselines'][name];lines.append(f"| {label} | {v['passed']}/{v['total']} | — |")
    for arm,label in [('structured','Учитель, короткая формула'),('direct','Учитель, сразу код')]:
        s=report['models'][arm]['scores'];n=s['q4:fresh-russian-v2'];f=s['q4:formal']
        lines.append(f"| {label} | {n['passed']}/{n['total']} | {f['passed']}/{f['total']} |")
    lines+=['',f'До открытия итогового теста по валидации выбран **{chosen}**. '
            'При выборе требуется не менее 95% на 20 формальных задачах, затем сравнивается точность на 32 русских условиях.','',
            '## Как обучалось','',
            'Большая модель Qwen создавала разные описания проверяемых алгоритмов. Второй проход той же модели '
            'восстанавливал выражение по тексту без показа эталона; несовпадения исключались. Это фильтр разметки, '
            'а не независимая человеческая проверка. Каждый принятый эталон дополнительно исполнялся на микрокодном ядре МК-61.','',
            'Обучение включает русский текст → формула, русский текст → байты, запуск, трассировку и исправление '
            'по фактической ошибке. Собственные ошибки собраны только на обучающих задачах. '
            'После 6000 шагов добавлен очищенный корпус с дополнительными разговорными формулировками и ещё 4000 шагов QAT. '
            'Исходные наборы и журналы сохранены.','',
            'Две версии стартуют с одинаковых весов. Одна пишет короткую алгебраическую формулу перед кодом, '
            'вторая сразу код. Само наличие формулы не доказывает универсального рассуждения.','',
            '## Проверка','',
            'Новые 64 русских условия написаны отдельно от генератора учителя и зафиксированы до градиентов. '
            'Числовые пробы до обучения исправлены: отрицательные значения для модуля/смены знака, допустимые положительные '
            'входы для задач о количестве. Две видимые и семь скрытых проверок на условие. '
            'Элементарные алгоритмы могут встречаться в обучении: измеряется перенос на новые формулировки.','',
            'Основной результат всегда получает программа, байты которой написала сама Flourish. '
            'Отдельный тест перевода в формулу использует компилятор только для диагностики и не входит в основную точность. '
            'Лимиты: 512 токенов контекста, три хода по 160 новых токенов, не более 105 байтов программы.','',
            '## Веса и исполнение','']
    for arm,m in report['models'].items():
        lines.append(f"- `{arm}`: [{m['q4_bytes']} байт MKQ4v1]({m['q4_file']}); [HF-веса]({m['hf_directory']}).")
    lines+=['','Q4-файлы реально упакованы и загружены заново. Активации и KV-кеш на хосте — FP32. '
            'Расчёт FP16 KV на устройстве: 1 310 720 байт для 512 токенов. '
            'Нативный запуск PicoCalc, его скорость и пиковая память пока не измерены.','',
            '[Методика этапа](DISTILLATION.md). Полные ответы, скрытые проверки, хеши, датасеты и журналы находятся '
            'в `.build/mk61-agent-20261106/distill-v1/` и `distill-broad/`.','']
    (HERE/'DISTILLATION_RESULTS.md').write_text('\n'.join(lines))
    print(json.dumps({'selected':chosen,'target_met':achieved,'models':{a:{'scores':m['scores'],'q4_bytes':m['q4_bytes']}for a,m in report['models'].items()}},ensure_ascii=False,indent=2))


if __name__=='__main__':main()
