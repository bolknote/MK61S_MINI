#ifndef STM3_PICO_UART1_H
#define STM3_PICO_UART1_H
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif
typedef struct {
 uint32_t(*micros)(void*);
 void*context;
 uint32_t gpio[2],pad[2],uart[8],reset_before,errors,actual_baud;
 int ready;
} stm3_pico_uart1;
int stm3_pico_uart1_begin(stm3_pico_uart1*,uint32_t(*)(void*),void*,uint32_t,uint32_t);
void stm3_pico_uart1_end(stm3_pico_uart1*);
uint32_t stm3_pico_uart1_micros(void*);
int stm3_pico_uart1_send(void*,const uint8_t*,unsigned,uint32_t);
int stm3_pico_uart1_read(void*,uint32_t);
#ifdef __cplusplus
}
#endif
#endif
