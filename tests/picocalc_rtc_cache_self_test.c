/* Execute the production cache against F1 counter/calendar and W0C semantics. */
#include "hal_interface.h"
#include "rtc_cache.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>

static RTC_TypeDef registers;
RTC_HandleTypeDef hrtc = {&registers, {1, 1, 1, 24}};
volatile RTC_TimeTypeDef_u rtc_time;
volatile RTC_DateTypeDef_u rtc_date;
static uint32_t counter, primask;
static unsigned date_reads, time_reads, writes, fail_date, fail_time;
static void (*after_date)(void), (*during_ack)(void);

uint32_t __get_PRIMASK(void) { return primask; }
void __disable_irq(void) { primask = 1; }
void __set_PRIMASK(uint32_t value) { primask = value; }
void test_rtc_write(volatile uint32_t *reg, uint32_t value) {
    assert(reg == &registers.CRL);
    if (during_ack) {
        void (*event)(void) = during_ack;
        during_ack = NULL;
        event();
    }
    const uint32_t status = RTC_CRL_SECF | RTC_CRL_ALRF | RTC_CRL_OWF | RTC_CRL_RSF;
    *reg = (*reg & status & value) | (*reg & RTC_CRL_RTOFF) | (value & RTC_CRL_CNF);
    ++writes;
}
static void day(void) {
    static const unsigned lengths[] = {31,28,31,30,31,30,31,31,30,31,30,31};
    RTC_DateTypeDef *d = &hrtc.DateToUpdate;
    unsigned length = lengths[d->Month - 1];
    if (d->Month == 2 && d->Year % 4 == 0) ++length;
    d->WeekDay = (uint8_t)(d->WeekDay % 7 + 1);
    if (++d->Date <= length) return;
    d->Date = 1;
    if (++d->Month <= 12) return;
    d->Month = 1;
    ++d->Year;
}
HAL_StatusTypeDef HAL_RTC_GetTime(RTC_HandleTypeDef *h, RTC_TimeTypeDef *out, uint32_t format) {
    assert(h == &hrtc && format == RTC_FORMAT_BIN);
    ++time_reads;
    if (fail_time) { --fail_time; return HAL_ERROR; }
    while (counter >= 86400) { counter -= 86400; day(); }
    out->Hours = (uint8_t)(counter / 3600);
    out->Minutes = (uint8_t)(counter / 60 % 60);
    out->Seconds = (uint8_t)(counter % 60);
    return HAL_OK;
}
HAL_StatusTypeDef HAL_RTC_GetDate(RTC_HandleTypeDef *h, RTC_DateTypeDef *out, uint32_t format) {
    ++date_reads;
    if (fail_date) { --fail_date; return HAL_ERROR; }
    RTC_TimeTypeDef ignored;
    if (HAL_RTC_GetTime(h, &ignored, format) != HAL_OK) return HAL_ERROR;
    *out = h->DateToUpdate;
    if (after_date) {
        void (*event)(void) = after_date;
        after_date = NULL;
        event();
    }
    return HAL_OK;
}
static void set(unsigned year, unsigned month, unsigned date,
                unsigned hour, unsigned minute, unsigned second) {
    hrtc.DateToUpdate = (RTC_DateTypeDef){1,(uint8_t)month,(uint8_t)date,(uint8_t)year};
    counter = hour * 3600 + minute * 60 + second;
    bios_rtc_cache_changed();
}
static void tick(unsigned seconds) {
    counter += seconds;
    registers.CRL |= RTC_CRL_SECF;
}
static void expect(unsigned year, unsigned month, unsigned date,
                   unsigned hour, unsigned minute, unsigned second) {
    assert(rtc_date._s.Year == year && rtc_date._s.Month == month && rtc_date._s.Date == date);
    assert(rtc_time._s.Hours == hour && rtc_time._s.Minutes == minute && rtc_time._s.Seconds == second);
}
static void tick_one(void) { tick(1); }
static void replace_clock(void) { set(25, 6, 7, 8, 9, 10); }
static void alarm_arrives(void) { registers.CRL |= RTC_CRL_ALRF; }

