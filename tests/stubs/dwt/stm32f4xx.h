#ifndef MK61_TEST_DWT_STM32F4XX_H
#define MK61_TEST_DWT_STM32F4XX_H
#include <stdint.h>
struct TestDwt { volatile uint32_t CTRL = 0, CYCCNT = 0; };
struct TestCoreDebug { volatile uint32_t DEMCR = 0; };
extern TestDwt test_dwt;
extern TestCoreDebug test_core_debug;
static constexpr uint32_t SystemCoreClock = 96000000;
#define DWT (&test_dwt)
#define CoreDebug (&test_core_debug)
#define CoreDebug_DEMCR_TRCENA_Msk (1U << 24)
#define DWT_CTRL_CYCCNTENA_Msk 1U
inline void __DSB() {}
inline void __ISB() {}
inline void __NOP() { ++test_dwt.CYCCNT; }
#endif
