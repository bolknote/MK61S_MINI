"""Actor-only paired-format adaptation; translation and mechanical checking stay fixed."""
from ca_common import ROOT as CA_ROOT,BZ_ROOT,BY_ROOT,BY_RESULTS,BX_RESULTS,ACTOR,PARENT,HERE,REPO,read,write,rows,sha,output_ids,compact_head,check_frozen as previous_check
from bx_common import ROOT as BX_ROOT
from bu_common import body_ids,ACTIONS,ACTION_IDS,CORRECT_IDS,END
from ay_common import save_rows
from bh_common import signature

ROOT=REPO/'.build/mk61-agent-20261106/spec-actor-paired-formats-v1'
CA_RESULTS=CA_ROOT/'server-results'


def check_frozen():
    previous_check();f=read(ROOT/'frozen.json')
    for name,digest in f['sources'].items():assert sha(HERE/name)==digest,name
    for name,digest in f['files'].items():assert sha(ROOT/name)==digest,name
    return f
