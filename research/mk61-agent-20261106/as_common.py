"""Predeclared protocol control after the first diagnostic (no weight selection)."""
from ar_common import *
ROOT = REPO / '.build/mk61-agent-20261106/spec-diagnostic-native-v1'


def check_frozen():
    frozen=read(ROOT/'frozen.json')
    for name,digest in frozen['sources'].items():assert sha(HERE/name)==digest,name
    assert sha(ROOT/'goals.json')==frozen['goals_sha256']
    assert sha(ROOT/'policy.json')==frozen['policy_sha256']
    assert sha(MODEL/'model.mkqb')==frozen['small_packet_sha256']
    return frozen
