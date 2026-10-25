PHDRS { seed PT_LOAD FLAGS(5); }
SECTIONS { .seed 0x10010000 : { KEEP(*(.m0_ddiv_seed17)) } :seed
/DISCARD/ : { *(.ARM.attributes) *(.comment) *(.note*) } }
