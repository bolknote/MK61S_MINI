#ifndef MK61_PICOCALC_BIOS_POWER_STATUS_H
#define MK61_PICOCALC_BIOS_POWER_STATUS_H
#include <stdint.h>

/* Read-only I2C register: {0x0F, tagged status byte}. No PMU writes. */
enum {
    BIOS_POWER_REG = 0x0F,
    BIOS_POWER_TAG = 0xA0,
    BIOS_POWER_TAG_MASK = 0xE0,
    BIOS_POWER_VALID = 0x10,
    BIOS_POWER_COMPLETE = 0x08,
    BIOS_POWER_CHARGING = 0x04,
    BIOS_POWER_EXTERNAL = 0x02,
    BIOS_POWER_BATTERY = 0x01,
    BIOS_POWER_POLL_MS = 500
};

/* AXP2101 STATUS1/2, read together. Match VBUS-good and VBUS-in use of
 * the board PMU. USB on the Pico itself is not a PMU VBUS measurement.
 * DONE is the charger's actual state 4, never an estimate from percent. */
static inline uint8_t bios_power_from_axp2101(int status1, int status2) {
    if(status1 < 0 || status1 > 255 || status2 < 0 || status2 > 255 ||
       ((status2 >> 5) & 3) == 3 || (status2 & 7) > 5) return BIOS_POWER_TAG;
    uint8_t value = BIOS_POWER_TAG | BIOS_POWER_VALID;
    if(status1 & 0x08) value |= BIOS_POWER_BATTERY;
    if((status1 & 0x20) && !(status2 & 0x08)) value |= BIOS_POWER_EXTERNAL;
    if((value & (BIOS_POWER_BATTERY | BIOS_POWER_EXTERNAL)) ==
                 (BIOS_POWER_BATTERY | BIOS_POWER_EXTERNAL)) {
        if((status2 & 7) == 4) value |= BIOS_POWER_COMPLETE;
        else if(((status2 >> 5) & 3) == 1) value |= BIOS_POWER_CHARGING;
    }
    return value;
}

static inline int bios_power_valid_encoding(uint8_t value) {
    if((value & BIOS_POWER_TAG_MASK) != BIOS_POWER_TAG) return 0;
    if(!(value & BIOS_POWER_VALID)) return value == BIOS_POWER_TAG;
    const unsigned charge = value & (BIOS_POWER_CHARGING | BIOS_POWER_COMPLETE);
    if(charge == (BIOS_POWER_CHARGING | BIOS_POWER_COMPLETE)) return 0;
    return !charge || (value & (BIOS_POWER_BATTERY | BIOS_POWER_EXTERNAL)) ==
                              (BIOS_POWER_BATTERY | BIOS_POWER_EXTERNAL);
}

#ifdef __cplusplus
extern "C" {
#endif
void bios_power_refresh(uint8_t pmu_online);
void bios_power_poll(uint8_t pmu_online);
#ifdef __cplusplus
}
#endif
#endif
