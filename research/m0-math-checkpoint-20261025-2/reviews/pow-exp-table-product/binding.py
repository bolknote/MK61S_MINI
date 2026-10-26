"""Frozen private table-product source/object/ELF binding and CPU-only rebuilds."""
import ast,difflib,hashlib,json,re,struct,subprocess,sys
from pathlib import Path
sys.dont_write_bytecode=True
R=Path('/Users/bolk/Projects/MK61S_MINI');O=Path(__file__).resolve().parent;W=R/'.build/m0-pow-exp-table-product-20261025';P=R/'.build/m0-exp-directed-product-20261024'
sys.path.insert(0,str(R/'tests'))
from check_stm32_vectors import ElfImage
def ref(p):p=Path(p);d=p.read_bytes();return dict(path=str(p),bytes=len(d),sha256=hashlib.sha256(d).hexdigest())
def pin(p,h):v=ref(p);assert v['sha256']==h,v;return v
def save(n,d):
 with (O/n).open('x')as f:json.dump(d,f,indent=2);f.write('\n')
 return ref(O/n)
def allocated(e):return {n:e.bytes_at(s)for n,s in e.named_sections.items()if s[2]&2 and s[1]!=8 and s[5]}
def bss(e):return {n:s[5]for n,s in e.named_sections.items()if s[2]&2 and s[1]==8 and s[5]}
def memory(e,a,n):
 s=next(s for s in e.sections if s[1]!=8 and s[3]<=a and a+n<=s[3]+s[5]);return e.bytes_at(s)[a-s[3]:a-s[3]+n]
refs=dict(FROZEN=pin(W/'FROZEN.json','dd0ec3663009cd390c710611e57ccc23d18c733201911471feae6e52e58e7d1c'),
 result=pin(W/'result.json','60e4347619b46d4b07bc2b81181f03ea233bd80cc890a88a80c98c1dea8d219d'),
 HANDOFF=pin(W/'HANDOFF.md','60e70ca8781ffdd290aa766a49ef9011a44dc46781a265cbe26000250782aaf6'),
 ELF=pin(W/'candidate.elf','e94a79c49895a7f5328d8ef0d9185d88fe920a3101433c771e31759fac936d98'),
 directed_review=pin(R/'.build/m0-exp-directed-product-independent-20261024/FINAL-REVIEW.json','0d6073f3534d2abb71ad3348096bca930d2513e3813b06dbcfb8911ca485839b'),
 near_one_review=pin(R/'.build/m0-exp-near-one-independent-20261025/FINAL-REVIEW.json','6c504f888e1ce0489379d1769b2d1e331b64bda0354eed746fbe98359748634b'),
 near_one_clarification=pin(R/'.build/m0-exp-near-one-independent-20261025/INTERVAL-CLARIFICATION.json','03ceff8e6e0f9e8ca790567f2045f1791c301f1544d2c0f8aaa234a19496c179'),
 near_one_ROOT=pin(R/'.build/m0-exp-near-one-root-acceptance-20261025-001/RECEIPT.json','0831d62fc51c2be190afc220525bb52974d83c5b236bba07359f6946d02c74a5'))
local=[]
for n,row in json.loads((W/'FROZEN.json').read_text())['files'].items():
 v=ref(W/n);assert v['bytes']==row['bytes']and v['sha256']==row['sha256'];local.append(v)
assert len(local)==123
lineage=[]
for n,row in json.loads((W/'source-lineage-pins.json').read_text())['files'].items():
 p=R/n;assert '/dev/'not in str(p)and '/.git/'not in str(p)
 v=ref(p);assert v['bytes']==row['bytes']and v['sha256']==row['sha256'];lineage.append(v)
assert len(lineage)==1349
assert (W/'candidate/native_eabi_m0.cpp').read_bytes()==(P/'candidate/native_eabi_m0.cpp').read_bytes()
patch='';changed=[]
names=['native_eabi_m0.S','native_eabi_m0_pow_exp_body.inc','native_eabi_m0_pow_exp_product.inc','native_eabi_m0_pow_exp_table_transition.inc','native_eabi_m0_pow_fast.inc']
for n in names:
 old=W/'control'/n;new=W/'candidate'/n;before=old.read_text()if old.exists()else '';after=new.read_text()
 if before!=after:
  changed.append(n);patch+=''.join(difflib.unified_diff(before.splitlines(True),after.splitlines(True),fromfile='a/code/'+n if old.exists()else '/dev/null',tofile='b/code/'+n))
