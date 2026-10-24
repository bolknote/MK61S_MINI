"""Rebuild public code and independently bind its allocated execution bytes."""
from pathlib import Path
import hashlib,json,subprocess,sys
sys.dont_write_bytecode=True
W=Path(__file__).resolve().parent;ROOT=W.parents[1]
sys.path.insert(0,str(ROOT/'tests'))
from check_stm32_vectors import ElfImage
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
build=json.loads((W/'candidate-build.json').read_text());cmd=list(build['commands'][-2])
assert cmd[0].endswith('arm-none-eabi-g++')
cmd[cmd.index('-o')+1]=str(W/'independent-public.o');subprocess.run(cmd,check=True)
assert sha(W/'independent-public.o')==sha(W/'candidate-full.o')
link=list(build['commands'][-1]);link[link.index(str(W/'candidate-full.o'))]=str(W/'independent-public.o');link[link.index('-o')+1]=str(W/'independent-public.elf');subprocess.run(link,check=True)
old=ElfImage(W/'candidate.elf');new=ElfImage(W/'independent-public.elf')
def allocated(e):return {n:e.bytes_at(s) for n,s in e.named_sections.items() if s[2]&2 and s[1]!=8}
assert allocated(old)==allocated(new)
assert all(old.symbols[n]==v for n,v in new.symbols.items() if n in old.symbols)
only_old=set(old.symbols)-set(new.symbols);only_new=set(new.symbols)-set(old.symbols)
different=[n for n in old.named_sections if old.bytes_at(old.named_sections[n])!=new.bytes_at(new.named_sections[n])]
if sha(W/'candidate.elf')==sha(W/'independent-public.elf'):
 assert not only_old and not only_new and not different
 metadata_difference='None: the entire independently relinked ELF is byte-identical.'
else:
 assert only_old=={'candidate-full.o'} and only_new=={'independent-public.o'},(only_old,only_new)
 assert old.symbols['candidate-full.o']==new.symbols['independent-public.o']==0
 assert set(different)=={'.symtab','.strtab'},different
 metadata_difference='Input object filename candidate-full.o versus independent-public.o, value0, in symtab/strtab.'
report=dict(status='PASS_PUBLIC_FULL_OBJECT_AND_ALL_EXECUTED_ALLOCATED_BYTES',candidate_full_object_sha256=sha(W/'candidate-full.o'),candidate_ELF_sha256=sha(W/'candidate.elf'),
            independent_object_byte_exact=True,independent_relink_allocated_bytes_exact_without_exclusions=True,common_symbol_addresses_exact=True,
            whole_independent_ELF_byte_identical=sha(W/'candidate.elf')==sha(W/'independent-public.elf'),only_nonallocated_difference=metadata_difference,
            source_include_sha256=sha(W/'native_eabi_m0_atan_fast.inc'),compile_command=cmd,link_command=link,production_image_created=False,hardware_accessed=False)
(W/'public-body-proof.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({k:v for k,v in report.items() if k not in ('compile_command','link_command')}))
