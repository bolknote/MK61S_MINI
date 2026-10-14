#!/usr/bin/env python3
"""Exact three-deep return-stack lifecycle, not a native writer recipe.

All primary fields, incoming ring tetras and per-tick key signals are free.
The specific 45/8B/48 composition has forced dispatch up to its decoder.
Other local instructions are classified separately, without inventing edges.
"""
from pathlib import Path
import runpy
from z3 import And, Or, Solver, ZeroExt, sat, unsat

root=Path(__file__).resolve().parent
q=runpy.run_path(str(root/'ik1302_symbolic.py'))
State,ex,keys,base=(q[n] for n in
                   ('State','execute_command','arbitrary_keys','base_solver'))
byte=lambda lo,hi:ZeroExt(4,lo)|(ZeroExt(4,hi)<<4)
address=lambda a:byte(a.r[36],a.r[39])
stack=lambda a:[byte(a.st[36+i],a.st[39+i]) for i in range(3)]
positions=(0,3,9,12,18,21)


def prove(p,claim,label):
    assert p.check()==sat,('empty premises',label)
    p.push();p.add(~claim)
    assert p.check()==unsat,label
    p.pop();print('PASS:',label,flush=True)


def main():
    a=State('constructor46');p=base(a,0x45);b=a
    for i,(ip,expected,tag) in enumerate(((0x45,0x8B,0x46),
                                        (0x8B,0x48,0x8C),
                                        (0x48,None,0x49))):
        prove(p,address(b)==ip,f'{ip:02X}: forced entry')
        before=b;out=[]
        b=ex(b,ip,*keys(f'constructor46_keys_{i}'),emitted_outputs=out)
        prove(p,And(*[v==w for v,w in zip(stack(b),[tag]+stack(before)[:2])],
                    *[b.r[pos]==a.r[pos] for pos in positions],
                    *[x==y for x,y in zip(out,before.m)]),
              f'{ip:02X}: pushes {tag:02X}, raw cache held, no primary ring output replaced')
        if expected is not None:prove(p,address(b)==expected,f'{ip:02X} dispatches {expected:02X}')
    prove(p,And(*[v==w for v,w in zip(stack(b),(0x49,0x8C,0x46))],
                Or(address(b)==0x4A,address(b)==0xB1)),
          '45/8B/48 leaves stack 49/8C/46 and enters only 4A or B1')
    # Any subsequent push drops the bottom word. It is not a fourth-deep
    # reserve that can be used after an unrelated call has been inserted.
    for ip in (0x4A,0xB2,0xB8,0xB9):
        a=State(f'drop46_{ip}');p=base(a,ip)
        p.add(*[v==w for v,w in zip(stack(a),(0x49,0x8C,0x46))])
        out=[];b=ex(a,ip,*keys(f'drop46_keys_{ip}'),emitted_outputs=out)
        pushed=(ip&0xF0)|((ip+1)&15)
        prove(p,And(*[v==w for v,w in zip(stack(b),(pushed,0x49,0x8C))],
                    *[b.r[pos]==a.r[pos] for pos in positions],
                    *[x==y for x,y in zip(out,a.m)]),
              f'{ip:02X}: drops the original 46 while holding all six cache tetras')
    pushers=[]
    for ip in range(256):
        a=State(f'constructor46_source_{ip}');p=base(a,ip)
        b=ex(a,ip,*keys(f'constructor46_source_keys_{ip}'))
        p.add(~And(*[v==w for v,w in zip(stack(b),[0x46]+stack(a)[:2])]))
        if p.check()==unsat:pushers.append(ip)
    assert pushers==[0x45],pushers
    print('PASS: all 256 words audited; only 45 universally pushes the return tag 46')
    print('LIMIT: decoder branch reachability and all possible stack-return routes '
          'are separate graph/native questions; this local contract alone excludes no partial K2.')


if __name__=='__main__':main()
