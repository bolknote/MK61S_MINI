"""Frozen gold-SPEC diagnostic; no optimizer or deployable oracle profile."""
from bx_common import ROOT as BX_ROOT,ACTOR,HERE,REPO,read,write,rows,sha,output_ids,compact_head,check_frozen as previous_check

ROOT=REPO/'.build/mk61-agent-20261106/spec-gold-cycle-diagnostic-v1'
BX_RESULTS=BX_ROOT/'server-results' if (BX_ROOT/'server-results/complete.json').exists() else BX_ROOT


def check_frozen():
    previous_check();f=read(ROOT/'frozen.json')
    for name,digest in f['sources'].items():assert sha(HERE/name)==digest,name
    for name,digest in f['files'].items():assert sha(ROOT/name)==digest,name
    for name,digest in f['actor'].items():assert sha(ACTOR/name)==digest,name
    return f
