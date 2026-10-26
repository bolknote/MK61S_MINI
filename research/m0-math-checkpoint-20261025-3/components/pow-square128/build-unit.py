"""Bare unit images contain only the actual square and bound old94-byte helper."""
from pathlib import Path
import hashlib,json,subprocess,sys
sys.dont_write_bytecode=True
W=Path(__file__).resolve().parent;ROOT=W.parents[1]
sys.path.insert(0,str(ROOT/'tests'))
from check_stm32_vectors import ElfImage
P=ROOT/'.build/m0-asin-scaled-bound-v164-20261023'
tc=Path('/Users/bolk/Library/Arduino15/packages/STMicroelectronics/tools/xpack-arm-none-eabi-gcc/14.2.1-1.1/bin')
source=(W/'control/native_eabi_m0_pow_root_prefix.inc').read_text()
start=source.index('\t.globl\tpow_integer128_approx_high64')
end=source.index('@ -- End function',start)
fragment=source[start:end].replace('pow_integer128_approx_high64','mk61_m0_square128_approx_bound')
(W/'helper.S').write_text('.syntax unified\n.cpu cortex-m0plus\n.thumb\n.section .square128_helper_only,"ax",%progbits\n'+fragment)
cmd=[str(tc/'arm-none-eabi-gcc'),'-mcpu=cortex-m0plus','-mthumb','-c',str(W/'helper.S'),'-o',str(W/'helper.o')]
subprocess.run(cmd,check=True);commands=[cmd]
base=ElfImage(P/'firmware/mk61s-picocalc-pico-h.elf');address=base.symbols['pow_integer128_approx_high64']&~1
script=(W/'square.ld').read_text().replace('code PT_LOAD FLAGS(5);','code PT_LOAD FLAGS(5); helper PT_LOAD FLAGS(5);')
script=script.replace(' /DISCARD/', ' .helper '+hex(address)+' : { KEEP(*(.square128_helper_only)) } :helper\n /DISCARD/')
(W/'unit.ld').write_text(script)
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest();meta={}
for label in ['control','candidate']:
 cmd=[str(tc/'arm-none-eabi-ld'),'--gc-sections','-e','pow_integer128_square','-T',str(W/'unit.ld'),str(W/('RP-'+label+'.o')),str(W/'helper.o'),'-o',str(W/('unit-'+label+'.elf'))]
 subprocess.run(cmd,check=True);commands.append(cmd)
 im=ElfImage(W/('unit-'+label+'.elf'));body=im.bytes_at(im.named_sections['.helper'])
 s=next(s for s in base.named_sections.values() if s[3]<=address<s[3]+s[5])
 assert len(body)==94 and body==base.bytes_at(s)[address-s[3]:address-s[3]+94]
 meta[label]=dict(ELF_sha256=sha(W/('unit-'+label+'.elf')),helper94bytes_exact_parent=True)
(W/'unit-build.json').write_text(json.dumps(dict(status='BARE_UNIT_BUILT',images=meta,commands=commands),indent=2)+'\n')
print(json.dumps(meta,indent=2))
