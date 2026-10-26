#ifndef MK61_ZX0_STREAM_HPP
#define MK61_ZX0_STREAM_HPP

#include "rust_types.h"

namespace zx0 {

// A resumable forward ZX0 v2 decoder. The destination itself is the dictionary;
// read/write positions are relative to its beginning. No input buffer or heap.
class StreamDecoder {
public:
  struct Memory {
    void* context;
    bool (*read)(void*, u16, u8&);
    bool (*write)(void*, u16, u8);
    u16 capacity;
  };
  void reset(const Memory& memory);
  bool feed(u8 value);
  bool complete() const { return state_ == DONE; }
  u16 written() const { return written_; }

private:
  enum State : u8 { LITERAL_LENGTH, LAST_LENGTH, OFFSET_HIGH, MATCH_LENGTH,
                    LITERALS, OFFSET_LOW, AFTER_LITERAL, AFTER_MATCH, DONE, BAD };
  Memory memory_ = {};
  State state_ = BAD;
  u16 written_ = 0, offset_ = 1, gamma_ = 1, remaining_ = 0;
  u8 bits_ = 0, mask_ = 0;
  bool control_ = true;
  void gamma(State state);
  bool match(u16 length);
  bool fail() { state_ = BAD; return false; }
};

} // namespace zx0
#endif
