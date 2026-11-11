"""Frozen single-section prompt ablation, with no parameter updates."""
from bz_common import ROOT as BZ_ROOT,BY_ROOT,BY_RESULTS,BX_RESULTS,ACTOR,PARENT,HERE,REPO,read,write,rows,sha,output_ids,compact_head,check_frozen as previous_check

ROOT=REPO/'.build/mk61-agent-20261106/spec-prompt-parts-v1'
BZ_RESULTS=BZ_ROOT/'server-results'
VARIANTS=('calls','diag','notes')


def check_frozen():
    previous_check();f=read(ROOT/'frozen.json')
    for name,digest in f['sources'].items():assert sha(HERE/name)==digest,name
    for name,digest in f['files'].items():assert sha(ROOT/name)==digest,name
    return f
