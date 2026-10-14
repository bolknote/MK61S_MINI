#!/usr/bin/env python3
"""Prove the output range of BC on the C8-inclusive reset control graph.

Combined with the whole-ROM fact that only BC can write M2[40], this rules
out a general 14-tetrade K2 swap by keys in this digital reset model.
Positive graph states are overapproximations; a universal bound over them
also bounds all actual executions covered by the model.
"""
from pathlib import Path
import runpy
from z3 import And, Or, sat, unsat


def check_writers():
    """Independently recheck both service-tetrade writers in all 768 words."""
    import json
    import subprocess
    root=Path(__file__).resolve().parent
    first=runpy.run_path(str(root/'ik1302_symbolic.py'))
    roms=json.loads(subprocess.check_output(['node','-e',
        'console.log(JSON.stringify(require(process.argv[1])))',str(first['ROM_PATH'])],text=True))
    actual={37:set(),40:set()}
    for chip in ('ИК1302','ИК1303','ИК1306'):
        q=runpy.run_path(str(root/'ik1302_symbolic.py'));r=roms[chip]
        q['execute_command'].__globals__.update(COMMANDS=r['команды'],
            SYNCS=r['синхропрограммы'],MICROS=r['микрокоманды'])
        for ip in range(256):
            a=q['State'](f'service_writer_{chip}_{ip}');out=[]
            q['execute_command'](a,ip,*q['arbitrary_keys'](f'service_keys_{chip}_{ip}'),
                                 emitted_outputs=out)
            for i in (37,40):
                p=q['base_solver'](a,ip);p.add(out[i]!=a.m[i])
                result=p.check();assert result in (sat,unsat)
                if result==sat:actual[i].add((chip,ip))
        print('PASS:',chip,'all 256 service-tetrade writer checks completed.',flush=True)
    assert actual=={37:{('ИК1302',0xBC)},40:{('ИК1302',0xBC)}},actual
    print('PASS: BC is the only possible writer of either service tetra in the closed ring.',flush=True)


def prove(m):
    root=Path(__file__).resolve().parent
    ctl=runpy.run_path(str(root/'audit_ms_rom_control.py'))
    successors,predecessors=ctl['graph'](m)
    q=m['q']; byte=m['byte']
    edges=[(source,target) for target in m['parents'] if target[0]==0xBC
           for source in predecessors[target]]
    assert edges
    categories={(source[0],source[2]) for source,_ in edges}
    assert categories=={(0xBB,0xAF),(0xBB,0xA3),(0xB3,0xAF)},categories
    assert {st[2] for st in m['parents'] if st[0]==0xBB}=={0xAF,0xA3}
    allowed={0xA3,0xAF,*range(0xF0,0x100)}
    output_union=set(); checked=0
    for source,target in edges:
        ip,sp,vector,selector,delta,r38,dr38,r26,types=source
        a,addr,av,old=m['templates'][ip][:4]
        assert types is None
        p=m['state_solver'](a,ip)
        p.add(av==vector,Or(*[a.s1==n for n in selector]),
              Or(*[a.r[38]==n for n in r38]),
              Or(*[a.r[26]==n for n in r26]),
              *[v==n for v,n in zip(old,sp)])
        if delta is not None:p.add(a.s1-a.r[35]==delta)
        if dr38 is not None:p.add(a.r[38]-a.r[35]==dr38)
        b=q['execute_command'](a,ip,*q['arbitrary_keys'](f'bc_bound_source_{checked}'))
        p.add(byte(b.r[36],b.r[39])==0xBC)
        assert p.check()==sat,(ip,source)
        out=[]
        q['execute_command'](b,0xBC,*q['arbitrary_keys'](f'bc_bound_write_{checked}'),
                             emitted_outputs=out)
        service=byte(out[37],out[40])
        p.push();p.add(~Or(*[service==v for v in allowed]))
        assert p.check()==unsat,(ip,source,'out of range')
        p.pop()
        p.push();p.add(~Or(out[40]==0xA,out[40]==0xF))
        assert p.check()==unsat,(ip,source,'high tetrade')
        p.pop()
        p.push();output_union.update(q['possible_values'](service,p,257));p.pop()
        checked+=1
    assert checked==len(edges)
    print(f'PASS: all {len(m["parents"])} reset-graph states and '
          f'{sum(map(len,successors.values()))} edges covered; '
          f'all {checked} BC predecessor edges checked exactly.',flush=True)
    print('PASS: every BC write has M2[40] in {A,F}; M2[40]:M2[37] in {'+
          ','.join(f'{v:02X}' for v in sorted(output_union))+'}.',flush=True)
    print('Positive range members are abstract possibilities, not demonstrated keyboard writes.',flush=True)
    return {'states':len(m['parents']),'edges':sum(map(len,successors.values())),
            'bcEdges':checked,'serviceBytes':sorted(output_union)}


if __name__=='__main__':
    import sys
    check_writers()
    sys.argv=['analyze_gates.py','--target','c7','--r38','--check-c8-invariants']
    model=runpy.run_path(str(Path(__file__).with_name('analyze_gates.py')))
    prove(model)
