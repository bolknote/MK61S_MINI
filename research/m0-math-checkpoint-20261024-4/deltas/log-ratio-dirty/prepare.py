"""Reuse the existing log10 reciprocal to repair the exact Q70 quotient."""
from pathlib import Path
import difflib
import hashlib
import json

W = Path(__file__).resolve().parent
ROOT = W.parents[1]
P = ROOT / '.build/m0-asin-scaled-bound-v164-20261023/source/code'
cpp = (P / 'native_eabi_m0.cpp').read_text()
anchor = '#include "native_eabi_m0_log70_center.inc"'
assert cpp.count(anchor) == 1
cpp = cpp.replace(anchor, '''#if defined(MK61_M0_RP2040_EABI) && MK61_M0_RP2040_EABI
#define MK61_M0_LOG10_TABLE_INCLUDED 1
#include "native_eabi_m0_log10_table.inc"
#endif
''' + anchor)
(W / 'native_eabi_m0.cpp').write_text(cpp)
log10 = (P / 'native_eabi_m0_log10.inc').read_text()
anchor = '#include "native_eabi_m0_log10_table.inc"'
assert log10.count(anchor) == 1
log10 = log10.replace(anchor, '#ifndef MK61_M0_LOG10_TABLE_INCLUDED\n' + anchor + '\n#endif')
(W / 'native_eabi_m0_log10.inc').write_text(log10)
old = (P / 'native_eabi_m0_log70_center.inc').read_text()
first = old.index('  uint32_t a=uint32_t(delta>>11);')
last = old.index('\n}', first)
replacement = '''  // The log10 table already stores floor(2^75/den), cleared to64.
  // Its Q46 product estimates H=delta*2^29/den within6.500062 units.
  const uint32_t* row=log10_table[(den>>1)-1024U];
  const U reciprocal=(U(row[1])<<32)|(row[0]&~63U);
  // At either dyadic half-segment endpoint the product needs only shifts.
  // R is a multiple of64, and R mod2^46 is nonzero for every odd den.
  if(delta>=(U(1)<<41)-1) {
    U q=reciprocal>>5;
    if(delta<(U(1)<<41)) q-=(reciprocal>>46)+1;
    const uint32_t r=(uint32_t(delta)<<29)-uint32_t(q)*den;
    return q+uint32_t(r>=den)+uint32_t(r>=2*den);
  }
  const U q=mk61_m0_log_product46(delta,reciprocal);
  const int32_t residue=int32_t((uint32_t(delta)<<29)-uint32_t(q)*den);
  const bool negative=residue<0;
  uint32_t top=negative?uint32_t(0)-uint32_t(residue)+den-1U:uint32_t(residue);
  uint32_t divisor=den<<2,correction;
  // Three quotient bits suffice. A negative residual needs ceil division
  // so that subtracting the correction produces exactly floor(H).
  asm volatile(".syntax unified\\n"
    "movs %[q],#0\\ncmp %[n],%[d]\\nblo 1f\\nsubs %[n],%[n],%[d]\\n1:\\nadcs %[q],%[q]\\n"
    "lsrs %[d],%[d],#1\\ncmp %[n],%[d]\\nblo 1f\\nsubs %[n],%[n],%[d]\\n1:\\nadcs %[q],%[q]\\n"
    "lsrs %[d],%[d],#1\\ncmp %[n],%[d]\\nblo 1f\\nsubs %[n],%[n],%[d]\\n1:\\nadcs %[q],%[q]\\n"
    ".syntax divided\\n" : [n]"+&l"(top),[d]"+&l"(divisor),[q]"=&l"(correction) : : "cc");
  return negative?q-correction:q+correction;'''
new = old[:first] + replacement + old[last:]
(W / 'native_eabi_m0_log70_center.inc').write_text(new)
(W / 'dirty-log-ratio-only.patch').write_text(''.join(difflib.unified_diff(
    old.splitlines(True), new.splitlines(True), fromfile='parent/native_eabi_m0_log70_center.inc',
    tofile='candidate/native_eabi_m0_log70_center.inc')))
(W / 'ratio.S').write_text('.syntax unified\n.cpu cortex-m0plus\n.thumb\n#include "native_eabi_m0_log70_ratio.inc"\n')
ratio = (P / 'native_eabi_m0_log70_ratio.inc').read_text()
control_asm = W / 'control-asm'
control_asm.mkdir(exist_ok=True)
(control_asm / 'ratio.S').write_bytes((W / 'ratio.S').read_bytes())
(control_asm / 'native_eabi_m0_log70_ratio.inc').write_text(ratio)
anchor = '.Llog_ratio70_slow:\n ldr r3,=mk61_m0_log_ratio70_slow\n bx r3\n'
new_ratio = '''.Llog_ratio70_slow:
 movs r3,r0
 orrs r3,r1
 beq .Llog_ratio70_zero
 ldr r3,=mk61_m0_log_ratio70_slow
 bx r3
.Llog_ratio70_zero:
 bx lr
'''
assert ratio.count(anchor) == 1
(W / 'native_eabi_m0_log70_ratio.inc').write_text(ratio.replace(anchor, new_ratio))
source = (ROOT / '.build/m0-ln-cold-entry-20261024/build.py').read_text()
source = source.replace("'native_eabi_m0_log70.inc'", "'native_eabi_m0_log70_center.inc'")
source = source.replace('0x101a0000', '0x101a0000')
source = source.replace("bindings = {n: resident.symbols[n] for n in names if n in resident.symbols}",
                        "bindings = {n: resident.symbols[n] for n in names if n in resident.symbols and n != 'mk61_m0_log_ratio70'}\n    for name in ('memset', 'memcpy'):\n        if name in names and name not in bindings:\n            bindings[name] = resident.symbols['__wrap_' + name]")
needle = "    subprocess.run(commands[0], check=True)"
add = """    asm_command = [str(CC / 'arm-none-eabi-gcc'), '-mcpu=cortex-m0plus', '-mthumb',
                   '-mfloat-abi=soft', '-DMK61_USE_M0_EABI=1', '-DMK61_M0_RP2040_EABI=1',
                   '-I', str(P / 'source/code'), '-c', str(W / ('ratio.S' if label=='candidate' else 'control-asm/ratio.S')), '-o', str(W / (label + '-ratio.o'))]
    commands.append(asm_command)
    subprocess.run(asm_command, check=True)
"""
assert source.count(needle) == 1
source = source.replace(needle, needle + '\n' + add)
source = source.replace("str(W / (label + '-full.o')), '-o', str(W / (label + '.elf'))]",
                        "str(W / (label + '-full.o')), str(W / (label + '-ratio.o')), '-o', str(W / (label + '.elf'))]")
(W / 'build.py').write_text(source)
source = (ROOT / '.build/m0-ln-cold-entry-20261024/probe.py').read_text()
source = source.replace("'native_eabi_m0_log70.inc'", "'native_eabi_m0_log70_center.inc'")
source = source.replace('PASS_PRIVATE_LN_COLD_ENTRY_PROBE_NOT_QUALIFICATION', 'PASS_PRIVATE_DIRTY_LOG_RATIO_PUBLIC_PROBE_NOT_QUALIFICATION')
(W / 'probe.py').write_text(source)
(W / 'preparation.json').write_text(json.dumps(dict(status='PRIVATE_EXACT_DIRTY_LOG_RATIO_PROTOTYPE',
    source_sha256=hashlib.sha256(new.encode()).hexdigest(), no_new_tables=True, no_canonical_or_device_changed=True), indent=2) + '\n')
