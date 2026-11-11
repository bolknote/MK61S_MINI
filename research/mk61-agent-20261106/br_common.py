"""Clean-cycle capacity comparison with function-matched3M and5M starts."""
from bp_common import HERE,REPO,SOURCES,read,write,rows,save_rows,sha,signature,ACTIONS,ACTION_IDS,CORRECT_IDS,END,body_ids,output_ids,compact_head,check_frozen as check_previous
from bl_common import ROOT as BL_ROOT

ROOT=REPO/'.build/mk61-agent-20261106/capacity-clean-cycles-v1'
SOURCE=SOURCES['full']
ARMS=['small','large']


def check_frozen():
    check_previous();f=read(ROOT/'frozen.json')
    for n,d in f['sources'].items():assert sha(HERE/n)==d,n
    for n,d in f['files'].items():assert sha(ROOT/n)==d,n
    for n,d in f['parent'].items():assert sha(SOURCE/n)==d,n
    return f
