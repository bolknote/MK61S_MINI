"""Required closure of the private R12 result in the actual release object.

The scalar C ABI does not describe this extra result. Acceptance therefore
requires the linked producer/wrapper/capture dataflow proved here, not a
compiler-independent assertion about a C++ call. The zero-byte source marker
locates the asm output definition without adding a synthetic timed veneer.
"""
from pathlib import Path
import hashlib,json,re,subprocess,sys
sys.dont_write_bytecode=True
W=Path(__file__).resolve().parent;ROOT=W.parents[1]
sealed=(W/'FROZEN.json').exists()
P=ROOT/'.build/m0-asin-scaled-bound-v164-20261023'
sys.path.insert(0,str(ROOT/'tests'))
from check_stm32_vectors import ElfImage
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
b=json.loads((W/'build.json').read_text());cc=Path(b['commands'][0][0]).parent
assert sha(W/'candidate.elf')==b['candidate_ELF_sha256']
assert sha(W/'candidate/native_eabi_m0.cpp')==b['source_sha256']
im=ElfImage(W/'candidate.elf');base=ElfImage(P/'firmware/mk61s-picocalc-pico-h.elf')
start=im.symbols['mk61_m0_exp']&~1;end=start+im.sizes['mk61_m0_exp']
marker=im.symbols['mk61_m0_exp_fraction_capture']&~1
wrapper=im.symbols['mk61_m0_pow_exp_product_flash']&~1
ram=im.symbols['mk61_m0_pow_exp_product']&~1
assert start<=marker<end
def parse(text):
 out={}
 for line in text.splitlines():
  m=re.match(r'^\s*([0-9a-f]+):\s+((?:[0-9a-f]{4}\s+)+)([a-z][a-z0-9.]*)\s*(.*)',line)
  if not m:continue
  address=int(m[1],16);halfwords=m[2].split()
  out[address]=dict(address=address,bytes=2*len(halfwords),mnemonic=m[3].split('.')[0],operands=m[4].split('@')[0].strip(),line=line.strip())
 return out
fresh_disassembly=subprocess.check_output([str(cc/'arm-none-eabi-objdump'),'-dr',str(W/'candidate.elf')],text=True)
if sealed:assert (W/'candidate.dis').read_text()==fresh_disassembly
else:(W/'candidate.dis').write_text(fresh_disassembly)
code=parse(fresh_disassembly);body={a:r for a,r in code.items() if start<=a<end}
calls=[r for r in body.values() if r['mnemonic']=='bl' and re.match(r'^[0-9a-f]+',r['operands']) and int(r['operands'].split()[0],16)==wrapper]
assert len(calls)==1,calls
entry=calls[0]['address']+calls[0]['bytes'];pending=[entry];visited=set();paths=[]
while pending:
 address=pending.pop()
 if address==marker:continue
 assert address in body,('capture not reached within public function',hex(address))
 if address in visited:continue
 visited.add(address);r=body[address];op=r['mnemonic'];operands=r['operands']
 assert not re.search(r'\b(?:ip|r12)\b',operands),('private result touched before marker',r)
 assert op not in ('bl','blx','bx'),('call/return before marker',r)
 assert not(op=='pop' and re.search(r'\bpc\b',operands)),r
 assert not re.match(r'pc\b',operands),r
 nxt=address+r['bytes']
 if op=='b':
  target=int(operands.split()[0],16);pending.append(target);paths.append([address,target])
 elif op.startswith('b') and op in ('beq','bne','bcs','bcc','bhs','blo','bmi','bpl','bvs','bvc','bhi','bls','bge','blt','bgt','ble'):
  target=int(operands.split()[0],16);pending.extend((target,nxt));paths.extend(([address,target],[address,nxt]))
 else:pending.append(nxt);paths.append([address,nxt])
assert paths and any(marker in edge for edge in paths)
adjacency={}
for x,y in paths:adjacency.setdefault(x,[]).append(y)
finished=set();active=set()
def acyclic(address):
 if address==marker or address in finished:return
 assert address not in active,('cycle before capture',hex(address))
 active.add(address)
 for target in adjacency[address]:acyclic(target)
 active.remove(address);finished.add(address)
acyclic(entry)

