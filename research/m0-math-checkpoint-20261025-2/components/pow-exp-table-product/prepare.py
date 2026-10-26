"""Add a table-only product entry; leave the general 77-instruction body intact."""
from pathlib import Path
import difflib, hashlib, json

W = Path(__file__).resolve().parent
assert not (W / 'FROZEN.json').exists()
for p in (W / 'control').iterdir():
    if p.is_file():
        (W / 'candidate' / p.name).write_bytes(p.read_bytes())

p = W / 'candidate/native_eabi_m0_pow_exp_body.inc'
s = p.read_text()
old = 'const U correction=mk61_m0_pow_exp_product(q,d);'
assert s.count(old) == 1
p.write_text(s.replace(old, 'const U correction=mk61_m0_pow_exp_table_product(q,d);'))

p = W / 'candidate/native_eabi_m0_pow_fast.inc'
s = p.read_text()
anchor = 'MK61_SOFT_PCS U mk61_m0_pow_exp_product(U q,U magnitude);'
assert s.count(anchor) == 1
s = s.replace(anchor, anchor + '\nMK61_SOFT_PCS U mk61_m0_pow_exp_table_product(U q,U magnitude);')
anchor = 'extern "C" MK61_SOFT_PCS U mk61_m0_pow_exp_product_flash(U,U);'
assert s.count(anchor) == 1
s = s.replace(anchor, anchor + '\n#if defined(MK61_M0_RP2040_EABI) && MK61_M0_RP2040_EABI\nextern "C" MK61_SOFT_PCS U mk61_m0_pow_exp_table_product_flash(U,U);\n#endif')
assert s.count(old) == 1
s = s.replace(old, 'const U correction=mk61_m0_pow_exp_table_product(q,d);')
assert s.count('#define mk61_m0_pow_exp_product mk61_m0_pow_exp_product_flash') == 1
s = s.replace('#define mk61_m0_pow_exp_product mk61_m0_pow_exp_product_flash',
              '#define mk61_m0_pow_exp_table_product mk61_m0_pow_exp_table_product_flash')
assert s.count('#undef mk61_m0_pow_exp_product') == 1
s = s.replace('#undef mk61_m0_pow_exp_product', '#undef mk61_m0_pow_exp_table_product')
p.write_text(s)

p = W / 'candidate/native_eabi_m0_pow_exp_product.inc'
s = p.read_text()
anchor = ' // Preserve the established168-byte RAM slot and all following symbols.'
assert s.count(anchor) == 1
prefix = s[:s.index(anchor)]
s = prefix + ''' // Only callers whose A is a literal exp_table[] root may use this entry.
 // The certified table has low32==0 only at index0, A==2^62.
 // The exact old rounded product is then (B>>2)+bool(B&2).
 .global mk61_m0_pow_exp_table_product
 .hidden mk61_m0_pow_exp_table_product
 .type mk61_m0_pow_exp_table_product,%function
 .thumb_func
mk61_m0_pow_exp_table_product:
 cmp r0,#0
 bne mk61_m0_pow_exp_product
 lsls r0,r3,#30
 lsrs r1,r3,#2
 lsrs r3,r2,#2
 orrs r0,r3
 movs r2,#0
 adcs r0,r2
 adcs r1,r2
 bx lr
 .size mk61_m0_pow_exp_table_product,.-mk61_m0_pow_exp_table_product
 // Reuse the original resident182-byte slot before its fixed RAM veneers.
 // The old generic154-byte body is unchanged; no extra scratch bank is used.
 .hword 0xbf00,0xbf00,0xbf00,0xbf00
#endif
'''
p.write_text(s)

wrapper = '''#if defined(MK61_USE_M0_EABI) && MK61_USE_M0_EABI && defined(MK61_M0_RP2040_EABI) && MK61_M0_RP2040_EABI
.syntax unified
.cpu cortex-m0plus
.thumb
.section .m0_pow_exp_table_transition,"ax",%progbits
.align 2
.global mk61_m0_pow_exp_table_product_flash
.hidden mk61_m0_pow_exp_table_product_flash
.type mk61_m0_pow_exp_table_product_flash,%function
.thumb_func
mk61_m0_pow_exp_table_product_flash:
 push {r0}
 ldr r0,1f
 mov r12,r0
 pop {r0}
 bx r12
 nop
1: .word mk61_m0_pow_exp_table_product
.size mk61_m0_pow_exp_table_product_flash,.-mk61_m0_pow_exp_table_product_flash
#endif
'''
(W / 'candidate/native_eabi_m0_pow_exp_table_transition.inc').write_text(wrapper)
p = W / 'candidate/native_eabi_m0.S'
s = p.read_text()
anchor = '#include "native_eabi_m0_pow_exp_product.inc"'
assert s.count(anchor) == 1
p.write_text(s.replace(anchor, anchor + '\n#include "native_eabi_m0_pow_exp_table_transition.inc"'))

patch = ''
for p in sorted((W / 'candidate').iterdir()):
    control = W / 'control' / p.name
    a = control.read_text().splitlines(True) if control.exists() else []
    patch += ''.join(difflib.unified_diff(a, p.read_text().splitlines(True),
        fromfile='a/code/' + p.name if control.exists() else '/dev/null',
        tofile='b/code/' + p.name))
(W / 'table-only-product.patch').write_text(patch)
print(json.dumps(dict(status='PREPARED_NOT_QUALIFIED', changed_files=[p.name for p in (W/'candidate').iterdir()
    if not (W/'control'/p.name).exists() or p.read_bytes() != (W/'control'/p.name).read_bytes()],
    generic154byte_source_prefix_unchanged=prefix == (W/'control/native_eabi_m0_pow_exp_product.inc').read_text().split(anchor if False else ' // Preserve the established168-byte RAM slot and all following symbols.')[0],
    patch_sha256=hashlib.sha256(patch.encode()).hexdigest()), indent=2))
