PHDRS { square PT_LOAD FLAGS(5); } SECTIONS { .square 0x10000000 : { *(.audit_square) } :square /DISCARD/ : { *(.ARM*) *(.comment) *(.note*) } }
