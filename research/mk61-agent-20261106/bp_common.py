"""Matched repeat of BL with only the proven review-state flags corrected."""
from bl_common import HERE,REPO,ROOT as PREVIOUS,PARENT,SOURCES,PRIORS,ACTIONS,ACTION_IDS,CORRECT_IDS,END,MAX_TURNS,body_ids,output_ids,compact_head,read,write,rows,save_rows,sha,signature,check_frozen as check_previous

ROOT=REPO/'.build/mk61-agent-20261106/spec-review-flag-fix-v1'
PRIOR_RESULTS=PREVIOUS/'server-results'if(PREVIOUS/'server-results/complete.json').exists()else PREVIOUS
DIAGNOSIS=REPO/'.build/mk61-agent-20261106/weight-diagnosis-v1'
BAD_SOURCES={a:PRIOR_RESULTS/'export'/('fixed3000_'+a)for a in ['lora','full']}
ARMS=['lora','full']
TEST_NUMBERS=['0.61379','1.11379','13.91379','31.66379','46.41379','61.16379','74.91379','89.66379','98.41379']


def check_frozen():
    check_previous();f=read(ROOT/'frozen.json')
    for n,d in f['sources'].items():assert sha(HERE/n)==d,n
    for n,d in f['files'].items():assert sha(ROOT/n)==d,n
    for role,folders in [('parents',SOURCES),('bad_models',BAD_SOURCES)]:
        for a,files in f[role].items():
            for n,d in files.items():assert sha(folders[a]/n)==d,(role,a,n)
    return f
