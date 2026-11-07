#ifndef MK61_BIOS_BOOT_ENTRY_H
#define MK61_BIOS_BOOT_ENTRY_H
#include <stdint.h>
extern volatile uint8_t bios_update_requested;
int bios_boot_keep_pico(void);
void bios_boot_enter(void) __attribute__((noreturn));
#endif
