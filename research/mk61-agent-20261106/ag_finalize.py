"""Finish the frozen inputs and retain ambiguity behavior before any SGD."""
import copy
import json
import random
import shutil
from ag_common import ROOT,read,write,sha
from ag_teacher import row,make_session
from ha_protocol import constants
from full_isa_vm import FullVM
from tasks import save_jsonl


def main():
    assert not(ROOT/'prepared.json').exists()and not(ROOT/'start-launch.json').exists()
    if(ROOT/'finalized-before-SGD.json').exists():return
    meta=json.loads((ROOT/'data-frozen.json').read_text());shutil.copyfile(ROOT/'data-frozen.json',ROOT/'data-before-finalize.json')
    policy=json.loads((ROOT/'policy.json').read_text());policy['body_weight']=2.
    policy['hard_quotas']={'write':7,'done':6,'run':2,'unsure':1};write(ROOT/'policy.json',policy)
    rows=read(ROOT/'lessons.jsonl');base=read(ROOT/'train.jsonl')[0];vm=FullVM();rng=random.Random(1014001)
    for i in range(128):
        text=rng.choice(['Нужна программа для X. ','Напиши код для R4. ','Хочу расчёт на МК-61. ','Результат требуется в X. ','Помоги обработать число. ','Подготовь вычисление. ','Сделай программу. ','Найди ответ на калькуляторе. '])+rng.choice([
          'Формулу ещё не сообщил.','Конкретную операцию пока не выбрали.','Что именно считать, я уточню позже.','Само условие пришлю следующим сообщением.','Требуемую функцию пока не назвал.','У задачи пока нет определения результата.','Неизвестно, какое значение нужно получить.','Выражение пока отсутствует.'])
        t=copy.deepcopy(base);t.update(id=f'ag:unknown:{i}',task=text,constants=constants(text),underspecified=True,level=1)
        s=make_session(t,{'initial_code':[0x50],'candidate_code':[0x50],'start_empty':i%2==0,'pre_run_all':True},vm)
        rows.append(row(s,t,'underspecified_retention'))
    save_jsonl(ROOT/'lessons.jsonl',rows);meta['lessons']=len(rows)
    write(ROOT/'finalized-before-SGD.json',{'body_loss_weight':2.,'ambiguity_retention_added':128,'optimizer_updates_before_change':0})
    meta['files']={p.name:sha(p)for p in ROOT.iterdir()if p.suffix in ['.json','.jsonl']and p.name not in ['data-frozen.json','start-launch.json']}
    write(ROOT/'data-frozen.json',meta);print(json.dumps({'finalized':True,'lessons':len(rows)}),flush=True)


if __name__=='__main__':main()
