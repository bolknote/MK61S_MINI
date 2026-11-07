#!/usr/bin/env python3
"""Known rankings and weighting checks; synthetic values are not hardware."""
from pathlib import Path
import copy,math,sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'research/m0-libc-batch-2026-11-07'))
from analyze import weighted,decision,LABELS
def main():
    logical=[dict(length=0,work=0,physical_index=0),dict(length=9,work=9,physical_index=1),dict(length=9,work=9,physical_index=1)]
    rows={0:dict(raw=[[20]*7]*9,repeats=10),1:dict(raw=[[80]*7]*9,repeats=10)}
    inverse=weighted(rows,[],logical,7,'inverse-length')['us_per_checked_iteration'];equal=weighted(rows,[],logical,7,'equal-length')['us_per_checked_iteration']
    assert math.isclose(inverse,(2+.1*8)/1.1) and equal==5
    assert math.isclose(weighted(rows,[],logical,7,'inverse-length')['quantization_bound_us'],.1)
    weights={k:{label:dict(us_per_checked_iteration=10.,quantization_bound_us=.001,seven_group_spread_us=0) for label in LABELS} for k in ('inverse-length','equal-length','inverse-work','ternary')}
    routes=[dict(functions={name:dict(weighted=copy.deepcopy(weights)) for name in ('strlen','strcmp')}) for _ in range(4)]
    for r in routes:
        for f in r['functions'].values():
            for w in f['weighted'].values():w['byte4']['us_per_checked_iteration']=8
    assert decision(routes,'strcmp','Flash','current-native')[0]['profile']==4
    assert math.isclose(decision(routes,'strcmp','SRAM','current-native')[0]['geomean_ratio_to_baseline'],.8)
    # The shared runtime can be slower while the standalone SDK is already
    # identical to the best local candidate. That must not fabricate a gain.
    for route in (0,2):
        for kind in weights:routes[route]['functions']['strlen']['weighted'][kind]['public-SDK']['us_per_checked_iteration']=8 if route==0 else 80
    v=decision(routes,'strlen','SRAM','public-SDK')[0]
    assert v['route_indexes']==[0] and v['geomean_ratio_to_baseline']==1
    assert decision(routes,'strcmp','SRAM','public-SDK')[0]['route_indexes']==[0,2]
    print('inverse/equal workload, duplicate mapping, known20percent ranking and runtime/SDK alias trap PASS; synthetic only')
if __name__=='__main__':main()
