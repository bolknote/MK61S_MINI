"""Natural Russian continuation of the two previously selected SPEC branches."""
from be_common import HERE,REPO,read,write,rows,save_rows,sha,ACTIONS,ACTION_IDS,CORRECT_IDS,END,MAX_TURNS,body_ids,output_ids,compact_head
from ba_common import prior
ROOT=REPO/'.build/mk61-agent-20261106/spec-preserve-v1'
_PREVIOUS=ROOT.parent/'spec-natural-v1'
PARENT=_PREVIOUS if(_PREVIOUS/'export/lora/model.mkqb').exists()else _PREVIOUS/'server-results'
ARMS=['lora','full'];SOURCES={a:PARENT/'export'/a for a in ARMS}
PRIORS=[prior(n)for n in ['semantic-spec-distill-v1','semantic-spec-distill-v2','semantic-spec-grounding-v1','semantic-spec-selfcheck-v1']]+[(ROOT.parent/'spec-translation-clean-v1' if (ROOT.parent/'spec-translation-clean-v1/export/lora').exists() else ROOT.parent/'spec-translation-clean-v1/server-results'),PARENT]
DEV_NUMBERS=['0.435','0.935','8.435','24.935','38.685','53.435','68.185','82.935','95.685']
TEST_NUMBERS=['0.485','0.985','11.435','26.935','42.685','56.435','71.185','87.935','96.685']

def signature(spec):
    import json
    from bg_spec import normal
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