assert patch==(W/'table-only-product.patch').read_text()
for p in (W/'control').iterdir():
 if p.suffix in ['.S','.inc','.cpp']and p.name not in names:assert p.read_bytes()==(W/'candidate'/p.name).read_bytes()
source=(R/'.build/m0-exp-cached-product-independent-20261024/bind_rebuild.py').read_text();fn=next(n for n in ast.parse(source).body if isinstance(n,ast.FunctionDef)and n.name=='relocs')
exec(compile(ast.Module(body=[fn],type_ignores=[]),'<accepted-semantic-relocs>','exec'),globals())
def sem(e):return {n:v for n,v in relocs(e).items()if n in allocated(e)}
old,new=[ElfImage(W/('RP-'+label+'-cpp.o'))for label in ['control','candidate']]
assert allocated(old)==allocated(new)and bss(old)==bss(new)
accepted=ElfImage(P/'RP-candidate.o');assert allocated(old)==allocated(accepted)and sem(old)==sem(accepted)
mapping={'mk61_m0_pow_exp_product':'mk61_m0_pow_exp_table_product','mk61_m0_pow_exp_product_flash':'mk61_m0_pow_exp_table_product_flash'}
oldr,newr=sem(old),sem(new);changed_relocs={}
for n,rows in oldr.items():
 if rows!=newr[n]:
  assert [(a,b,mapping.get(c,c))for a,b,c in rows]==newr[n]
  delta=[dict(before=a,after=b)for a,b in zip(rows,newr[n])if a!=b];assert len(delta)==1;changed_relocs[n]=delta
assert set(changed_relocs)=={'.m0_pow_refine_extension','.scratch_y.m0_pow_hot','.m0_pow_small_y_cold'}
contexts=[]
for context in ['generic_M0','M4_soft','M4_hard']:
 for kind in ['cpp','asm']:
  a,b=[ElfImage(W/(context+'-'+label+'-'+kind+'.o'))for label in ['control','candidate']]
  assert allocated(a)==allocated(b)and sem(a)==sem(b)and bss(a)==bss(b);contexts.append([context,kind])
a,b=[ElfImage(W/('RP-'+label+'-asm.o'))for label in ['control','candidate']]
aa,bb=allocated(a),allocated(b);asm_delta={n:[len(aa.get(n,b'')),len(bb.get(n,b''))]for n in aa.keys()|bb.keys()if aa.get(n,b'')!=bb.get(n,b'')}
assert asm_delta=={'.scratch_y.m0_pow_hot':[504,520],'.m0_pow_exp_table_transition':[0,16]}
im=ElfImage(W/'candidate.elf');parent=ElfImage(P/'candidate.elf');base=ElfImage(R/'.build/m0-asin-scaled-bound-v164-20261023/firmware/mk61s-picocalc-pico-h.elf')
general=im.symbols['mk61_m0_pow_exp_product']&~1;entry=im.symbols['mk61_m0_pow_exp_table_product']&~1
assert entry==general+154 and memory(im,general,154)==memory(parent,general,154)
name='_ZN7m0_eabiL9exp_tableE';table=memory(im,im.symbols[name],4096);assert table==memory(base,base.symbols[name],4096)
roots=struct.unpack('<512Q',table)
def certify(rs):assert len(rs)==512 and rs[0]==1<<62 and [i for i,v in enumerate(rs)if v&0xffffffff==0]==[0]and all(1<<62<=v<1<<63 for v in rs)
certify(roots);neg=0
for i,v in [(0,(1<<62)+(1<<32)),(1,roots[1]&~0xffffffff),(0,0)]:
 r=list(roots);r[i]=v
 try:certify(r)
 except AssertionError:neg+=1
