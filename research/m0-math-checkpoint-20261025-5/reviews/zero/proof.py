"""Fresh register-permutation, carry/liveness and emitted-code proof."""
import hashlib,json,re,struct,sys
from pathlib import Path
sys.dont_write_bytecode=True
R=Path('/Users/bolk/Projects/MK61S_MINI');O=Path(__file__).resolve().parent;sys.path.insert(0,str(R/'tests'))
from check_stm32_vectors import ElfImage
def ref(p):
 p=Path(p);b=p.read_bytes();return dict(path=str(p),bytes=len(b),sha256=hashlib.sha256(b).hexdigest())
def mem(e,a,n):
 s=next(s for s in e.sections if s[1]!=8 and s[3]<=a and a+n<=s[3]+s[5]);return e.bytes_at(s)[a-s[3]:a-s[3]+n]
def branch(e,a,cc):
 h=struct.unpack('<H',mem(e,a,2))[0];assert h>>8==0xd0+cc;i=h&255;return a+4+2*(i-256 if i>=128 else i)
def instructions(name,a,b):
 out=[]
 for line in (O/(name+'.elf.actual.dis')).read_text().splitlines():
  m=re.match(r'^([0-9a-f]+):\s+[0-9a-f]{4}\s+([a-z][a-z0-9.]*)\s+(.*)$',line)
  if not m:continue
  pc=int(m[1],16)
  if not a<=pc<b:continue
  op=m[2];args=m[3].split('@')[0].split('<')[0].strip()
  if op.startswith('b'):
   target=int(args,16);assert a<=target<b;args='relative_'+str(target-a)
  out.append((op,args))
 return out
images={n:ElfImage(O/'rebuild'/(n+'.elf'))for n in ['control','candidate']};mapping={};prefixes=[]
for tag in ['mk61_m0_reciprocal1','mk61_m0_reciprocal1_sw']:
 c,n=images['control'],images['candidate'];sym=lambda e,s:e.symbols[tag+s]&~1
 cb,nb=sym(c,'_before_second_product'),sym(n,'_before_second_product');ca,na=sym(c,'_after_second_product'),sym(n,'_after_second_product')
 old=instructions('control',cb,ca);new=instructions('candidate',nb,na)
 renamed=[(op,re.sub(r'\br[04]\b',lambda m:'r4'if m[0]=='r0'else'r0',args))for op,args in old];assert renamed==new and ca-cb==na-nb==36
 assert mem(c,ca,16).hex()=='019c6c431b19520ed9010a434401a01a'
 nr=sym(n,'_after_y_residual');assert mem(n,na,nr-na).hex()=='019969435b18520ed9010a43a01a'
 half=sym(n,'_half_normalization');assert mem(n,half,8).hex()=='690ae8055b0a1843'and mem(c,sym(c,'_half_normalization'),2).hex()=='6400'
 cert=sym(n,'_certificate_begin');full=sym(n,'_certificate_full');up=sym(n,'_certificate_up');down=sym(n,'_certificate_down');pack=sym(n,'_pack_begin')
 assert mem(n,cert,12).hex()=='150c030c5d43641b630c9b04';prefixes.append(mem(n,cert,12))
 assert up==cert+16 and branch(n,cert+12,0)==full and branch(n,cert+14,2)==down
 assert mem(n,full,44)==mem(c,sym(c,'_certificate_full'),44)
 assert branch(n,full+44,4)==down and mem(n,full+46,2).hex()=='0026'
 assert mem(n,up,4).hex()=='01307141'and mem(c,sym(c,'_certificate_up'),6).hex()=='002201305141'
 assert mem(n,down,8)==mem(c,sym(c,'_certificate_down'),8)and mem(n,pack,16)==mem(c,sym(c,'_pack_begin'),16)
 mapping[tag]=dict(before_second=hex(nb),after_second=hex(na),after_residual=hex(nr),half=hex(half),begin=hex(cert),full=hex(full),up=hex(up),down=hex(down),pack=hex(pack))
