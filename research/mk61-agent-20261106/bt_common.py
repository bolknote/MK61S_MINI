"""Weight-frozen context and symbolic-observation ablations."""
from bs_common import HERE,REPO,SOURCE,ROOT as BS_ROOT,read,write,rows,save_rows,sha,signature,ACTIONS,ACTION_IDS,CORRECT_IDS,END,body_ids,output_ids,compact_head,check_frozen as previous_check
ROOT=REPO/'.build/mk61-agent-20261106/harness-symbolic-context-v1'
CONFIGS={
 'baseline':{'context':1024,'KV':'FP32','symbolic':False},
 'half1024':{'context':1024,'KV':'FP16','symbolic':False},
 'context1536':{'context':1536,'KV':'FP16','symbolic':False},
 'symbolic1024':{'context':1024,'KV':'FP32','symbolic':True},
 'combined1536':{'context':1536,'KV':'FP16','symbolic':True}}


def check_frozen():
    previous_check();f=read(ROOT/'frozen.json')
    for n,d in f['sources'].items():assert sha(HERE/n)==d,n
    for n,d in f['files'].items():assert sha(ROOT/n)==d,n
    for n,d in f['parent'].items():assert sha(SOURCE/n)==d,n
    return f
