#!/usr/bin/env python3
"""Exact primary-ROM writer and predecessor inventory; never native witness.

Every command is executed symbolically for arbitrary initial IK1302 fields,
per-tick keyboard pins and future ring. SAT edges are conditional gadgets,
not claims that their input metadata can be prepared from reset by keys.
"""
import hashlib
import json
from pathlib import Path
import runpy
from z3 import And, sat, unsat, ZeroExt

root=Path(__file__).resolve().parent
q=runpy.run_path(str(root/'ik1302_symbolic.py'))
State,ex,base,keys=(q[n] for n in ('State','execute_command','base_solver','arbitrary_keys'))
byte=lambda lo,hi:ZeroExt(4,lo)|(ZeroExt(4,hi)<<4)
address=lambda a:byte(a.r[36],a.r[39])
top=lambda a:byte(a.st[36],a.st[39])
positions=(0,3,9,12,18,21)
targets=(0x32,0x34,0x46,0xA3,0xA8,0xBC,0xC7,0xE7,0xE9)

def necessary(p,claim):
    p.push();p.add(~claim);outcome=p.check();p.pop()
    assert outcome in (sat,unsat),p.reason_unknown()
    return outcome==unsat

def inventory():
    rows=[];edges={ip:[] for ip in targets};m2_writers=[]
    for ip in range(256):
        a=State('cache46_audit_%02X'%ip);out=[]
        b=ex(a,ip,*keys('cache46_audit_keys_%02X'%ip),emitted_outputs=out)
        p=base(a,ip);assert p.check()==sat
        writes=[]
        for i,value in enumerate(out):
            if not value.eq(a.m[i]) and not necessary(p,value==a.m[i]):writes.append(i)
        is_return=necessary(p,address(b)==top(a))
        is_vector=necessary(p,address(b)==byte(a.r[37],a.r[40]))
        kind='return' if is_return else 'vector' if is_vector else 'other'
        row={'ip':ip,'writes':writes,'kind':kind,
             'holdsA6':necessary(p,And(*[b.r[i]==a.r[i] for i in positions])),
             'holdsA12':necessary(p,And(*[b.r[3*i]==a.r[3*i] for i in range(12)]))}
        if any(i%3==1 for i in writes):
            row['M2']=[i for i in writes if i%3==1]
            m2_writers.append(row)
        for target in targets:
            p.push();p.add(address(b)==target);outcome=p.check()
            assert outcome in (sat,unsat),p.reason_unknown()
            if outcome==sat:
                edges[target].append({'ip':ip,'kind':kind,
                  'holdsA6':necessary(p,And(*[b.r[i]==a.r[i] for i in positions])),
                  'holdsA12':necessary(p,And(*[b.r[3*i]==a.r[3*i] for i in range(12)])),
                  'noRingWrite':necessary(p,And(*[x==y for x,y in zip(out,a.m)]))})
            p.pop()
        rows.append(row)
    actual={row['ip'] for row in m2_writers}
    assert actual=={0x32,0x34,0xA3,0xA8,0xBC,0xC7,0xE7,0xE9},actual
    nonreturn46={e['ip'] for e in edges[0x46] if e['kind']!='return'}
    assert nonreturn46=={0x42,0x43,0xA3},nonreturn46
    assert all(e['holdsA6'] for e in edges[0x46] if e['ip'] in (0x42,0xA3))
    assert not next(e for e in edges[0x46] if e['ip']==0x43)['holdsA6']
    return {'scope':'exact 256 primary ROM words; SAT edges are not native reachability',
            'romSha256':hashlib.sha256(q['ROM_PATH'].read_bytes()).hexdigest(),
            'rows':rows,'M2writers':m2_writers,'edges':edges}

def report(result):
    print('PASS: all 256 primary ROM words, all outgoing tetras and nine target predecessor sets checked.',flush=True)
    for row in result['M2writers']:
        print('M2 WRITER %02X'%row['ip'],'slots',row['M2'],
              'holdsA6',row['holdsA6'],'holdsA12',row['holdsA12'],'next',row['kind'],flush=True)
    for target,edges in result['edges'].items():
        normal=[e for e in edges if e['kind']!='return']
        returns=[e for e in edges if e['kind']=='return']
        print('TARGET %02X nonreturn'%target,json.dumps([{**e,'ip':'%02X'%e['ip']} for e in normal]),flush=True)
        print('TARGET %02X stack-return rawA6/no-write sources'%target,
              ' '.join('%02X'%e['ip'] for e in returns if e['holdsA6'] and e['noRingWrite']),flush=True)
    print('LIMIT: no SAT metadata, return tag or physical target page is asserted native.',flush=True)

if __name__=='__main__':
    import sys
    result=inventory()
    if '--json' in sys.argv:print(json.dumps(result))
    else:report(result)
