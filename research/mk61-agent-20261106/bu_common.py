"""Phase-specific SPEC adaptation; original tool actor stays immutable."""
from bt_common import HERE,REPO,SOURCE,BS_ROOT,ROOT as BT_ROOT,read,write,rows,save_rows,sha,signature,ACTIONS,ACTION_IDS,CORRECT_IDS,END,body_ids,output_ids,compact_head,check_frozen as previous_check
ROOT=REPO/'.build/mk61-agent-20261106/spec-phase-adapter-v1'


def check_inputs():
    previous_check();f=read(ROOT/'inputs-frozen.json')
    for n,d in f['sources'].items():assert sha(HERE/n)==d,n
    for n,d in f['files'].items():assert sha(ROOT/n)==d,n
    for n,d in f['parent'].items():assert sha(SOURCE/n)==d,n
    return f


def check_frozen():
    check_inputs();f=read(ROOT/'frozen.json')
    for n,d in f['files'].items():assert sha(ROOT/n)==d,n
    return f
