#ifndef MK61_PICOCALC_BIOS_RTC_CACHE_H
#define MK61_PICOCALC_BIOS_RTC_CACHE_H

/* Foreground snapshots; the RTC second flag needs no additional interrupt. */
void bios_rtc_cache_init(void);
void bios_rtc_cache_poll(void);
/* Call after changing time/date or restoring the software calendar. */
void bios_rtc_cache_changed(void);

#endif
