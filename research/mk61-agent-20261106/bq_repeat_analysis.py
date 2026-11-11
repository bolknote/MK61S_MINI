"""Paired task-cluster uncertainty and conclusions after the frozen BP exam."""
import json
import numpy as np
from bp_common import ROOT,HERE,read,write,sha,check_frozen


def main():
    check_frozen();assert read(ROOT/'finish.json')['complete']
    endpoints=read(ROOT/'paired-endpoints.json');out={};rng=np.random.default_rng(261119991)
    for arm in ['lora','full']:
        before={x['id']:x for x in endpoints['bad_'+arm]};after={x['id']:x for x in endpoints['fixed3000_'+arm]};assert before.keys()==after.keys()
        tasks=sorted({x['task_id']for x in before.values()});assert len(tasks)==256;index={k:i for i,k in enumerate(tasks)};d=np.zeros((256,4),dtype=np.float64)
        for k,b in before.items():
            c=after[k];i=index[b['task_id']]
            d[i,0]+=int(c['pass'])-int(b['pass'])
            d[i,1]+=(int(c['pass'])-int(b['pass']))if not b['initially_correct']else 0
            d[i,2]+=int(c['finished']and not c['program_correct'])-int(b['finished']and not b['program_correct'])
            d[i,3]+=(int(not c['program_correct'])-int(not b['program_correct']))if b['initially_correct']else 0
        sample=rng.integers(0,256,size=(10000,256));values=d[sample].sum(1)/np.array([512,256,512,256])*100
        point=d.sum(0)/np.array([512,256,512,256])*100
        out[arm]={k:{'delta_percentage_points':float(point[j]),'CI95_percentile':[float(x)for x in np.percentile(values[:,j],[2.5,97.5])]}for j,k in enumerate(['completion','repairs','false_accepted_DONE','corruption'])}
    write(ROOT/'paired-uncertainty.json',{'arms':out,'method':'10000 paired bootstrap draws of256 task clusters, both starts stay together','fixed_training_seed':True,'does_not_measure_training_seed_uncertainty':True})
    path=HERE/'SPEC_REVIEW_FLAG_FIX_RESULTS.md';text=path.read_text()
    lead=('Контролируемый повтор не подтвердил общий выигрыш от одного исправления флагов. У полной ветки на новом тесте завершения364→361, ложные принятые DONE8→9; это небольшие различия. У LoRA завершения335→354, но ложные принятые DONE8→20 и порча4→9. Ошибка разметки была реальной, однако считать её главной причиной потери качества по этому повтору нельзя. Рабочий профиль не заменён.\n\n')
    if 'Контролируемый повтор не подтвердил общий выигрыш'not in text:
        at=text.index('\n\n')+2;text=text[:at]+lead+text[at:]
    if '## Неопределённость эффекта'not in text:
        lines=['','## Неопределённость эффекта','',
               'Разница — исправленные флаги минус ошибочные флаги. Интервалы95% получены попарным bootstrap по256 задачам; два начальных состояния одной задачи не разделялись. Это неопределённость по задачам при одном seed обучения, не устойчивость к разным seed.','',
               '| Ветка | Завершения, п.п. | Исправления, п.п. | Ложные принятые DONE, п.п. | Порча, п.п. |',
               '|---|---:|---:|---:|---:|']
        for arm,m in out.items():
            cells=[]
            for k in ['completion','repairs','false_accepted_DONE','corruption']:
                x=m[k];lo,hi=x['CI95_percentile'];cells.append(f"{x['delta_percentage_points']:+.2f} [{lo:+.2f}; {hi:+.2f}]")
            lines.append('| '+arm+' | '+' | '.join(cells)+' |')
        lines+=['','Эти данные дают признаки плато нынешнего совместного обучения, но не доказывают предел ёмкости3M. Для такого вывода нужны отдельно качество на обученных задачах и контролируемое сравнение с большей моделью при тех же данных и протоколе.','']
        text+='\n'.join(lines)
    post=read(ROOT/'server-results/postflight.json')
    if not post.get('live_remote_recheck_completed',True):
        text=text.replace('`server-results/postflight.json` подтверждает завершение своих контейнеров, неизменность замороженных входов и сохранение основного профиля.',
            '`server-results/postflight.json`: завершение всех запущенных рабочих процессов подтверждено скачанной итоговой квитанцией контроллера, исходники и данные проверены локально. Повторная онлайн-проверка живого состояния сервера недоступна: SSH banner timeout после шести попыток. Это не затронуло обучение, закрытый тест и сверку Q4, которые уже завершились.')
    for a,b in {'завершения364':'завершения 364','DONE8':'DONE 8','завершения335':'завершения 335','порча4':'порча 4','Интервалы95':'Интервалы 95','по256':'по 256','ёмкости3M':'ёмкости 3M'}.items():text=text.replace(a,b)
    path.write_text(text);finish=read(ROOT/'finish.json');finish['report_sha256']=sha(path);finish['post_analysis_source_sha256']=sha(__file__);write(ROOT/'finish.json',finish)
    diagnosis=HERE/'WEIGHT_DIAGNOSIS_RESULTS.md';dtext=diagnosis.read_text()
    if '## Последующий контролируемый повтор'not in dtext:
        dtext+='\n## Последующий контролируемый повтор\n\nПовтор от тех же родителей с единственным исправлением5344 флагов завершён. На новом закрытом тесте он не подтвердил общий выигрыш: full364→361 завершение и8→9 ложных принятых DONE; LoRA335→354 завершения, но8→20 ложных DONE. Ошибка состояния действительно была, но гипотеза о её главном причинном вкладе не подтверждена этим повтором. См. [результаты повтора](SPEC_REVIEW_FLAG_FIX_RESULTS.md).\n'
        for a,b in {'исправлением5344':'исправлением 5344','full364':'full 364','и8':'и 8','LoRA335':'LoRA 335','но8':'но 8'}.items():dtext=dtext.replace(a,b)
        diagnosis.write_text(dtext)
        receipt_path=ROOT.parent/'weight-diagnosis-v1/complete.json';receipt=read(receipt_path);receipt['report_sha256']=sha(diagnosis);receipt['later_controlled_repeat_report']=str(path);write(receipt_path,receipt)
    print(json.dumps({'paired_uncertainty':out,'report':str(path)},ensure_ascii=False),flush=True)


if __name__=='__main__':main()
