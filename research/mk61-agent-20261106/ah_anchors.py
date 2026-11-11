"""Retain only proven correct decisions from successful balanced trajectories."""
import collections
import json
from ah_common import ROOT,PARENT,read,write,sha
from ah_teacher import correct,make_session,expert
from full_isa_vm import FullVM
from tasks import save_jsonl


def main():
    ROOT.mkdir(exist_ok=True)
    if(ROOT/'anchor-frozen.json').exists():return
    vm=FullVM();audit=json.loads((PARENT/'balanced-fresh-audit.json').read_text());rows=[];seen=set();rejected=0
    for part,taskfile,seedfile in [('main','fresh.jsonl','fresh-seeds.jsonl'),('neighbors','fresh-neighbors.jsonl','fresh-neighbor-seeds.jsonl'),('goals','fresh-goals.jsonl','fresh-goal-seeds.jsonl')]:
        tasks={t['id']:t for t in read(PARENT/taskfile)};seeds=read(PARENT/seedfile)
        for seed,episode in zip(seeds,audit[part]['raw']['details']):
            if not episode['pass']:continue
            t=tasks[seed['task_id']];s=make_session(t,seed,vm)
            for h in episode['history']:
                if'prompt'not in h or'generation'not in h:continue
                assert s.request()==h['prompt'],('Anchor replay mismatch',t['id'])
                g=h['generation'];expected,body=expert(s,t);ok=g.get('action')==expected and not g.get('codec_error')
                if ok and expected=='write':ok=correct(vm,t,g['body'],s.pool)
                elif ok and expected=='run':ok=g['body']==body
                elif ok and expected=='done':ok=correct(vm,t,s.body,s.pool)and s.eligibility()[0]
                if ok:
                    key=json.dumps([h['prompt'],g['action'],g['body']],ensure_ascii=False)
                    if key not in seen:
                        rows.append({'task_id':t['id'],'prompt':h['prompt'],'action':g['action'],'body':g['body'],
                          'correctness':int(correct(vm,t,s.body,s.pool)),'level':t.get('level',1),'group':t['group'],
                          'origin':'ROM_verified_old_policy','runtime_has_expected':False,'source_part':part})
                        seen.add(key)
                else:rejected+=1
                if g.get('codec_error'):break
                s.apply_action(g['action'],g['body'])
                if s.finished or s.abstained:break
    assert len(rows)>500
    save_jsonl(ROOT/'anchors.jsonl',rows)
    write(ROOT/'anchor-frozen.json',{'rows':len(rows),'actions':dict(collections.Counter(r['action']for r in rows)),
      'nonexpert_or_wrong_decisions_excluded':rejected,'sha256':sha(ROOT/'anchors.jsonl'),
      'source_audit_sha256':sha(PARENT/'balanced-fresh-audit.json'),'verified_correct_old_decisions_only':True,
      'previous_viewed_exam_is_training_now':True,'frozen_before_SGD':True})
    print(json.dumps({'anchors':len(rows),'actions':dict(collections.Counter(r['action']for r in rows))}),flush=True)


if __name__=='__main__':main()
