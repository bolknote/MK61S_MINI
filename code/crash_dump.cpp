#include "crash_dump.hpp"

#include "config.h"

#if MK61_CRASH_DUMP_SUPPORTED
  #include <Arduino.h>
  #include <stm32f4xx.h>
#endif

namespace crash_dump {
namespace {

constexpr u32 fnv1a_character(u32 state, char value) {
  return (state ^ (u8) value) * 16777619UL;
}

constexpr u32 fnv1a_text(const char* text, u32 state = 2166136261UL) {
  return *text == 0 ? state : fnv1a_text(
      text + 1, fnv1a_character(state, *text));
}

#if defined(MK61_BOARD_CLASSIC_V2)
static constexpr char BUILD_PROFILE[] = "classic-v2-uc1609";
#elif defined(MK61_BOARD_CLASSIC_V3)
static constexpr char BUILD_PROFILE[] = "classic-v3-uc1609";
#elif defined(MK61_BOARD_40TH)
static constexpr char BUILD_PROFILE[] = "40th-uc1609";
#elif defined(MK61_DISPLAY_UC1609)
// Compatibility selector retained for sketches that predate the explicit
// Classic V2/V3 board profiles.
static constexpr char BUILD_PROFILE[] = "uc1609-compat";
#elif defined(MK61_OLED1602_WS0010)
  #if defined(REVISION_V2)
static constexpr char BUILD_PROFILE[] = "mini-v2-ws0010";
  #else
static constexpr char BUILD_PROFILE[] = "mini-v3-ws0010";
  #endif
#elif defined(MK61_LCD1602_A02)
  #if defined(REVISION_V2)
static constexpr char BUILD_PROFILE[] = "mini-v2-a02";
  #else
static constexpr char BUILD_PROFILE[] = "mini-v3-a02";
  #endif
#else
  #if defined(REVISION_V2)
static constexpr char BUILD_PROFILE[] = "mini-v2-a00";
  #else
static constexpr char BUILD_PROFILE[] = "mini-v3-a00";
  #endif
#endif

static constexpr u32 BUILD_ID =
  fnv1a_text(BUILD_PROFILE, fnv1a_text(FIRMWARE_VER));

#if MK61_CRASH_DUMP_SUPPORTED

static constexpr usize EMERGENCY_STACK_SIZE = 512;
static constexpr usize BASIC_FRAME_WORDS = 8;
static constexpr usize SRAM_FIRST_ADDRESS = 0x20000000UL;
static constexpr u32 CFSR_STACKING_ERRORS = (1UL << 4) | (1UL << 12);

extern "C" {
extern u8 _ebss;
extern u8 _estack;

__attribute__((used, aligned(8), section(".bss.mk61_crash_stack")))
u8 mk61_crash_emergency_stack[EMERGENCY_STACK_SIZE];

__attribute__((used, aligned(8), section(".noinit.mk61_crash")))
volatile crash_dump_format::Record mk61_crash_record;
}

static volatile u32 runtime_state;
static volatile u32 runtime_detail;
static volatile u32 runtime_uptime_ms;
static volatile u32 classic_ticks;
static volatile u32 classic_steps;
static volatile u32 classic_missed;
static volatile u32 classic_pending;
static u32 reset_flags;
static bool layout_valid;

static void begin_record_update(void) {
  mk61_crash_record.magic = 0;
  __DSB();
}

static void finish_record_update(void) {
  mk61_crash_record.crc32 =
      crash_dump_format::calculate_crc(mk61_crash_record);
  __DSB();
  mk61_crash_record.magic = crash_dump_format::MAGIC;
  __DSB();
}

static bool frame_in_sram(usize address) {
  const usize ram_end = (usize) &_estack;
  return (address & 3U) == 0 &&
         address >= SRAM_FIRST_ADDRESS &&
         address <= ram_end - BASIC_FRAME_WORDS * sizeof(u32);
}

static void fill_invalid_frame(void) {
  mk61_crash_record.stacked_r0 = crash_dump_format::INVALID_STACK_WORD;
  mk61_crash_record.stacked_r1 = crash_dump_format::INVALID_STACK_WORD;
  mk61_crash_record.stacked_r2 = crash_dump_format::INVALID_STACK_WORD;
  mk61_crash_record.stacked_r3 = crash_dump_format::INVALID_STACK_WORD;
  mk61_crash_record.stacked_r12 = crash_dump_format::INVALID_STACK_WORD;
  mk61_crash_record.stacked_lr = crash_dump_format::INVALID_STACK_WORD;
  mk61_crash_record.stacked_pc = crash_dump_format::INVALID_STACK_WORD;
  mk61_crash_record.stacked_xpsr = crash_dump_format::INVALID_STACK_WORD;
}

static void fill_frame(const u32* frame) {
  mk61_crash_record.stacked_r0 = frame[0];
  mk61_crash_record.stacked_r1 = frame[1];
  mk61_crash_record.stacked_r2 = frame[2];
  mk61_crash_record.stacked_r3 = frame[3];
  mk61_crash_record.stacked_r12 = frame[4];
  mk61_crash_record.stacked_lr = frame[5];
  mk61_crash_record.stacked_pc = frame[6];
  mk61_crash_record.stacked_xpsr = frame[7];
}

extern "C" __attribute__((noreturn, noinline, used, externally_visible))
void mk61_crash_fault_entry(u32 exc_return, u32 original_msp,
                            u32 original_psp,
                            const u32* callee_saved) {
  const u32 captured_primask = __get_PRIMASK();
  __disable_irq();

  const bool previous_valid = crash_dump_format::valid(mk61_crash_record);
  const u32 next_sequence = previous_valid
      ? mk61_crash_record.sequence + 1U : 1U;

  begin_record_update();
  mk61_crash_record.version = crash_dump_format::VERSION;
  mk61_crash_record.size = sizeof(crash_dump_format::Record);
  mk61_crash_record.sequence = next_sequence;
  mk61_crash_record.exception_number = __get_IPSR() & 0x1FFU;
  mk61_crash_record.exc_return = exc_return;
  mk61_crash_record.msp = original_msp;
  mk61_crash_record.psp = original_psp;
  mk61_crash_record.control = __get_CONTROL();
  mk61_crash_record.primask = captured_primask;
  mk61_crash_record.basepri = __get_BASEPRI();
  mk61_crash_record.faultmask = __get_FAULTMASK();

  mk61_crash_record.cfsr = SCB->CFSR;
  mk61_crash_record.hfsr = SCB->HFSR;
  mk61_crash_record.dfsr = SCB->DFSR;
  mk61_crash_record.afsr = SCB->AFSR;
  mk61_crash_record.mmfar = SCB->MMFAR;
  mk61_crash_record.bfar = SCB->BFAR;
  mk61_crash_record.icsr = SCB->ICSR;
  mk61_crash_record.shcsr = SCB->SHCSR;
  mk61_crash_record.rcc_csr_at_fault = RCC->CSR;
  mk61_crash_record.rcc_csr_after_reboot = 0;
  mk61_crash_record.build_id = BUILD_ID;

  u32 flags = 0;
  const bool uses_psp = (exc_return & (1UL << 2)) != 0;
  const bool extended_frame = (exc_return & (1UL << 4)) == 0;
  if(uses_psp) flags |= crash_dump_format::STACK_USED_PSP;
  if(extended_frame) flags |= crash_dump_format::EXTENDED_FP_FRAME;
  const usize stack_address = uses_psp ? original_psp : original_msp;
  // В extended Cortex-M4F frame базовый r0..xPSR остаётся первым по SP;
  // S0..S15/FPSCR расположены выше него, а не перед ним.
  const usize frame_address = stack_address;
  if((mk61_crash_record.cfsr & CFSR_STACKING_ERRORS) == 0 &&
     frame_address >= stack_address && frame_in_sram(frame_address)) {
    fill_frame((const u32*) frame_address);
    flags |= crash_dump_format::FRAME_VALID;
  } else {
    fill_invalid_frame();
  }
  if(callee_saved != nullptr) {
    mk61_crash_record.r4 = callee_saved[0];
    mk61_crash_record.r5 = callee_saved[1];
    mk61_crash_record.r6 = callee_saved[2];
    mk61_crash_record.r7 = callee_saved[3];
    mk61_crash_record.r8 = callee_saved[4];
    mk61_crash_record.r9 = callee_saved[5];
    mk61_crash_record.r10 = callee_saved[6];
    mk61_crash_record.r11 = callee_saved[7];
    flags |= crash_dump_format::CALLEE_SAVED_VALID;
  }
  mk61_crash_record.capture_flags = flags;

  mk61_crash_record.runtime_uptime_ms = runtime_uptime_ms;
  mk61_crash_record.runtime_state = runtime_state;
  mk61_crash_record.runtime_detail = runtime_detail;
  mk61_crash_record.classic_ticks = classic_ticks;
  mk61_crash_record.classic_steps = classic_steps;
  mk61_crash_record.classic_missed = classic_missed;
  mk61_crash_record.classic_pending = classic_pending;
  finish_record_update();
  NVIC_SystemReset();
  while(true) {}
}

#define MK61_DEFINE_FAULT_HANDLER(name)                                    \
  extern "C" __attribute__((naked, used, externally_visible))             \
  void name(void) {                                                        \
    __asm__ volatile(                                                      \
      "mov r0, lr\n"                                                      \
      "mrs r1, msp\n"                                                     \
      "mrs r2, psp\n"                                                     \
      "movw r3, #:lower16:mk61_crash_emergency_stack\n"                   \
      "movt r3, #:upper16:mk61_crash_emergency_stack\n"                   \
      "add.w r3, r3, #512\n"                                              \
      "bic r3, r3, #7\n"                                                  \
      "stmdb r3!, {r4-r11}\n"                                             \
      "msr msp, r3\n"                                                     \
      "b mk61_crash_fault_entry\n");                                      \
  }

MK61_DEFINE_FAULT_HANDLER(HardFault_Handler)
MK61_DEFINE_FAULT_HANDLER(MemManage_Handler)
MK61_DEFINE_FAULT_HANDLER(BusFault_Handler)
MK61_DEFINE_FAULT_HANDLER(UsageFault_Handler)

#undef MK61_DEFINE_FAULT_HANDLER

#endif

} // namespace

void initialize(void) {
#if MK61_CRASH_DUMP_SUPPORTED
  reset_flags = RCC->CSR;
  layout_valid = (usize) &mk61_crash_record >= (usize) &_ebss &&
      (usize) &mk61_crash_record + sizeof(mk61_crash_record) <=
          (usize) &_estack;

  if(crash_dump_format::valid(mk61_crash_record)) {
    begin_record_update();
    mk61_crash_record.rcc_csr_after_reboot = reset_flags;
    finish_record_update();
  } else {
    mk61_crash_record.magic = 0;
  }

  RCC->CSR |= RCC_CSR_RMVF;
  SCB->SHCSR |= SCB_SHCSR_MEMFAULTENA_Msk |
                SCB_SHCSR_BUSFAULTENA_Msk |
                SCB_SHCSR_USGFAULTENA_Msk;
  __DSB();
  __ISB();
#endif
}

bool available(void) {
#if MK61_CRASH_DUMP_SUPPORTED
  return layout_valid && crash_dump_format::valid(mk61_crash_record);
#else
  return false;
#endif
}

bool copy(crash_dump_format::Record& output) {
#if MK61_CRASH_DUMP_SUPPORTED
  if(!available()) return false;
  const volatile u32* source =
      reinterpret_cast<const volatile u32*>(&mk61_crash_record);
  u32* destination = reinterpret_cast<u32*>(&output);
  for(usize index = 0; index < sizeof(output) / sizeof(u32); index++) {
    destination[index] = source[index];
  }
  return crash_dump_format::valid(output);
#else
  (void) output;
  return false;
#endif
}

void clear(void) {
#if MK61_CRASH_DUMP_SUPPORTED
  mk61_crash_record.magic = 0;
  __DSB();
#endif
}

u32 boot_reset_flags(void) {
#if MK61_CRASH_DUMP_SUPPORTED
  return reset_flags;
#else
  return 0;
#endif
}

u32 current_build_id(void) {
  return BUILD_ID;
}

bool memory_layout_valid(void) {
#if MK61_CRASH_DUMP_SUPPORTED
  return layout_valid;
#else
  return false;
#endif
}

void update_runtime(u32 state, u32 detail, u32 uptime_ms) {
#if MK61_CRASH_DUMP_SUPPORTED
  runtime_state = state;
  runtime_detail = detail;
  runtime_uptime_ms = uptime_ms;
#else
  (void) state;
  (void) detail;
  (void) uptime_ms;
#endif
}

void update_classic(u32 ticks, u32 steps, u32 missed, u32 pending) {
#if MK61_CRASH_DUMP_SUPPORTED
  classic_ticks = ticks;
  classic_steps = steps;
  classic_missed = missed;
  classic_pending = pending;
#else
  (void) ticks;
  (void) steps;
  (void) missed;
  (void) pending;
#endif
}

bool persisted(void) {
#if MK61_CRASH_DUMP_SUPPORTED
  return available() &&
      (mk61_crash_record.capture_flags &
       crash_dump_format::PERSISTED_TO_C5) != 0;
#else
  return false;
#endif
}

bool mark_persisted(void) {
#if MK61_CRASH_DUMP_SUPPORTED
  if(!available()) return false;
  begin_record_update();
  mk61_crash_record.capture_flags |= crash_dump_format::PERSISTED_TO_C5;
  finish_record_update();
  return true;
#else
  return false;
#endif
}

#if MK61_CRASH_DUMP_SUPPORTED && MK61_ENABLE_FAULT_INJECTION
[[noreturn]] void inject_usage_fault(void) {
  update_runtime(RUNTIME_FAULT_TEST, 6, millis());
  __DSB();
  __asm__ volatile("udf #0");
  while(true) {}
}

[[noreturn]] void inject_bus_fault(void) {
  update_runtime(RUNTIME_FAULT_TEST, 5, millis());
  __DSB();
  // Синхронная загрузка из отсутствующего внешнего memory space даёт precise
  // BusFault; в отличие от buffered store, PC и BFAR остаются однозначными.
  const u32 value = *reinterpret_cast<volatile u32*>(0x60000000UL);
  __asm__ volatile("" : : "r"(value) : "memory");
  while(true) {}
}

[[noreturn]] void inject_hard_fault(void) {
  update_runtime(RUNTIME_FAULT_TEST, 3, millis());
  SCB->SHCSR &= ~(SCB_SHCSR_USGFAULTENA_Msk |
                  SCB_SHCSR_BUSFAULTENA_Msk);
  __DSB();
  __ISB();
  __asm__ volatile("udf #0");
  while(true) {}
}
#endif

} // namespace crash_dump
