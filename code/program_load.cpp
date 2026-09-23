#include "program_load.hpp"
#include "base91.hpp"
#include "crc32.hpp"
#include "mk61emu_core.h"
#include "zx0_stream.hpp"

namespace program_load {
namespace {
enum State : u8 { IDLE, ACTIVE, COMPLETE, FAILED };
State state = IDLE;
zx0::StreamDecoder decoder;
u16 start_address;
u32 expected_crc;
const char* last_error = nullptr;

bool fail(const char* message) {
  state = FAILED;
  last_error = message;
  return false;
}
bool read(void*, u16 position, u8& value) {
  return core_61::read_absolute_program(start_address + position, value);
}
bool write(void*, u16 position, u8 value) {
  return core_61::write_absolute_program(start_address + position, value);
}
bool space(char ch) { return ch == ' ' || ch == '\t'; }
bool end(char ch) { return ch == 0 || ch == '\r' || ch == '\n'; }
const char* skip(const char* p) { while(p != nullptr && space(*p)) ++p; return p; }
} // namespace

void reset() { state = IDLE; last_error = nullptr; }
bool blocked() { return state == ACTIVE || state == FAILED; }
void cancel() { if(state == ACTIVE) fail("Incomplete ZX0 program"); }
const char* error() { return last_error == nullptr ? "Incomplete ZX0 program" : last_error; }
u16 written() { return decoder.written(); }

bool start(const char* args, u16 limit) {
  if(state == ACTIVE) return fail("Previous ZX0 program is incomplete");
  const char* p = skip(args);
  u16 address = 0;
  if(p == nullptr) return fail("Usage: ztart <four-digit-address> <CRC32>");
  for(u8 i = 0; i < 4; ++i) {
    if(*p < '0' || *p > '9') return fail("ztart address needs four decimal digits");
    address = address * 10 + (*p++ - '0');
  }
  if(!space(*p)) return fail("ztart address needs four decimal digits");
  p = skip(p);
  u32 crc = 0;
  for(u8 i = 0; i < 8; ++i) {
    const char ch = *p++;
    const int digit = ch >= '0' && ch <= '9' ? ch - '0' :
        ch >= 'a' && ch <= 'f' ? ch - 'a' + 10 :
        ch >= 'A' && ch <= 'F' ? ch - 'A' + 10 : -1;
    if(digit < 0) return fail("ztart CRC32 needs eight hex digits");
    crc = (crc << 4) | digit;
  }
  if(!end(*skip(p))) return fail("Unexpected text after ztart CRC32");
  if(limit > core_61::EXTENDED_ADDRESS_LIMIT || address >= limit)
    return fail("Program address out of range");
  start_address = address;
  expected_crc = crc;
  decoder.reset({nullptr, read, write, u16(limit - address)});
  state = ACTIVE;
  last_error = nullptr;
  return true;
}

bool data(const char* args) {
  if(state != ACTIVE) return fail("zin requires an active ztart");
  const char* p = skip(args);
  usize length = 0;
  // 235 payload characters plus "zin " fit the 239-character terminal line.
  if(p == nullptr) return fail("Empty zin block");
  while(!end(p[length]) && !space(p[length])) {
    if(++length > 235) return fail("zin block is too long");
  }
  if(!end(*skip(p + length))) return fail("Unexpected text after zin block");
  u8 bytes[206]; // Worst case: 14 bits per pair of basE91 characters.
  usize count;
  if(!base91::decode(p, length, bytes, sizeof(bytes), count))
    return fail("Invalid Base91 block");
  for(usize i = 0; i < count; ++i)
    if(!decoder.feed(bytes[i])) return fail("Invalid ZX0 stream or program memory full");
  if(!decoder.complete()) return true;

  // Acquire the hardware CRC only after decompression. In particular, C6 may
  // use the same unit while reading the next zin line from compressed storage.
  mk61_crc32::Context crc;
  for(u16 i = 0; i < decoder.written(); ++i) {
    u8 value;
    if(!read(nullptr, i, value)) return fail("Cannot read loaded program");
    crc.update_byte(value);
  }
  if(crc.finish() != expected_crc) return fail("Program CRC32 mismatch");
  state = COMPLETE;
  return true;
}
} // namespace program_load
