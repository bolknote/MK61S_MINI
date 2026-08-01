#ifndef MK61_CRASH_DUMP_FORMAT_HPP
#define MK61_CRASH_DUMP_FORMAT_HPP

#include "rust_types.h"

namespace crash_dump_format {

static constexpr u32 MAGIC = 0x4331364DUL; // "M61C" little-endian.
static constexpr u32 VERSION = 1;
static constexpr u32 RECORD_SIZE = 192;
static constexpr u32 INVALID_STACK_WORD = 0xDEADDEADUL;

enum CaptureFlag : u32 {
  FRAME_VALID = 1UL << 0,
  STACK_USED_PSP = 1UL << 1,
  EXTENDED_FP_FRAME = 1UL << 2,
  PERSISTED_TO_C5 = 1UL << 3
};

// Поля намеренно только 32-битные: fault-handler заполняет запись прямыми
// aligned-записями, не вызывая memcpy, файловую систему или периферию CRC.
struct Record {
  u32 magic;
  u32 version;
  u32 size;
  u32 sequence;

  u32 exception_number;
  u32 exc_return;
  u32 msp;
  u32 psp;

  u32 stacked_r0;
  u32 stacked_r1;
  u32 stacked_r2;
  u32 stacked_r3;
  u32 stacked_r12;
  u32 stacked_lr;
  u32 stacked_pc;
  u32 stacked_xpsr;

  u32 control;
  u32 primask;
  u32 basepri;
  u32 faultmask;

  u32 cfsr;
  u32 hfsr;
  u32 dfsr;
  u32 afsr;
  u32 mmfar;
  u32 bfar;
  u32 icsr;
  u32 shcsr;

  u32 rcc_csr_at_fault;
  u32 rcc_csr_after_reboot;
  u32 build_id;
  u32 capture_flags;

  u32 runtime_uptime_ms;
  u32 runtime_state;
  u32 runtime_detail;
  u32 classic_ticks;
  u32 classic_steps;
  u32 classic_missed;
  u32 classic_pending;

  u32 reserved[8];
  u32 crc32;
};

static_assert(sizeof(Record) == RECORD_SIZE,
              "Crash record v1 must remain exactly 192 bytes");
static_assert(alignof(Record) == alignof(u32),
              "Crash record must retain a simple word layout");

u32 calculate_crc(const Record& record);
u32 calculate_crc(const volatile Record& record);
bool valid(const Record& record);
bool valid(const volatile Record& record);

const char* exception_name(u32 exception_number);

// Человекочитаемый отчёт не содержит завершающий NUL. Ноль означает
// невалидную запись либо недостаточный буфер.
u16 format_report(const Record& record, u32 current_build_id,
                  u8* output, usize capacity);

} // namespace crash_dump_format

#endif
