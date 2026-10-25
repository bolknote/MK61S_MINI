pow_integer128_approx_high64 = 0x1014e669;
pow_integer128_multiply = 0x100f9269;
mk61_m0_bound80_old_compare = 0x1014f721;
PHDRS { front PT_LOAD FLAGS(5); }
SECTIONS { .front 0x10150000 : { KEEP(*(.m0_pow_boundary_exact)) } :front
/DISCARD/ : { *(.ARM.exidx*) *(.ARM.extab*) *(.comment) *(.note*) *(.ARM.attributes) } }
