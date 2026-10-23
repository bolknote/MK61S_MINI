"""One-off exact-source and small boundary replay of the d2uiz delta only."""
import collections,datetime,hashlib,json,math,re,struct,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];OUT=Path(__file__).resolve().parent
P=ROOT/'.build/m0-u32-original-goal-20261023';V=ROOT/'.build/m0-asin-scaled-bound-v164-20261023';H=ROOT/'.build/m0-float-fma-qualification-20261023/support'
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
assert sha(P/'HANDOFF.md')=='aa6f45d43388c94298dbd2ed5be220daa98842e1d3b50cdddfc2128d2ca7cd51'
assert sha(P/'result.json')=='1d4e45dbd257d8fbf33bf9516a966fb74bbbdf33145d3448be1a95175d3f1c8c'
index=json.loads((P/'result.json').read_text())
for n,v in index['artifacts'].items():assert sha(P/n)==v['sha256'] and(P/n).stat().st_size==v['bytes']
build=json.loads((P/'build.json').read_text());iso=json.loads((P/'isolation.json').read_text())
for n,h in build['input_sources'].items():assert sha(V/'source/code'/n)==h
assert (P/'native_eabi_m0.S').read_bytes()==(V/'source/code/native_eabi_m0.S').read_bytes()
expected_helpers={'native_eabi_m0_arm_self_test.py':'cdc8ac6c98bad5db3539a494207c556ce4ae49146c8a76b88cf58c4a5c79bee3','check_stm32_vectors.py':'360413d0e17fd36154f91d53a83ea40e19326c7cde041a48a71b3d92748a7708'}
for n,h in expected_helpers.items():assert sha(H/n)==h
sys.path.insert(0,str(H));from check_stm32_vectors import ElfImage
from native_eabi_m0_arm_self_test import Machine
def allocated(e):return {n:(s[1],s[5],e.bytes_at(s)if s[1]!=8 else b'')for n,s in e.named_sections.items()if s[2]&2}
rebuilds=[]
for tag,command,target in [('assembly',iso['commands'][1],'candidate-assembly.o'),('cpp',iso['commands'][3],'candidate-cpp.o')]:
 command=command[:];command[-1]=str(OUT/('rebuilt-'+tag+'.o'));subprocess.run(command,check=True)
 a,b=ElfImage(P/target),ElfImage(command[-1]);assert allocated(a)==allocated(b)and a.symbols==b.symbols
 rebuilds.append(dict(tag=tag,command=command,rebuilt_sha256=sha(command[-1]),producer_object_sha256=sha(P/target),allocated_and_symbol_identity=True))
oldS,newS=ElfImage(P/'control-assembly.o'),ElfImage(P/'candidate-assembly.o');oldC,newC=ElfImage(P/'control-cpp.o'),ElfImage(P/'candidate-cpp.o')
a,b=allocated(oldS),allocated(newS);assert set(b)-set(a)=={'.text.__aeabi_d2uiz'}and not(set(a)-set(b))and all(a[n]==b[n]for n in a)
c,d=allocated(oldC),allocated(newC);assert set(c)-set(d)=={'.text.__aeabi_d2uiz'}and not(set(d)-set(c))and all(c[n]==d[n]for n in d)
raw=(P/'candidate.bin').read_bytes();diag=ElfImage(P/'candidate.elf');assert len(raw)==80 and raw==b['.text.__aeabi_d2uiz'][2]==diag.bytes_at(diag.named_sections['.text'])
assert len(raw)-len(c['.text.__aeabi_d2uiz'][2])==54
for context in ['M4_soft','M4_hard','generic_M0']:
 for suffix in ['S','cpp']:assert allocated(ElfImage(P/(context+'-'+suffix+'-control.o')))==allocated(ElfImage(P/(context+'-'+suffix+'-candidate.o')))
