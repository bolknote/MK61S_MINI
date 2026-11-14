#ifndef MK61EMU_STANDALONE_HPP
#define MK61EMU_STANDALONE_HPP

// A core-only build has no Arduino board, peripherals or resident workspace.
// Keep the existing STM32 configuration path unchanged. Other platforms own
// their UI and scheduling and use the same calculator implementation.
#if defined(__ARM_ARCH_7EM__)
#define IS_CORTEX_M4() 1
#else
#define IS_CORTEX_M4() 0
#endif
#ifndef MK61_CORE_HOT_TABLES_IN_SRAM
#define MK61_CORE_HOT_TABLES_IN_SRAM 0
#endif
#ifndef MK61_CORE_MERGED_TICK
#define MK61_CORE_MERGED_TICK 1
#endif
#ifndef MK61_CORE_UNROLL_SCHEDULE
#define MK61_CORE_UNROLL_SCHEDULE 1
#endif
#ifndef MK61_ENABLE_DWT_PROFILER
#define MK61_ENABLE_DWT_PROFILER 0
#endif

#define dbg(MODULE, ...) do {} while(0)
#define dbgln(MODULE, ...) do {} while(0)
#define dbghex(MODULE, ...) do {} while(0)
#define dbghexln(MODULE, ...) do {} while(0)
#define dbgtrace(MODULE, ...) do {} while(0)

#endif
