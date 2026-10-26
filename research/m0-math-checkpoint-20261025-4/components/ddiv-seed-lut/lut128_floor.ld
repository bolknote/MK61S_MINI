PHDRS { code PT_LOAD FLAGS(5); }
SECTIONS { .seed 0x101e1000 : { KEEP(*(.m0_ddiv_seed17)) } :code
/DISCARD/ : { *(.ARM.exidx*) *(.ARM.extab*) *(.comment) *(.note*) *(.ARM.attributes) } }