ELF=V/'firmware/mk61s-picocalc-pico-h.elf';ROM=ROOT/'research/rp2040-memset-2026-10-21/capture/bootrom.bin';REF=ROOT/'.build/m0-v138-execution-20261023/reference/reference.elf'
assert sha(ELF)=='3b92d7dc30cc860c0b1f17943f1cd626f94112a98adaf165ec4f9cd300364db1'
assert sha(ROM)=='ef07d54bdd259c7858483606118a3c704976801823c38ac5a2fcdffacd2d83fe'
assert sha(REF)=='b66da3a6805ecd110580e6dd281e17c37bc4399bee0ba1fae86f8c8cf78bfc26'
def oracle(x):
 value=struct.unpack('<d',struct.pack('<Q',x))[0]
 return 0 if math.isnan(value)or value<=0 else 0xffffffff if value>=4294967296 else int(value)
# Validate the exact retained256 set and every correct raw output/cost, while
# replaying only representatives of its two paths plus selected boundaries.
q=json.loads((P/'qualification.json').read_text());known=[r for r in q['rows']if r['group']=='known_slower'];old256=[r for r in json.loads((V/'slower-inputs.json').read_text())['rows']if r['operation']=='d2uiz']
assert len(known)==256 and {r['x']for r in known}=={r['x']for r in old256}
counts=collections.Counter();representatives={}
for row in known:
 expected=oracle(int(row['x'],16));assert row['expected']==expected and all(v==expected for v in row['outputs'].values())
 triple=tuple(row['instructions'][n]for n in ['candidate','baseline','Qfplib']);assert triple[0]<triple[2];counts[triple]+=1;representatives.setdefault(triple,row)
assert counts=={(22,50,43):94,(20,47,43):162}
jobs={0,1<<63,0x7fefffffffffffff,0xffefffffffffffff,0x7ff0000000000000,0xfff0000000000000}
for k in [-1074,-1022,-1,0,1,19,20,21,30,31,32,1023]:
 at=struct.unpack('<Q',struct.pack('<d',math.ldexp(1.,k)))[0]
 for x in [at-1,at,at+1]:jobs|={x,x|(1<<63)}
for n in [3,1048577,2097153,2147483649,4294967295]:
 at=struct.unpack('<Q',struct.pack('<d',float(n)))[0]
 for x in [at-1,at,at+1]:jobs|={x,x|(1<<63)}
for bit in [0,19,20,31,32,51]:jobs|={0x7ff0000000000000|(1<<bit),0xfff0000000000000|(1<<bit)}
jobs|={int(r['x'],16)for r in representatives.values()}
m=Machine(ELF,True,stack_bytes=4096,bootrom=ROM);ref=Machine(REF,True,stack_bytes=4096);m.uc.mem_write(0x10181000,raw);m.elf.symbols['candidate_d2uiz']=diag.symbols['candidate_d2uiz']
from unicorn import UC_HOOK_MEM_WRITE
rows=[];speed=[];calls=0;states=[struct.pack('<7I',17,3,17,3,5,2,csr)for csr in [1,3]]
for x in sorted(jobs):
 expected=oracle(x)
 for state in states:
  results={};cost={}
  for label,name,machine in [('candidate','candidate_d2uiz',m),('baseline','__aeabi_d2uiz',m),('Qfplib','qfp_double2uint',ref)]:
   machine.uc.mem_write(0xd0000060,state);writes=[];hook=machine.uc.hook_add(UC_HOOK_MEM_WRITE,lambda u,k,a,s,v,d:writes.append((a,s)))if label=='candidate'else None
   try:got,_,cost[label]=machine.call(name,x,count=True)
   finally:
    if hook is not None:machine.uc.hook_del(hook)
   calls+=1;got&=0xffffffff
   if label!='Qfplib':assert got==expected,(label,hex(x),got,expected)
   if label=='candidate':assert not writes,('new leaf wrote memory',hex(x),writes)
   assert bytes(machine.uc.mem_read(0xd0000060,28))==state
   results[label]=got
  rows.append(dict(x=f'{x:016X}',CSR=struct.unpack_from('<I',state,24)[0],expected=expected,outputs=results))
  for triple,row in representatives.items():
   if int(row['x'],16)==x:assert tuple(cost[n]for n in ['candidate','baseline','Qfplib'])==triple;speed.append(dict(x=row['x'],CSR=struct.unpack_from('<I',state,24)[0],instruction_counts=cost))
