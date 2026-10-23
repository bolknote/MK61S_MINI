"""One-off review/replay of the exact mixed-sign delta, no new test framework."""
import datetime,hashlib,json,math,struct,sys
from fractions import Fraction
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];OUT=Path(__file__).resolve().parent
P=ROOT/'.build/m0-mixed-sign-original-goal-20261023';V=ROOT/'.build/m0-asin-scaled-bound-v164-20261023';Q=ROOT/'.build/m0-float-fma-qualification-20261023';H=Q/'support'
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
assert sha(P/'HANDOFF.md')=='67b94bd5e403cd3a0ab82f708da2f5eeaf85e79934fd1232b1c343ac4ff91e5c'
assert sha(P/'result.json')=='5b1fa3434b9bd887115a2e00926ae48ec8d924d382c6926d9f06a15fdf8a83d5'
result=json.loads((P/'result.json').read_text())
for n,d in result['artifacts'].items():assert sha(P/n)==d['sha256'] and (P/n).stat().st_size==d['bytes']
baseline=V/'source/code/native_eabi_m0_rp2040.S';ELF=V/'firmware/mk61s-picocalc-pico-h.elf';ROM=ROOT/'research/rp2040-memset-2026-10-21/capture/bootrom.bin';REF=ROOT/'.build/m0-v138-execution-20261023/reference/reference.elf'
assert sha(baseline)=='8d158f7ca11db44245fa4bc9dbb24a5906c09a773037abba78247e06b8be2212'
assert sha(ELF)=='3b92d7dc30cc860c0b1f17943f1cd626f94112a98adaf165ec4f9cd300364db1'
assert sha(ROM)=='ef07d54bdd259c7858483606118a3c704976801823c38ac5a2fcdffacd2d83fe'
reference_manifest=ROOT/'.build/m0-v138-execution-20261023/execution-manifest.json'
assert sha(reference_manifest)=='fd584f3e2b9a1387ff236eabdac66b888c452b16cb73c21449c6cb0b8262b18c'
assert sha(REF)==json.loads(reference_manifest.read_text())['flash_addon']['elf_sha256']=='b66da3a6805ecd110580e6dd281e17c37bc4399bee0ba1fae86f8c8cf78bfc26'
expected_helpers={'native_eabi_m0_arm_self_test.py':'cdc8ac6c98bad5db3539a494207c556ce4ae49146c8a76b88cf58c4a5c79bee3','check_stm32_vectors.py':'360413d0e17fd36154f91d53a83ea40e19326c7cde041a48a71b3d92748a7708'}
for n,h in expected_helpers.items():assert sha(H/n)==h
sys.path[:0]=[str(H)];from check_stm32_vectors import ElfImage
from native_eabi_m0_arm_self_test import Machine,SP
# Check all source outside the one replaced block without relying on the
# producer's object summary.
old=baseline.read_text();new=(P/'native_eabi_m0_rp2040.S').read_text();label='.Lda_mixed_general:';end='mk61_m0_dadd_end:'
assert old.split(label)[0]==new.split(label)[0]
assert old.split(end,1)[1]==new.split(end,1)[1]
co,ca=ElfImage(P/'control-full.o'),ElfImage(P/'candidate-full.o')
def allocated(e):return {n:(s[1],s[5],e.bytes_at(s) if s[1]!=8 else b'')for n,s in e.named_sections.items() if s[2]&2}
ao,an=allocated(co),allocated(ca);changed=[n for n in ao if ao[n]!=an[n]];assert set(ao)==set(an) and changed==['.text.mk61_rp2040_arithmetic']
oldend,newend=co.symbols['mk61_m0_dadd_end'],ca.symbols['mk61_m0_dadd_end'];assert (oldend,newend)==(764,648)
assert ao[changed[0]][2][oldend:]==an[changed[0]][2][newend:]
diag=ElfImage(P/'candidate.elf');binary=(P/'candidate.bin').read_bytes();linked=diag.bytes_at(diag.named_sections['.text']);public=an[changed[0]][2][:648]
assert len(binary)==648 and binary==linked and public[:2]+public[6:]==binary[:2]+binary[6:]
assert ca.symbols['__aeabi_dadd']==diag.symbols['candidate_dadd']-0x10180000 and ca.symbols['__aeabi_dsub']==diag.symbols['candidate_dsub']-0x10180000
rel=ca.named_sections['.rel.text.mk61_rp2040_arithmetic'];rels=[struct.unpack_from('<2I',ca.bytes_at(rel),i)for i in range(0,rel[5],8)];active=[r for r in rels if r[0]<648];assert len(active)==1 and active[0][0]==2
symtab=ca.sections[rel[6]];sym=struct.unpack_from('<IIIBBH',ca.bytes_at(symtab),(active[0][1]>>8)*16);strings=ca.bytes_at(ca.sections[symtab[6]]);name=strings[sym[0]:strings.index(b'\0',sym[0])].decode();assert name=='mk61_m0_dadd_slow'
h1,h2=struct.unpack_from('<2H',binary,2);sg=(h1>>10)&1;i1=1^((h2>>13)&1)^sg;i2=1^((h2>>11)&1)^sg;offset=(sg<<24)|(i1<<23)|(i2<<22)|((h1&1023)<<12)|((h2&2047)<<1);offset-= (1<<25)if sg else 0
target=0x10180000+2+4+offset;base=ElfImage(ELF);assert target==base.symbols['mk61_m0_dadd_slow']&~1
contexts=[]
for n in ['M4_soft','M4_hard','generic_M0']:
 a,b=ElfImage(P/(n+'-control.o')),ElfImage(P/(n+'-candidate.o'));assert allocated(a)==allocated(b);assert sum(s[1]for s in allocated(a).values())==0;contexts.append(n)
