"""Both actual entries versus exact integer frames; explicit native ARM fixtures."""
from pathlib import Path
from collections import Counter
import ast,gzip,hashlib,importlib.util,json,struct,subprocess,sys,time
sys.dont_write_bytecode=True
W=Path(__file__).resolve().parent;ROOT=W.parents[1]
P=ROOT/'.build/m0-math-unified-pow-rsqrt-seedreuse-r42-20261026'
D=ROOT/'.build/m0-pow-rsqrt-r38-live-profile-20261026'
M=ROOT/'.build/m0-math-unified-pow-rsqrt-negfirst-r41-20261026'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
assert sha(P/'FROZEN.json')=='b5e0bf1e6316a2bc0924127f0b9564c025cb042842f4d3527ce1eef8fd48a676'
assert sha(D/'FROZEN.json')=='3257d6a962a261c65ff01daba80189190302661f700f53ca2b1ffc79a48e5630'
assert sha(M/'FROZEN.json')=='a7d40e058c905f614b5404f509041c1d640c4bfaa8483244ec6dc310bb51197f'
assert not(W/'helper-unit-result.json').exists()
models=[n for n in ast.parse((M/'helper-unit.py').read_text()).body if isinstance(n,ast.FunctionDef)and n.name in ('model','generated')];assert len(models)==2
scope={'mask':(1<<32)-1,'mask64':(1<<64)-1};exec(compile(ast.Module(body=models,type_ignores=[]),'inherited_exact_integer_model','exec'),scope);model=scope['model'];generated=scope['generated']
def load(n,p):
    spec=importlib.util.spec_from_file_location(n,p/'harness.py');h=importlib.util.module_from_spec(spec);spec.loader.exec_module(h);return h.machine()
machines={'parent':load('r42_unit',P),'candidate':load('r43_unit',W)};assert all(not m.rom_models for m in machines.values())
from unicorn import UC_HOOK_CODE,UC_HOOK_MEM_READ,UC_HOOK_MEM_WRITE
from unicorn.arm_const import UC_ARM_REG_R0,UC_ARM_REG_R12,UC_ARM_REG_XPSR
sys.path.insert(0,str(ROOT/'tests'));from check_stm32_vectors import ElfImage
ctx=0x20020000;fixture_base=0x101e0000;fixture_info={};fixture_name='r43_native_test_entry';tc=Path(json.loads((W/'link-result.json').read_bytes())['commands'][0][0]).parent
for label,m in machines.items():
    target=m.elf.symbols['mk61_m0_pow_rsqrt_local_q8_native'if label=='candidate'else'mk61_m0_pow_rsqrt_local_q8']
    text=f'''.syntax unified
.cpu cortex-m0plus
.thumb
.section .text,"ax",%progbits
.balign 4
.global {fixture_name}
.type {fixture_name},%function
.thumb_func
{fixture_name}:
 push {{r4,lr}}
 ldr r2,[r0,#28]
 ldr r3,=0x7fffffff
 subs r2,r2,r3
 cmp r2,#1
 bhi reject
 ldr r3,={target|1}
 blx r3
 pop {{r4,pc}}
reject:
 bkpt #0
 .ltorg
.size {fixture_name},.-{fixture_name}
'''
    src=W/(label+'-native-fixture.S');src.write_text(text);out=W/(label+'-native-fixture.elf')
    command=[str(tc/'arm-none-eabi-gcc'),'-mcpu=cortex-m0plus','-mthumb','-nostdlib','-Wl,-Ttext=0x101e0000','-Wl,--entry='+fixture_name,str(src),'-o',str(out)]
    subprocess.run(command,check=True,cwd=W);f=ElfImage(out);assert(f.symbols[fixture_name]&~1)==fixture_base
    for s in m.elf.named_sections.values():
        if s[2]&2 and s[5]:assert not(s[3]<ctx+44 and ctx<s[3]+s[5])
    for fs in f.named_sections.values():
        if not(fs[2]&2 and fs[5]):continue
        for s in m.elf.named_sections.values():
            if s[2]&2 and s[5]:assert not(s[3]<fs[3]+fs[5]and fs[3]<s[3]+s[5])
        for seg in m.elf.segments:
            if seg[0]==1 and seg[4]:assert not(seg[3]<fs[3]+fs[5]and fs[3]<seg[3]+seg[4])
        assert not(fs[3]<ctx+44 and ctx<fs[3]+fs[5])
    assert fixture_name not in m.elf.symbols;f.load(m.uc);m.elf.symbols[fixture_name]=f.symbols[fixture_name]
    dis=subprocess.check_output([str(tc/'arm-none-eabi-objdump'),'-dr',str(out)],text=True);(W/(label+'-native-fixture.dis')).write_text(dis)
    fixture_info[label]=dict(source_sha256=sha(src),ELF_sha256=sha(out),command=command,base=fixture_base,production_target=target|1,disjoint_all_production_VMA_LMA_and_context=True,explicit_test_symbol_added_to_call_namespace_only=True)
