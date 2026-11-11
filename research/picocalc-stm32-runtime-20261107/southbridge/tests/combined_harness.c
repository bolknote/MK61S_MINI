// Only physical peripherals are modeled. Compile the genuine ported runtime,
// UART/DMA bridge, clock function, I2C callbacks, FIFO and backlight code.
#include "hal_interface.h"
#include "stm3_uart_dma.h"
#include "backlight.h"
#include "i2cs.h"
#include "fifo.h"
#include "regs.h"
#include "rtc.h"
#include "eeprom.h"
#include "stm3_runtime.h"
#include <stddef.h>
uint32_t SystemCoreClock=8000000u;
volatile uint32_t systicks_counter;
volatile uint8_t rtc_reg_xor_events;
volatile RTC_TimeTypeDef_u rtc_time,rtc_alarm_time;
volatile RTC_DateTypeDef_u rtc_date,rtc_alarm_date;
I2C_HandleTypeDef hi2c1,hi2c2;
RTC_HandleTypeDef hrtc;
TIM_HandleTypeDef htim1,htim2,htim3;
uint8_t io_matrix[9],js_bits;
static uint8_t regs[REG_ID_LAST],tx_bytes[10],tx_n;
static uint8_t*rx_at;
static uint16_t rx_n,hold=10;
static uint32_t modeled_stop,modeled_sleep,modeled_tick_init;
uint8_t reg_get_value(enum reg_id r){return regs[r];}
void reg_set_value(enum reg_id r,uint8_t v){regs[r]=v;}
uint8_t reg_is_bit_set(enum reg_id r,uint8_t bit){return regs[r]&bit;}
uint8_t keyboard_get_capslock(void){return 0;}
uint8_t keyboard_get_numlock(void){return 0;}
uint16_t keyboard_get_hold_period(void){return hold;}
void keyboard_set_hold_period(uint16_t value){hold=value;}
HAL_StatusTypeDef HAL_I2C_Slave_Seq_Receive_IT(I2C_HandleTypeDef*h,uint8_t*p,uint16_t n,uint32_t flags){
 (void)h;(void)flags;rx_at=p;rx_n=n;return HAL_OK;
}
HAL_StatusTypeDef HAL_I2C_Slave_Seq_Transmit_IT(I2C_HandleTypeDef*h,uint8_t*p,uint16_t n,uint32_t flags){
 (void)h;(void)flags;if(n>10)__builtin_trap();for(unsigned i=0;i<n;++i)tx_bytes[i]=p[i];tx_n=(uint8_t)n;return HAL_OK;
}
HAL_StatusTypeDef HAL_I2C_EnableListen_IT(I2C_HandleTypeDef*h){(void)h;return HAL_OK;}
HAL_StatusTypeDef HAL_I2C_DeInit(I2C_HandleTypeDef*h){(void)h;return HAL_OK;}
HAL_StatusTypeDef HAL_I2C_Init(I2C_HandleTypeDef*h){(void)h;return HAL_OK;}
uint32_t HAL_I2C_GetError(I2C_HandleTypeDef*h){(void)h;return HAL_I2C_ERROR_AF;}
HAL_StatusTypeDef HAL_RTC_SetDate(RTC_HandleTypeDef*h,RTC_DateTypeDef*d,uint32_t f){(void)h;(void)d;(void)f;return HAL_OK;}
HAL_StatusTypeDef HAL_RTC_SetTime(RTC_HandleTypeDef*h,RTC_TimeTypeDef*d,uint32_t f){(void)h;(void)d;(void)f;return HAL_OK;}
void i2cs_fill_buffer_RTC_date(uint8_t*const b,const volatile RTC_DateTypeDef*const p){(void)b;(void)p;}
void i2cs_fill_buffer_RTC_time(uint8_t*const b,const volatile RTC_TimeTypeDef*const p){(void)b;(void)p;}
void i2cs_RTC_date_from_buffer(volatile RTC_DateTypeDef*const p,const uint8_t*const b){(void)b;(void)p;}
void i2cs_RTC_time_from_buffer(volatile RTC_TimeTypeDef*const p,const uint8_t*const b){(void)b;(void)p;}
uint32_t HAL_RCC_GetPCLK1Freq(void){return 36000000u;}
HAL_StatusTypeDef HAL_InitTick(uint32_t priority){(void)priority;++modeled_tick_init;return HAL_OK;}
HAL_StatusTypeDef HAL_TIM_Base_Stop_IT(TIM_HandleTypeDef*h){(void)h;return HAL_OK;}
HAL_StatusTypeDef HAL_TIM_Base_Start_IT(TIM_HandleTypeDef*h){(void)h;return HAL_OK;}
void HAL_SuspendTick(void){}
void HAL_ResumeTick(void){}
void HAL_PWR_EnterSTOPMode(uint32_t r,uint8_t e){(void)r;(void)e;++modeled_stop;}
void HAL_PWR_EnterSLEEPMode(uint32_t r,uint8_t e){(void)r;(void)e;++modeled_sleep;}
void Error_Handler(void){__builtin_trap();}
__attribute__((used)) void harness_init(void){
 htim1.Instance=TIM1;htim2.Instance=TIM2;htim3.Instance=TIM3;
 TIM1->ARR=800;TIM3->ARR=512;TIM2->ARR=999;TIM2->CNT=0;TIM2->SR=0;
 regs[REG_ID_BAT]=173;fifo_flush();coproc_setup();coproc_resume();
}
__attribute__((used)) uint32_t harness_poll(void){coproc_poll();return coproc_stack_unused();}
__attribute__((used)) uint32_t harness_arena_offset(void){return (uint32_t)offsetof(stm3_runtime,arena);}
__attribute__((used)) const uint8_t*harness_rx_buffer(void){return stm3_uart_rx_buffer();}
__attribute__((used)) void harness_rx_irq(void){DMA1_Channel3_IRQHandler();}
__attribute__((used)) uint32_t harness_storage_idle(void){return (uint32_t)coproc_storage_idle();}
__attribute__((used)) uint32_t harness_suspend(void){coproc_suspend();return 0;}
__attribute__((used)) uint32_t harness_resume(void){coproc_resume();return 0;}
__attribute__((used)) uint32_t harness_micros(void){return coproc_time_us(0);}
__attribute__((used)) uint32_t harness_set_clock(uint32_t ms){systicks_counter=ms;return ms;}
__attribute__((used)) uint32_t harness_clock72(void){SystemClock_Config();return SystemCoreClock;}
__attribute__((used)) uint32_t harness_sleep(void){coproc_enter_sleep();return (modeled_stop<<16)|modeled_sleep;}
__attribute__((used)) uint32_t harness_enqueue(uint32_t state,uint32_t key){
 const struct fifo_item item={.state=(enum key_state)state,.key=(uint8_t)key};return fifo_enqueue(item);
}
__attribute__((used)) uint32_t harness_backlight_cycle(uint32_t which){
 if(which==0)lcd_backlight_update_up();else if(which==1)lcd_backlight_update_down();else kbd_backlight_update_loop();
 return ((uint32_t)regs[REG_ID_BKL]<<8)|regs[REG_ID_BK2];
}
__attribute__((used)) uint32_t harness_backlight_off(void){lcd_backlight_off();kbd_backlight_off();return 0;}
__attribute__((used)) uint32_t harness_backlight_on(void){lcd_backlight_on();kbd_backlight_on();return 0;}
__attribute__((used)) uint32_t harness_i2c(uint32_t reg,uint32_t is_write,uint32_t value){
 i2cs_state=I2CS_STATE_IDLE;tx_n=0;
 HAL_I2C_AddrCallback(&hi2c1,I2C_DIRECTION_TRANSMIT,0x3e);
 if(rx_n!=1)__builtin_trap();*rx_at=(uint8_t)(reg|(is_write?0x80u:0));
 HAL_I2C_SlaveRxCpltCallback(&hi2c1);
 if(is_write){if(rx_n!=1)__builtin_trap();*rx_at=(uint8_t)value;HAL_I2C_SlaveRxCpltCallback(&hi2c1);}
 HAL_I2C_ListenCpltCallback(&hi2c1); // STOP, then read as the stock Pico driver.
 HAL_I2C_AddrCallback(&hi2c1,I2C_DIRECTION_RECEIVE,0x3e);
 if(tx_n!=2)__builtin_trap();
 HAL_I2C_ListenCpltCallback(&hi2c1);
 return ((uint32_t)tx_bytes[0]<<8)|tx_bytes[1];
}
void*memcpy(void*d,const void*s,size_t n){volatile uint8_t*p=d;const uint8_t*q=s;while(n--)*p++=*q++;return d;}
void*memset(void*d,int v,size_t n){volatile uint8_t*p=d;while(n--)*p++=(uint8_t)v;return d;}
void*memmove(void*d,const void*s,size_t n){uint8_t*p=d;const uint8_t*q=s;if(p<q){for(size_t i=0;i<n;++i)p[i]=q[i];}else{while(n){--n;p[n]=q[n];}}return d;}