int main(void) {
    registers.CRH = 2; /* Existing alarm enable; seconds IRQ stays disabled. */
    registers.CRL = RTC_CRL_RSF | RTC_CRL_RTOFF;
    counter = 12 * 3600 + 34 * 60 + 56;
    bios_rtc_cache_init();
    expect(24,1,1,12,34,56);
    assert(date_reads == 1 && time_reads == 2 && writes == 1);
    for (unsigned i=0; i<100000; ++i) bios_rtc_cache_poll();
    assert(date_reads == 1 && time_reads == 2 && writes == 1);

    tick(1); bios_rtc_cache_poll(); expect(24,1,1,12,34,57);
    const unsigned before = date_reads;
    for (unsigned i=0; i<100000; ++i) bios_rtc_cache_poll();
    assert(date_reads == before);

    /* A simultaneous alarm must survive the second-flag acknowledgement. */
    during_ack = alarm_arrives;
    tick(1); bios_rtc_cache_poll();
    assert(registers.CRL == (RTC_CRL_ALRF | RTC_CRL_RSF | RTC_CRL_RTOFF));
    registers.CRL |= RTC_CRL_CNF | RTC_CRL_OWF;
    tick(1); bios_rtc_cache_poll();
    assert((registers.CRL & (RTC_CRL_ALRF|RTC_CRL_OWF|RTC_CRL_CNF)) ==
           (RTC_CRL_ALRF|RTC_CRL_OWF|RTC_CRL_CNF));
    registers.CRL = RTC_CRL_RSF | RTC_CRL_RTOFF;

    /* Failed reads stay pending even though the second flag was cleared. */
    RTC_DateTypeDef_u saved_date = {.raw=rtc_date.raw};
    RTC_TimeTypeDef_u saved_time = {.raw=rtc_time.raw};
    tick(1); fail_date = 1; bios_rtc_cache_poll();
    assert(rtc_date.raw == saved_date.raw && rtc_time.raw == saved_time.raw);
    bios_rtc_cache_poll(); expect(24,1,1,12,35,0);
    tick(1); fail_time = 1; bios_rtc_cache_poll();
    bios_rtc_cache_poll(); expect(24,1,1,12,35,1);
    tick(1); after_date = NULL; fail_time = 2;
    bios_rtc_cache_poll(); bios_rtc_cache_poll(); bios_rtc_cache_poll();
    expect(24,1,1,12,35,2);

    /* Rollover between the two reads must not publish an old date/new time. */
    set(24,2,28,23,59,59); bios_rtc_cache_poll();
    saved_date.raw = rtc_date.raw; saved_time.raw = rtc_time.raw;
    bios_rtc_cache_changed(); after_date = tick_one;
    bios_rtc_cache_poll();
    assert(rtc_date.raw == saved_date.raw && rtc_time.raw == saved_time.raw);
    bios_rtc_cache_poll(); expect(24,2,29,0,0,0);
    tick(86400); bios_rtc_cache_poll(); expect(24,3,1,0,0,0);
    set(23,2,28,23,59,59); bios_rtc_cache_poll();
    tick(1); bios_rtc_cache_poll(); expect(23,3,1,0,0,0);
    set(24,12,31,23,59,59); bios_rtc_cache_poll();
    tick(1); bios_rtc_cache_poll(); expect(25,1,1,0,0,0);

    /* An I2C setter preempting a refresh must win over its old local reads. */
    saved_date.raw = rtc_date.raw; saved_time.raw = rtc_time.raw;
    bios_rtc_cache_changed(); after_date = replace_clock;
    bios_rtc_cache_poll();
    assert(rtc_date.raw == saved_date.raw && rtc_time.raw == saved_time.raw);
    bios_rtc_cache_poll(); expect(25,6,7,8,9,10);
    set(25,6,7,8,9,11); bios_rtc_cache_poll(); expect(25,6,7,8,9,11);
    /* Restoring only the software calendar must also force a refresh. */
    hrtc.DateToUpdate.Date = 8; bios_rtc_cache_changed(); bios_rtc_cache_poll();
    expect(25,6,8,8,9,11);

    /* STOP does not need a seconds IRQ; a latched event covers many days. */
    const uint32_t enables = registers.CRH;
    tick(3*86400 + 5); bios_rtc_cache_poll(); expect(25,6,11,8,9,16);
    assert(registers.CRH == enables && !(registers.CRH & 1));
    primask = 1; bios_rtc_cache_changed(); bios_rtc_cache_poll(); assert(primask == 1);
    primask = 0; bios_rtc_cache_changed(); bios_rtc_cache_poll(); assert(primask == 0);
    /* Real F1 SECF precedes CNT by one RTCCLK (RM0008 18.3.5). The next
     * counter update must be observed even though SECF is already clear. */
    registers.CRL |= RTC_CRL_SECF;
    bios_rtc_cache_poll(); expect(25,6,11,8,9,16);
    assert(!(registers.CRL & RTC_CRL_SECF));
    ++counter;
    bios_rtc_cache_poll(); expect(25,6,11,8,9,17);
    const unsigned synchronized = date_reads;
    for (unsigned i=0; i<100000; ++i) bios_rtc_cache_poll();
    assert(date_reads == synchronized);
    puts("RTC cache PASS: idle, early SECF, seconds, W0C alarm race, errors, setters, midnight/leap/year, calendar restore, STOP and PRIMASK");
    return 0;
}
