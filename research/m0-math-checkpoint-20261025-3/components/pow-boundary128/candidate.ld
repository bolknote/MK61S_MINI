mk61_m0_boundary128_compare = 0x1014f721;
pow_integer128_square = 0x100f9c9d;
pow_integer128_multiply = 0x100f9269;
pow_integer128_approx_high64 = 0x1014e669;
PHDRS { front PT_LOAD FLAGS(5); code PT_LOAD FLAGS(5); }
SECTIONS { .front 0x10150000 : { KEEP(*(.m0_pow_boundary_exact)) } :front
.boundary128 0x101e0000 : { KEEP(*(.m0_pow_boundary128_code)) *(.rodata*) } :code
/DISCARD/ : { *(.ARM.exidx*) *(.ARM.extab*) *(.comment) *(.note*) *(.ARM.attributes) } }
