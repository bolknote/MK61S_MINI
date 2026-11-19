#include "bios_sleep.h"
#include "hal_interface.h"

static volatile uint32_t renewed;
static volatile uint8_t requested, slept;
volatile bios_sleep_statistics bios_sleep_stats;

uint8_t bios_sleep_requested(void) { return requested; }
uint8_t bios_sleep_status(void) {
    return BIOS_SLEEP_TAG | (requested ? BIOS_SLEEP_REQUESTED : 0) |
           (slept ? BIOS_SLEEP_SLEPT : 0);
}
void bios_sleep_write(uint8_t command) {
    if (command != BIOS_SLEEP_ENTER && command != BIOS_SLEEP_LEAVE) return;
    const uint32_t mask = __get_PRIMASK();
    __disable_irq();
    if (command == BIOS_SLEEP_ENTER) {
        renewed = uptime_ms();
        if (!requested) slept = 0;
        requested = 1;
    } else {
        requested = slept = 0;
    }
    __set_PRIMASK(mask);
}
void bios_sleep_poll(uint8_t allowed) {
    if (!requested || __get_PRIMASK() || __get_IPSR() || __get_BASEPRI() || __get_FAULTMASK()) return;
    __disable_irq();
    if ((uint32_t)(uptime_ms() - renewed) >= BIOS_SLEEP_LEASE_MS) {
        requested = slept = 0;
        ++bios_sleep_stats.expired;
    }
    /* Keep clocks, TIM2/SysTick, I2C, UART/DMA, GPIO, RTC and PMU intact.
     * A pending IRQ also wakes WFI under PRIMASK, then executes at unmask.
     * The existing 1 ms timer bounds keyboard/PMU foreground service gaps. */
    if (requested && allowed && !(SCB->SCR & (SCB_SCR_SLEEPDEEP_Msk | SCB_SCR_SLEEPONEXIT_Msk))) {
        const uint32_t begin = coproc_time_us(0);
        slept = 1;
        ++bios_sleep_stats.waits;
        __DSB();
        __WFI();
        __ISB();
        bios_sleep_stats.wait_us += coproc_time_us(0) - begin;
    }
    __set_PRIMASK(0);
}
