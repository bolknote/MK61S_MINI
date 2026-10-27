"""One source-linked image per machine, actual BootROM and whole-bank loader."""
from pathlib import Path
import hashlib,json,struct,sys
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1]
sys.path[:0]=[str(ROOT/'.build/m0-float-fma-qualification-20261023/support'),str(ROOT/'tests')]
from native_eabi_m0_arm_self_test import Machine,SP,bits
from check_stm32_vectors import ElfImage
ROM=ROOT/'research/rp2040-memset-2026-10-21/capture/bootrom.bin'
assert hashlib.sha256(ROM.read_bytes()).hexdigest()=='ef07d54bdd259c7858483606118a3c704976801823c38ac5a2fcdffacd2d83fe'
linked=json.loads((HERE/'link-result.json').read_bytes())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def machine(label='candidate'):
 path=HERE/(label+'.elf');assert sha(path)==linked['images'][label]['ELF_sha256']
 m=Machine(path,True,bootrom=ROM);assert not m.rom_models
 symbols=m.elf.symbols;hot=m.elf.named_sections['.scratch_y'];expected=m.elf.bytes_at(hot)
 # Explicitly remove the direct VMA load, so initialization must copy Flash LMA.
 m.uc.mem_write(hot[3],bytes([0xa5])*4096)
 ranges=[(hot[3],hot[3]+hot[5])]
 for begin,end in [('__data_start__','__data_end__'),('__bss_start__','__bss_end__')]:
  a,b=symbols[begin],symbols[end]
  if b>a:m.uc.mem_write(a,bytes([0x5a])*(b-a));ranges.append((a,b))
 m.rom_init_write_ranges=ranges
 try:value,_,count=m.call('unified_math_init',0,count=True)
 finally:m.rom_init_write_ranges=[]
 assert value&0xffffffff==1
 assert bytes(m.uc.mem_read(hot[3],hot[5]))==expected
 assert bytes(m.uc.mem_read(hot[3]+hot[5],4096-hot[5]))==bytes([0xa5])*(4096-hot[5])
 assert bytes(m.uc.mem_read(symbols['__scratch_y_source__'],hot[5]))==expected
 ptr=struct.unpack('<4I',m.uc.mem_read(symbols['aeabi_mem_funcs'],16));assert all(0<x<0x4000 and x&1 for x in ptr)
 m.unified_loader_report=dict(actual_ARM_calls=1,instructions=count,whole_scratch_y_bytes=hot[5],reserved_tail_untouched=True,actual_ROM_pointers=list(ptr),no_old_firmware_overlay_loaded=True)
 m.calls=0;m.stack_lowest=SP
 return m
