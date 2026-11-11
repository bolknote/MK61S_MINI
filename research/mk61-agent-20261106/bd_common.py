"""Frozen 2x2 diagnostic: hypothesis provider versus program controller."""
from bc_common import HERE,REPO,read,write,rows,save_rows,sha,compact_head,output_ids
from ba_common import prior

ROOT=REPO/'.build/mk61-agent-20261106/spec-factorial-diagnostic-v1'
PARENT=prior('semantic-spec-selfcheck-v1')
SOURCE=PARENT/'export/spec'
MODEL=ROOT/'export/spec'
ARMS=['own_actor','oracle_actor','own_mechanical','oracle_mechanical']


def check_frozen():
    f=read(ROOT/'frozen.json')
    for name,digest in f['sources'].items():assert sha(HERE/name)==digest,name
    for name,digest in f['files'].items():assert sha(ROOT/name)==digest,name
    from bc_common import check_frozen as old_check
    old_check()
    return f
