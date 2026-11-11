"""Natural Russian continuation of the two previously selected SPEC branches."""
from be_common import HERE,REPO,read,write,rows,save_rows,sha,ACTIONS,ACTION_IDS,CORRECT_IDS,END,MAX_TURNS,body_ids,output_ids,compact_head
from ba_common import prior
ROOT=REPO/'.build/mk61-agent-20261106/spec-natural-v1'
_PREVIOUS=ROOT.parent/'spec-translation-clean-v1'
PARENT=_PREVIOUS if(_PREVIOUS/'export/lora/model.mkqb').exists()else _PREVIOUS/'server-results'
ARMS=['lora','full'];SOURCES={a:PARENT/'export'/a for a in ARMS}
PRIORS=[prior(n)for n in ['semantic-spec-distill-v1','semantic-spec-distill-v2','semantic-spec-grounding-v1','semantic-spec-selfcheck-v1']]+[PARENT]
DEV_NUMBERS=['0.425','0.925','8.375','24.875','38.625','53.375','68.125','82.875','95.625']
TEST_NUMBERS=['0.475','0.975','11.375','26.875','42.625','56.375','71.125','87.875','96.625']

def signature(spec):
    import json
    from bf_spec import normal
    from ay_finalize import angular
    return json.dumps([normal(spec['X']),sorted(spec['writes']),spec['angle']if angular(spec['X'])else None],sort_keys=True)

def check_frozen():
    f=read(ROOT/'frozen.json')
    for n,d in f['sources'].items():assert sha(HERE/n)==d,n
    for n,d in f['files'].items():assert sha(ROOT/n)==d,n
    for a,items in f['parents'].items():
        for n,d in items.items():assert sha(SOURCES[a]/n)==d,(a,n)
    from be_common import check_frozen as previous
    previous();return f
