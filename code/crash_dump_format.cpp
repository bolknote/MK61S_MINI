// Cold diagnostic formatting must follow the mixed F411 size policy too;
// global -O3 otherwise expands the repeated register/hex output into ~18 KiB.
#include "firmware_optimization.hpp"
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

    // Keep the repeated label/value pair shared in the resident image.
    // Formatting and truncation still use the same bounded primitives.
    __attribute__((noinline)) void hex_field(const char* label, u32 value) {
      text(label);
      hex(value);
    }
    __attribute__((noinline)) void decimal_field(const char* label, u32 value) {
      text(label);
      decimal(value);
    }

    // Each NUL-separated label consumes the next adjacent record word.
    // Read the object representation without treating member subobjects as
    // an array; the compiler lowers the fixed-size copy to a word load.
    __attribute__((noinline)) void hex_fields(const char* labels,
                                             const Record& record,
                                             usize offset) {
      const u8* value = reinterpret_cast<const u8*>(&record) + offset;
      while(*labels != 0) {
        u32 word;
        __builtin_memcpy(&word, value, sizeof(word));
        hex_field(labels, word);
        value += sizeof(u32);
        while(*labels++ != 0) {}
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

// Record v1 fixes both field types and order. Guard the adjacent spans
// consumed by hex_fields if a future edit changes that layout.
static_assert(
    offsetof(Record, stacked_xpsr) == offsetof(Record, stacked_r0) + 7 * sizeof(u32) &&
    offsetof(Record, r11) == offsetof(Record, r4) + 7 * sizeof(u32) &&
    offsetof(Record, psp) == offsetof(Record, msp) + sizeof(u32) &&
    offsetof(Record, faultmask) == offsetof(Record, control) + 3 * sizeof(u32) &&
    offsetof(Record, afsr) == offsetof(Record, cfsr) + 3 * sizeof(u32) &&
    offsetof(Record, shcsr) == offsetof(Record, icsr) + sizeof(u32) &&
    offsetof(Record, rcc_csr_after_reboot) == offsetof(Record, rcc_csr_at_fault) + sizeof(u32),
    "Crash report word groups must remain adjacent");

void append_registers(ReportBuilder& report, const Record& record) {
  report.hex_fields("r0=\0,r1=\0,r2=\0,r3=\0"
                    "\nr12=\0,lr=\0,pc=\0,xpsr=\0",
                    record, offsetof(Record, stacked_r0));
  report.character('\n');
  if((record.capture_flags & CALLEE_SAVED_VALID) != 0) {
    report.hex_fields("r4=\0,r5=\0,r6=\0,r7=\0"
                      "\nr8=\0,r9=\0,r10=\0,r11=\0",
                      record, offsetof(Record, r4));
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
                  u8* output, usize capacity,
                  const ReportMetadata* metadata) {
  if(!valid(record) || output == 0 || capacity == 0) return 0;

  ReportBuilder report(output, capacity);
  report.decimal_field("MK61 CRASH DUMP 1\nsequence=", record.sequence);
  report.text(",exception=");
  report.text(exception_name(record.exception_number));
  report.character('(');
  report.decimal(record.exception_number);
  report.hex_field(")\nbuild=", record.build_id);
  report.hex_field(",current_build=", current_build_id);
  if(metadata != nullptr && metadata->device_public_id != nullptr &&
     metadata->current_build_profile != nullptr) {
    report.text("\ndevice_public=");
    report.text(metadata->device_public_id);
    report.text(",current_profile=");
    report.text(metadata->current_build_profile);
  }
  report.hex_field("\nexc_return=", record.exc_return);
  report.text(",frame=");
  report.text((record.capture_flags & FRAME_VALID) != 0 ? "valid" : "invalid");
  report.text(",stack=");
  report.text((record.capture_flags & STACK_USED_PSP) != 0 ? "PSP" : "MSP");
  report.text(",fp=");
  report.text((record.capture_flags & EXTENDED_FP_FRAME) != 0
                  ? "extended" : "basic");
  report.decimal_field(",persisted=", (record.capture_flags & PERSISTED_TO_C5) != 0 ? 1 : 0);
  report.character('\n');

  append_registers(report, record);

  report.hex_fields("msp=\0,psp=\0", record, offsetof(Record, msp));
  report.hex_fields(",control=\0,primask=\0,basepri=\0,faultmask=\0", record, offsetof(Record, control));
  report.character('\n');

  report.hex_fields("cfsr=\0,hfsr=\0,dfsr=\0,afsr=\0", record, offsetof(Record, cfsr));
  report.hex_field("\nmmfar=", record.mmfar);
  report.decimal_field(",mmfar_valid=", (record.cfsr & (1UL << 7)) != 0 ? 1 : 0);
  report.hex_field(",bfar=", record.bfar);
  report.decimal_field(",bfar_valid=", (record.cfsr & (1UL << 15)) != 0 ? 1 : 0);
  report.hex_fields(",icsr=\0,shcsr=\0", record, offsetof(Record, icsr));
  report.character('\n');

  report.hex_fields("rcc_at_fault=\0,rcc_after_reboot=\0", record, offsetof(Record, rcc_csr_at_fault));
  report.decimal_field("\nuptime_ms=", record.runtime_uptime_ms);
  report.decimal_field(",runtime_state=", record.runtime_state);
  report.hex_field(",runtime_detail=", record.runtime_detail);
  report.decimal_field("\nclassic_ticks=", record.classic_ticks);
  report.decimal_field(",steps=", record.classic_steps);
  report.decimal_field(",missed=", record.classic_missed);
  report.decimal_field(",pending=", record.classic_pending);
  report.character('\n');

  return report.ok() && report.length() <= 0xFFFFU
      ? (u16) report.length() : 0;
}

} // namespace crash_dump_format
