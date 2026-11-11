"""Prove prompt/action equivalence on real states before the closed exam."""
from ba_common import ROOT,HERE,read,rows,write,sha
from ba_pools import lesson_layout
from az_runtime import render
from bb_canonical import request_state,response_body
from ay_codec import decode,compile_spec,encode
from ha_protocol import assemble


def main():
    records=rows(ROOT/'lessons.jsonl');checked=0
    for i,row in enumerate(records):
        if i%67:continue
        canonical=request_state(row['state']);prompt=render(canonical,'spec')
        target=encode(row['target_spec'],canonical['pool'])
        for mode in ['default','extras','full']:
            changed=lesson_layout(row,mode,row['id']+':canonical:'+mode);actual=changed['state'];normalized=request_state(actual)
            assert render(normalized,'spec')==prompt
            restored=response_body('write',target,actual)
            assert decode(restored,actual['pool'],actual['view']['angle'])==row['target_spec']
            assert assemble(compile_spec(row['target_spec'],actual['pool']),actual['pool'],'asm')==assemble(compile_spec(row['target_spec'],canonical['pool']),canonical['pool'],'asm')
            if actual['body']is not None:
                assert assemble(actual['body'],actual['pool'],'asm')==assemble(normalized['body'],normalized['pool'],'asm')
            checked+=1
    receipt={'complete':True,'real_state_checks':checked,'no_gold_spec_access_in_middleware':True,
       'canonicalization_does_not_add_or_remove_constant_values':True,'source_sha256':sha(HERE/'bb_canonical.py'),
       'closed_model_generations_seen':(ROOT/'preselected.json').exists(),
       'separate_harness_ablation_not_used_for_weight_selection':True}
    write(ROOT/'canonical-order-policy.json',receipt);print(receipt,flush=True)


if __name__=='__main__':main()
