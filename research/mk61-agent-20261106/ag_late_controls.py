"""Matched last-action controls: finish correct code, abstain on unresolved errors."""
import json
from ag_common import ROOT,read,write,sha
from ag_teacher import make_session,row
from full_isa_vm import FullVM,check_task
from tasks import save_jsonl

def main():
    assert not(ROOT/'prepared.json').exists()and not(ROOT/'start-launch.json').exists()
    if(ROOT/'late-controls-before-SGD.json').exists():return
    vm=FullVM();tasks={t['id']:t for t in read(ROOT/'train.jsonl')};rows=read(ROOT/'hard-lessons.jsonl')
    for f in read(ROOT/'forty-errors.jsonl'):
        t=tasks[f['task_id']];assert check_task(vm,t['reference_code'],t)['pass']
        for good,code in [(False,f['wrong_code']),(True,t['reference_code'])]:
            s=make_session(t,{'initial_code':code,'candidate_code':code,'pool':f['pool'],'pre_run_all':True},vm)
            for _ in range(9):s.apply_action('run',[0])
            r=row(s,t,'matched_last_action',hard_case=True);assert r['action']==('done'if good else'unsure')
            rows.append(r)
    save_jsonl(ROOT/'hard-lessons.jsonl',rows)
    write(ROOT/'late-controls-before-SGD.json',{'states_added':80,'all_forty_references_reverified':True,'optimizer_updates_before_change':0})
    meta=json.loads((ROOT/'data-frozen.json').read_text());meta['hard_lessons']=len(rows)
    meta['files']={p.name:sha(p)for p in ROOT.iterdir()if p.suffix in ['.json','.jsonl']and p.name not in ['data-frozen.json','start-launch.json']}
    write(ROOT/'data-frozen.json',meta);print(json.dumps({'hard_lessons':len(rows),'added':80}),flush=True)

if __name__=='__main__':main()
