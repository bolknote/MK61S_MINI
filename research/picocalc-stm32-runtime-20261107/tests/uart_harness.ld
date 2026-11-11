ENTRY(harness_init)
MEMORY { FLASH (rx) : ORIGIN = 0x08000000, LENGTH = 64K
 RAM (rwx) : ORIGIN = 0x20000000, LENGTH = 20K }
SECTIONS {
 .text : { *(.text*) *(.rodata*) . = ALIGN(4); } >FLASH
 .data : { *(.data*) . = ALIGN(4); } >RAM AT>FLASH
 .bss (NOLOAD) : { *(.bss*) *(COMMON) . = ALIGN(4); } >RAM
 /DISCARD/ : { *(.ARM.exidx*) *(.ARM.extab*) *(.comment*) *(.note*) }
}
