"""Learn from false self-check DONEs while preserving the existing protocol."""
from ay_common import HERE,REPO,ACTIONS,ACTION_IDS,CORRECT_IDS,END,MAX_TURNS,body_ids,output_ids,compact_head,read,rows,write,save_rows,sha
from ba_common import prior,PRIORS as EARLIER,TRAIN_NUMBERS as BEFORE_TRAIN,DEV_NUMBERS as BEFORE_DEV,TEST_NUMBERS as BEFORE_TEST
ROOT=REPO/'.build/mk61-agent-20261106/semantic-spec-selfcheck-v1'
PARENT=prior('semantic-spec-grounding-v1');PRIORS=[*EARLIER,PARENT];SOURCE=PARENT/'export/spec';RUNS=['seed-a','seed-b']
DEV_NUMBERS=['0.325','0.675','6.75','18.25','32.75','44.25','58.5','72.5','84.25']
TEST_NUMBERS=['0.175','0.825','8.75','21.25','34.5','49.75','61.25','77.5','86.75']
TRAIN_NUMBERS=list(dict.fromkeys(BEFORE_TRAIN+BEFORE_DEV+BEFORE_TEST))

def check_frozen():
    f=read(ROOT/'frozen.json')
    for n,d in f['sources'].items():assert sha(HERE/n)==d,n
    for n,d in f['files'].items():assert sha(ROOT/n)==d,n
    for n,d in f['parent'].items():assert sha(SOURCE/n)==d,n
    from ay_common import INITIAL
    for n,d in f['foundation'].items():assert sha(INITIAL/n)==d,n
    for n,d in f['external_sources'].items():assert sha(REPO/n)==d,n
    return f
