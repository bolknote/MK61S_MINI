"""Fresh R38 ARM with explicitly inherited frozen R37 gold/reference/costs."""
from pathlib import Path
from collections import Counter
import ast,gzip,hashlib,importlib.util,json,re,struct,sys,time
sys.dont_write_bytecode=True
W=Path(__file__).resolve().parent;ROOT=W.parents[1]
S=ROOT/'.build/m0-math-unified-exp-row0-midpoint-r38-20261026'
P=ROOT/'.build/m0-math-unified-exp-row0-small-r37-qualification-20261026'
phase=sys.argv[1];assert phase in ['full','boundary','power','edge','admission']
read=lambda p:json.loads(p.read_bytes())
def sha(p):
    h=hashlib.sha256()
    with p.open('rb')as f:
        for b in iter(lambda:f.read(1048576),b''):h.update(b)
    return h.hexdigest()
assert sha(S/'FROZEN.json')=='da406f31b39e0a01ee415a1ee9d2658d1fbed5ac5ceb04784dc8a25e146a60a2'
assert sha(P/'FROZEN.json')=='00dc5efa117f764392cacc06a7d97145ba9cca7650909dd4fc6b68cda5bae8e4'
assert not(W/(phase+'-result.json')).exists()
inputs=S if phase=='admission'else P
inputname='probe-records.jsonl.gz'if phase=='admission'else phase+'-records.jsonl.gz'
assert sha(inputs/inputname)==read(inputs/'FROZEN.json')['files'][inputname]['sha256']
spec=importlib.util.spec_from_file_location('r38_'+phase,S/'harness.py');h=importlib.util.module_from_spec(spec);spec.loader.exec_module(h)
from native_eabi_m0_arm_self_test import SP
from unicorn import UC_HOOK_CODE
from unicorn.arm_const import UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2,UC_ARM_REG_R3,UC_ARM_REG_R6,UC_ARM_REG_R7,UC_ARM_REG_R12,UC_ARM_REG_SP,UC_ARM_REG_XPSR
m=h.machine();assert not m.rom_models
states={'READY':struct.pack('<7I',0,0,0,0,0,0,1),'DIRTY':struct.pack('<7I',17,3,17,3,5,2,3),'PENDING':struct.pack('<7I',0x80000001,7,0x80000001,7,0x11223344,0x55667788,2)}
current={};visits=Counter();poison=None;nzcv=None;row0={};row0cost={};start=time.monotonic()
steptext=(S/'source/code/native_eabi_m0_exp_table.inc').read_text()
STEP_H=int(re.search(r'exp_step_high=UINT64_C\((\d+)\)',steptext)[1]);STEP_L=int(re.search(r'exp_step_low=(\d+)U',steptext)[1])
assert (STEP_H,STEP_L)==(24973259072661436,3588551130)
poison_set=set()
if phase=='boundary':
    model=ROOT/'.build/m0-exp-row0-normalized-outer-study-20261026'
    assert sha(model/'FROZEN.json')=='e3f966ec5df296b89d9268c8919dc5244f742cf112cad764b77c2b7c96732537'
    poison_set.update(read(model/'result.json')['inherited_profile_eligible_arguments'])
    smallmodel=ROOT/'.build/m0-exp-row0-small-negative-study-20261026'
    assert sha(smallmodel/'FROZEN.json')=='6f0681fa4ef90e4536c386302c7c972db4fd997e2c53e2d908c8b00e658e01ee'
    poison_set.update(read(smallmodel/'result.json')['inherited_profile_eligible_arguments'])
    oldmeta=ROOT/'.build/m0-math-unified-exp-positive-bridge-r33-qualification-20261026'
    assert sha(oldmeta/'FROZEN.json')=='6cc6994839b641b9496508dcf0181918089835a8327b3f71862ee5cd759c9fde'
    with gzip.open(oldmeta/'boundary-records.jsonl.gz','rt')as f:
        for line in f:
            rr=json.loads(line);pp=rr.get('actual_bridge_helper_params')
            if pp and not pp[2]&511:poison_set.add(rr['x'])
    assert len(poison_set)==154


