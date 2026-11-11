"""Test literal remapping and independent labels before SGD."""
import collections
from decimal import Decimal
from ba_common import ROOT,PRIORS,DEV_NUMBERS,TEST_NUMBERS,read,rows,write
from ba_pools import layout,goal_layout,lesson_layout,remap
from ba_teacher import clean_wording
from az_data import numbers
from ay_finalize import semantic_key
from ay_codec import decode
from full_isa_vm import FullVM
from ar_spec import verify
from ha_protocol import assemble,canonical


def main():
    vm=FullVM();prior_keys={semantic_key(g['spec'])for p in PRIORS for s in ['train','development','closed']for g in rows(p/(s+'-clean.jsonl'))}
    seen=set(prior_keys);counts={};checked=0
    for split in ['train','development','closed']:
        goals=rows(ROOT/(split+'-clean.jsonl'));own=set()
        banned={canonical(abs(Decimal(x)))for x in(DEV_NUMBERS+TEST_NUMBERS if split=='train'else TEST_NUMBERS if split=='development'else[])}
        for g in goals:
            key=semantic_key(g['spec']);old_allowed=split=='train'and g.get('curriculum')in ['replay','retired_exam_error']
            assert key not in seen or old_allowed,(split,g['id']);assert clean_wording(g['task'])
            assert not(numbers(g['spec']['X'])&banned)
            assert not({canonical(abs(Decimal(x)))for x in g['pool']}&banned)
            own.add(key)
        seen.update(own);counts[split]=len(goals)
        for g in goals[:24]:
            raw=assemble(g['reference_body'],g['pool'],'asm')
            for mode in ['extras','full','distractors']:
                p=goal_layout(g,mode)
                assert assemble(p['reference_body'],p['pool'],'asm')==raw
                assert decode(p['spec_body'],p['pool'],g['spec']['angle'])==g['spec']
                assert verify(vm,p['reference_body'],p['pool'],g['spec'],g['public_inputs'])['status']=='TESTED';checked+=1
    values=rows(ROOT/'lessons.jsonl');sample=[r for i,r in enumerate(values)if i%97==0][:600];relabelled=0
    for row in sample:
        for mode in ['default','extras','full','distractors']:
            changed=lesson_layout(row,mode,row['id']+':check:'+mode)
            if row['state']['body']is not None:
                assert assemble(row['state']['body'],row['state']['pool'],'asm')==assemble(changed['state']['body'],changed['state']['pool'],'asm')
            assert row['state']['runs']==changed['state']['runs']and row['state']['remaining']==changed['state']['remaining']
            assert decode(changed['spec_body'],changed['state']['pool'],changed['target_spec']['angle'])==changed['target_spec'];relabelled+=1
    assert all(r['correctness']==1 for r in values if r['action']=='done')
    report={'dataset_questions':counts,'permuted_goal_ROM_checks':checked,'real_state_relabellings':relabelled,
       'new_exam_prior_signatures_excluded':True,'closed_and_development_not_used_for_mining':True,
       'positive_DONE_labels_correct':True,'optimizer_updates':0}
    write(ROOT/'checks.json',report);print(report,flush=True)


if __name__=='__main__':main()
