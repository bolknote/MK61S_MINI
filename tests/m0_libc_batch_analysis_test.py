#!/usr/bin/env python3
"""Known rankings and weighting checks; synthetic values are not hardware."""
from pathlib import Path
import copy,math,sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'research/m0-libc-batch-2026-11-07'))
from analyze import weighted,decision,regression_map,LABELS
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
    # Native and SDK can have different costs on the same measured row.
    # Keeping a native-only map would conceal an SDK-specific regression.
    c=dict(length=9,banks='SRAM',alignment=[0,0],mode='equal',count=9,seed_hex='')
    cases=[c,dict(c,alignment=[1,0])];data={0:dict(raw=[[20]*7]*6+[[10]*7,[40]*7]),1:dict(raw=[[60]*7]*6+[[10]*7,[40]*7])}
    native=regression_map(cases,data,3,7);sdk=regression_map(cases,data,3,6)
    assert [v['median_ratio_to_baseline'] for v in native]==[.5,1.5]
    assert [v['median_ratio_to_baseline'] for v in sdk]==[2.,6.]
    assert all(v['baseline']=='public-SDK' for v in sdk) and len(sdk)==2
    print('workload, duplicate mapping, ranking, runtime/SDK alias trap and separate SDK/native regression maps PASS; synthetic only')
if __name__=='__main__':main()
