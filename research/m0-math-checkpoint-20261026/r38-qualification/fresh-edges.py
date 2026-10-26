"""Fresh public candidate/parent/Qfp/MPFR plus actual bridge-entry metadata."""
from pathlib import Path
from collections import Counter
import ast,gzip,hashlib,importlib.util,json,re,struct,sys,time
sys.dont_write_bytecode=True
W=Path(__file__).resolve().parent;ROOT=W.parents[1]
S=ROOT/'.build/m0-math-unified-exp-row0-midpoint-r38-20261026'
P=ROOT/'.build/m0-math-unified-exp-row0-small-r37-20261026'
REF=ROOT/'.build/m0-v138-execution-20261023/reference/reference.elf'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
assert sha(S/'FROZEN.json')=='da406f31b39e0a01ee415a1ee9d2658d1fbed5ac5ceb04784dc8a25e146a60a2'
assert sha(P/'FROZEN.json')=='540e32a2a2cac7faa476b08ca792778ea7f327c6c35eb7e73aae7eb5c5f869e7'
assert sha(REF)=='b66da3a6805ecd110580e6dd281e17c37bc4399bee0ba1fae86f8c8cf78bfc26'
assert not(W/'fresh-edge-result.json').exists()
sys.path[:0]=[str(ROOT/'.build/m0-float-fma-qualification-20261023'),str(ROOT/'.build/m0-float-fma-qualification-20261023/support')]
from native_eabi_m0_arm_self_test import Machine,SP
from m0_mpfr_oracle import Oracle
from oracles import equal
from unicorn import UC_HOOK_CODE
from unicorn.arm_const import UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2,UC_ARM_REG_R3,UC_ARM_REG_R6,UC_ARM_REG_R7,UC_ARM_REG_R12,UC_ARM_REG_SP,UC_ARM_REG_XPSR
def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path/'harness.py');h=importlib.util.module_from_spec(spec);spec.loader.exec_module(h);return h.machine()
machines={'candidate':load('r38_fresh',S),'parent':load('r37_parent_fresh',P),'Qfplib':Machine(REF,True)}
assert all(not m.rom_models for m in machines.values())
states={'READY':struct.pack('<7I',0,0,0,0,0,0,1),'DIRTY':struct.pack('<7I',17,3,17,3,5,2,3),'PENDING':struct.pack('<7I',0x80000001,7,0x80000001,7,0x11223344,0x55667788,2)}
current={};visits=Counter();row0={};poison=None;flags=None
def read(uc,r):return uc.reg_read(r)&0xffffffff
def dispatch(uc,address,size,arg):
    base=read(uc,UC_ARM_REG_SP);n=read(uc,UC_ARM_REG_R2)
    if poison is not None and not n&511:uc.reg_write(UC_ARM_REG_R12,poison)
    if flags is not None:uc.reg_write(UC_ARM_REG_XPSR,(uc.reg_read(UC_ARM_REG_XPSR)&0x0fffffff)|(flags<<28))
    current['dispatch']=(read(uc,UC_ARM_REG_R0)|(read(uc,UC_ARM_REG_R1)<<32),n,read(uc,UC_ARM_REG_R6)|(read(uc,UC_ARM_REG_R7)<<32),struct.unpack('<I',uc.mem_read(base+28,4))[0],read(uc,UC_ARM_REG_R12),base)
    visits['dispatch']+=1
def helper(uc,address,size,arg):
    x,n,q,dhi,frac,base=current['dispatch'];assert not(x>>63)and dhi<1<<31
    assert read(uc,UC_ARM_REG_SP)==base-40 and not((base-40)&7)
    params=tuple(read(uc,r)for r in [UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2,UC_ARM_REG_R3])+(struct.unpack('<I',uc.mem_read(base-40,4))[0],)
    expect=(q>>48,dhi,n,frac if n&511 else 0x40000000,512-(q&1023))
    assert params==expect,(params,expect)
    assert 16384<=params[0]<=32767 and 1<=(dhi+1024)>>10<=2939 and n<=756388 and 0<=params[4]<=3
    current['helper']=params;visits['helper']+=1
    if not n&511:visits['row0_helper']+=1