states={'READY':struct.pack('<7I',0,0,0,0,0,0,1),'DIRTY':struct.pack('<7I',17,3,17,3,5,2,3),'PENDING':struct.pack('<7I',0x80000001,7,0x80000001,7,0x11223344,0x55667788,2)}
frames=[]
with gzip.open(D/'records.jsonl.gz','rt')as f:
    for line in f:
        r=json.loads(line)
        if r['SIO']=='READY'and'q8_frame'in r['actual_native_metadata']:frames.append(r['actual_native_metadata']['q8_frame'])
assert len(frames)==1116
mode=None;poison=0;flags=0;native_C=Counter();hooks=[]
def poison_entry(uc,a,size,when):
    if mode==when:
        uc.reg_write(UC_ARM_REG_R12,poison);uc.reg_write(UC_ARM_REG_XPSR,(uc.reg_read(UC_ARM_REG_XPSR)&0x0fffffff)|(flags<<28))
def native_entry(uc,a,size,arg):
    C=(uc.reg_read(UC_ARM_REG_XPSR)>>29)&1;high=struct.unpack('<I',uc.mem_read(uc.reg_read(UC_ARM_REG_R0)+28,4))[0]
    assert high in(0x7fffffff,0x80000000)and C==int(high==0x80000000);native_C[C]+=1
def sio_access(*args):raise AssertionError('pure Q8 entry accessed SIO')
for label,m in machines.items():
    a=m.elf.symbols['mk61_m0_pow_rsqrt_local_q8']&~1;hooks.append((m,m.uc.hook_add(UC_HOOK_CODE,poison_entry,user_data='generic',begin=a,end=a)))
    hooks.append((m,m.uc.hook_add(UC_HOOK_CODE,poison_entry,user_data='native',begin=fixture_base,end=fixture_base)))
    hooks.append((m,m.uc.hook_add(UC_HOOK_MEM_READ|UC_HOOK_MEM_WRITE,sio_access,begin=0xd0000060,end=0xd000007b)))
    if label=='candidate':
        a=m.elf.symbols['mk61_m0_pow_rsqrt_local_q8_native']&~1;hooks.append((m,m.uc.hook_add(UC_HOOK_CODE,native_entry,begin=a,end=a)))
calls=Counter();routes=Counter();generic_delta=Counter();native_delta=Counter();rows=0;carry_rows=0;carry_phase=False;started=time.monotonic();current={}
def run(p,state,out):
    global rows,carry_rows,mode,current
    expected,route=model(p);routes[route]+=1;data=struct.pack('<11I',*p);sb=states[state];values={};costs={}
    if carry_phase and route=='up'and(((((p[10]<<32)|p[9])>>10)&0xffffffff)==0xffffffff):assert expected&0xffffffff==0;carry_rows+=1
    for mode in('generic','native'):
        for label,m in machines.items():
            name=mode+'-'+label;current=dict(index=rows,mode=mode,label=label,frame=p,SIO=state,NZCV=flags,R12=poison)
            m.uc.mem_write(ctx,data);m.uc.mem_write(0xd0000060,sb)
            got,_,count=m.call('mk61_m0_pow_rsqrt_local_q8'if mode=='generic'else fixture_name,ctx,count=True);calls[name]+=1
            assert got==expected,(current,got,expected)
            assert bytes(m.uc.mem_read(ctx,44))==data and bytes(m.uc.mem_read(0xd0000060,28))==sb
            values[name]=got;costs[name]=count
    gd=costs['generic-candidate']-costs['generic-parent'];nd=costs['native-candidate']-costs['native-parent'];assert gd==2 and nd==-1,(current,costs)
    generic_delta[gd]+=1;native_delta[nd]+=1
    order=['generic-parent','generic-candidate','native-parent','native-candidate'];out.write(struct.pack('<11I4Q6I',*p,*(values[n]for n in order),*(costs[n]for n in order),flags,poison));rows+=1
