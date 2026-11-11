"""Broad3M recovery with translation replay; the working parent stays immutable."""
from br_common import HERE,REPO,SOURCE,BL_ROOT,read,write,rows,save_rows,sha,signature,ACTIONS,ACTION_IDS,CORRECT_IDS,END,body_ids,output_ids,compact_head,check_frozen as previous_check
from bp_common import ROOT as BP_ROOT
ROOT=REPO/'.build/mk61-agent-20261106/spec-diverse-recovery-v1'


def check_frozen():
    previous_check();f=read(ROOT/'frozen.json')
    for n,d in f['sources'].items():assert sha(HERE/n)==d,n
    for n,d in f['files'].items():assert sha(ROOT/n)==d,n
    for n,d in f['parent'].items():assert sha(SOURCE/n)==d,n
    return f