u=ElfImage(O/'rebuild/unit/candidate.elf');start=u.symbols['unit_certificate_begin']&~1;prefixes.append(mem(u,start,12));assert len(set(prefixes))==1
mapping['unit']=dict(begin=hex(start),up=hex(start+16),full=hex(branch(u,start+12,0)),down=hex(branch(u,start+14,2)))
parent=R/'.build/m0-pow-reciprocal-certificate-independent-20261025';receipt=json.loads((parent/'FINAL-REVIEW.json').read_text());prior=receipt['evidence']['proof.json'];assert ref(prior['path'])==prior
root=ref(R/'.build/m0-pow-reciprocal-certificate-root-acceptance-20261025-001/RECEIPT.json');assert root['sha256']=='aa392003a9237e3d945768cfd2651c9aa3d8be2746a9e5046e520e68298801ba'and root['bytes']==22999
out=dict(status='PASS_FRESH_KNOWN_ZERO_REGISTER_PERMUTATION_LIVE_FLAGS_AND_EMITTED_FALLBACK_PROOF',
 parent_universal_certificate_proof=prior,later_parent_ROOT_additive=root,
 product='At the actual positive-one second-product entry, R0=R4=0. The complete36B Thumb multiplication is exactly renamed R0<->R4, including branch predicates, from equal initial states; all other outputs and NZCV coincide.',
 xH_and_residual='R1 old product temporary is dead. LDR/MUL/ADD using R1 instead of R4 computes identical xH*a0 and R3 sum; LSLS R1,R3,7 overwrites that temporary. R4 remains0. SUBS R0,R4,R2 kills the scratch R0 and all prior NZCV; full R0-R7/R12/SP/NZCV/frame28 rejoin.',
 zero_double='R4=0 is retained through signed correction. Removing LSLS R4,1 is safe: the next LSRS R1,R5,9 overwrites NZC before any consumer; V was not changed by the removed shift.',
 certificate='Only scratch R6->R3 changes. Every scratch read follows its definition. The same uint32 bound E=[0,131071], inclusive two signed discontinuity bands and complete full-product fallback apply. Emitted12B prefix is exact register renaming.',
 generic_R6_contract='ARBITRARY R6 survives every decisive shared macro branch, not merely the private zero case. Full multiplication may clobber R6; no generic full-path preservation claim.',
 positive_ADC='Existing MOVS R6,0 before quotient rounding still executes. Decisive certificate never writes R6; ADD R0,1 sets carry before ADC R1,R6. The removed MOVS R2,0 has no remaining reader: down shift defines R2 before ORR and pack defines it again.',
 full_path='Restore modular base, execute identical44B complete product/borrow/CMP prefix. BMI goes directly down; positive path explicitly MOVS R6,0 then branches up before ADC. R3 scratch is overwritten before its first old full-product use.',
 pack='Down shifts and16B pack unchanged. Only dead R3/R6 differ; R0/R1/R2/R4/R5/R7/R12/SP/NZCV and frame are projected equally before pack; all saved R4-R7 restored.',
 no_unchanged186B_suffix_claim=True,positive_one_precondition_not_generic_C_ABI=True,
 source_reverse_binding_not_used_as_only_equivalence_proof=True,mapping=mapping,
 exact_lossless_RNE_and_IEEE_guards_precision_inherited_by_full_source_proof=True,
 performance='Only deletes second-product reconstruction, zero doubling, decisive-positive zero MOV; full-positive zero restore replaces old zero MOV. No instruction path gains cost relative to immediate Certificate, but Certificate ancestral regressions persist.',
 parent32_public_regressions_and2_already_losing_not_erased=True,performance_adoption_GO=False,ARM_calls=0,MPFR_inputs=0,devices=0)
with(O/'proof.json').open('x')as f:json.dump(out,f,indent=2);f.write('\n')
print(json.dumps(ref(O/'proof.json')),flush=True)
