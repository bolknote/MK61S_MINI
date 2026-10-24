mk61_m0_pow_dispatch = 0x101612f5;
__aeabi_ddiv = 0x100f7e89;
__aeabi_dmul = 0x100f7cb7;
mk61_m0_sqrt = 0x1016bb01;
pow_rsqrt = 0x10160ef1;
pow_root128_ranged = 0x1014ed69;
mk61_m0_pow_negative_integer_dispatch = 0x10161235;
mk61_m0_pow_positive_checked_dispatch = 0x200383c1;
mk61_m0_pow_near_one_binomial_dispatch = 0x100f8435;
PHDRS { entry PT_LOAD FLAGS(5); square PT_LOAD FLAGS(5); ordinary PT_LOAD FLAGS(5); }
SECTIONS {
 .pow 0x101614cc : { *(.m0_pow_dispatch_extension) } :entry
 .square 0x10161e00 : { *(.m0_pow_square_exact_only) } :square
 .ordinary 0x10162200 : { *(.m0_pow_dispatch_ordinary) *(.text*) *(.rodata*) } :ordinary
 /DISCARD/ : { *(.ARM*) *(.comment) *(.note*) }
}