if phase=='admission':
    with gzip.open(S/'probe-records.jsonl.gz','rt')as f:
        for line in f:
            rr=json.loads(line)
            if rr['instructions']['candidate']-rr['instructions']['parent']<-1000:poison_set.add(rr['x'])
    assert len(poison_set)==19

def reg(uc,r):return uc.reg_read(r)&0xffffffff
def dispatch(uc,address,size,arg):
    base=reg(uc,UC_ARM_REG_SP);n=reg(uc,UC_ARM_REG_R2)
    if poison is not None and not n&511:uc.reg_write(UC_ARM_REG_R12,poison)
    if nzcv is not None:uc.reg_write(UC_ARM_REG_XPSR,(uc.reg_read(UC_ARM_REG_XPSR)&0x0fffffff)|(nzcv<<28))
    x=reg(uc,UC_ARM_REG_R0)|(reg(uc,UC_ARM_REG_R1)<<32);q=reg(uc,UC_ARM_REG_R6)|(reg(uc,UC_ARM_REG_R7)<<32);dhi=struct.unpack('<I',uc.mem_read(base+28,4))[0]
    current['dispatch']=(x,n,q,dhi,reg(uc,UC_ARM_REG_R12),base)
    current['eligible_fast']=not(x>>63)and not(n&511)and dhi<1<<21 and not(q&512)
    dlo=struct.unpack('<I',uc.mem_read(base+24,4))[0]
    current['eligible_small']=not(n&511)and dhi==0xffffffff and dlo>=2 and(q+2)&3==0
    current['eligible_midpoint']=not(n&511)and dhi==0xffffffff and(q&1023)==512 and(dlo+2)&3==0
    current['eligible_norm']=current['eligible_midpoint']or current['eligible_small']or(not(n&511)and dhi>=1<<31 and (q+4)&7==0)
    if current['eligible_small']or current['eligible_midpoint']:
        mag=x&0x7fffffffffffffff;ee=(mag>>52)-1023;sig=(mag&((1<<52)-1))|(1<<52);assert -11<=ee<=9
        R=((sig<<(ee+12))-n*STEP_H-((n*STEP_L)>>32))&((1<<64)-1)
        if x>>63:R=(-R)&((1<<64)-1)
        assert R==(dhi<<32)|dlo,('source D differs exact analytic R',x,n,dhi,dlo,R)
    if current['eligible_norm']:
        assert q&1023 in [508,510,512,514,516]and 16384<=q>>48<=32767
        dlo=struct.unpack('<I',uc.mem_read(base+24,4))[0];D=(dhi<<32)|dlo;D-=1<<64
        kk=struct.unpack('<i',uc.mem_read(base+8,4))[0]
        assert q==2*((1<<62)-((-D+2)>>2))and kk==((-n if x>>63 else n)//512)-1
        assert -1022<=kk<=1023
    if current['eligible_fast']:assert 509<=q&1023<=511 and 16384<=q>>48<=16392
    visits['dispatch']+=1
def fast(uc,address,size,arg):
    assert current['eligible_fast'];current['fast']='positive21';visits['fast21']+=1
def normalized(uc,address,size,arg):
    assert current['eligible_norm'];current['fast']='midpoint17'if current['eligible_midpoint']else'small17'if current['eligible_small']else'normalized17';visits[current['fast']]+=1
def helper(uc,address,size,arg):
    x,n,q,dhi,F,base=current['dispatch'];assert not current['eligible_fast']and not current['eligible_norm']and not(x>>63)and dhi<1<<31
    actual=tuple(reg(uc,r)for r in [UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2,UC_ARM_REG_R3])+(struct.unpack('<I',uc.mem_read(base-40,4))[0],)
    assert reg(uc,UC_ARM_REG_SP)==base-40 and actual==(q>>48,dhi,n,F if n&511 else 0x40000000,512-(q&1023))
    assert 16384<=actual[0]<=32767 and 1<=(dhi+1024)>>10<=2939 and n<=756388 and 0<=actual[4]<=3
    current['helper']=True;visits['helper']+=1
def refine(uc,address,size,arg):current['refine']=True;visits['refine']+=1
entry=m.elf.symbols['mk61_m0_exp_positive_dispatch']&~1
# These literal offsets are separately checked against the current disassembly
# and SHA-pinned source certificate; +0x64 is the first fast pack instruction.
fn=next(n for n in ast.parse((S/'verify-private-return.py').read_text()).body if isinstance(n,ast.FunctionDef)and n.name=='parse');env={'re':re};exec(compile(ast.Module(body=[fn],type_ignores=[]),'p','exec'),env)
parsed=env['parse']((S/'candidate.dis').read_text());negative=int(parsed[entry+2]['operands'].split()[0],16);normalized_pack=negative+16
assert parsed[normalized_pack]['mnemonic']=='mov'and parsed[normalized_pack]['operands']=='r0, r6'
hooks=[]
for addr,fn in [(entry,dispatch),(entry+0x64,fast),(normalized_pack,normalized),(m.elf.symbols['mk61_m0_exp_positive_upper']&~1,helper),(m.elf.symbols['exp_refine']&~1,refine)]:
    hooks.append(m.uc.hook_add(UC_HOOK_CODE,fn,begin=addr,end=addr))
def call(x,sb):
    current.clear();m.uc.mem_write(0xd0000060,sb)
    got,_,cost=m.call('_ZN12compact_math3expEd',x,count=True)
    if sb==states['READY']:assert not struct.unpack('<7I',m.uc.mem_read(0xd0000060,28))[6]&2
    else:assert bytes(m.uc.mem_read(0xd0000060,28))==sb
    if current.get('eligible_fast')or current.get('eligible_norm'):assert current.get('fast')and not current.get('helper')and not current.get('refine')
    return got,cost
calls=0;remaining=set();parentloss=set();wrong=0;new=[];increases=[];deltas=Counter();relations=Counter();unique=set();poisoncalls=0
try:
    with gzip.open(inputs/inputname,'rt')as stream,gzip.GzipFile(filename=str(W/(phase+'-records.jsonl.gz')),mode='wb',mtime=0)as out:
        for i,line in enumerate(stream):
            if i%8192==0:print('R38',phase,i,'elapsed',round(time.monotonic()-start,1),'loss',len(remaining),'new',len(new),flush=True)
            old=json.loads(line);x=old['x'];unique.add(x);state=old['SIO']
            if phase in ['edge','admission']:
                parentlabel='parent'if phase=='admission'else'candidate'
                parentout=old['outputs'][parentlabel];parentcost=old['instructions'][parentlabel];gold=old['expected'];qout=old['outputs']['Qfplib'];qc=old['instructions']['Qfplib'];qok=old['correct']['Qfplib']
            else:
                parentout=old['candidate_output'];parentcost=old['candidate_instructions'];gold=old['expected_inherited_directed_MPFR'];qout=old['inherited_Qfplib_output'];qc=old['inherited_Qfplib_instructions'];qok=old['inherited_Qfplib_correct']
            got,cost=call(int(x,16),states[state]);calls+=1
            assert f'{got:016X}'==parentout,('output differs frozen correct R37',phase,x,state,f'{got:016X}',parentout)
            change=cost-parentcost;deltas[change]+=1
            if change>0:increases.append(dict(x=x,SIO=state,parent=parentcost,candidate=cost,delta=change,Qfplib=qc,Qfplib_correct=qok))
            if qok:
                relation='strict'if cost<qc else'equal'if cost==qc else'slower';relations[relation]+=1
                if parentcost>qc:parentloss.add(x)
                if cost>qc:
                    remaining.add(x)
                    if parentcost<=qc:new.append(dict(x=x,SIO=state,parent=parentcost,candidate=cost,Qfplib=qc))
            else:wrong+=1
            if phase in ['boundary','admission']and x in poison_set:
                row0[x]=int(gold,16);row0cost[x,state]=cost
            route=current['fast']if current.get('fast')else'helper_decline'if current.get('helper')and current.get('refine')else'helper_accept'if current.get('helper')else'fallback'if current.get('dispatch')else'no_bridge'
            r=dict(operation='exp',index=old.get('index',i),x=x,group=old['group'],SIO=state,expected_inherited_directed_MPFR=gold,candidate_output=f'{got:016X}',candidate_instructions=cost,
             inherited_R37_output=parentout,inherited_R37_instructions=parentcost,inherited_Qfplib_output=qout,inherited_Qfplib_instructions=qc,inherited_Qfplib_correct=qok,actual_bridge_route=route)
            out.write((json.dumps(r,separators=(',',':'))+'\n').encode())
    if phase in ['boundary','admission']:
        assert len(row0)==(154 if phase=='boundary'else 19)
        for x,gold in row0.items():
            for state,sb in states.items():
                for poison in [0,0x12345678,0x7fffffff,0x80000000,0xffffffff]:
                    for nzcv in range(16):
                        got,cost=call(int(x,16),sb);poisoncalls+=1
                        assert got==gold and cost==row0cost[x,state]
        poison=None;nzcv=None
except Exception as error:
    (W/(phase+'-FAILURE.json')).write_text(json.dumps(dict(error=repr(error),phase=phase,completed_public_ARM_calls=calls,completed_poison_calls=poisoncalls,current={k:v for k,v in current.items()}),indent=2)+'\n');raise
finally:
    for hook in hooks:m.uc.hook_del(hook)
assert(calls,len(unique),len(parentloss))==({'full':(989922,494961,260),'boundary':(176952,58984,442),'power':(31842,10614,10),'edge':(30939,10313,20),'admission':(26007,8669,510)}[phase])
assert poisoncalls==({'boundary':36960,'admission':4560}.get(phase,0))
result=dict(status='COMPLETED_FRESH_R38_'+phase.upper()+'_WITH_INHERITED_R37_ORACLES_QFP_PARENT',phase=phase,source_FROZEN_sha256=sha(S/'FROZEN.json'),parent_qualification_FROZEN_sha256=sha(P/'FROZEN.json'),candidate_ELF_sha256=sha(S/'candidate.elf'),input_records_sha256=sha(inputs/inputname),input_source_FROZEN_sha256=sha(inputs/'FROZEN.json'),input_source=str(inputs.relative_to(ROOT)),records_sha256=sha(W/(phase+'-records.jsonl.gz')),
 unique_inputs=len(unique),state_rows=calls,actual_fresh_public_R38_ARM_calls=calls,actual_fresh_public_index0_poison16NZCV_calls=poisoncalls,actual_qualified_public_ARM_calls=calls+poisoncalls,
 actual_fresh_parent_Qfp_MPFR_calls=0,all_oracles_Qfp_parent_from_frozen_input_source=True,source_is_R38_diagnostic_not_R37_qualification=(phase=='admission'),inherited_R37_calls_not_fresh=True,all_outputs_exact_frozen_correctly_rounded_R37=True,candidate_wrong=0,
 parent_losing_inputs=len(parentloss),candidate_losing_inputs=len(remaining),fixed_inputs=len(parentloss-remaining),new_losing_inputs=len(remaining-parentloss),remaining_losing_arguments=sorted(remaining),new_correct_Qfplib_loss_rows=new,
 all_parent_increases=increases,instruction_delta_histogram=dict(deltas),correct_inherited_Qfplib_relations=dict(relations),wrong_inherited_Qfplib_rows_retained=wrong,
 actual_private_entry_counts=dict(visits),all_actual_fast_inputs_within_proved_domain=True,all_actual_helper_parameters_exact_and_in_domain=True,row0_public_poison_unique_inputs=len(row0),all_poison_bits_and_costs_exact=True,
 observed_stack=SP-m.stack_lowest,not_universal_stack_bound=True,diagnostics_primitives_inherited_oracles_generation_not_pooled=True,no_nominal_reference_filter=True,
 physical_cycles_measured=False,hardware_accessed=False,integration_GO=False,goal_complete=False,elapsed_seconds=time.monotonic()-start)
(W/(phase+'-result.json')).write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps({k:v for k,v in result.items()if k not in ['remaining_losing_arguments','all_parent_increases','new_correct_Qfplib_loss_rows']},indent=2),flush=True)
