PHDRS { code PT_LOAD FLAGS(5); }
SECTIONS { .d2f 0x10163000 : { *(.text.__aeabi_d2f) } :code
 /DISCARD/ : { *(.ARM*) *(.comment) *(.note*) } }
