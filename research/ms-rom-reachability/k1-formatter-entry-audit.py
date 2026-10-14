#!/usr/bin/env python3
"""Audit EE/46 in the existing complete C8-inclusive reset abstraction.

The generated cache contains only explicit numeric graph data, command-line
options, versions and source hashes: never a pickled namespace/environment.
Use --reuse for read-only subsequent queries with identical source hashes.
"""
import argparse
from datetime import datetime,timezone
import gzip
import hashlib
import json
from pathlib import Path
import runpy
import sys
from z3 import get_version_string

root=Path(__file__).resolve().parent
reference=root.parents[2]/'MK-61'/'tests'/'emulator'
cache_path=root/'k1-formatter-reset-graph.json.gz'
argv=['analyze_gates.py','--target','c7','--r38','--check-c8-invariants']
sources=[root/'analyze_gates.py',root/'ik1302_symbolic.py',root/'audit_ms_rom_control.py',
         Path(__file__).resolve(),reference/'mk61.cjs',reference/'rom.cjs']
fingerprints=lambda:{str(path):hashlib.sha256(path.read_bytes()).hexdigest() for path in sources}

def report(data):
    states=data['states'];ids=data['indexes']['byIp'].get('EE',[])
    tops=sorted({states[i][1][0] for i in ids})
    matches=[i for i in ids if states[i][1][0]==0x46]
    print('Complete cached graph:',len(states),'states,',sum(map(len,data['successors'])),'edges',flush=True)
    print('EE entries:',len(ids),'all top tags:', ' '.join('%02X'%v for v in tops),flush=True)
    print('EE with top46:',len(matches),flush=True)
    for i in matches:
        path=[];cursor=i
        while cursor is not None:path.append(cursor);cursor=data['parents'][cursor]
        path.reverse();expanded=[]
        for index in path:
            ip=states[index][0];expanded.append(ip)
            if ip==0x93:expanded.append(0x94)
            if ip==0x12:expanded.append(0xC6)
        print('CANDIDATE state',i,states[i],flush=True)
        print('CANDIDATE reset path:', ' '.join('%02X'%ip for ip in expanded),flush=True)
    if not matches:
        print('PASS: no reset-reachable EE/top46 state exists in this completed overapproximation, including any number of admitted C8 calls.',flush=True)
    else:
        print('LIMIT: abstract candidate paths are not native keyboard protocols.',flush=True)
    print('Cache:',cache_path,flush=True)

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--reuse',action='store_true');options=parser.parse_args()
    hashes=fingerprints()
    if options.reuse:
        with gzip.open(cache_path,'rt',encoding='utf8') as stream:data=json.load(stream)
        assert data['schema']=='mk61-reset-control-graph-v1'
        assert data['metadata']['sourceSha256']==hashes,'source hashes differ; the cached proof must not be reused'
        assert data['metadata']['argv']==argv
        assert data['metadata']['complete'] and data['metadata']['pending']==0 and data['metadata']['terminal'] is None
        assert len(data['states'])==len(data['parents'])==len(data['successors'])
        assert all(0<=i<len(data['states']) for edges in data['successors'] for i in edges)
        print('PASS cache provenance and closed-index checks.',flush=True)
    else:
        sys.argv=argv
        model=runpy.run_path(str(root/'analyze_gates.py'))
        assert model['args'].limit==150000
        assert model['args'].target=='c7' and model['args'].r38 and model['args'].check_c8_invariants
        assert not model['args'].first_entry_lemmas and not model['args'].physical_key_rows
        assert not model['queue'] and model['terminal'] is None,'incomplete graph is not an exclusion proof'
        control=runpy.run_path(str(root/'audit_ms_rom_control.py'))
        successors,_=control['graph'](model)
        states=list(model['parents']);indexes={state:i for i,state in enumerate(states)}
        by_ip={}
        for i,state in enumerate(states):by_ip.setdefault('%02X'%state[0],[]).append(i)
        data={'schema':'mk61-reset-control-graph-v1',
              'metadata':{'createdUtc':datetime.now(timezone.utc).isoformat(),'sourceSha256':hashes,
                          'argv':argv,'arguments':vars(model['args']),'pythonVersion':sys.version,
                          'z3Version':get_version_string(),'complete':True,'pending':0,'terminal':None,
                          'stateFields':['ip','stack3','vector','selectorSet','selectorMinusR35','r38Set','r38MinusR35','r26Set','types'],
                          'fusedCommands':{'93':['93','94'],'12':['12','C6']},
                          'scope':'digital reset overapproximation; arbitrary ring inputs/keys; C8 admitted, no first-entry lemmas'},
              'states':states,'parents':[None if model['parents'][s] is None else indexes[model['parents'][s]] for s in states],
              'successors':[[indexes[t] for t in successors[s]] for s in states],
              'indexes':{'byIp':by_ip,'roots':[i for i,s in enumerate(states) if model['parents'][s] is None]}}
        assert fingerprints()==hashes,'source files changed while the graph was being computed'
        # This is a generated data artifact, not a serialization of the live
        # process: every field above is selected explicitly and is JSON-safe.
        with gzip.open(cache_path,'wt',encoding='utf8',compresslevel=9) as stream:json.dump(data,stream,separators=(',',':'))
        print('PASS complete graph exported with source provenance.',flush=True)
    report(data)
