#ifndef MK61_PICOCALC_PMU_ASYNC_H
#define MK61_PICOCALC_PMU_ASYNC_H
#include "hal_interface.h"
#include "power_status.h"

/* Boot configuration keeps the original HAL contract. After start, legacy
 * reads use the last complete snapshot and writes enter a bounded/coalesced
 * register queue. Only this service owns the running PMU I2C2 peripheral. */
HAL_StatusTypeDef bios_pmu_mem_read(I2C_HandleTypeDef*,uint16_t,uint16_t,uint16_t,uint8_t*,uint16_t,uint32_t);
HAL_StatusTypeDef bios_pmu_mem_write(I2C_HandleTypeDef*,uint16_t,uint16_t,uint16_t,uint8_t*,uint16_t,uint32_t);
uint8_t bios_pmu_legacy_ready(void);
void bios_pmu_legacy_complete(void);
void bios_power_legacy_battery(uint8_t value);
void bios_pmu_quiesce(void);
void bios_pmu_resume(void);
void bios_pmu_sync_irq_masks(void); /* Implemented beside the legacy AXP IRQ masks. */
void I2C2_EV_IRQHandler(void);
void I2C2_ER_IRQHandler(void);

typedef struct {
    uint32_t starts,completions,errors,timeouts,busy_guards;
    uint32_t recoveries,recovery_failures,snapshots,incoherent;
    uint32_t cached_reads,queued_writes,last_error;
} bios_pmu_statistics;
const volatile bios_pmu_statistics* bios_pmu_counters(void);
#endif
