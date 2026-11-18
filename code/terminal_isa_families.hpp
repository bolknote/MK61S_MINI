#ifndef MK61_TERMINAL_ISA_FAMILIES_HPP
#define MK61_TERMINAL_ISA_FAMILIES_HPP

#include <stddef.h>
#include <string.h>

namespace terminal_mnemonics {

// 00..3F and 50..5F are literals. Each remaining opcode row shares a
// prefix and uses the same register alphabet, including the M8 byte for Д.
template<const auto& Csv>
class RegisterFamilies {
  static constexpr const char* row(unsigned family) {
    const char* p = Csv;
    for(unsigned entries = family * 16; entries; --entries) {
      while(*p && *p != ',') ++p;
      if(!*p) __builtin_trap();
      ++p;
    }
    return p;
  }

  static constexpr size_t prefix_size(const char* first) {
    size_t length = 0;
    while(first[length] && first[length] != ',') ++length;
    if(length < 2) __builtin_trap();
    return length - 1;  // Exclude the register suffix.
  }

  static constexpr size_t prefix_bytes() {
    size_t size = 0;
    for(unsigned family = 4; family <= 14; ++family)
      if(family != 5) size += prefix_size(row(family)) + 1;
    return size;
  }

  template<size_t Length>
  struct LiteralRun { char bytes[Length]; };

  template<size_t Length>
  static constexpr LiteralRun<Length> literal(const char* begin) {
    LiteralRun<Length> run = {};
    for(size_t i = 0; i < Length; ++i) run.bytes[i] = begin[i];
    return run;
  }

  // Separate constants let GCC use each literal directly as a memcpy source.
  static constexpr auto head = literal<row(4) - Csv>(Csv);
  static constexpr auto control = literal<row(6) - row(5)>(row(5));
  char prefixes[prefix_bytes()];
  char registers[16];

 public:
  constexpr RegisterFamilies() : prefixes{}, registers{} {
    char* next = prefixes;
    for(unsigned family = 4; family <= 14; ++family) {
      if(family == 5) continue;
      const char* entry = row(family);
      const char* first = entry;
      const size_t length = prefix_size(first);
      for(size_t i = 0; i < length; ++i) *next++ = first[i];
      *next++ = 0;
      // Check every entry at compile time, including the reserved opcodes.
      for(unsigned reg = 0; reg < 16; ++reg) {
        if(family >= 7 && reg == 15) {
          if(*entry++ != '?') __builtin_trap();
        } else {
          for(size_t i = 0; i < length; ++i)
            if(*entry++ != first[i]) __builtin_trap();
          if(family == 4) registers[reg] = *entry;
          if(*entry++ != registers[reg]) __builtin_trap();
        }
        if(*entry++ != (family == 14 && reg == 15 ? '\0' : ',')) __builtin_trap();
      }
    }
  }

  // The caller owns a scratch lease of sizeof(Csv) bytes.
  void expand(char* dest) const {
    memcpy(dest, head.bytes, sizeof(head));
    dest += sizeof(head);
    const char* prefix = prefixes;
    for(unsigned family = 4; family <= 14; ++family) {
      if(family == 5) {
        memcpy(dest, control.bytes, sizeof(control));
        dest += sizeof(control);
        continue;
      }
      const size_t length = strlen(prefix);
      for(unsigned reg = 0; reg < 16; ++reg) {
        if(family >= 7 && reg == 15) {
          *dest++ = '?';
        } else {
          memcpy(dest, prefix, length);
          dest += length;
          *dest++ = registers[reg];
        }
        *dest++ = ',';
      }
      prefix += length + 1;
    }
    dest[-1] = 0;
  }
};

} // namespace terminal_mnemonics
#endif
