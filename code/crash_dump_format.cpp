#include "crash_dump_format.hpp"

#include <stddef.h>

namespace crash_dump_format {
namespace {

static constexpr u32 CRC_INITIAL = 0xFFFFFFFFUL;
static constexpr u32 CRC_POLYNOMIAL = 0xEDB88320UL;

template<typename BytePointer>
u32 crc_bytes(BytePointer data, usize size) {
  u32 state = CRC_INITIAL;
  for(usize index = 0; index < size; index++) {
    state ^= (u8) data[index];
    for(u8 bit = 0; bit < 8; bit++) {
      state = (state & 1U) != 0
          ? (state >> 1) ^ CRC_POLYNOMIAL : state >> 1;
    }
  }
  return state ^ CRC_INITIAL;
}

template<typename RecordReference>
u32 record_crc(RecordReference& record) {
  const volatile u8* bytes =
      reinterpret_cast<const volatile u8*>(&record);
  const usize first = offsetof(Record, version);
  const usize last = offsetof(Record, crc32);
  return crc_bytes(bytes + first, last - first);
}

template<typename RecordReference>
bool record_valid(RecordReference& record) {
  return record.magic == MAGIC &&
         record.version == VERSION &&
         record.size == sizeof(Record) &&
         record.crc32 == record_crc(record);
}

class ReportBuilder {
  public:
    ReportBuilder(u8* output, usize capacity)
      : output_(output), capacity_(capacity), length_(0), valid_(output != 0) {}

    void text(const char* value) {
      if(value == 0) {
        valid_ = false;
        return;
      }
      while(*value != 0) character(*value++);
    }

    void character(char value) {
      if(!valid_ || length_ >= capacity_) {
        valid_ = false;
        return;
      }
      output_[length_++] = (u8) value;
    }

    void decimal(u32 value) {
      char digits[10];
      usize count = 0;
      do {
        digits[count++] = (char) ('0' + value % 10U);
        value /= 10U;
      } while(value != 0 && count < sizeof(digits));
      while(count != 0) character(digits[--count]);
    }

    void hex(u32 value) {
      static constexpr char DIGITS[] = "0123456789ABCDEF";
      text("0x");
      for(i8 shift = 28; shift >= 0; shift -= 4) {
        character(DIGITS[(value >> shift) & 0x0FU]);
      }
    }

    bool ok(void) const { return valid_; }
    usize length(void) const { return length_; }

  private:
    u8* output_;
    usize capacity_;
    usize length_;
    bool valid_;
};

void append_registers(ReportBuilder& report, const Record& record) {
  report.text("r0="); report.hex(record.stacked_r0);
  report.text(",r1="); report.hex(record.stacked_r1);
  report.text(",r2="); report.hex(record.stacked_r2);
  report.text(",r3="); report.hex(record.stacked_r3);
  report.text("\nr12="); report.hex(record.stacked_r12);
  report.text(",lr="); report.hex(record.stacked_lr);
  report.text(",pc="); report.hex(record.stacked_pc);
  report.text(",xpsr="); report.hex(record.stacked_xpsr);
  report.character('\n');
  if((record.capture_flags & CALLEE_SAVED_VALID) != 0) {
    report.text("r4="); report.hex(record.r4);
    report.text(",r5="); report.hex(record.r5);
    report.text(",r6="); report.hex(record.r6);
    report.text(",r7="); report.hex(record.r7);
    report.text("\nr8="); report.hex(record.r8);
    report.text(",r9="); report.hex(record.r9);
    report.text(",r10="); report.hex(record.r10);
    report.text(",r11="); report.hex(record.r11);
    report.character('\n');
  }
}

} // namespace

u32 calculate_crc(const Record& record) {
  return record_crc(record);
}

u32 calculate_crc(const volatile Record& record) {
  return record_crc(record);
}

bool valid(const Record& record) {
  return record_valid(record);
}

bool valid(const volatile Record& record) {
  return record_valid(record);
}

const char* exception_name(u32 exception_number) {
  switch(exception_number) {
    case 2: return "NMI";
    case 3: return "HardFault";
    case 4: return "MemManage";
    case 5: return "BusFault";
    case 6: return "UsageFault";
    default: return "Unknown";
  }
}

u16 format_report(const Record& record, u32 current_build_id,
                  u8* output, usize capacity) {
  if(!valid(record) || output == 0 || capacity == 0) return 0;

  ReportBuilder report(output, capacity);
  report.text("MK61 CRASH DUMP 1\nsequence=");
  report.decimal(record.sequence);
  report.text(",exception=");
  report.text(exception_name(record.exception_number));
  report.character('(');
  report.decimal(record.exception_number);
  report.text(")\nbuild=");
  report.hex(record.build_id);
  report.text(",current_build=");
  report.hex(current_build_id);
  report.text("\nexc_return=");
  report.hex(record.exc_return);
  report.text(",frame=");
  report.text((record.capture_flags & FRAME_VALID) != 0 ? "valid" : "invalid");
  report.text(",stack=");
  report.text((record.capture_flags & STACK_USED_PSP) != 0 ? "PSP" : "MSP");
  report.text(",fp=");
  report.text((record.capture_flags & EXTENDED_FP_FRAME) != 0
                  ? "extended" : "basic");
  report.text(",persisted=");
  report.decimal((record.capture_flags & PERSISTED_TO_C5) != 0 ? 1 : 0);
  report.character('\n');

  append_registers(report, record);

  report.text("msp="); report.hex(record.msp);
  report.text(",psp="); report.hex(record.psp);
  report.text(",control="); report.hex(record.control);
  report.text(",primask="); report.hex(record.primask);
  report.text(",basepri="); report.hex(record.basepri);
  report.text(",faultmask="); report.hex(record.faultmask);
  report.character('\n');

  report.text("cfsr="); report.hex(record.cfsr);
  report.text(",hfsr="); report.hex(record.hfsr);
  report.text(",dfsr="); report.hex(record.dfsr);
  report.text(",afsr="); report.hex(record.afsr);
  report.text("\nmmfar="); report.hex(record.mmfar);
  report.text(",mmfar_valid=");
  report.decimal((record.cfsr & (1UL << 7)) != 0 ? 1 : 0);
  report.text(",bfar="); report.hex(record.bfar);
  report.text(",bfar_valid=");
  report.decimal((record.cfsr & (1UL << 15)) != 0 ? 1 : 0);
  report.text(",icsr="); report.hex(record.icsr);
  report.text(",shcsr="); report.hex(record.shcsr);
  report.character('\n');

  report.text("rcc_at_fault="); report.hex(record.rcc_csr_at_fault);
  report.text(",rcc_after_reboot="); report.hex(record.rcc_csr_after_reboot);
  report.text("\nuptime_ms="); report.decimal(record.runtime_uptime_ms);
  report.text(",runtime_state="); report.decimal(record.runtime_state);
  report.text(",runtime_detail="); report.hex(record.runtime_detail);
  report.text("\nclassic_ticks="); report.decimal(record.classic_ticks);
  report.text(",steps="); report.decimal(record.classic_steps);
  report.text(",missed="); report.decimal(record.classic_missed);
  report.text(",pending="); report.decimal(record.classic_pending);
  report.character('\n');

  return report.ok() && report.length() <= 0xFFFFU
      ? (u16) report.length() : 0;
}

} // namespace crash_dump_format
