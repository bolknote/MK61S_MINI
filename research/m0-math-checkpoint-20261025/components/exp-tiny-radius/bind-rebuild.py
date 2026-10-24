"""Bind intended complete sources, all unchanged ASM, and rebuild outputs."""
from pathlib import Path
import ast,hashlib,json,shlex,struct,subprocess,sys
sys.dont_write_bytecode=True
W=Path(__file__).resolve().parent;ROOT=W.parents[1]
P=ROOT/'.build/m0-asin-scaled-bound-v164-20261023'
F=ROOT/'.build/m0-f2d-leaf-20261024'
sys.path.insert(0,str(ROOT/'tests'))
from check_stm32_vectors import ElfImage
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
def allocated(e):return {n:e.bytes_at(s) for n,s in e.named_sections.items() if s[2]&2 and s[1]!=8 and s[5]}
tree=ast.parse((ROOT/'.build/m0-exp-cached-product-independent-20261024/bind_rebuild.py').read_text())
fn=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='relocs')
exec(compile(ast.Module(body=[fn],type_ignores=[]),str(W/'bind-rebuild.py'),'exec'),globals())
def semrelocs(e):return {n:v for n,v in relocs(e).items() if n in allocated(e)}
commands=[];objects={}
entry=next(e for e in json.loads((P/'build/compile_commands.json').read_text()) if e['file'].endswith('/code/native_eabi_m0.S'))
flags=shlex.split(entry['command'])
for label in ('control','candidate'):
 for p in (F/'candidate').glob('native_eabi_m0*'):
  if p.suffix in ('.S','.inc'):assert (W/label/p.name).read_bytes()==p.read_bytes(),str(p)
 c=list(flags);c[c.index(entry['file'])]=str(W/label/'native_eabi_m0.S')
 out=W/('ASM-'+label+'.o');c[c.index('-o')+1]=str(out)
 subprocess.run(c,cwd=W,check=True);commands.append(c);objects[label]=ElfImage(out)
 base=ElfImage(F/'RP-candidate.o')
 assert allocated(objects[label])==allocated(base)
 assert semrelocs(objects[label])==semrelocs(base)
assert allocated(objects['control'])==allocated(objects['candidate'])
build=json.loads((W/'build.json').read_text())
# Rebuild two complete RP CPP objects and both full exp overlay ELFs,
# then both complete ASM objects. Debug sections are included in equality.
commands += [c for c in build['commands'] if Path(c[c.index('-o')+1]).name in ('RP-control.o','RP-candidate.o','control.elf','candidate.elf')]
outputs={c[c.index('-o')+1] for c in commands};folder=W/'rebuild';folder.mkdir(exist_ok=True);records=[]
for c in commands:
 original=Path(c[c.index('-o')+1]);rewritten=[str(folder/Path(s).name) if s in outputs else s for s in c]
 subprocess.run(rewritten,cwd=W,check=True)
 assert original.read_bytes()==(folder/original.name).read_bytes(),original.name
 records.append(dict(original=str(original.relative_to(W)),rebuilt=str((folder/original.name).relative_to(W)),sha256=sha(original),bytes=original.stat().st_size,command=rewritten))
assert len(records)==6
im=ElfImage(W/'candidate.elf');candidate=ElfImage(W/'RP-candidate.o')
helper=next(n for n in im.symbols if 'exp_tiny_rne' in n)
body=im.bytes_at(im.named_sections['.text'])
section=candidate.named_sections['.m0_exp_tiny'];literal=candidate.bytes_at(section)
assert len(literal)==196
offset=(im.symbols[helper]&~1)-im.named_sections['.text'][3]
assert body[offset:offset+len(literal)]==literal
assert not semrelocs(candidate).get('.m0_exp_tiny')
# Explicit PHDRS forbid ELF headers or padding from overwriting neighbors.
raw=(W/'candidate.elf').read_bytes();phoff=struct.unpack_from('<I',raw,28)[0];phentsize,phnum=struct.unpack_from('<HH',raw,42)
loads=[]
for i in range(phnum):
 typ,off,vma,pma,filesz,memsz,flg,align=struct.unpack_from('<8I',raw,phoff+i*phentsize)
 if typ==1:
  assert vma==pma and filesz==memsz
  assert (0x101a0000<=vma and vma+filesz<=0x10200000) or (vma==0x20038ee4 and filesz==168)
  loads.append(dict(address=hex(vma),bytes=filesz))
assert len(loads)==2
out=dict(status='PASS_FULL_SOURCE_CPP_ASM_BINDING_AND_SIX_BYTE_EXACT_REBUILDS',
 source_sha256=build['source_sha256'],candidate_ELF_sha256=sha(W/'candidate.elf'),
 full_ASM_all_allocated_bytes_semantic_relocations_equal_qualified_f2d=True,
 d2f_f2d_and_other_RP_ASM_sections_unchanged=True,
 helper_complete_source_and_linked_bytes_exact=True,helper_bytes=196,
 helper_external_calls_ROM_or_relocations=0,explicit_loads=loads,
 selected_generic_M0_M4_CPP_unchanged_from_build=True,
 ASM_generic_M0_M4_inherited_from_byte_identical_f2d_sources=True,
 whole_M4_firmware_not_built=True,records=records,hardware_accessed=False)
(W/'rebuild-proof.json').write_text(json.dumps(out,indent=2)+'\n')
print(json.dumps({k:v for k,v in out.items() if k!='records'},indent=2))
