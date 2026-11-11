"""Post-training weight diagnosis; no SGD, promotion or new sealed-test claims."""
from bl_common import REPO,HERE,ROOT as PREVIOUS,SOURCES,read,write,rows,save_rows,sha,ACTIONS,ACTION_IDS,CORRECT_IDS,output_ids,compact_head,check_frozen as check_previous

ROOT=REPO/'.build/mk61-agent-20261106/weight-diagnosis-v1'
RESULTS=PREVIOUS/'server-results' if (PREVIOUS/'server-results/complete.json').exists() else PREVIOUS
OLD=SOURCES['full']
NEW=RESULTS/'export/fixed3000_full'


def check():
    check_previous();f=read(ROOT/'frozen.json')
    for n,d in f['sources'].items():assert sha(HERE/n)==d,n
    for n,d in f['files'].items():assert sha(ROOT/n)==d,n
    for label,folder in [('old',OLD),('new',NEW)]:
        for n,d in f['models'][label].items():assert sha(folder/n)==d,(label,n)

