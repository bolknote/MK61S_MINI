"""Prefilled previous histories are real calls outside the new episode budget."""
import json
from aq_common import ROOT,read,write,sha
from aq_data import initial,expert
from aq_runtime import snapshot
from full_isa_vm import FullVM
from tasks import save_jsonl


def main():
    if(ROOT/'external-data-frozen.json').exists():return
    vm=FullVM();rows=[]
    for g in read(ROOT/'train.jsonl'):
        for r in g['rows']:
            s=initial(g,g['rows'][3],vm);s.apply_action('write',r['body']);s.apply_action('run',[1]);s.apply_action('run',[2]);s.apply_action('run',[0])
            claim=[1,0,0,r['body'][0],r['body'][0]]if r['class']=='correct'else[0,255,255,0,0]
            s.apply_action('diag',claim)
            s.initial_history=len(s.history)
            s.observation='Предыдущая правка выполнена; проверка нового кода продолжается.'
            a,b,ok=expert(s,g);state=snapshot(s);assert state['remaining']==12 and state['revision']==1
            assert a==('done'if r['class']=='correct'else'write')
            row={'id':f'aq:external:{len(rows):07}','group_id':g['id'],'state':state,'action':a,'body':b,'correctness':int(ok),
              'origin':'trajectory','scenario':'real_prefilled_history_new_budget','family':g['family'],'pair_tag':g['pair_tag']}
            if a=='write':row['before_body']=list(s.body)
            rows.append(row)
    save_jsonl(ROOT/'extra-lessons.jsonl',rows)
    write(ROOT/'external-data-frozen.json',{'files':{'extra-lessons.jsonl':sha(ROOT/'extra-lessons.jsonl')},
      'rows':len(rows),'all_prefills_executed_by_live_session':True,'initial_history_boundary_explicit':True,'frozen_before_SGD':True})
    print(json.dumps({'extra_live_examples':len(rows),'frozen':True}),flush=True)


if __name__=='__main__':main()
