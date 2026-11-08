#ifndef MK61_STM3_CRC_F103_H
#define MK61_STM3_CRC_F103_H
#include <stddef.h>
#include <stdint.h>
#include "stm32f1xx.h"

/* RM0008 section 4: fixed MSB-first polynomial 0x04C11DB7, whole
 * 32-bit writes only. RBIT converts the wire's reflected IEEE CRC32;
 * the last 0..3 bytes continue the reflected accumulator in software. */
static inline uint32_t stm3_f103_crc32(const void* data,size_t bytes) {
    const uint8_t* p=(const uint8_t*)data;
    uint32_t value=~0u;
    if(bytes>=4) {
        const uint32_t mask=__get_PRIMASK();__disable_irq();
        const uint32_t enabled=RCC->AHBENR&RCC_AHBENR_CRCEN;
        RCC->AHBENR|=RCC_AHBENR_CRCEN;(void)RCC->AHBENR;
        CRC->CR=CRC_CR_RESET;
        do {
            const uint32_t word=(uint32_t)p[0]|((uint32_t)p[1]<<8)|
                ((uint32_t)p[2]<<16)|((uint32_t)p[3]<<24);
            CRC->DR=__RBIT(word);p+=4;bytes-=4;
        } while(bytes>=4);
        value=__RBIT(CRC->DR);
        if(!enabled)RCC->AHBENR&=~RCC_AHBENR_CRCEN;
        __set_PRIMASK(mask);
    }
    while(bytes--) {
        value^=*p++;
        for(unsigned bit=0;bit<8;++bit)value=(value>>1)^((value&1)?0xedb88320u:0u);
    }
    return ~value;
}
#endif
