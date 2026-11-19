#include "bios_sleep.h"
#include "hal_interface.h"
#include <assert.h>
#include <stdio.h>

SCB_Type test_scb;
static uint32_t ms, us, mask, ipsr, basepri, faultmask, waits, barriers, delay=900;
static unsigned leave_before_mask;
uint32_t uptime_ms(void) { return ms; }
uint32_t coproc_time_us(void *context) { assert(!context);return us; }
uint32_t __get_PRIMASK(void) { return mask; }
uint32_t __get_IPSR(void) { return ipsr; }
uint32_t __get_BASEPRI(void) { return basepri; }
uint32_t __get_FAULTMASK(void) { return faultmask; }
void __disable_irq(void) {
    if(leave_before_mask) { leave_before_mask=0;bios_sleep_write(BIOS_SLEEP_LEAVE); }
    mask=1;
}
void __set_PRIMASK(uint32_t value) { mask=value; }
void __DSB(void) { ++barriers; }
void __ISB(void) { ++barriers; }
void __WFI(void) { assert(mask==1 && test_scb.SCR==0);++waits;us+=delay; }
static void enter(void) { bios_sleep_write(BIOS_SLEEP_ENTER); }
static void leave(void) { bios_sleep_write(BIOS_SLEEP_LEAVE); }
int main(void) {
    assert(bios_sleep_status()==BIOS_SLEEP_TAG);
    for(unsigned i=0;i<10000;++i) bios_sleep_poll(1);
    assert(!waits && !bios_sleep_stats.wait_us && !mask);
    for(unsigned i=0;i<256;++i) if(i!=BIOS_SLEEP_ENTER && i!=BIOS_SLEEP_LEAVE) bios_sleep_write((uint8_t)i);
    assert(!bios_sleep_requested());
    enter();assert(bios_sleep_status()==(BIOS_SLEEP_TAG|BIOS_SLEEP_REQUESTED));
    bios_sleep_poll(0);assert(!waits); // A resident module/exchange blocks sleep.
    bios_sleep_poll(1);assert(waits==1 && bios_sleep_stats.waits==1 && bios_sleep_stats.wait_us==900 && !mask);
    assert(bios_sleep_status()==(BIOS_SLEEP_TAG|BIOS_SLEEP_REQUESTED|BIOS_SLEEP_SLEPT));
    ms=1999;bios_sleep_poll(1);assert(waits==2);
    enter();ms+=1999;bios_sleep_poll(1);assert(waits==3); // Lease renewed, SLEPT retained.
    ms+=1;bios_sleep_poll(1);assert(waits==3 && !bios_sleep_requested());
    assert(bios_sleep_status()==BIOS_SLEEP_TAG);
    enter();leave();bios_sleep_poll(1);assert(waits==3);
    // Wraparound, including the real microsecond timer wrapping during WFI.
    ms=0xfffffff0u;us=0xffffff00u;enter();ms+=1999;bios_sleep_poll(1);
    assert(waits==4 && bios_sleep_stats.wait_us==3600);ms+=1;bios_sleep_poll(1);assert(waits==4);
    enter();leave_before_mask=1;bios_sleep_poll(1);assert(waits==4 && !mask); // Wake command wins race.
    // Never disturb a caller's exception/mask or a deep-sleep configuration.
    enter();mask=1;bios_sleep_poll(1);assert(mask==1);leave();assert(mask==1);mask=0;
    enter();ipsr=1;bios_sleep_poll(1);ipsr=0;basepri=16;bios_sleep_poll(1);basepri=0;
    faultmask=1;bios_sleep_poll(1);faultmask=0;
    test_scb.SCR=4;bios_sleep_poll(1);assert(test_scb.SCR==4);
    test_scb.SCR=2;bios_sleep_poll(1);assert(test_scb.SCR==2);test_scb.SCR=0;
    assert(waits==4 && !mask);leave();
    // A pending IRQ can return WFI immediately; this cannot create fictitious elapsed time.
    delay=0;enter();bios_sleep_poll(1);leave();assert(waits==5 && bios_sleep_stats.wait_us==3600);
    assert(barriers==2*waits);
    assert(bios_sleep_stats.expired==2);
    puts("M3 retained-Pico sleep PASS: explicit commands, lease/renewal/wrap, module guard, IRQ race/masks, elapsed WFI, no clock/power/reset access");
}
