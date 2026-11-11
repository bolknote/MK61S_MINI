"""Clean Russian-to-SPEC continuation: matched LoRA and full-weight Q4 training."""
from bc_common import HERE,REPO,read,write,rows,save_rows,sha,ACTIONS,ACTION_IDS,CORRECT_IDS,END,MAX_TURNS,body_ids,output_ids,compact_head
from ba_common import prior
ROOT=REPO/'.build/mk61-agent-20261106/spec-translation-clean-v1'
PARENT=prior('semantic-spec-selfcheck-v1');SOURCE=PARENT/'export/spec';ARMS=['lora','full']
PRIORS=[prior(n)for n in ['semantic-spec-distill-v1','semantic-spec-distill-v2','semantic-spec-grounding-v1','semantic-spec-selfcheck-v1']]
DEV_NUMBERS=['0.225','0.775','7.375','18.875','33.625','46.375','62.125','75.875','89.625']
TEST_NUMBERS=['0.275','0.725','9.875','23.375','37.125','52.625','66.875','81.375','94.125']

def check_frozen():
    f=read(ROOT/'frozen.json')
    for n,d in f['sources'].items():assert sha(HERE/n)==d,n
    for n,d in f['files'].items():assert sha(ROOT/n)==d,n
    for n,d in f['parent_model'].items():assert sha(SOURCE/n)==d,n
    from bc_common import check_frozen as old_check
    old_check();return f
