ENTRY(module_entry)
SECTIONS {
 . = 0x20000000;
 .image : { KEEP(*(.text.module_entry)) *(.text*) *(.rodata*) *(.data*) . = ALIGN(4); }
 __image_end = .;
 .bss (NOLOAD) : { *(.bss*) *(COMMON) . = ALIGN(4); }
 __memory_end = .;
 /DISCARD/ : { *(.ARM.exidx*) *(.ARM.extab*) *(.comment*) *(.note*) }
 ASSERT(__memory_end - 0x20000000 <= 6144, "STM3 module exceeds SRAM budget")
}
