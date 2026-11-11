"""Exhaustive, ROM-backed inspection of all 40 previous raw false DONEs."""
import collections
import json
from ag_common import ROOT,PARENT,HERE,read,write,sha
from ha_protocol import assemble
from full_isa_vm import FullVM,check_task

CATEGORIES={
 'constant_binding':['target:0001','target:0025','general:0048','general:0057','general:0077','general:0114','general:0120','general:0123','general:0132','general:0135','general:0136','general:0147','general:0152','general:0188'],
 'register_binding':['general:0146','general:0155','general:0178','general:0187','general:0189','general:0190','general:0225','general:0233','general:0237'],
 'missing_operations':['target:0015','target:0020','target:0023','target:0047','general:0096'],
 'wrong_operation':['general:0065','general:0129','general:0162','general:0186','general:0200'],
 'expression_structure':['general:0078','general:0185','general:0205','general:0208','general:0222'],
 'control_flow':['general:0219']}
LABELS={'constant_binding':'Неверная константа','register_binding':'Неверный регистр','missing_operations':'Пропущенные команды',
 'wrong_operation':'Заменённая операция','expression_structure':'Порядок и структура выражения','control_flow':'Остановка и ветвление'}


def main():
    ROOT.mkdir(exist_ok=True);tasks={t['id']:t for t in read(PARENT/'fresh.jsonl')};seeds=read(PARENT/'fresh-seeds.jsonl')
    audit=json.loads((PARENT/'replay-fresh-audit.json').read_text())['main']['raw'];vm=FullVM();records=[]
    mapping={f'af:fresh:{key}':category for category,keys in CATEGORIES.items()for key in keys}
    for i,(seed,r)in enumerate(zip(seeds,audit['details'])):
        if not(r['finished']and not r['program_correct']):continue
        t=tasks[r['id']];code=assemble(r['body'],seed['pool'],'asm');checked=check_task(vm,code,t);assert not checked['pass']
        failure=next(j for j,x in enumerate(checked['details'])if not x['pass']);case=(t['public_tests']+t['hidden_tests'])[failure]
        actual=checked['details'][failure]['segments'][0]['actual'];expected=case['segments'][0]['expected']
        public_failures=sum(not x['pass']for x in checked['details'][:len(t['public_tests'])])
        h=[h for h in r['history']if'generation'in h];done=h[-1];assert done['kind']=='done'
        records.append({'episode_index':i,'task_id':t['id'],'task':t['task'],'category':mapping[t['id']],
            'initially_correct':r['initially_correct'],'model_writes':sum(h['kind']=='write'for h in h),'body':r['body'],'pool':seed['pool'],
            'wrong_code':code,'reference_code':t['reference_code'],'done_prompt':done['prompt'],
            'public_failure_cases':public_failures,'hidden_only_failure':public_failures==0,
            'first_failure':{'case':failure,'public':failure<len(t['public_tests']),'inputs':case['segments'][0]['inputs'],
               'actual_X':actual['numeric']['X'],'expected_X':expected['numeric']['X'],'actual_status':actual['status'],'expected_status':expected['status']}})
    assert len(records)==40;counts=collections.Counter(r['category']for r in records)
    from tasks import save_jsonl
    save_jsonl(ROOT/'forty-errors.jsonl',records)
    summary={'episodes':40,'distinct_tasks':len({r['task_id']for r in records}),'categories':dict(counts),
      'correct_starts_broken':sum(r['initially_correct']for r in records),'no_attempted_WRITE':sum(r['model_writes']==0 for r in records),
      'publicly_observable_failures':sum(not r['hidden_only_failure']for r in records),'hidden_only_failures':sum(r['hidden_only_failure']for r in records),
      'source_audit_sha256':sha(PARENT/'replay-fresh-audit.json'),'teacher_verified_all_references':True}
    write(ROOT/'forty-analysis.json',summary)
    lines=['# Разбор всех 40 оставшихся ложных DONE','',
      'Это полный основной raw-экзамен выбранного адаптера finish-debug-v1. Категории назначены при разборе фактических программ; число эпизодов не равно числу уникальных задач. Все ошибочные результаты повторно проверены ROM-эмулятором.','',
      '| Ошибка | Эпизодов |','|---|---:|',*[f'| {LABELS[k]} | {v} |'for k,v in counts.items()], '',
      f'Изначально верных программ испорчено: {summary["correct_starts_broken"]}. Без попытки WRITE: {summary["no_attempted_WRITE"]}. Несоответствие видно уже на открытых случаях: {summary["publicly_observable_failures"]}; только на скрытых: {summary["hidden_only_failures"]}. «Видно» здесь означает офлайн-сравнение с эталоном: сама сеть эталона не получала.','']
    for n,r in enumerate(records,1):
        f=r['first_failure'];lines += [f'{n}. **{LABELS[r["category"]]}** — {r["task"]}',
          '   Выдано: `'+bytes(r['wrong_code']).hex(' ').upper()+'`.',
          '   Эталон: `'+bytes(r['reference_code']).hex(' ').upper()+'`.',
          f'   Первый провал: случай {f["case"]}, X={f["actual_X"]}, требуется {f["expected_X"]}; статусы {f["actual_status"]}/{f["expected_status"]}. Начальный код '+('был верен.'if r['initially_correct']else'был ошибочным.'),'']
    (HERE/'FORTY_FALSE_DONE_ANALYSIS.md').write_text('\n'.join(lines)+'\n');print(json.dumps(summary,ensure_ascii=False),flush=True)


if __name__=='__main__':main()
