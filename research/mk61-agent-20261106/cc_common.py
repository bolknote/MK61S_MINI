"""Train only the three existing action rows; preserve body weights and runtime."""
from cb_common import *
from cb_common import ROOT as CB_ROOT,ACTOR as WORKING_SOURCE,PARENT as TRANSLATOR_SOURCE,check_frozen as previous_check
CB_RESULTS=CB_ROOT/'server-results'
ROOT=REPO/'.build/mk61-agent-20261106/spec-action-choice-v1'
ACTOR=ROOT/'profiles/parent'
WORKING=ROOT/'profiles/working'
PARENT=ROOT/'profiles/translator'

def check_frozen():
    previous_check();f=read(ROOT/'frozen.json')
    for n,d in f['sources'].items():assert sha(HERE/n)==d,n
    for n,d in f['files'].items():assert sha(ROOT/n)==d,n
    return f
