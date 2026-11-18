#include "rtc_cache.h"
#include "hal_interface.h"

extern RTC_HandleTypeDef hrtc;

static volatile uint32_t changed;
static uint32_t published;
static uint8_t pending;

void bios_rtc_cache_changed(void) {
    const uint32_t mask = __get_PRIMASK();
    __disable_irq();
    ++changed;
    __set_PRIMASK(mask);
}

void bios_rtc_cache_poll(void) {
    const uint32_t generation = changed;
    if (!pending && generation == published && !(hrtc.Instance->CRL & RTC_CRL_SECF))
        return;

    pending = 1;
    /* CRL status flags are write-zero-to-clear. Preserve a simultaneous
     * alarm/overflow/synchronization flag, including one not yet observed.
     * Retain CNF if a caller already owns configuration mode. RTOFF is RO. */
    WRITE_REG(hrtc.Instance->CRL, (hrtc.Instance->CRL & RTC_CRL_CNF) |
              RTC_CRL_ALRF | RTC_CRL_OWF | RTC_CRL_RSF);

    RTC_DateTypeDef_u date = {.raw = 0};
    RTC_TimeTypeDef_u time = {.raw = 0};
    /* F1 GetDate also performs the software calendar rollover. Keep that
     * behavior, but run it on second changes rather than every main turn. */
    if (HAL_RTC_GetDate(&hrtc, &date._s, RTC_FORMAT_BIN) != HAL_OK ||
        HAL_RTC_GetTime(&hrtc, &time._s, RTC_FORMAT_BIN) != HAL_OK)
        return;

    const uint32_t mask = __get_PRIMASK();
    __disable_irq();
    /* An I2C setter may have interrupted the reads; a second may also have
     * elapsed between date and time. Retry without publishing a mixed pair. */
    /* RM0008 18.3.5: SECF precedes the counter update by one RTCCLK.
     * A very fast foreground can still read the previous second after
     * acknowledging SECF. Keep the refresh pending until the snapshot
     * advances; never busy-wait here or leave that old second cached. */
    if (generation == changed && !(hrtc.Instance->CRL & RTC_CRL_SECF) &&
        (generation != published || date.raw != rtc_date.raw || time.raw != rtc_time.raw)) {
        rtc_date.raw = date.raw;
        rtc_time.raw = time.raw;
        published = generation;
        pending = 0;
    }
    __set_PRIMASK(mask);
}

void bios_rtc_cache_init(void) {
    pending = 1;
    bios_rtc_cache_changed();
    bios_rtc_cache_poll();
}
