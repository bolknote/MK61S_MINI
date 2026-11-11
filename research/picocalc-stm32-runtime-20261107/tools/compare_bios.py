#!/usr/bin/env python3
"""Read compiled ELF sizes; no target I/O or performance claim."""
from pathlib import Path
import hashlib,json,struct,subprocess
from elf32 import ELF
R=Path(__file__).resolve().parents[1];B=R.parents[1]/'.build/stm32-module-runtime-20261107'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def measure(label,path,optimization,reserved_flash=0):
 e=ELF(path);h=struct.unpack_from('<16sHHIIIIIHHHHHH',e.data);strings=e.section_data(e.sections[h[13]])
 sections={}
 for s in e.sections:
  end=strings.find(b'\0',s[0]);name=strings[s[0]:end].decode()
  if s[2]&2:sections[name]=s[5]
 data=sections.get('.data',0);bss=sections.get('.bss',0);reserve=sections.get('._user_heap_stack',0)
 end=max(s['physical']+len(s['data'])for s in e.segments if s['data']and 0x08000000<=s['physical']<0x08010000)
 flash=end-0x08000000
 return dict(label=label,optimization=optimization,elf=str(path),elf_sha256=sha(path),flash_bytes=flash,data_bytes=data,bss_bytes=bss,global_ram_bytes=data+bss,linker_heap_stack_including_alignment=reserve,ram_after_globals_bytes=20480-data-bss,ram_after_reserve_bytes=20480-data-bss-reserve,flash_reserved_for_settings=reserved_flash,flash_available_after_image_and_settings=65536-flash-reserved_flash)
rows=[measure('Stock keyboard v1.6',B/'baseline-firmware/picocalc_keyboard.ino.elf','-Os -flto'),measure('Southbridge upstream default',B/'community-southbridge/build-default/picocalc_BIOS_jcs.elf','-O3'),measure('Southbridge size build',B/'community-southbridge/build-size/picocalc_BIOS_jcs.elf','-Os -flto'),measure('Stock + our module runtime / UART DMA',B/'firmware/picocalc_keyboard.ino.elf','-Os -flto')]
for row in rows:
 if row['label'].startswith('Southbridge'):
  row['flash_reserved_for_settings']=2048;row['flash_available_after_image_and_settings']-=2048
stock,default,small,ours=rows
report=dict(status='COMPILED_SIZE_COMPARISON',date='2026-11-07',compiler='xPack arm-none-eabi GCC14.2.1',target='STM32F103R8 Cortex-M3 soft float ABI',physical_io=False,performance_measured=False,community_commit=subprocess.check_output(['git','-C',str(B/'community-southbridge'),'rev-parse','HEAD'],text=True).strip(),community_submodules=subprocess.check_output(['git','-C',str(B/'community-southbridge'),'submodule','status'],text=True).splitlines(),stock_commit='fdcfe2c87a56b6dbcd540e91de1161d483872af9',rows=rows,delta=dict(flash_saved=stock['flash_bytes']-small['flash_bytes'],flash_saved_percent=100*(stock['flash_bytes']-small['flash_bytes'])/stock['flash_bytes'],global_ram_saved=stock['global_ram_bytes']-small['global_ram_bytes'],net_extra_free_flash_after_settings_reserve=small['flash_available_after_image_and_settings']-stock['flash_available_after_image_and_settings']),limits=['Compare bare keyboard bases, not bare Southbridge against stock+runtime','Same compiler, upstream library versions and different feature sets; not a controlled functional-equivalence comparison','Southbridge default runs at4MHz; compute and2.25Mbaud need a72MHz profile and clock/timing integration','No power, timing, keyboard or UART hardware validation','Community mirror can lag original host; Flash2KiB reserved for settings'])
(B/'bios-comparison.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report,indent=2))
