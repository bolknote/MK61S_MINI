PHDRS { code PT_LOAD FLAGS(5); }
SECTIONS { .f2d 0x10164000 : { *(.m0_conversion_fixed.__aeabi_f2d) } :code
 /DISCARD/ : { *(.ARM*) *(.comment) *(.note*) } }
