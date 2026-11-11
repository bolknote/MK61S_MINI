"""Preserve review usage in future snapshots; overlay fixes on immutable BL data."""
import copy
import json
from transformers import AutoTokenizer
from bn_common import ROOT,PREVIOUS,NEW,read,write,rows,save_rows,sha,check
from bj_runtime import snapshot as original_snapshot,SPEC_DIAG
from bl_runtime import Session,render
from bl_vm import CachedVM
from bl_spec import install


def snapshot(session):
    state=original_snapshot(session)
    state['replan_attempted']=bool(session.replan_attempted)
    return state


def corrected(row):
    result=copy.deepcopy(row)
    if 'raw_prompt'not in row and (row['state'].get('observation')or'').startswith('SPEC_REVISED'):
        result['state']['replan_attempted']=True
    return result


def main():
    check();source=PREVIOUS/'lessons.jsonl';values=rows(source);valid=set(read(PREVIOUS/'valid-ids.json'));changes=[]
    for i,r in enumerate(values):
        new=corrected(r)
        if new==r:continue
        assert i in valid
        before=copy.deepcopy(r);before['state']['replan_attempted']=True;assert new==before
        changes.append({'index':i,'id':r['id'],'origin':r['origin'],'action':r['action'],
                        'set_state':{'replan_attempted':True},'evidence':r['state']['observation']})
    assert len(changes)==5344
    save_rows(ROOT/'review-state-corrections.jsonl',changes)
    # A real DIAG/review cycle must leave zero reviews in the snapshot and retain
    # the exact program. This guards the serialization defect behind the data bug.
    install();g=rows(PREVIOUS/'train-clean.jsonl')[0];vm=CachedVM()
    s=Session(g,g['reference_body'],vm,'spec',g['spec'],True);initial=list(s.body)
    s.apply_action('diag',SPEC_DIAG);s.replan_attempted=True;s.apply_replan(g['spec_body'])
    state=snapshot(s);assert state['replan_attempted']and state['body']==initial
    tok=AutoTokenizer.from_pretrained(NEW/'hf',local_files_only=True);p,_=render(state,tok)
    assert 'Разборов SPEC осталось: 0.'in p and 'Разборов SPEC осталось: 1.'not in p
    write(ROOT/'review-state-fix-checks.json',{'complete':True,'corrected_rows':len(changes),
          'source_lessons_sha256':sha(source),'patch_sha256':sha(ROOT/'review-state-corrections.jsonl'),
          'real_review_cycle_snapshot_preserves_used_flag':True,'reference_code_and_labels_unchanged':True,
          'original_dataset_and_weights_untouched':True,'optimizer_updates':0})
    print(json.dumps(read(ROOT/'review-state-fix-checks.json')),flush=True)


if __name__=='__main__':main()
