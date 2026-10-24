"""Bare exact-square code, with local labels retained only for audit hooks."""
from pathlib import Path
import hashlib,json,subprocess,sys
sys.dont_write_bytecode=True
W=Path(__file__).resolve().parent;ROOT=W.parents[1];sys.path.insert(0,str(ROOT/'tests'))
from check_stm32_vectors import ElfImage
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
b=json.loads((W/'build.json').read_text());cc=Path(b['commands'][0][0]).parent
assert sha(W/'square.S')==b['square_source_sha256']
(W/'unit.ld').write_text('PHDRS { square PT_LOAD FLAGS(5); } SECTIONS { .square 0x10000000 : { *(.m0_pow_square_exact_only) } :square /DISCARD/ : { *(.ARM*) *(.comment) *(.note*) } }\n')
commands=[[str(cc/'arm-none-eabi-gcc'),'-mcpu=cortex-m0plus','-mthumb','-DMK61_USE_M0_EABI=1','-DMK61_M0_RP2040_EABI=1','-Wa,-L','-c',str(W/'square.S'),'-o',str(W/'square-audit.o')],
 [str(cc/'arm-none-eabi-ld'),'-e','mk61_m0_pow_square_exact','-T',str(W/'unit.ld'),str(W/'square-audit.o'),'-o',str(W/'unit.elf')]]
for command in commands:subprocess.run(command,cwd=W,check=True)
im=ElfImage(W/'unit.elf');public=ElfImage(W/'candidate.elf')
assert im.bytes_at(im.named_sections['.square'])==public.bytes_at(public.named_sections['.square'])
assert '.Lsquare_choose_word' in im.symbols
assert not subprocess.check_output([str(cc/'arm-none-eabi-nm'),'-u',str(W/'unit.elf')],text=True)
out=dict(status='BUILT_BARE_EXACT_SQUARE_BYTE_IDENTICAL_PUBLIC',square_source_sha256=sha(W/'square.S'),
 public_ELF_sha256=sha(W/'candidate.elf'),unit_ELF_sha256=sha(W/'unit.elf'),
 product_audit_address=hex(im.symbols['.Lsquare_choose_word']),unit_function_bytes=im.sizes['mk61_m0_pow_square_exact'],
 audit_local_labels_no_code_difference=True,commands=commands,hardware_accessed=False)
(W/'unit-build.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps({k:v for k,v in out.items() if k!='commands'},indent=2))
