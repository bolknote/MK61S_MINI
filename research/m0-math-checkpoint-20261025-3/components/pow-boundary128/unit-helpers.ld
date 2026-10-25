pow_integer128_approx_high64 = 0x1014e669;
PHDRS { mul PT_LOAD FLAGS(5); cmp PT_LOAD FLAGS(5); }
SECTIONS { .multiply 0x100f9268 : { KEEP(*(.unit_multiply)) } :mul
.compare 0x1014f720 : { KEEP(*(.unit_compare)) } :cmp
/DISCARD/ : { *(.ARM.exidx*) *(.ARM.extab*) *(.comment) *(.note*) *(.ARM.attributes) } }
