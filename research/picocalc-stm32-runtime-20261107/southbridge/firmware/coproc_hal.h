#ifndef COPROC_HAL_H
#define COPROC_HAL_H
#include <stdint.h>
void coproc_setup(void);
void coproc_poll(void);
void coproc_suspend(void);
void coproc_resume(void);
int coproc_storage_idle(void);
uint32_t coproc_stack_unused(void);
uint32_t coproc_time_us(void*);
void coproc_enter_sleep(void);
#endif
