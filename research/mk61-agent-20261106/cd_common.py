"""Learn the utility of the existing DIAG action; freeze every other decision."""
from cc_common import *
from cc_common import ROOT as CC_ROOT,check_frozen as previous_check
CC_RESULTS=CC_ROOT/'server-results'
ROOT=REPO/'.build/mk61-agent-20261106/spec-review-utility-v1'
ACTOR=ROOT/'profiles/parent'
WORKING=ROOT/'profiles/working'
PARENT=ROOT/'profiles/translator'

def check_frozen():
    previous_check();f=read(ROOT/'frozen.json')
    for n,d in f['sources'].items():assert sha(HERE/n)==d,n
    for n,d in f['files'].items():assert sha(ROOT/n)==d,n
    return f
