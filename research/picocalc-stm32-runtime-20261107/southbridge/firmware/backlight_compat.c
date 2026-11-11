// Stock PicoCalc register semantics: raw 0..255 values, exact read-back.
// Keep Southbridge's pin/timer ownership and keyboard shortcut entry points.
#include "backlight.h"
#include "hal_interface.h"
#include "regs.h"
extern TIM_HandleTypeDef htim1,htim3;
static uint32_t duty(TIM_HandleTypeDef*timer,uint8_t value){
 return ((timer->Instance->ARR+1u)*value+127u)/255u;
}
void lcd_backlight_update_from_reg(void){
 __HAL_TIM_SET_COMPARE(&htim1,TIM_CHANNEL_1,duty(&htim1,reg_get_value(REG_ID_BKL)));
}
void lcd_backlight_on(void){lcd_backlight_update_from_reg();}
void lcd_backlight_off(void){__HAL_TIM_SET_COMPARE(&htim1,TIM_CHANNEL_1,0);}
void lcd_backlight_update(uint8_t value){
 reg_set_value(REG_ID_BKL,value);lcd_backlight_update_from_reg();
}
void lcd_backlight_update_up(void){
 unsigned value=((unsigned)reg_get_value(REG_ID_BKL)+16u)/16u*16u;
 lcd_backlight_update((uint8_t)(value>240u?240u:value));
}
void lcd_backlight_update_down(void){
 const unsigned value=(unsigned)reg_get_value(REG_ID_BKL)/16u*16u;
 lcd_backlight_update((uint8_t)(value<=16u?16u:value-16u));
}
void kbd_backlight_on(void){
 __HAL_TIM_SET_COMPARE(&htim3,TIM_CHANNEL_3,duty(&htim3,reg_get_value(REG_ID_BK2)));
}
void kbd_backlight_off(void){__HAL_TIM_SET_COMPARE(&htim3,TIM_CHANNEL_3,0);}
void kbd_backlight_update(uint8_t value){reg_set_value(REG_ID_BK2,value);kbd_backlight_on();}
void kbd_backlight_update_loop(void){
 const unsigned value=((unsigned)reg_get_value(REG_ID_BK2)+32u)/32u*32u;
 kbd_backlight_update((uint8_t)(value>240u?0u:value));
}
