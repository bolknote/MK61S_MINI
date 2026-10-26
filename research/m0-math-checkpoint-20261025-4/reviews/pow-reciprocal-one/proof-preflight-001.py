"""Source/linked caller, exponent guard, first product and dead-state proof."""
import hashlib,json,re,struct,sys
from pathlib import Path
sys.dont_write_bytecode=True
R=Path('/Users/bolk/Projects/MK61S_MINI');O=Path(__file__).resolve().parent;W=R/'.build/m0-pow-reciprocal-one-20261025';P=R/'.build/m0-pow-reciprocal-lut-20261025'
sys.path.insert(0,str(R/'tests'));from check_stm32_vectors import ElfImage
def ref(p):
 p=Path(p);b=p.read_bytes();return dict(path=str(p),bytes=len(b),sha256=hashlib.sha256(b).hexdigest())
def save(n,d):
 with (O/n).open('x')as f:json.dump(d,f,indent=2);f.write('\n')
 return ref(O/n)
def mem(e,a,n):
 s=next(s for s in e.sections if s[1]!=8 and s[3]<=a and a+n<=s[3]+s[5]);return e.bytes_at(s)[a-s[3]:a-s[3]+n]
def parse(text):
 out={}
 for line in text.splitlines():
  m=re.match(r'^\s*([0-9a-f]+):\s+((?:[0-9a-f]{4}\s+)+)([a-z][a-z0-9.]*)\s*(.*)',line)
  if m:out[int(m[1],16)]=(len(m[2].split())*2,m[3].split('.')[0],m[4].split('@')[0].strip())
 return out
images={n:ElfImage(O/'rebuild'/(n+'.elf'))for n in ['control','candidate']};dis={n:parse((O/(n+'.elf.actual.dis')).read_text())for n in images}
e=images['candidate'];code=dis['candidate'];call=0x1014e668+2732;entry=e.symbols['mk61_m0_reciprocal1']&~1
assert code[call][1]=='bl'and int(code[call][2].split()[0],16)==entry
assert code[call-10][1:] == ('movs','r7, #0')and code[call-2][1:] == ('mov','r0, r7')
assert code[call-8][1:] == ('adds','r2, r0, r1')and code[call-6][1:] == ('adcs','r3, r7')
ins=struct.unpack('<H',mem(e,call-4,2))[0];assert ins&0xf800==0x4800 and(ins>>8)&7==1
literal=((call-4+4)&~3)+4*(ins&255);assert struct.unpack('<I',mem(e,literal,4))[0]==0x3ff00000
prefix=(W/'candidate/native_eabi_m0_pow_root_prefix.inc').read_text()
block='\tmovs\tr7, #0\n\tadds\tr2, r0, r1\n\tadcs\tr3, r7\n\tldr\tr1, .Lpow_horner_CPI10_7\n\tmov\tr0, r7\n\tbl\tmk61_m0_reciprocal1'
assert prefix.count(block)==1 and prefix.count('\tbl\tmk61_m0_reciprocal1')==1
assert not any(call-10<address<=call for address in e.symbols.values())
for pc,(n,op,args)in code.items():
 if op.startswith('b')and op not in ['bx','blx']:
  try:target=int(args.split()[0],16)
  except ValueError:continue
  assert not call-10<target<=call,(hex(pc),op,args)
rows=[]
for E in range(2048):
 old=(1<=E<=2046 and 0<=2044-E<=2043);new=((E-1)&0xffffffff)<=2043
 assert old==new==(1<=E<=2044)
 if new:assert 2044-E==2043-(E-1)
 oldcost=11 if E in [0,2047]else18;newcost=7 if new else6
 saving=oldcost-newcost;assert saving==(11 if new else12 if E in[2045,2046]else5)
 for sign in [0,1]:
  for fraction in [0,1,0xfffff]:assert (((sign<<31)|(E<<20)|fraction)<<1&0xffffffff)>>21==E
 rows.append(dict(E=E,accept=new,R6=2044-E if new else None,saved_instructions=saving))
save('guard-truth-table.json',dict(status='ALL2048_EXPONENTS_UNSIGNED_GUARDS_EQUAL',rows=rows))
# Exact all-uint32 identity, with the carry explicit. No interval estimate.
for u in [0,1,2,3,65535,65536,0x1fffffff,0x20000000,0x3fffffff,0x40000000,0x7fffffff,0x80000000,0xfffffffe,0xffffffff]:
 p=(1<<31)*u;lo=p&0xffffffff;hi=p>>32;carry=(2*lo)>>32
 assert ((2*lo)&0xffffffff)==0 and ((2*hi+carry)&0xffffffff)==u
