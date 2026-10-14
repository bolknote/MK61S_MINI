#!/usr/bin/env python3
"""The alternate 21->23 exit starts another DD; it is not a last-DD bypass.

Also checks the short 73/6F return: its marker is cleared by 86 before D3.
Neither statement excludes every later read, command, or new selector epoch.
"""
import runpy
from pathlib import Path

from z3 import And, Or, ZeroExt, sat, unsat

q = runpy.run_path(str(Path(__file__).with_name('ik1302_symbolic.py')))
State,execute,base,keys = (q[n] for n in
    ('State','execute_command','base_solver','arbitrary_keys'))
byte = lambda lo,hi:ZeroExt(4,lo)|(ZeroExt(4,hi)<<4)
address = lambda a:byte(a.r[36],a.r[39])
stack = lambda a:[byte(a.st[36+i],a.st[39+i]) for i in range(3)]
facts = 0


def prove(ip,label,claim,condition=None):
    global facts
    a = State(f'write_exit_fact_{facts}')
    b = execute(a,ip,*keys(f'write_exit_keys_{facts}'))
    p = base(a,ip)
    if condition is not None:
        p.add(condition(a))
    assert p.check()==sat,('empty condition',label)
    p.add(~claim(a,b))
    assert p.check()==unsat,label
    facts += 1
    print('PASS:',label,flush=True)


for ip,exits in ((0x23,(0x24,0x25)),(0x24,(0x25,))):
    prove(ip,f'{ip:02X} stays on the path to 25 and preserves selector',
          lambda a,b,exits=exits:And(Or(*[address(b)==n for n in exits]),
                                    b.r[38]==a.r[38]))
prove(0x25,'25 sets S1=4, enters 01, pushes 26, preserves selector',
      lambda a,b:And(address(b)==0x01,b.s1==4,b.r[38]==a.r[38],
          *[v==w for v,w in zip(stack(b),[0x26]+stack(a)[:2])]))
for ip,exits in ((0x01,(0x01,0x02)),(0x02,(0x02,0x03)),(0x03,(0x04,)),
                 (0x04,(0xBA,)),(0xBA,(0xCB,)),(0xCB,(0xDD,))):
    prove(ip,f'S1=4: {ip:02X} remains in the write helper, preserving stack/selector/S1',
          lambda a,b,exits=exits:And(Or(*[address(b)==n for n in exits]),
              b.s1==4,b.r[38]==a.r[38],*[v==w for v,w in zip(stack(a),stack(b))]),
          lambda a:a.s1==4)
prove(0xDD,'S1=4: the next DD enters D4 and preserves the address stack',
      lambda a,b:And(address(b)==0xD4,*[v==w for v,w in zip(stack(a),stack(b))]),
      lambda a:a.s1==4)
print('PASS: 21->23 can only wait forever in the helper or encounter another '
      'DD with a D4/26 write return before any C8. It cannot belong to the '
      'suffix after the last selector-setting DD. Arbitrary read waits and '
      'both 23 branches are covered.',flush=True)

# This is a call, not the 6D/6F/62/6E bootstrap. Preserve the real tag 74.
prove(0x73,'73 pushes 74 on its 6F branch',
      lambda a,b:Or(address(b)!=0x6F,And(
          *[v==w for v,w in zip(stack(b),[0x74]+stack(a)[:2])])) )
prove(0x6F,'6F enters 62 and preserves the address stack',
      lambda a,b:And(address(b)==0x62,*[v==w for v,w in zip(stack(a),stack(b))]))
prove(0x62,'with tag 74, 62 returns to 74, not 6E',
      lambda a,b:address(b)==0x74,lambda a:stack(a)[0]==0x74)
prove(0x74,'74 enters 86',lambda a,b:address(b)==0x86)
prove(0x86,'86 enters D3 and clears the marker',
      lambda a,b:And(address(b)==0xD3,b.r[26]==0))
print('PASS: 73->6F->62 returns through 74->86->D3. The newly prepared '
      'marker is cleared before D3; substituting return 6E invents a path. '
      'Later continuations after D3 remain a separate question.',flush=True)
print(f'PASS: {facts} universal local facts.',flush=True)
