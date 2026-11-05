#include "stm32_def.h"
#ifndef DEVICE_ID1
#define DEVICE_ID1 UID_BASE
#endif
#ifndef DEVICE_ID2
#define DEVICE_ID2 (UID_BASE+4U)
#endif
#ifndef DEVICE_ID3
#define DEVICE_ID3 (UID_BASE+8U)
#endif

#define CONCATS(a,b) a " " b
#ifndef BOARD_NAME
#if defined(STM32F411xE)
#define BOARD_NAME "BLACKPILL_F411CE"
#else
#define BOARD_NAME "BLACKPILL_F401CC"
#endif
#endif