# Independent oracle: exact Fraction sum followed by CPython's correctly
# rounded rational-to-binary64 conversion. No producer integer/MPFR code used.
SIGN=1<<63;MASK=SIGN-1;INF=0x7ff0000000000000
def bits(x):return struct.unpack('<Q',struct.pack('<d',x))[0]
def value(x):return struct.unpack('<d',struct.pack('<Q',x))[0]
def rational(x):
 e=(x>>52)&2047;n=(x&((1<<52)-1))|((1<<52)if e else 0);scale=(e if e else 1)-1075;n=-n if x&SIGN else n
 return Fraction(n<<scale,1)if scale>=0 else Fraction(n,1<<-scale)
def oracle(op,a,b):
 if op=='dsub':b^=SIGN
 if (a&MASK)>=INF or (b&MASK)>=INF:return bits(value(a)+value(b))
 total=rational(a)+rational(b)
 if not total:return (a&b)&SIGN if not(a&MASK)and not(b&MASK)else 0
 try:return bits(float(total))
 except OverflowError:return (SIGN if total<0 else 0)|INF
def equal(a,b):return bool((a&MASK)>INF and a&(1<<51))if(b&MASK)>INF else a==b
jobs=[]
def mixed(e,d,fa,fb):
 a=(e<<52)|fa;b=((e-d)<<52)|fb
 for x,y in [(a,b|SIGN),(b|SIGN,a),(a|SIGN,b),(b,a|SIGN)]:jobs.extend([('dadd',x,y),('dsub',x,y^SIGN)])
for d in [2,3,31,32,33,52,53,54]:
 for fa,fb in [(0,0),(1,(1<<52)-1),((1<<52)-1,1)]:mixed(1023,d,fa,fb)
for e in [55,2045]:
 for d in [2,32,54]:mixed(e,d,0,(1<<52)-1)
