"""Test numeric holdouts and real full RUN cycles before freezing the course."""
from decimal import Decimal
from az_common import ROOT,PARENT,DEV_NUMBERS,TEST_NUMBERS,read,rows,write
from az_teacher import pool_for
from az_runtime import Session
from ay_codec import encode,decode,compile_spec
from ay_finalize import semantic_key
from az_data import numbers
from ar_spec import verify
from full_isa_vm import FullVM
from ha_protocol import canonical


def main():
    vm=FullVM();roundtrips=0
    for split in ['train','development','closed']:
        for g in rows(ROOT/(split+'-asts.jsonl')):
            assert decode(encode(g['spec'],g['pool']),g['pool'],g['spec']['angle'])==g['spec'];roundtrips+=1
    p=pool_for('Синус -22 и 0.125, разность с 53.25')
    assert all(x in p for x in ['-22','22','0.125','-0.125','53.25','-53.25'])
    g=rows(ROOT/'train-clean.jsonl')[0]
    # Explicit negative constants and a fresh held-out literal survive both codecs.
    literal_checks=0
    for value in ['22','-22','0.125','53.25']:
        text='Вычисли синус '+value+' градусов.';pool=pool_for(text)
        spec={'X':['sin',{'constant':value}],'writes':{},'angle':'DEG'}
        restored=decode(encode(spec,pool),pool,'DEG');assert restored==spec
        assert verify(vm,compile_spec(restored,pool),pool,spec,[{}])['status']=='TESTED';literal_checks+=1
    cycles=0
    for arm in ['hex','spec']:
        for case in [0,1]:
            s=Session(g,g['reference_body'],vm,arm,start_case=case)
            assert s.eligibility()[0]
            body=g['reference_body']if arm=='hex'else g['spec_body']
            for _ in range(2):
                s.apply_action('write',body)
                assert set(s.runs)=={case}and not s.eligibility()[0]
                s.apply_action('run',[1-case]);assert set(s.runs)=={0,1}and s.eligibility()[0]
                case=1-case
            s.apply_action('done',[]);assert s.finished and len(s.history)==5
            cycles+=1
    prior={semantic_key(x['spec'])for split in ['train','development','closed']for x in rows(PARENT/(split+'-clean.jsonl'))}
    seen=set(prior);question_seen=set();counts={}
    for split in ['train','development','closed']:
        values=rows(ROOT/(split+'-clean.jsonl'));own=set()
        forbidden=DEV_NUMBERS+TEST_NUMBERS if split=='train'else TEST_NUMBERS if split=='development'else[]
        banned={canonical(abs(Decimal(x)))for x in forbidden}
        for row in values:
            key=semantic_key(row['spec']);replay=row.get('curriculum')=='replay'
            assert key not in seen or(split=='train'and replay),(split,row['id'])
            assert not(numbers(row['spec']['X'])&banned),(split,row['id'])
            assert not({canonical(abs(Decimal(x)))for x in row['pool']}&banned)
            assert verify(vm,row['reference_body'],row['pool'],row['spec'],row['public_inputs'])['status']=='TESTED'
            assert decode(row['spec_body'],row['pool'],row['spec']['angle'])==row['spec']
            q=(row['spec']['angle'],row['task']);assert q not in question_seen
            own.add(key)
        question_seen.update((r['spec']['angle'],r['task'])for r in values);seen.update(own);counts[split]=len(values)
    malformed=0
    for body in [[],[255],[15,0],[255,255],[255,0,1],[255,16],[255,16,250],[255,64,0],[255,True]]:
        try:decode(body,p,'RAD')
        except (ValueError,TypeError):malformed+=1
        else:raise AssertionError(('malformed accepted',body))
    result={'AST_roundtrips':roundtrips,'new_literal_ROM_checks':literal_checks,'full_two_edit_RUN_cycles':cycles,
        'families_and_numeric_holdouts_checked':True,'no_prior_exam_signatures_replayed':True,
        'counts':counts,'malformed_rejections':malformed,'optimizer_updates':0}
    write(ROOT/'codec-checks.json',result);print(result,flush=True)


if __name__=='__main__':main()
