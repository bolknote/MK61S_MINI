#include "power_status.h"
#include "hal_interface.h"
#include "regs.h"

extern I2C_HandleTypeDef hi2c2;
static uint32_t last_refresh;

/* Foreground only. Slave-I2C callbacks return the cached byte and never
 * perform a nested transaction with the PMU. A failed read clears VALID. */
void bios_power_refresh(uint8_t pmu_online) {
    uint8_t raw[2] = {0}, value = BIOS_POWER_TAG;
    last_refresh = uptime_ms();
    if(pmu_online && HAL_I2C_Mem_Read(&hi2c2, 0x68, 0x00,
           I2C_MEMADD_SIZE_8BIT, raw, sizeof(raw), 4) == HAL_OK)
        value = bios_power_from_axp2101(raw[0], raw[1]);
    /* Telemetry is volatile, not an EEPROM setting: don't mark registers
     * unsynced or postpone pending settings writes on every refresh. */
    uint8_t* const regs = reg_raw_access();
    regs[BIOS_POWER_REG] = value;
    /* Preserve legacy percent, but never leave its old false charging flag
     * set by the insertion/DONE interrupt handlers. */
    regs[REG_ID_BAT] = (regs[REG_ID_BAT] & 0x7F) |
                      ((value & BIOS_POWER_CHARGING) ? 0x80 : 0);
}

void bios_power_poll(uint8_t pmu_online) {
    if((uint32_t)(uptime_ms() - last_refresh) >= BIOS_POWER_POLL_MS)
        bios_power_refresh(pmu_online);
}
