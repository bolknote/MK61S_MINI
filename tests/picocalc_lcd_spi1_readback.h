#ifndef PICOCALC_LCD_SPI1_READBACK_H
#define PICOCALC_LCD_SPI1_READBACK_H

#include <stdbool.h>
#include <stdint.h>

/* Test builds replace only the hardware access, preserving the command
 * protocol and APP control flow on the host. */
#ifdef PICOCALC_LCD_READBACK_HOST
bool picocalc_lcd_test_begin(void);
bool picocalc_lcd_test_end(void);
bool picocalc_lcd_test_lines(void *,bool,bool);
bool picocalc_lcd_test_transfer(void *,uint8_t,uint8_t *);
static bool hw_begin(void){return picocalc_lcd_test_begin();}
static bool hw_end(void){return picocalc_lcd_test_end();}
static bool hw_lines(void *ctx,bool selected,bool data){return picocalc_lcd_test_lines(ctx,selected,data);}
static bool hw_transfer(void *ctx,uint8_t out,uint8_t *in){return picocalc_lcd_test_transfer(ctx,out,in);}
#else
/* RP2040 SPI1 and SIO registers. LCD SCK/TX/RX/CS/DC are GP10/11/12/13/14.
 * Save the firmware's SPI format and divider, read at <=2 MHz, and restore
 * them after every bounded set of reads. No DMA is active at this boundary. */
#define REG(address) (*(volatile uint32_t *)(uintptr_t)(address))
#define SPI_CR0 REG(0x40040000u)
#define SPI_CR1 REG(0x40040004u)
#define SPI_DR REG(0x40040008u)
#define SPI_SR REG(0x4004000cu)
#define SPI_CPSR REG(0x40040010u)
#define GPIO_SET REG(0xd0000014u)
#define GPIO_CLR REG(0xd0000018u)
#define LCD_CS (1u<<13)
#define LCD_DC (1u<<14)
static uint32_t saved_cr0,saved_cr1,saved_cpsr;
static bool hw_idle(void) {
    for(unsigned i=0;i<1000000u;++i)if(!(SPI_SR&16u))return true;
    return false;
}
static bool hw_begin(void) {
    if(!hw_idle() || (SPI_CR0&15u)!=7u || (SPI_CR1&7u)!=2u)return false;
    for(unsigned i=0;i<64u && (SPI_SR&4u);++i)(void)SPI_DR;
    if(SPI_SR&4u)return false;
    saved_cr0=SPI_CR0;saved_cr1=SPI_CR1;saved_cpsr=SPI_CPSR;
    SPI_CR1=saved_cr1&~2u;SPI_CR0=saved_cr0&~0xff00u;SPI_CPSR=24u;SPI_CR1=saved_cr1;
    GPIO_SET=LCD_CS|LCD_DC;
    return true;
}
static bool hw_end(void) {
    const bool idle=hw_idle();GPIO_SET=LCD_CS|LCD_DC;
    SPI_CR1=saved_cr1&~2u;SPI_CR0=saved_cr0;SPI_CPSR=saved_cpsr;SPI_CR1=saved_cr1;
    return idle;
}
static bool hw_lines(void *ctx,bool selected,bool data) {
    (void)ctx;
    if(!hw_idle()){GPIO_SET=LCD_CS|LCD_DC;return false;}
    if(!selected)GPIO_SET=LCD_CS;
    if(data)GPIO_SET=LCD_DC;else GPIO_CLR=LCD_DC;
    if(selected)GPIO_CLR=LCD_CS;
    return true;
}
static bool hw_transfer(void *ctx,uint8_t out,uint8_t *in) {
    (void)ctx;unsigned i;
    for(i=0;i<1000000u && !(SPI_SR&2u);++i){}
    if(i==1000000u)return false;
    SPI_DR=out;
    for(i=0;i<1000000u && !(SPI_SR&4u);++i){}
    if(i==1000000u)return false;
    *in=(uint8_t)SPI_DR;return true;
}
#endif

#endif
