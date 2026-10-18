/* HIL only: never bundled. The runner requires explicit fault-test opt-in. */
#include "mk61_app.h"
#ifndef PICO_SOFTWARE_HANG
#define PICO_SOFTWARE_HANG 0
#endif
int main(void) {
    const mk61_app_services* service=mk61_app_get_services(mk61_api,MK61_SERVICE_CAP_DEBUG_IO);
    if(!service) return 1;
#if PICO_SOFTWARE_HANG
    char message[]="PICO SOFTWARE INTENTIONAL WATCHDOG\n";
    service->call(MK61_SERVICE_DEBUG_WRITE,sizeof(message)-1,0,0,message);
    mk61_api->delay_ms(150);
    for(;;) __asm volatile("nop");
#else
    char message[]="PICO SOFTWARE INTENTIONAL HARDFAULT\n";
    service->call(MK61_SERVICE_DEBUG_WRITE,sizeof(message)-1,0,0,message);
    mk61_api->delay_ms(150);
    __asm volatile("movs r4, #44\nmovs r5, #55\n.hword 0xDE00\n" ::: "r4","r5","memory");
    return 2;
#endif
}
