"""Freeze the controlled data correction and a fresh closed exam before SGD."""
import json
import time
from decimal import Decimal
from bp_common import ROOT,PREVIOUS,PRIOR_RESULTS,SOURCES,BAD_SOURCES,TEST_NUMBERS,HERE,PRIORS,read,write,rows,sha,signature,check_previous
from be_language import paths3
from ha_protocol import canonical


def main():
    check_previous();assert not(ROOT/'frozen.json').exists()
    for name in ['training-inputs.json','teacher-frozen.json','ast-frozen.json']:
        for n,d in read(ROOT/name)['files'].items():assert sha(ROOT/n)==d,n
    assert sha(ROOT/'teacher-audit.jsonl')==read(ROOT/'teacher-frozen.json')['audit_sha256']
    assert sha(ROOT/'development-clean.jsonl')==sha(PREVIOUS/'development-clean.jsonl')
    assert sha(ROOT/'policy.json')==sha(PREVIOUS/'policy.json')
    values=rows(ROOT/'lessons.jsonl');valid=read(ROOT/'valid-ids.json')
    train_signatures={signature(values[i]['target_spec'])for i in valid}
    old_signatures={signature(g['spec'])for p in list(dict.fromkeys([*PRIORS,PRIOR_RESULTS]))for split in ['train','development','closed']for g in rows(p/(split+'-clean.jsonl'))}
    new={signature(g['spec'])for g in rows(ROOT/'closed-clean.jsonl')}
    assert not new&train_signatures and not new&old_signatures
    held={tuple(x)for x in read(ROOT/'ast-frozen.json')['test_triples']}
    assert not any(paths3(values[i]['target_spec']['X'])&held for i in valid)
    banned={canonical(abs(Decimal(x)))for x in TEST_NUMBERS}
    assert not any(any(canonical(abs(Decimal(x)))in banned for x in values[i]['state']['pool'])for i in valid)
    for a in ['lora','full']:
        assert sha(ROOT/('initial-'+a+'.safetensors'))==sha(PREVIOUS/('initial-'+a+'.safetensors'))
        assert read(SOURCES[a]/'manifest.json')['selected_checkpoint_sha256']==sha(ROOT/('initial-'+a+'.safetensors'))
        assert read(BAD_SOURCES[a]/'manifest.json')['selected_checkpoint_sha256']==sha(PRIOR_RESULTS/a/'last.safetensors')
    files={**read(ROOT/'training-inputs.json')['files'],**read(ROOT/'teacher-frozen.json')['files'],**read(ROOT/'ast-frozen.json')['files']}
    for n in ['training-inputs.json','teacher-frozen.json','teacher-audit.jsonl','ast-frozen.json']:files[n]=sha(ROOT/n)
    sources={**read(PREVIOUS/'frozen.json')['sources'],**{p.name:sha(p)for p in HERE.glob('bp_*.py')},
             'bo_review_state_fix.py':sha(HERE/'bo_review_state_fix.py'),'bn_common.py':sha(HERE/'bn_common.py')}
    def assets(folder):return{str(p.relative_to(folder)):sha(p)for p in [folder/'model.mkqb',*sorted((folder/'hf').iterdir())]if p.is_file()}
    write(ROOT/'frozen.json',{'sources':sources,'files':files,'parents':{a:assets(p)for a,p in SOURCES.items()},
          'bad_models':{a:assets(p)for a,p in BAD_SOURCES.items()},'SGD_started':False,'closed_model_generations_seen':False,'unix':time.time()})
    write(ROOT/'prepared.json',{'complete':True,'optimizer_updates':0,'corrected_rows':5344,'valid_rows':len(valid),
          'fresh_closed_questions':len(rows(ROOT/'closed-clean.jsonl')),'same_policy_and_initial_weights':True})
    print(json.dumps(read(ROOT/'prepared.json')),flush=True)


if __name__=='__main__':main()
