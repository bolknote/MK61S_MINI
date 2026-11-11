"""One frozen compact-prompt candidate; immutable actor and BU1500 translator."""
from by_common import ROOT as BY_ROOT,BX_RESULTS,ACTOR,HERE,REPO,read,write,rows,sha,output_ids,compact_head,check_frozen as previous_check
from bx_common import PARENT

ROOT=REPO/'.build/mk61-agent-20261106/spec-compact-prompt-v1'
BY_RESULTS=BY_ROOT/'server-results'


def check_frozen():
    previous_check();f=read(ROOT/'frozen.json')
    for name,digest in f['sources'].items():assert sha(HERE/name)==digest,name
    for name,digest in f['files'].items():assert sha(ROOT/name)==digest,name
    return f