assert neg==3
wrapper=im.symbols['mk61_m0_pow_exp_table_product_flash']&~1
assert memory(im,wrapper,12)==memory(base,0x1016b3b8,12)==bytes.fromhex('01b40248844601bc6047c046')
assert int.from_bytes(memory(im,wrapper+12,4),'little')==entry|1
assert im.named_sections['.scratch_y'][5]==4080 and im.sizes['mk61_m0_pow_exp_table_product']==20
old_overlay=memory(parent,general,168);overlap=[max(entry,general),min(entry+20,general+168)]
assert overlap[1]-overlap[0]==14 and old_overlay[154:168]!=memory(im,entry,14)
compiled=json.loads((W/'compile.json').read_text());linked=json.loads((W/'link.json').read_text());outdir=O/'rebuild';outdir.mkdir();commands=[];rebuilt=[]
selected=[c for c in compiled['commands']if c[c.index('-o')+1].endswith(('/RP-candidate-cpp.o','/RP-candidate-asm.o'))]
selected+=[c for c in linked['commands']if c[c.index('-o')+1].endswith('/fixture-candidate.o')]
for oldcmd in selected:
 cmd=list(oldcmd);oldout=Path(cmd[cmd.index('-o')+1]);cmd[cmd.index('-o')+1]=str(outdir/oldout.name)
 assert not any(x in cmd for x in ['-MD','-MMD','-MF','-save-temps'])
 p=subprocess.run(cmd,cwd=W,capture_output=True);(outdir/(oldout.name+'.stdout')).write_bytes(p.stdout);(outdir/(oldout.name+'.stderr')).write_bytes(p.stderr)
 assert p.returncode==0,p.stderr.decode();assert (outdir/oldout.name).read_bytes()==oldout.read_bytes();commands.append(cmd);rebuilt.append(ref(outdir/oldout.name))
oldcmd=next(c for c in linked['commands']if c[c.index('-o')+1].endswith('/candidate.elf'))
script=(W/'candidate-relocated.ld').read_text()
for n in ['RP-candidate-cpp.o','fixture-candidate.o']:script=script.replace(str(W/n),str(outdir/n))
(outdir/'candidate.ld').write_text(script)
cmd=[str(outdir/'candidate.ld')if x==str(W/'candidate-relocated.ld')else str(outdir/Path(x).name)if x in [str(W/'RP-candidate-cpp.o'),str(W/'fixture-candidate.o'),str(W/'candidate.elf')]else '-Map='+str(outdir/'candidate.map')if x.startswith('-Map=')else x for x in oldcmd]
p=subprocess.run(cmd,cwd=W,capture_output=True);(outdir/'candidate.elf.stdout').write_bytes(p.stdout);(outdir/'candidate.elf.stderr').write_bytes(p.stderr)
assert p.returncode==0,p.stderr.decode();assert (outdir/'candidate.elf').read_bytes()==(W/'candidate.elf').read_bytes();commands.append(cmd);rebuilt.append(ref(outdir/'candidate.elf'))
tc=Path(compiled['commands'][0][0]).parent
dis=subprocess.check_output([str(tc/'arm-none-eabi-objdump'),'-dr',str(outdir/'candidate.elf')])
(O/'candidate.actual.dis').write_bytes(dis)
out=dict(status='PASS_FROZEN_TABLE_PRODUCT_SOURCE_OBJECT_AND_ELF_BINDING',accepted_refs=refs,local=local,external=lineage,
 local_count=len(local),external_count=len(lineage),source_basis='directed-product CPP575da330; near-one is separately accepted sibling and is not in this pow ELF',
 exact_patch_changed_files=changed,CPP_all_allocated_bytes_and_tables_unchanged=True,three_literal_table_call_relocations=changed_relocs,
 ASM_delta=asm_delta,other_source_semantic_relocations_BSS_and_selected_contexts_unchanged=contexts,
 general154_same_address_and_bytes=True,table=dict(bytes_sha256=hashlib.sha256(table).hexdigest(),roots=512,low32zero_only_index0=True,negative_controls=3),
 new_wrapper16_bytes_and_scalar_argument_tail_return=True,own_whole_exact_rebuild_count=4,rebuild_commands=commands,rebuilt=rebuilt,
 fresh_disassembly=ref(O/'candidate.actual.dis'),
 overlay_hazard=dict(old_overlay_start=hex(general),old_overlay_bytes=168,new_entry_start=hex(entry),new_entry_bytes20=True,
 destructive_overlap_bytes=14,old_padding_differs_from_new_code=True,automatic_overlay_composition_forbidden=True),
 no_integrated_exp_consumer_in_pow_ELF='mk61_m0_exp_fraction_capture'not in im.symbols,
 future_source_merge_relink_actual_R12_and_loader_guards_required=True,integration_GO=False,device_IO=0,Git=0,canonical=0,network=0)
print(json.dumps(dict(binding=save('binding.json',out),rebuild_count=4),indent=2))
