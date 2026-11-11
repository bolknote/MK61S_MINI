"""SPEC continuation: literal grounding and ROM-labelled completion errors."""
from ay_common import HERE,REPO,ACTIONS,ACTION_IDS,CORRECT_IDS,END,MAX_TURNS,body_ids,output_ids,compact_head,read,rows,write,save_rows,sha

ROOT=REPO/'.build/mk61-agent-20261106/semantic-spec-grounding-v1'
def prior(name):
    p=ROOT.parent/name
    return p if(p/'export/spec/model.mkqb').exists()else p/'server-results'
PARENT=prior('semantic-spec-distill-v2')
PRIORS=[prior('semantic-spec-distill-v1'),PARENT]
SOURCE=PARENT/'export/spec'
RUNS=['seed-a','seed-b']
DEV_NUMBERS=['0.55','0.95','7.75','16.5','28.25','43.5','59','71.25','83']
TEST_NUMBERS=['0.15','0.625','10.75','19.25','31.5','47.25','63.5','76.25','88.5']
from az_common import TRAIN_NUMBERS as BEFORE_TRAIN,DEV_NUMBERS as BEFORE_DEV,TEST_NUMBERS as BEFORE_TEST
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