# Recompute the19 cited BL targets directly from the frozen V164 ELF.
def at(e,address,size):
 s=next(s for s in e.sections if s[1]!=8 and s[3]<=address and address+size<=s[3]+s[5]);return e.bytes_at(s)[address-s[3]:address-s[3]+size]
callers=json.loads((P/'linked-callers.json').read_text())['rows'];assert len(callers)==19
for row in callers:
 address=int(row['call'].split(':',1)[0],16);h1,h2=struct.unpack('<2H',at(m.elf,address,4));s=(h1>>10)&1;i1=1^((h2>>13)&1)^s;i2=1^((h2>>11)&1)^s;off=(s<<24)|(i1<<23)|(i2<<22)|((h1&1023)<<12)|((h2&2047)<<1);off-=(1<<25)if s else 0
 assert address+4+off==m.elf.symbols['__aeabi_d2uiz']&~1
for n,v in index['artifacts'].items():assert sha(P/n)==v['sha256']
with(OUT/'ARM-samples.json').open('x')as f:f.write(json.dumps(rows,indent=2)+'\n')
report=dict(status='D2UIZ_DELTA_TECHNICAL_GO_NOT_PRODUCTION',recorded_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),HANDOFF_sha256=sha(P/'HANDOFF.md'),producer_result_sha256=sha(P/'result.json'),patch_sha256=sha(P/'unsigned32-only.patch'),candidate_body_sha256=sha(P/'candidate.bin'),candidate_ELF_sha256=sha(P/'candidate.elf'),source_rebuilds=rebuilds,object_isolation='Exactly80B assembly section added,26B C++ wrapper removed; all other allocated sections and BSS sizes unchanged; +54B unlinked object sections, not full firmware Flash estimate',public_diagnostic_body='All80 bytes including literal identical, no helper relocation',mathematical_review=['sign=1 returns0 for all classes including negativeNaN/Inf/zero; nonnegative E<1023 returns0.','For0<=e<=20 use H>>(20-e); for21<=e<=31 concatenate disjoint H<<(e-20) and L>>(52-e), exact floor/truncation. All shifts0..31 and outputs fit uint32.','For e32..1023 saturateUINT_MAX; e1024 is all-ones exponent and (high<<12)|low distinguishes Inf from every52-bit NaN payload.','Policy equals old D::unsigned32/magnitude_integer; out-of-C-range behavior is project policy, not a new language guarantee.'],old256=dict(rows=256,source_set_matches_V164=True,all_raw_outputs_correct_under_independent_oracle=True,candidate_faster_correct_Qfplib=256,instruction_groups=[dict(candidate=k[0],baseline=k[1],Qfplib=k[2],cases=v)for k,v in sorted(counts.items())],two_path_representatives_replayed=speed),independent_replay=dict(inputs=len(jobs),ARM_calls=calls,wrong=0,SIO_states=['READY','READY|DIRTY'],zero_candidate_memory_writes=True,ABI_SP_R4_R11='PASS via unchanged pinned Machine',oracle='Host int(exact binary64) truncation plus explicit NaN/negative/overflow project policy, independent of producer integer-bit/MPFR implementation',samples_sha256=sha(OUT/'ARM-samples.json')),M4_soft_hard_generic_M0_allocated_controls='Assembly+C++ identical',linked_direct_BL_calls_verified=19,blockers=[],limitations=['This80B delta only; no47966-case rerun or unrelated math/framework expansion.','Instruction counts are not physical cycles; production integration/full firmware size/cache/IRQ/platform acceptance remain open.','The56 wrong Qfplib results in the wider author corpus are retained; no all-input speed theorem or complete library goal claim.','No hardware/Flash/Git/canonical/source or new numeric version changed.'],helpers=expected_helpers,baseline_ELF_sha256=sha(ELF),ROM_sha256=sha(ROM),reference_ELF_sha256=sha(REF),device_accessed=False)
with(OUT/'receipt.json').open('x')as f:f.write(json.dumps(report,indent=2)+'\n')
print(json.dumps(dict(status=report['status'],inputs=len(jobs),ARM_calls=calls,old256_verified=True,receipt_sha256=sha(OUT/'receipt.json'))))
