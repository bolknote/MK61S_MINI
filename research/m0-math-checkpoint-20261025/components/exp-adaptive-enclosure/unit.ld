PHDRS { code PT_LOAD FLAGS(5); }
SECTIONS { . = 0x10166000; .unit : { *(.text*) *(.rodata*) } :code /DISCARD/ : { *(.ARM.exidx*) *(.ARM.extab*) *(.comment) *(.ARM.attributes) *(.note*) } }
