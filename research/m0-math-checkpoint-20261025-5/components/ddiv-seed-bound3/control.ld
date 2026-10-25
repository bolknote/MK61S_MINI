PHDRS { code PT_LOAD FLAGS(5); }
SECTIONS { .unit 0x101e1000 : { KEEP(*(.unit)) } :code
/DISCARD/ : { *(.ARM.exidx*) *(.ARM.extab*) *(.comment) *(.note*) *(.ARM.attributes) } }
