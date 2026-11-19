#ifndef MK61_PICOCALC_BIOS_SLEEP_H
#define MK61_PICOCALC_BIOS_SLEEP_H
#include <stdint.h>

/* Volatile I2C ABI: no power/reset, EEPROM, option-byte or clock changes.
 * Read {REG, TAG|REQUESTED|SLEPT}. SLEPT records a WFI attempt since ENTER;
 * it does not claim the core is asleep while servicing this I2C request. */
enum {
    BIOS_SLEEP_REG = 0x10,
    BIOS_SLEEP_TAG = 0xD0,
    BIOS_SLEEP_MASK = 0xFC,
    BIOS_SLEEP_REQUESTED = 1,
    BIOS_SLEEP_SLEPT = 2,
    BIOS_SLEEP_ENTER = 0xA5,
    BIOS_SLEEP_LEAVE = 0x5A,
    BIOS_SLEEP_LEASE_MS = 2000
};
typedef struct {
    uint32_t waits;
    uint32_t wait_us;
    uint32_t expired;
} bios_sleep_statistics;
#ifdef __cplusplus
extern "C" {
#endif
extern volatile bios_sleep_statistics bios_sleep_stats;
uint8_t bios_sleep_requested(void);
#if defined(__GNUC__)
__attribute__((noinline))
#endif
uint8_t bios_sleep_status(void);
#if defined(__GNUC__)
__attribute__((noinline))
#endif
void bios_sleep_write(uint8_t command);
#if defined(__GNUC__)
__attribute__((noinline))
#endif
void bios_sleep_poll(uint8_t allowed);
#ifdef __cplusplus
}
#endif
#endif