for d in [0,1,55,56]:mixed(1023,d,0,1)
for e in [54,2046]:mixed(e,2,1,1)
for a,b in [(0,SIGN),(SIGN,SIGN),(1,0x0010000000000000),(INF,INF|SIGN),(INF|1,0x3ff0000000000000),(0x7fefffffffffffff,0x7fefffffffffffff)]:jobs.extend([('dadd',a,b),('dsub',a,b)])
known=[r for r in json.loads((V/'slower-inputs.json').read_text())['rows']if r['operation']in ['dadd','dsub']];assert len(known)==17
knownkeys={(r['operation'],int(r['x'],16),int(r['y'],16))for r in known};jobs=list(dict.fromkeys(jobs+list(knownkeys)))
m=Machine(ELF,True,stack_bytes=4096,bootrom=ROM);ref=Machine(REF,True,stack_bytes=4096)
m.uc.mem_write(0x10180000,binary)
for n in ['candidate_dadd','candidate_dsub']:m.elf.symbols[n]=diag.symbols[n]
states=[struct.pack('<7I',17,3,17,3,5,2,csr)for csr in [1,3]];rows=[];speeds=[];calls=0
for op,a,b in jobs:
 expected=oracle(op,a,b)
 for state in states:
  out={};counts={}
  for label,n,machine in [('candidate','candidate_'+op,m),('baseline','__aeabi_'+op,m)]+([('Qfplib','qfp_'+op,ref)]if(op,a,b)in knownkeys else []):
   machine.uc.mem_write(0xd0000060,state);got,_,count=machine.call(n,a,b,count=(op,a,b)in knownkeys);calls+=1
   assert bytes(machine.uc.mem_read(0xd0000060,28))==state
   assert equal(got,expected),(label,op,hex(a),hex(b),hex(got),hex(expected));out[label]=f'{got:016X}';counts[label]=count
  rows.append(dict(operation=op,x=f'{a:016X}',y=f'{b:016X}',SIO_CSR=struct.unpack_from('<I',state,24)[0],expected=f'{expected:016X}',outputs=out))
  if(op,a,b)in knownkeys:
   assert counts['candidate']<counts['Qfplib'];speeds.append(dict(operation=op,x=f'{a:016X}',y=f'{b:016X}',SIO_CSR=struct.unpack_from('<I',state,24)[0],instruction_counts=counts))
for n,d in result['artifacts'].items():assert sha(P/n)==d['sha256']
report=dict(status='MIXED_SIGN_DELTA_TECHNICAL_GO_NOT_PRODUCTION',recorded_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),source_patch_sha256=sha(P/'mixed-sign-only.patch'),HANDOFF_sha256=sha(P/'HANDOFF.md'),producer_result_sha256=sha(P/'result.json'),candidate_source_sha256=sha(P/'native_eabi_m0_rp2040.S'),candidate_ELF_sha256=sha(P/'candidate.elf'),candidate_bin_sha256=sha(P/'candidate.bin'),baseline_ELF_sha256=sha(ELF),helpers=expected_helpers,ROM_sha256=sha(ROM),reference_ELF_sha256=sha(REF),allocated_object_isolation=dict(old_block=764,new_block=648,only_section_changed=changed,remaining_multiply_divide_bytes_identical=True,no_new_BSS_or_rodata=True,unchanged_zero_allocated_contexts=contexts),body_binding=dict(full_source_public_prefix_matches_648_executed_bytes_except_single_BL=True,public_entry_offsets_match=True,relocation_offset=2,relocation_symbol=name,linked_original_fallback=hex(target)),mathematical_review=['Entry guards retain normal operands/max_exponent55..2045; mixed near cancellation handles gaps0/1; changed branch sees2..54.','For2<=d<=54,2^51<M-N/2^d<2^53; at most one normalization shift and larger exponent fixes sign.','Far jam preserves the side of all even-integer midpoint boundaries (2^30/2^31) and normalization boundary; exact remainder retains tie information.','NEG carry gives correct fractional borrow, SBC propagates through64 retained bits; one shift carries the fractional limb. Guard/sticky increment plus clearLSB on exact tie implements RNE, including binade carry.'],independent_replay=dict(unique_inputs=len(jobs),ARM_calls=calls,wrong=0,SIO_states=['READY','READY|DIRTY'],R4_R11_SP_and_stack_write_guard='PASS via unchanged pinned Machine',oracle='Own exact Fraction sum and independent CPython rational-to-double RNE; quiet NaN class policy for IEEE controls',actual_ROM_initializers=m.rom_initializers,rows=rows,known17_instruction_comparisons=speeds),blockers=[],limitations=['Finite delta validation; no all-input correctness/speed proof or general goal completion.','No physical cycles/cache/IRQ/whole-platform acceptance; no firmware or production integration GO.','1766 inherited targeted slow-correct-Qfplib cases and all other cold/fallback deficits remain as producer reports; general pow trap unchanged.','Unchanged V164 certificates reused, no10807/fullmatrix replay; fullsource/SIO/ABI scope is this648B arithmetic block and its unchanged fallback binding.'],mutations=dict(own_review_files_only=True,frozen_canonical_Git_USB_lease_or_firmware_changed=False))
with(OUT/'receipt.json').open('x')as f:f.write(json.dumps(report,indent=2)+'\n')
print(json.dumps(dict(status=report['status'],independent_inputs=len(jobs),ARM_calls=calls,known_slower_inputs_now_faster=len(knownkeys),receipt_sha256=sha(OUT/'receipt.json'))))