try:
    with gzip.GzipFile(filename=str(W/'helper-unit-records.bin.gz'),mode='wb',mtime=0)as out:
        for p in frames:
            for state in states:run(p,state,out)
        for i,p in enumerate(generated()):
            if i%16384==0:print('R43 both-entry uv-grid',i,'/131072',flush=True)
            run(p,'READY',out)
        carry_phase=True
        for seed in(0x7fffffff,0x80000000,0xffffffff):
            for high in(0x7fffffff,0x80000000):
                for tail in(510,512,514):
                    for qhi in(0x400003ff,0x7fffffff):
                        for scale in(510,1021,1532):
                            p=[0,0x100000,seed*seed>>32,scale<<20,0,0,seed,high,0x40000000,0xfffffc00|tail,qhi]
                            for state in states:run(p,state,out)
        carry_phase=False
        for p in frames[::31]:
            for state in states:
                for poison in(0,0x12345678,0x7fffffff,0x80000000,0xffffffff):
                    for flags in range(16):run(p,state,out)
        poison=flags=0
except Exception as e:
    (W/'helper-unit-FAILURE.json').write_text(json.dumps(dict(error=repr(e),current=current,completed_ARM_calls=dict(calls),completed_rows=rows),indent=2)+'\n');raise
finally:
    for m,h in hooks:m.uc.hook_del(h)
assert rows==143384 and sum(calls.values())==573536 and carry_rows==180 and sum(native_C.values())==rows
result=dict(status='PASS_R43_BOTH_ACTUAL_ENTRIES_WITH_EXPLICIT_NATIVE_ARM_FIXTURES',candidate_ELF_sha256=sha(W/'candidate.elf'),parent_source_FROZEN_sha256=sha(P/'FROZEN.json'),captured_metadata_FROZEN_sha256=sha(D/'FROZEN.json'),fixtures=fixture_info,captured_frame_cases1116=True,generated_uv_sign_grid_cases131072=True,selected_poison_frames36_all5R12_all16NZCV_all3SIO=True,state_rows=rows,completed_ARM_calls=dict(calls),actual_qualified_control_ARM_calls=sum(calls.values()),candidate_wrong=0,integer_formula_routes=dict(routes),generic_instruction_delta_histogram=dict(generic_delta),native_fixture_instruction_delta_histogram=dict(native_delta),all_generic_parent_instruction_increase_rows=rows,all_native_fixture_parent_instruction_increase_rows=0,every_generic_increase_retained_in_binary_rows=True,explicit_carry_up_rows=carry_rows,frame_readonly=True,ordinary_generic_arbitrary_NZCV_contract_checked=True,native_incoming_C_from_actual_fixture_guard_checked_every_call=True,native_entry_C_histogram=dict(native_C),ordinary_APCS_callee_saved_SP_checked_every_call=True,R12_all16NZCV_and_threeSIO_results_invariant=True,no_SIO_access=True,synthetic_frames_and_native_fixtures_not_public_accuracy_gold=True,MPFR_calls=0,records_sha256=sha(W/'helper-unit-records.bin.gz'),record_format='<11I4Q6I',hardware_accessed=False,physical_cycles_measured=False,integration_GO=False,goal_complete=False,elapsed_seconds=time.monotonic()-started)
(W/'helper-unit-result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2),flush=True)
