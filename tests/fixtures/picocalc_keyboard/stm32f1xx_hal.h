#pragma once
#include <stdint.h>
#include <stddef.h>
typedef struct {unsigned id;} GPIO_TypeDef;
extern GPIO_TypeDef fake_ports[3];
uint32_t LL_GPIO_IsInputPinSet(GPIO_TypeDef*,uint32_t);
void LL_GPIO_ResetOutputPin(GPIO_TypeDef*,uint32_t);
void LL_GPIO_SetOutputPin(GPIO_TypeDef*,uint32_t);
