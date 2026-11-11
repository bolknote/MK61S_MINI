"""Keep only valid decisions from each teacher's successful actual episodes."""
import collections
import json
from ai_common import ROOT,PARENT,TEACHERS,read,write,sha
from ai_teacher import correct,make_session,expert
from full_isa_vm import FullVM
from tasks import save_jsonl


def main():
    ROOT.mkdir(exist_ok=True)
    if(ROOT/'anchor-frozen.json').exists():return
    vm=FullVM();meta={};all_rows=[]
    for name,path in [('balanced',PARENT/'initial-fresh-audit.json'),('distill',PARENT/'distill/terminal-fresh-audit.json')]:
        audit=json.loads(path.read_text());rows=[];seen=set();rejected=0
        for part,taskfile,seedfile in [('main','fresh.jsonl','fresh-seeds.jsonl'),('skills','fresh-skills.jsonl','fresh-skill-seeds.jsonl'),('goals','fresh-goals.jsonl','fresh-goal-seeds.jsonl')]:
            tasks={t['id']:t for t in read(PARENT/taskfile)};seeds=read(PARENT/seedfile)
            for seed,episode in zip(seeds,audit[part]['raw']['details']):
                if not episode['pass']:continue
                t=tasks[seed['task_id']];s=make_session(t,seed,vm)
                for h in episode['history']:
                    if'prompt'not in h or'generation'not in h:continue
                    assert s.request()==h['prompt'],('Teacher history mismatch',name,t['id'])
                    g=h['generation'];expected,body=expert(s,t);ok=g.get('action')==expected and not g.get('codec_error')
                    if ok and expected=='write':ok=correct(vm,t,g['body'],s.pool)
                    elif ok and expected=='run':ok=g['body']==body
                    elif ok and expected=='done':ok=correct(vm,t,s.body,s.pool)and s.eligibility()[0]
                    if ok:
                        key=json.dumps([h['prompt'],g['action'],g['body']],ensure_ascii=False)
                        if key not in seen:
                            rows.append({'task_id':t['id'],'prompt':h['prompt'],'action':g['action'],'body':g['body'],
                              'correctness':int(correct(vm,t,s.body,s.pool)),'eligible_for_DONE':s.eligibility()[0],
                              'level':t.get('level',1),'group':t['group'],'origin':'verified_teacher','teacher':name,
                              'runtime_has_expected':False,'source_part':part});seen.add(key)
                    else:rejected+=1
                    if g.get('codec_error'):break
                    s.apply_action(g['action'],g['body'])
                    if s.finished or s.abstained:break
        # Older balanced decisions already passed the same ROM/expert checks.
        if name=='balanced':
            for r in read(PARENT/'anchors.jsonl'):
                key=json.dumps([r['prompt'],r['action'],r['body']],ensure_ascii=False)
                if key not in seen:rows.append({**r,'teacher':name,'eligible_for_DONE':r['action']=='done'if'eligible_for_DONE'not in r else r['eligible_for_DONE']});seen.add(key)
        assert len(rows)>500
        file=ROOT/f'anchors-{name}.jsonl';save_jsonl(file,rows);all_rows+=rows
        meta[name]={'rows':len(rows),'actions':dict(collections.Counter(r['action']for r in rows)),'nonexpert_decisions_excluded':rejected,
          'sha256':sha(file),'source_audit_sha256':sha(path),'teacher_master_sha256':sha(TEACHERS[name][0]/'model.safetensors'),'teacher_packet_sha256':sha(TEACHERS[name][1])}
    save_jsonl(ROOT/'anchors.jsonl',all_rows)
    write(ROOT/'anchor-frozen.json',{'teachers':meta,'rows':len(all_rows),'verified_correct_decisions_only':True,'old_exam_now_training':True,'frozen_before_SGD':True})
    print(json.dumps(meta),flush=True)


if __name__=='__main__':main()
