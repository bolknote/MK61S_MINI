PHDRS { code PT_LOAD FLAGS(5); }
SECTIONS { . =0x10166000; .unit : { *(.m0_exp_small_products) } :code /DISCARD/ : { *(.ARM.exidx*) *(.ARM.extab*) *(.comment) *(.ARM.attributes) *(.note*) } }
