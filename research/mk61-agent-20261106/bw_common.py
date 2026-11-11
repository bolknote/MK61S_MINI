"""Immutable factorial comparison of initial and repeated SPEC interpretation."""
from bv_common import ROOT as BV_ROOT,BU_ROOT,PARENT,HERE,REPO,SOURCE,read,write,rows,save_rows,sha,signature,output_ids,compact_head,check_frozen as previous_check
ROOT=REPO/'.build/mk61-agent-20261106/spec-phase-routing-v1'
BV_RESULTS=BV_ROOT/'server-results'if(BV_ROOT/'server-results/complete.json').exists()else BV_ROOT
MODELS={'actor':ROOT/'actor-profile','U':PARENT,'N':BV_RESULTS/'export/final'}
ROUTES={'UU':('U','U'),'NU':('N','U'),'UN':('U','N'),'NN':('N','N')}


def check_frozen():
    previous_check();f=read(ROOT/'frozen.json')
    for name,d in f['sources'].items():assert sha(HERE/name)==d,name
    for name,d in f['files'].items():assert sha(ROOT/name)==d,name
    for role,files in f['models'].items():
        for name,d in files.items():assert sha(MODELS[role]/name)==d,(role,name)
    return f
