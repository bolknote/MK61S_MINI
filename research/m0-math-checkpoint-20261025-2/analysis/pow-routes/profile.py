"""Measure original remaining35 public and direct first-tier pow routes."""
from collections import Counter,defaultdict
import json,sys
sys.dont_write_bytecode=True
from parent_harness import *
from unicorn.arm_const import UC_ARM_REG_LR

m=machine('candidate');image=images['candidate']
targets=['pow_root128_ranged','pow_positive_checked','pow_refine_checked','pow_fast_log',
         'mk61_m0_pow_log_select','pow_first_cell','mk61_m0_pow_midpoint','mk61_m0_cr_pow',
         'mk61_m0_cr_pow_refined','pow_dyadic128_checked','mk61_m0_pow_exp_table_product']
entries={}
for name in targets:
    address=image.symbols.get(name,m.elf.symbols.get(name))
    if address is not None:entries[address&~1]=name
active=[];tick=0;times=Counter();returns=defaultdict(list)
def hook(uc,pc,size,user):
    global tick
    while active and pc==active[-1][1]:
        name,lr,start=active.pop();times[name]+=tick-start
        if name=='pow_root128_ranged':returns[name].append(f'{uc.reg_read(UC_ARM_REG_R0)|(uc.reg_read(UC_ARM_REG_R1)<<32):016X}')
    if pc in entries:active.append((entries[pc],uc.reg_read(UC_ARM_REG_LR)&~1,tick))
    tick+=1
m.uc.hook_add(UC_HOOK_CODE,hook)
jobs=json.loads((W/'original153.json').read_text())['rows']
jobs=[r for r in jobs if any(v['candidate']>v['Qfplib'] for v in r['states'])]
rows=[]
for row in jobs:
    results={}
    for label,name in [('public','_ZN12compact_math3powEdd'),('direct','mk61_m0_pow_positive_checked_dispatch')]:
        active.clear();times.clear();returns.clear();tick=0
        m.uc.mem_write(0xd0000060,states['READY'])
        value,_,cost=m.call(name,int(row['x'],16),int(row['y'],16),count=True)
        state_after(m,states['READY'])
        while active:
            n,lr,start=active.pop();times[n]+=tick-start
        results[label]=dict(output=f'{value:016X}',instructions=cost,inclusive_instructions=dict(times),root_returns=dict(returns))
    assert results['public']['output']==results['direct']['output']
    assert results['public']['instructions']==row['states'][0]['candidate']
    rows.append(dict(x=row['x'],y=row['y'],Qfplib=row['states'][0]['Qfplib'],**results))
    print(row['x'],row['y'],'pub/direct/qfp',results['public']['instructions'],results['direct']['instructions'],row['states'][0]['Qfplib'],
          'root',results['public']['inclusive_instructions'].get('pow_root128_ranged',0),'direct_firstcell',results['direct']['inclusive_instructions'].get('pow_first_cell',0),flush=True)
out=dict(status='ROUTE_ANALYSIS_NO_NEW_CANDIDATE',actual_ARM_calls=2*len(rows),fresh_MPFR_or_Qfplib_calls=0,
         parent_ELF_sha256=sha(W/'candidate.elf'),all_public_direct_bits_identical=True,rows=rows,hardware_accessed=False)
(A/'profile.json').write_text(json.dumps(out,indent=2)+'\n')
