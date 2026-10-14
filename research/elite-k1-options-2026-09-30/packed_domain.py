"""Exercise real calculator GET/SET for every hull pair and random words."""
from copy import deepcopy
import json
from pathlib import Path
import random
import subprocess
import sys

ROOT=Path('/Users/bolk/Projects/MK61S_MINI')
HERE=Path(__file__).resolve().parent
sys.path[:0]=[str(HERE/'packed-drones'),str(ROOT/'tools')]
from assembler import Assembler
from game import create_game
from program_pack import program_binary

a=Assembler()
a.data[28]=[0]*9
m=a.module(0,'packed hull domain driver')
m.raw(0x2F,0x50,0x2F,0x2A).op('stop')
m.label('again').open_page(28).ld(6).st('B').call('packed_get').st('D')
m.ld(5).call('packed_set').close_page(28).ld('D').st('C').op('stop').jump('again')
helper=next(m for m in create_game().modules if m.name=='packed drone hulls')
a.modules.append(deepcopy(helper))
banks,info=a.link()
image=b''.join(banks.get(b,bytes(112)) for b in range(32))
folder=HERE/'packed-domain'
folder.mkdir(exist_ok=True)
(folder/'elite.bin').write_bytes(program_binary(image))
(folder/'autoexec.m61').write_text('reinit\nload 0000 elite.bin\nrun\n')

rng=random.Random(61919)
cases=[]
for index in range(5):
    for old in range(19):
        for new in range(19):
            hp=[rng.randrange(19) for _ in range(5)]
            hp[index]=old
            cases.append((hp,index,new))
for _ in range(1000):
    cases.append(([rng.randrange(19) for _ in range(5)],rng.randrange(5),rng.randrange(19)))
for index in range(5):
    for hp in ([0]*5,[18]*5,[0 if i==index else 18 for i in range(5)],
               [18 if i==index else 0 for i in range(5)]):
        for new in (0,1,17,18):cases.append((hp,index,new))

commands=['dump']
sentinels=[4711,5822,6933,7044]
for i,n in enumerate(sentinels,1):commands.append(f'set 28 {i} {n}')
for hp,index,new in cases:
    packed=sum(n*19**i for i,n in enumerate(hp))
    commands += [f'set 28 0 {packed}',f'set 28 5 {new}',f'set 28 6 {index}','run']
result=subprocess.run([str(HERE/'runner'),str(folder)],input='\n'.join(commands)+'\n',
                      text=True,capture_output=True,check=True,timeout=120)
states=[json.loads(line) for line in result.stdout.splitlines()]
assert len(states)==len(cases)+1
for (hp,index,new),s in zip(cases,states[1:]):
    assert not s['error'] and not s['running'],s
    assert s['regs'][12]==hp[index],(hp,index,new,s)
    expect=hp.copy();expect[index]=new
    assert s['pages'][4][0]==sum(n*19**i for i,n in enumerate(expect)),(hp,index,new,s)
    assert s['pages'][4][1:5]==sentinels,s
    assert s['regs'][10]==new,s
report=dict(cases=len(cases),every_old_new_pair_per_slot=5*19*19,random_cases=1000,
            boundary_cases=80,max_packed=19**5-1,steps=sum(s['steps'] for s in states[1:]),
            all_four_spare_words_preserved=True)
(HERE/'packed-domain.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report))
