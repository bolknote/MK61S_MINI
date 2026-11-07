#ifndef PICOCALC_BIOS_POWER_TEST_HAL_H
#define PICOCALC_BIOS_POWER_TEST_HAL_H
#include <stdint.h>
typedef struct { unsigned unused; } I2C_HandleTypeDef;
enum { HAL_OK=0, HAL_ERROR=1, I2C_MEMADD_SIZE_8BIT=1 };
uint32_t uptime_ms(void);
int HAL_I2C_Mem_Read(I2C_HandleTypeDef*,uint16_t,uint16_t,uint16_t,uint8_t*,uint16_t,uint32_t);
#endif
