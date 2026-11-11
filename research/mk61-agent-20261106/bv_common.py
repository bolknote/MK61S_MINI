"""Recover lost SPEC translations while retaining the BU composition gains."""
from bu_common import HERE,REPO,SOURCE,ROOT as BU_ROOT,BT_ROOT,BS_ROOT,read,write,rows,save_rows,sha,signature,ACTIONS,ACTION_IDS,CORRECT_IDS,END,body_ids,output_ids,compact_head,check_frozen as previous_check
ROOT=REPO/'.build/mk61-agent-20261106/spec-retention-recovery-v1'
PARENT_RESULTS=BU_ROOT/'server-results'if(BU_ROOT/'server-results/complete.json').exists()else BU_ROOT
PARENT=PARENT_RESULTS/'export/final'
PARENT_CHECKPOINT=PARENT_RESULTS/'last.safetensors'


def check_frozen():
    previous_check();f=read(ROOT/'frozen.json')
    for n,d in f['sources'].items():assert sha(HERE/n)==d,n
    for n,d in f['files'].items():assert sha(ROOT/n)==d,n
    for n,d in f['parent'].items():assert sha(PARENT/n)==d,n
    assert sha(PARENT_CHECKPOINT)==f['parent_adapter_sha256']
    return f
