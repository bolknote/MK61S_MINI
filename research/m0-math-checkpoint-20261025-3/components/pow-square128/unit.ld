pow_integer128_approx_high64 = 0x1014e669;
PHDRS { code PT_LOAD FLAGS(5); helper PT_LOAD FLAGS(5); }
SECTIONS { .square 0x100f9c9c : { KEEP(*(.m0_pow_square_fixed)) } :code
 .helper 0x1014e668 : { KEEP(*(.square128_helper_only)) } :helper
 /DISCARD/ : { *(.ARM.exidx*) *(.ARM.extab*) *(.comment) *(.note*) *(.ARM.attributes) } }
