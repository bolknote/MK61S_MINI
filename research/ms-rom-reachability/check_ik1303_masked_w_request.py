#!/usr/bin/env python3
"""A visible Y marker masks the secondary decoder's pending W/Q request.

Conditional ROM proof, not an arbitrary keyboard or whole-system theorem.
The native delayed-request test establishes the stated page geometry.
"""
import json
import runpy
import subprocess
from pathlib import Path
from z3 import And, ZeroExt, sat, unsat

q=runpy.run_path(str(Path(__file__).with_name('ik1302_symbolic.py')))
rom=json.loads(subprocess.check_output(['node','-e',
    'console.log(JSON.stringify(require(process.argv[1])["ИК1303"]))',str(q['ROM_PATH'])],text=True))
q['execute_command'].__globals__.update(COMMANDS=rom['команды'],
    SYNCS=rom['синхропрограммы'],MICROS=rom['микрокоманды'])
State,ex,base,keys=(q[n] for n in ('State','execute_command','base_solver','arbitrary_keys'))
byte=lambda lo,hi:ZeroExt(4,lo)|(ZeroExt(4,hi)<<4)
address=lambda a:byte(a.r[36],a.r[39])

def prove(p,claim,label):
    assert p.check()==sat,('empty premise',label)
    p.push();p.add(~claim);answer=p.check()
    assert answer==unsat,(label,p.model() if answer==sat else answer)
    p.pop();print('PASS:',label,flush=True)

names=['marker','control','X1','X','Y','Z','T','U','V','W','Q','P7','P8','P9','P10']
seq=[0x6E,0x5E,0x39,0x6E,0x6E,0x5E,0x50,0x52,0x53,0x4F,0x24,0x39,0x6E,0x6E,0x6E]
pages={n:State('masked_page_'+n).m for n in names}
a=State('masked_cycle');a.m=pages['marker'];p=base(a,0x6E)
p.add(a.r[29]==0,pages['marker'][22]==15,pages['Y'][22]==15,
      pages['control'][34]==1,pages['control'][31]==15,
      pages['Z'][34]==0,pages['Z'][31]==0)
for n in ('X','P8','P9','P10'):p.add(pages[n][22]!=15)
b=a
for i,(name,ip) in enumerate(zip(names,seq)):
    prove(p,address(b)==ip,'masked request cycle: %02X(%s)'%(ip,name))
    out=[];b=ex(b,ip,*keys('masked_'+str(i)),serial_inputs=pages[names[(i+1)%15]],emitted_outputs=out)
    prove(p,And(*[x==y for x,y in zip(out,pages[name])]),
          '%02X(%s) leaves its complete ring page unchanged'%(ip,name))
prove(p,And(address(b)==0x6E,b.r[29]==0),'cycle returns to the same control premise after 15 commands')
print('CONTRACT: the numeric contents of U/V/W/Q and all non-tested page fields are arbitrary. W is visited by 4F and Q by 24, never the request decoder 6E/5E. No amount of idle repetition of this conditional cycle submits Q.',flush=True)