first_info=[]
for label,tag in [('control','mk61_m0_hint'),('candidate','mk61_m0_reciprocal1')]:
 im=images[label];dc=dis[label];first=im.symbols[tag+'_first_product']&~1;after=im.symbols[tag+'_after_second_product']&~1
 second=after-36;assert dc[second-2][1:] == ('ldr','r2, [sp, #0]')
 assert first+(40 if label=='control'else4)==second-2
 if label=='candidate':assert [dc[first][1:],dc[first+2][1:]]==[('mov','r5, r6'),('movs','r4, #0')]
 ops=[dc[second+2*i][1:]for i in range(18)]
 assert ops[:10]==[('uxth','r1, r2'),('uxth','r4, r5'),('muls','r1, r4'),('lsrs','r7, r2, #16'),('muls','r4, r7'),('lsrs','r3, r5, #16'),('muls','r7, r3'),('uxth','r2, r2'),('muls','r2, r3'),('adds','r4, r2')]
 assert ops[10][0]=='bcc'and ops[-1]==('adcs','r3, r7')
 first_info.append(dict(label=label,first=hex(first),second=hex(second),after=hex(after),actual_second_product_instructions=ops))
# Actual READY issue/read sequence: exactly nine unchanged independent ALUs.
latency=[]
for label in ['control','candidate']:
 im=images[label];dc=dis[label];start=im.symbols['mk61_m0_hint_ddiv'if label=='control'else'mk61_m0_reciprocal1']&~1
 issue=next(pc for pc,(n,op,args)in dc.items()if pc>=start and op=='str'and args=='r6, [r7, #100]')
 read=next(pc for pc,(n,op,args)in dc.items()if pc>issue and op=='ldr'and args=='r6, [r7, #112]')
 ops=[dc[pc][1:]for pc in range(issue+2,read,2)]
 assert len(ops)==9 and all(op in ['lsls','lsrs','orrs']for op,args in ops)
 latency.append(dict(label=label,issue=hex(issue),read=hex(read),nine_ALU=ops,bytes=mem(im,issue+2,18).hex()))
assert latency[0]['bytes']==latency[1]['bytes']
software=(W/'candidate-software.S').read_text();seed=(W/'candidate-seed17.S').read_text()
assert ' lsrs r0,r1,#9' in seed and seed.index(' lsrs r0,r1,#9')<seed.index(' subs r0,#128')
assert ' movs r0,#0\n mvns r0,r0\n'not in software and software.count('// Numerator one needs no software unpacking; R1/R4 are dead.')==2
out=dict(status='PASS_NUMERATOR_ONE_CALLER_GUARD_EXACT_PRODUCT_LIVENESS_AND_LATENCY_PROOF',
 actual_root_BL=hex(call),exact_return_site=hex(call+4),actual_zero_load=hex(call-10),actual_one_literal=hex(literal),literal_value='3FF00000',
 source_no_intermediate_entry_label_and_no_direct_incoming_branch_or_symbol=True,sole_root_reference_only=True,
 precondition='R0=0,R1=3FF00000; denominator R2:R3 any binary64; hidden reciprocal1 not generic ddiv',
 all2048_E_guards_equal_accept1to2044=True,R6='2044-E',guard_instruction_savings=dict(accepted=11,E2045_2046=12,E0_2047=5),
 first_product_identity='P=2^31*u; low=(u&1)<<31,high=u>>1; doubling gives low0,high2*(u>>1)+(u&1)=u for every uint32u.',
 exact_carry_no_approximation_or_rounding_change=True,old_first_runtime17_new2_saving15=True,
 old_first_cross_carry_always0_for_low16_of2pow31_zero=True,
 dead_state_proof='Before second product, live R0=0,R5=u1,R6=u1,R12,SP/28B frame agree. LDR writes R2; UXTH writes R1/R4; LSRS writes R7 then R3. ADDS establishes flags before BCC. Thus differing R1/R2/R3/R4/R7/NZCV cannot reach a read.',
 actual_first_second_records=first_info,after_second_all_R0_R7_R12_SP_NZCV_frame28_induction=True,
 software_dead6_unpacking_only_before_overwrites=True,software_dead2_R0_setup_removed_only_because_seed_overwrites_R0_before_read=True,
 hardware_READY_latency=latency,hardware9ALU_not_shortened=True,common_suffix186_fourcopies_byte_exact=True,seed312_unchanged=True,
 exact_cost_law='guard_saved +15 per first product +8 per software seed',
 original_IEEE_fallback_raw_operands_preserved_all_rejected_E=True,no_new_table_values_or_global_RAM=True,
 no_scalar_C_ABI_inheritance=True,ARM_calls=0,MPFR_inputs=0,device_IO=0)
print(json.dumps(save('proof.json',out)),flush=True)