size=base.sizes['mk61_m0_pow_exp_product_flash'];assert size==16
cmd=[str(cc/'arm-none-eabi-objdump'),'-d','--start-address='+hex(wrapper),'--stop-address='+hex(wrapper+size),str(P/'firmware/mk61s-picocalc-pico-h.elf')]
text=subprocess.check_output(cmd,text=True)
if sealed:assert (W/'private-wrapper.dis').read_text()==text
else:(W/'private-wrapper.dis').write_text(text)
wrap=parse(text);assert wrap
section=next(s for s in base.named_sections.values() if s[3]<=wrapper<s[3]+s[5])
raw=base.bytes_at(section)[wrapper-section[3]:wrapper-section[3]+size]
# This is the existing real Flash-to-RAM tail veneer, not another caller.
# It saves/restores argument r0 and SP, then BXes to the RAM producer without
# changing LR. The producer therefore returns directly to the original caller;
# no code can overwrite its extra R12 result on a return through this veneer.
assert raw[:12]==bytes.fromhex('01b40248844601bc6047c046')
assert raw[12:]==(ram|1).to_bytes(4,'little')
leaf=[r for a,r in code.items() if ram<=a<ram+im.sizes['mk61_m0_pow_exp_product']]
mentions=[(n,r) for n,r in enumerate(leaf) if re.search(r'\b(?:ip|r12)\b',r['operands'])]
assert len(mentions)==1 and mentions[0][1]['mnemonic']=='mov'
n,r=mentions[0];assert re.fullmatch(r'(?:ip|r12),\s*r4',r['operands'])
assert leaf[n+1]['mnemonic']=='lsls' and leaf[n+1]['operands'].replace(' ','')=='r4,r4,#1'
assert all(r['mnemonic'] not in ('bl','blx','bx','b') for r in leaf)
# Close the compiler-defined R12 value through its actual first MOV to a
# low register, on every path capable of reaching that consumer.
consumer=next(a for a,r in body.items() if a>=marker and r['mnemonic']=='mov'
              and re.fullmatch(r'r[0-7],\s*(?:ip|r12)',r['operands']))
conditional={'beq','bne','bcs','bcc','bhs','blo','bmi','bpl','bvs','bvc','bhi','bls','bge','blt','bgt','ble'}
def live_range(instructions):
 edges={}
 for a,r in instructions.items():
  op=r['mnemonic'];args=r['operands'];nxt=a+r['bytes']
  if op=='b':targets=[int(args.split()[0],16)]
  elif op in conditional:targets=[int(args.split()[0],16),nxt]
  elif op=='bx' or (op=='pop' and re.search(r'\bpc\b',args)):targets=[]
  else:targets=[nxt]
  edges[a]=[t for t in targets if t in instructions]
 rev={}
 for a,targets in edges.items():
  for t in targets:rev.setdefault(t,[]).append(a)
 def reach(first,graph):
  seen=set();pending=[first]
  while pending:
   a=pending.pop()
   if a in seen:continue
   seen.add(a);pending.extend(graph.get(a,[]))
  return seen
 live=reach(marker,edges)&reach(consumer,rev)
 assert marker in live and consumer in live
 for a in live-{consumer}:
  r=instructions[a]
  assert r['mnemonic'] not in ('bl','blx','bx') and not re.search(r'\b(?:ip|r12)\b',r['operands']),(a,r)
  assert not re.match(r'pc\b',r['operands']),('unmodelled PC write in live range',a,r)
 active=set();done=set()
 def acyclic_live(a):
  if a==consumer or a in done:return
  assert a not in active,('cycle in private live range',hex(a))
  active.add(a)
  for t in edges[a]:
   if t in live:acyclic_live(t)
  active.remove(a);done.add(a)
 acyclic_live(marker)
 return live
live=live_range(body)
out=dict(status='PASS_REQUIRED_LINKED_PRIVATE_R12_RETURN_DATAFLOW',
 candidate_ELF_sha256=sha(W/'candidate.elf'),source_sha256=b['source_sha256'],
 public_function_start=hex(start),public_function_size=im.sizes['mk61_m0_exp'],
 actual_fresh_disassembly_sha256=hashlib.sha256(fresh_disassembly.encode()).hexdigest(),
 product_call=hex(calls[0]['address']),private_output_definition_marker=hex(marker),
 all_post_call_paths_reach_marker_before_R12_write_call_or_return=True,
 call_to_marker_instructions=[body[a] for a in sorted(visited)],CFG_edges=paths,
 marker_allocated_bytes=0,extra_actual_timed_veneer_or_NOP=False,
 actual_consumer=hex(consumer),marker_to_consumer_live_instructions=len(live)-1,
 all_marker_to_consumer_paths_preserve_R12_without_call_or_touch=True,
 original_wrapper_address=hex(wrapper),original_wrapper_bytes=size,original_wrapper_sha256=hashlib.sha256(raw).hexdigest(),
 wrapper_tail_jumps_actual_RAM_leaf_after_restoring_R0_and_SP=True,
 no_post_producer_wrapper_or_return_trampoline_can_clobber_R12=True,
 leaf_captures_R4_fraction_immediately_before_rounding_once=True,
 scalar_return_P_unchanged_extra_R12_is_caller_clobbered=True,
 index0_uncalled_fraction_arbitrary_but_new_gate_source_preconditions_exclude_it=True,
 compiler_and_flags_dependent_private_contract=True,
 required_again_for_every_changed_release_object_not_generic_CXX_ABI_claim=True,
 code_and_real_wrapper_only_no_firmware_execution_ROM_mocks_or_device=True)
if sealed:assert json.loads((W/'private-return-proof.json').read_text())==out
else:(W/'private-return-proof.json').write_text(json.dumps(out,indent=2)+'\n')
print(json.dumps({k:v for k,v in out.items() if k not in ('call_to_marker_instructions','CFG_edges')},indent=2))
