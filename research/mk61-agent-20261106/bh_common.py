"""Natural Russian continuation of the two previously selected SPEC branches."""
from be_common import HERE,REPO,read,write,rows,save_rows,sha,ACTIONS,ACTION_IDS,CORRECT_IDS,END,MAX_TURNS,body_ids,output_ids,compact_head
from ba_common import prior
ROOT=REPO/'.build/mk61-agent-20261106/spec-pairs-v1'
_PREVIOUS=ROOT.parent/'spec-natural-v1'
PARENT=_PREVIOUS if(_PREVIOUS/'export/lora/model.mkqb').exists()else _PREVIOUS/'server-results'
ARMS=['lora','full'];SOURCES={a:PARENT/'export'/a for a in ARMS}
PRIORS=[prior(n)for n in ['semantic-spec-distill-v1','semantic-spec-distill-v2','semantic-spec-grounding-v1','semantic-spec-selfcheck-v1']]+[(ROOT.parent/'spec-translation-clean-v1' if (ROOT.parent/'spec-translation-clean-v1/export/lora').exists() else ROOT.parent/'spec-translation-clean-v1/server-results'),PARENT,(ROOT.parent/'spec-preserve-v1' if (ROOT.parent/'spec-preserve-v1/export/lora').exists() else ROOT.parent/'spec-preserve-v1/server-results')]
DEV_NUMBERS=['0.445','0.945','8.455','24.955','38.705','53.455','68.205','82.955','95.705']
TEST_NUMBERS=['0.495','0.995','11.455','26.955','42.705','56.455','71.205','87.955','96.705']

def signature(spec):
    import json
    from bh_spec import normal
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
