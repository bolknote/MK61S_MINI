"""Paired phase consistency with a cumulative, never-reset regression bank."""
from bw_common import ROOT as BW_ROOT,BV_ROOT,BU_ROOT,BV_RESULTS,HERE,REPO,MODELS as BW_MODELS,read,write,rows,save_rows,sha,signature,output_ids,compact_head,check_frozen as previous_check
from bv_common import PARENT_CHECKPOINT
from bu_common import body_ids
ROOT=REPO/'.build/mk61-agent-20261106/spec-phase-consistency-v1'
ACTOR=BW_MODELS['actor'];PARENT=BW_MODELS['U']
BW_RESULTS=BW_ROOT/'server-results'if(BW_ROOT/'server-results/complete.json').exists()else BW_ROOT


def check_frozen():
    previous_check();f=read(ROOT/'frozen.json')
    for n,d in f['sources'].items():assert sha(HERE/n)==d,n
    for n,d in f['files'].items():assert sha(ROOT/n)==d,n
    assert sha(PARENT_CHECKPOINT)==f['parent_adapter_sha256']
    return f
