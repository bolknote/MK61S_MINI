import argparse
import json
from pathlib import Path
from vc_common import HERE,write


def main():
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);a=p.parse_args();root=a.root.resolve()
    final=json.loads((root/'final-export.json').read_text());selection=json.loads((root/'preselected.json').read_text())
    reports={k:json.loads((root/'results'/(k+'.json')).read_text())for k in ['baseline','slow-best','fast-best']}
    slow=reports['slow-best']['details'];fast=reports['fast-best']['details'];assert [r['id']for r in slow]==[r['id']for r in fast]
    pair=selection['ensemble'];accepted=[s['score']>=pair['slow']and f['score']>=pair['fast']for s,f in zip(slow,fast)]
    positive=sum(r['label']for r in slow);negative=len(slow)-positive
    ensemble={'true_positive':sum(a and r['label']for a,r in zip(accepted,slow)),'positive':positive,
      'false_positive':sum(a and not r['label']for a,r in zip(accepted,slow)),'negative':negative,
      'validation_coverage':pair['coverage'],'thresholds':{'slow':pair['slow'],'fast':pair['fast']}}
    ensemble['coverage']=ensemble['true_positive']/positive
    native=json.loads((root/'native-verification.json').read_text());post=json.loads((root/'postflight.json').read_text())
    chosen=final['selected_label'];single=reports[chosen];qualified=single['validation']['coverage']>=.8
    use_pair=pair['coverage']>single['validation']['coverage'];mode='ensemble'if use_pair else chosen
    summary={'selected_label':chosen,'mode_selected_on_validation':mode,'single_qualified_on_validation':qualified,
      'ensemble_qualified_on_validation':pair['coverage']>=.8,'ensemble_fresh':ensemble,
      'models':{k:{'validation':r['validation'],'fresh':r['fresh']}for k,r in reports.items()},
      'coder_weights_unchanged':True,'fresh_used_for_selection':False,'native':native,'postflight':post,
      'planned_active_model_images':1,'planned_models_on_SD':3 if use_pair else 2,'physical_picocalc_measured':False,
      'activation_recommended':bool((pair['coverage']>=.8 if use_pair else qualified) and (ensemble['false_positive']==0 if use_pair else single['fresh']['false_positive']==0))}
    write(root/'comparison.json',summary)
    lines=['# Отдельный 3M Q4-проверяющий программ','',
      'Кодирующая модель `harness-debug-v3/active-best` не менялась. Два отдельных проверяющих обучены определять соответствие русского условия, сырого HEX и фактических открытых запусков. Они выдают одну оценку d/t; эталонных значений и скрытых тестов во входе нет.',
      '', '| Снимок | Верных принято на валидации | Ошибочных принято на новом наборе | Верных принято на новом наборе |',
      '|---|---:|---:|---:|']
    for name,r in reports.items():
        v=r['validation'];f=r['fresh'];lines.append(f'| {name} | {v["true_positive"]}/{v["positive"]} | {f["false_positive"]}/{f["negative"]} | {f["true_positive"]}/{f["positive"]} |')
    lines += [f'| Два проверяющих согласны | {round(pair["coverage"]*pair["positive"])}/{pair["positive"]} | {ensemble["false_positive"]}/{negative} | {ensemble["true_positive"]}/{positive} |',
      '', f'Выбор по валидации: **{mode}**. Порог подбирается только на валидации: ноль ложных принятий и максимум принятых верных программ. Целевое покрытие — не менее 80%. Это порог на конечном наборе, а не гарантия для произвольного задания.',
      'Проверяющие имеют ту же архитектуру 3,022,080 параметров, Q4 с первого шага, контекст 1024. Обучение: 2000 шагов каждый, одинаковые сбалансированные выборки, LR 2e-5 и 5e-5. Все входные эмбеддинги заморожены; веса кодирующей модели не менялись.',
      'На PicoCalc модели предполагается загружать по очереди с SD в одну область для весов и повторно использовать KV/workspace. Одновременно держать все образы в памяти не требуется; цена — дополнительные загрузки и прогоны. Физический PicoCalc не измерялся.',
      f'CPU/B200/C++ совпали по решению на {native["decisions_match"]}/{native["probes"]} пробах. Все три Q4 повторно экспортированы без изменения полезных данных; input embedding не изменён.',
      'Проверяющие не включаются в рабочий harness, если они не прошли порог валидации. Уровень покрытия, число неверных допусков и ограничения сохранены в comparison.json.',
      '', f'- [Выбранный проверяющий]({root}/export/selected-budget/model.mka)',f'- [Медленный профиль]({root}/export/slow-best/model.mka)',
      f'- [Быстрый профиль]({root}/export/fast-best/model.mka)',f'- [Результаты и пороги]({root}/comparison.json)']
    if(root/'agent-loop.json').exists():
        agent=json.loads((root/'agent-loop.json').read_text());summary['agent_loop']=agent;write(root/'comparison.json',summary)
        lines += ['', '## Кодирующая модель с проверяющим',json.dumps({k:v for k,v in agent.items()if k!='details'},ensure_ascii=False,indent=2)]
    path=HERE/'VERIFIER_RESULTS.md';path.write_text('\n'.join(lines)+'\n')
    state_path=HERE/'work-state.json';state=json.loads(state_path.read_text());counted=state.get('semantic_verifier_v1',{}).get('completed',False)
    state['semantic_verifier_v1']={'completed':True,'report':str(path),'mode':mode,'single_qualified':qualified,'ensemble_qualified':pair['coverage']>=.8,
      'results':summary['models'],'ensemble_fresh':ensemble,'updates_each':2000}
    if not counted:state['completed_training_runs']+=2;state['total_accounted_optimizer_updates_lower_bound']+=4000
    state['all_own_jobs_complete']=True;state['phase']='semantic_verifier_v1_complete';write(state_path,state)
    print(json.dumps({'mode':mode,'single':single['fresh'],'ensemble':ensemble,'report':str(path)},ensure_ascii=False),flush=True)


if __name__=='__main__':main()
