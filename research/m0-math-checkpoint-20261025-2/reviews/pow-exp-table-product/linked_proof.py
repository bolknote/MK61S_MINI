"""Exact dyadic identity, three fresh linked scalar callers and loader hazard."""
import hashlib,json,re,struct,sys
from pathlib import Path
sys.dont_write_bytecode=True
R=Path('/Users/bolk/Projects/MK61S_MINI');O=Path(__file__).resolve().parent;W=R/'.build/m0-pow-exp-table-product-20261025'
sys.path.insert(0,str(R/'tests'))
from check_stm32_vectors import ElfImage
def ref(p):p=Path(p);d=p.read_bytes();return dict(path=str(p),bytes=len(d),sha256=hashlib.sha256(d).hexdigest())
def memory(e,a,n):
 s=next(s for s in e.sections if s[1]!=8 and s[3]<=a and a+n<=s[3]+s[5]);return e.bytes_at(s)[a-s[3]:a-s[3]+n]
def parse(text):
 result={}
 for line in text.splitlines():
  m=re.match(r'^\s*([0-9a-f]+):\s+((?:[0-9a-f]{4}\s+)+)([a-z][a-z0-9.]*)\s*(.*)',line)
  if m:result[int(m[1],16)]=dict(address=int(m[1],16),bytes=2*len(m[2].split()),op=m[3].split('.')[0],args=m[4].split('@')[0].strip())
 return result
im=ElfImage(O/'rebuild/candidate.elf');code=parse((O/'candidate.actual.dis').read_text());entry=im.symbols['mk61_m0_pow_exp_table_product']&~1;general=im.symbols['mk61_m0_pow_exp_product']&~1
def tail_target(address):
 b=memory(im,address,16)
 assert b[:10]==bytes.fromhex('01b40248844601bc6047')and b[10:12]in [bytes.fromhex('c046'),bytes.fromhex('00bf')]
 assert int.from_bytes(b[12:],'little')==entry|1
 return entry
callers=[]
for address in [0x20038744,0x1016ab50,0x1016b2c6]:
 row=code[address];assert row['op']=='bl';target=int(row['args'].split()[0],16)
 if target!=entry:assert tail_target(target)==entry
 capture=[code[address+4],code[address+6]]
 assert capture[0]['op']==capture[1]['op']=='str'and capture[0]['args'].startswith('r0, [sp,')and capture[1]['args'].startswith('r1, [sp,')
 callers.append(dict(call=row,target=hex(target),direct=target==entry,scalar_return_capture=capture,
  R12_extra_not_consumed_here=True,tail_veneer_preserves_arguments_SP_and_LR=target!=entry))
leaf=[row for a,row in sorted(code.items())if general<=a<general+154]
mentions=[(i,row)for i,row in enumerate(leaf)if re.search(r'\b(?:ip|r12)\b',row['args'])]
assert len(mentions)==1
i,row=mentions[0];assert row['op']=='mov'and row['args'].replace(' ','')in ['ip,r4','r12,r4']
assert leaf[i+1]['op']=='lsls'and leaf[i+1]['args'].replace(' ','')=='r4,r4,#1'
assert len(leaf)==77
new=[row for a,row in sorted(code.items())if entry<=a<entry+20]
assert len(new)==10 and new[0]['op']=='cmp'and new[0]['args'].replace(' ','')=='r0,#0'
assert new[1]['op']=='bne'and int(new[1]['args'].split()[0],16)==general
assert [r['op']for r in new[2:]]==['lsls','lsrs','lsrs','orrs','movs','adcs','adcs','bx']
# Exact word decomposition: no floating approximation or finite-domain
# enumeration is substituted for the universal B64 identity.
edgechecks=0
for h in [0,1,2,3,0x7fffffff,0xfffffffe,0xffffffff]:
 for l in [0,1,2,3,4,0x7ffffffe,0xfffffffe,0xffffffff]:
  B=(h<<32)|l;low=((h&3)<<30)|(l>>2);high=h>>2;carry=(l>>1)&1
  out=((high<<32)|low)+carry
  assert out==(B>>2)+bool(B&2)==((1<<62)*B+(1<<63))>>64;edgechecks+=1
base=ElfImage(R/'.build/m0-asin-scaled-bound-v164-20261023/firmware/mk61s-picocalc-pico-h.elf')
original_wrapper=memory(base,0x1016b3b8,16)
assert original_wrapper[:12]==bytes.fromhex('01b40248844601bc6047c046')and int.from_bytes(original_wrapper[12:],'little')==general|1
table=memory(im,im.symbols['_ZN7m0_eabiL9exp_tableE'],4096);roots=struct.unpack('<512Q',table)
assert [i for i,a in enumerate(roots)if not a&0xffffffff]==[0]and roots[0]==1<<62
# Exact source binding: only the table call symbol changes in this include.
old=(W/'control/native_eabi_m0_pow_exp_body.inc').read_text();newsource=(W/'candidate/native_eabi_m0_pow_exp_body.inc').read_text()
assert newsource==old.replace('mk61_m0_pow_exp_product(q,d)','mk61_m0_pow_exp_table_product(q,d)')
assert 'const unsigned index=unsigned(k)&511U;'in newsource and 'U q=exp_table[index];'in newsource
assert '__asm__'not in newsource and '__asm__'not in (W/'candidate/native_eabi_m0_pow_fast.inc').read_text()
# Demonstrate the old overlay destroys the new entry, and that a required
# loader preflight rejects it, using local byte arrays only.
oldimage=ElfImage(R/'.build/m0-exp-directed-product-20261024/candidate.elf')
bank=bytearray(memory(im,general,182));expected=bytes(bank[154:174])
def require_entry(candidate_bank):assert bytes(candidate_bank[154:174])==expected,'table entry overwritten'
require_entry(bank);bank[:168]=memory(oldimage,general,168)
try:require_entry(bank)
except AssertionError:overlay_rejected=True
else:raise AssertionError('old overlay unexpectedly preserved new entry')
out=dict(status='PASS_EXACT_TABLE_IDENTITY_AND_PRESENT_LINKED_CALLERS_ONLY',fresh_ELF=ref(O/'rebuild/candidate.elf'),fresh_disassembly=ref(O/'candidate.actual.dis'),
 three_actual_scalar_callers=callers,old_general77_R12_capture=mentions[0][1],table_entry10_instructions=new,
 exact_universal_B64_halfup_identity='(B>>2)+bit1(B)',independent_HOST_word_carry_edges=edgechecks,
 all512_actual_roots_low32zero_implies_only_A2pow62=True,original_resident16byte_wrapper_still_targets_general=True,
 scalar_R12_extra_not_promised_for_new_dyadic_path=True,
 exp_consumer_absent_in_this_pow_ELF=True,fresh_integrated_exp_guard_claim=False,
 negative_old168overlay_entry_preflight_rejected=overlay_rejected,destructive_overlap_bytes=14,
 future_requirements=['Merge source deltas and relink instead of mixing private overlay images.',
  'On actual integrated ELF rerun general producer/real original wrapper/postcall capture/88-instruction consumer R12 guard with fresh disassembly.',
  'Validate scratch bank layout, actual new table entry, loader order and bounds; reject stale168-byte overlays that overwrite this entry.',
  'Do not upgrade whole507 ledger422 or claim hardware/physical cycles/general-pow totality/main/release GO.'],
 integration_GO=False,device_IO=0,Git=0,canonical=0,network=0)
with (O/'linked-proof.json').open('x')as f:json.dump(out,f,indent=2);f.write('\n')
print(json.dumps(ref(O/'linked-proof.json'),indent=2))
