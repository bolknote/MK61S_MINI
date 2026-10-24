PHDRS { code PT_LOAD FLAGS(5); }
SECTIONS { .tiny 0x10190000 : { KEEP(*(.m0_exp_tiny)) } :code /DISCARD/ : { *(.text*) *(.ARM*) *(.comment) *(.note*) } }