def refine(uc,address,size,arg):visits['refine']+=1;current['refine']=True
def normalized(uc,address,size,arg):
    x,n,q,dhi,F,base=current['dispatch'];assert not n&511 and dhi>=1<<31 and q&1023 in [508,510,512,514,516]
    dlo=struct.unpack('<I',uc.mem_read(base+24,4))[0];D=((dhi<<32)|dlo)-(1<<64)
    kk=struct.unpack('<i',uc.mem_read(base+8,4))[0]
    assert q==2*((1<<62)-((-D+2)>>2))and kk==((-n if x>>63 else n)//512)-1
    assert -1022<=kk<=1023
    if q&1023 in [510,512,514]:
        assert dhi==0xffffffff and dlo>=2
        mag=x&0x7fffffffffffffff;ee=(mag>>52)-1023;sig=(mag&((1<<52)-1))|(1<<52);assert -11<=ee<=9
        R=((sig<<(ee+12))-n*24973259072661436-((n*3588551130)>>32))&((1<<64)-1)
        if x>>63:R=(-R)&((1<<64)-1)
        assert R==(dhi<<32)|dlo
        if q&1023==512:assert(dlo+2)&3==0
        visits['midpoint17'if q&1023==512 else'small17']+=1
    else:visits['normalized17']+=1
    current['normalized']=True
m=machines['candidate'];hooks=[]
for symbol,fn in [('mk61_m0_exp_positive_dispatch',dispatch),('mk61_m0_exp_positive_upper',helper),('exp_refine',refine)]:
    entry=m.elf.symbols[symbol]&~1;hooks.append(m.uc.hook_add(UC_HOOK_CODE,fn,begin=entry,end=entry))
fn=next(n for n in ast.parse((S/'verify-private-return.py').read_text()).body if isinstance(n,ast.FunctionDef)and n.name=='parse');env={'re':re};exec(compile(ast.Module(body=[fn],type_ignores=[]),'p','exec'),env)
code=env['parse']((S/'candidate.dis').read_text());entry=m.elf.symbols['mk61_m0_exp_positive_dispatch']&~1;negative=int(code[entry+2]['operands'].split()[0],16);pack=negative+16
assert code[pack]['mnemonic']=='mov'and code[pack]['operands']=='r0, r6'
hooks.append(m.uc.hook_add(UC_HOOK_CODE,normalized,begin=pack,end=pack))
o=Oracle();counts=Counter();remaining=set();parentloss=set();increases=[];new=[];wrong=0;deltas=Counter();relations=Counter();start=time.monotonic();records=0
inputs=json.loads((W/'fresh-edge-inputs.json').read_bytes())['groups']
try:
    with gzip.GzipFile(filename=str(W/'fresh-edge-records.jsonl.gz'),mode='wb',mtime=0)as stream:
        for i,(xhex,group)in enumerate(inputs.items()):
            if i%1024==0:print('R38 boundaries',i,'/',len(inputs),'elapsed',round(time.monotonic()-start,1),'loss',len(remaining),'new',len(new),flush=True)
            x=int(xhex,16);gold=o.reference('exp',x)
            for state,sb in states.items():
                current.clear();out={};cost={};correct={}
                for label,mach in machines.items():
                    mach.uc.mem_write(0xd0000060,sb)
                    v,_,c=mach.call('qfp_dexp'if label=='Qfplib'else'_ZN12compact_math3expEd',x,count=True)
                    counts[label]+=1;out[label]=f'{v:016X}';cost[label]=c;correct[label]=equal(v,gold,64)
                    if state=='READY':assert not struct.unpack('<7I',mach.uc.mem_read(0xd0000060,28))[6]&2
                    else:assert bytes(mach.uc.mem_read(0xd0000060,28))==sb
                    if label!='Qfplib':assert correct[label],(label,xhex,state,out[label],f'{gold:016X}')
                r=dict(x=xhex,group=group,SIO=state,expected=f'{gold:016X}',outputs=out,instructions=cost,correct=correct,actual_bridge_helper_params=current.get('helper'),candidate_refine=bool(current.get('refine')),normalized_row0=bool(current.get('normalized')))
                if current.get('helper')and not current['helper'][2]&511:row0.setdefault(xhex,dict(expected=gold,instructions=cost['candidate']))
                d=cost['candidate']-cost['parent'];deltas[d]+=1
                if d>0:increases.append(r)
                if correct['Qfplib']:
                    rel='slower'if cost['candidate']>cost['Qfplib']else'equal'if cost['candidate']==cost['Qfplib']else'strict';relations[rel]+=1
                    if cost['parent']>cost['Qfplib']:parentloss.add(xhex)
                    if rel=='slower':
                        remaining.add(xhex)
                        if cost['parent']<=cost['Qfplib']:new.append(r)
                else:wrong+=1
                stream.write((json.dumps(r,separators=(',',':'))+'\n').encode());records+=1
    poisoncalls=0;selected=[]
except Exception as error:
    (W/'fresh-edge-FAILURE.json').write_text(json.dumps(dict(error=repr(error),completed_ARM_calls=dict(counts),completed_rows=records,actual_current_context=current,candidate_ELF_sha256=sha(S/'candidate.elf')),indent=2)+'\n');raise
finally:
    for h in hooks:m.uc.hook_del(h)
result=dict(status='COMPLETED_R38_FRESH_PUBLIC_EDGES_AND_ACTUAL_PRIVATE_METADATA',source_FROZEN_sha256=sha(S/'FROZEN.json'),candidate_ELF_sha256=sha(S/'candidate.elf'),input_sha256=sha(W/'fresh-edge-inputs.json'),records_sha256=sha(W/'fresh-edge-records.jsonl.gz'),
 unique_inputs=len(inputs),state_rows=records,actual_base_public_ARM_calls=dict(counts),actual_public_index0_poison16NZCV_calls=poisoncalls,actual_qualified_public_ARM_calls=sum(counts.values())+poisoncalls,
 actual_directed_MPFR_inputs=len(inputs),generation_MPFR_calls_not_validation_pool=True,primitive_or_stub_calls=0,candidate_wrong=0,
 parent_losing_inputs=len(parentloss),candidate_losing_inputs=len(remaining),fixed_inputs=len(parentloss-remaining),new_losing_inputs=len(remaining-parentloss),new_correct_Qfplib_loss_rows=new,
 remaining_losing_arguments=sorted(remaining),all_parent_increases=increases,instruction_delta_histogram=dict(deltas),correct_Qfplib_relations=dict(relations),wrong_Qfplib_rows_retained=wrong,
 actual_private_entry_counts=dict(visits),all_actual_helper_params_match_callsite_metadata=True,all_actual_helper_inputs_within_proved_domain=True,
 row0_helper_unique_inputs=len(row0),row0_public_poison_selected_inputs=len(selected),public_poison_tests_not_part_of_this_fresh_campaign=True,
 observed_stacks={n:SP-mm.stack_lowest for n,mm in machines.items()},no_nominal_reference_domain_filter=True,physical_cycles_measured=False,
 hardware_accessed=False,integration_GO=False,goal_complete=False,elapsed_seconds=time.monotonic()-start)
(W/'fresh-edge-result.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps({k:v for k,v in result.items()if k not in ['remaining_losing_arguments','all_parent_increases','new_correct_Qfplib_loss_rows']},indent=2),flush=True)
