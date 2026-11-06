#ifndef MK61_PACKED_TEXT_HPP
#define MK61_PACKED_TEXT_HPP
#include <stddef.h>
#include <stdint.h>
#include <string.h>
#if (defined(__arm__) && defined(ARDUINO_ARCH_STM32) && \
     defined(MK61_F401_PRODUCT_BUILD) && MK61_F401_PRODUCT_BUILD && \
     (defined(STM32F401xC) || defined(STM32F401xE)) && \
     !defined(MK61_CORE_STANDALONE) && !defined(MK61_BUILD_TERMINAL_MODULE)) || \
    defined(MK61_TEST_PACKED_TEXT)
#define MK61_PACKED_TEXT_ENABLED 1
#else
#define MK61_PACKED_TEXT_ENABLED 0
#endif
namespace packed_text {
#if MK61_PACKED_TEXT_ENABLED
#include "packed_text_catalog.inc"
class Text {
  // STM32 Flash and SRAM pointers start above 64 KiB. Reserve the otherwise
  // unused low range for bitstream positions, keeping literal arguments small.
  static constexpr uintptr_t limit=65536;
  struct Encoded {uintptr_t bits;};
  union Data {
    const char* plain;uintptr_t encoded;
    constexpr Data(const char* p):plain(p){}
    constexpr Data(Encoded e):encoded(e.bits){}
  } data_;
  constexpr explicit Text(Encoded e):data_(e){}
  uintptr_t bits() const {uintptr_t b;__builtin_memcpy(&b,&data_,sizeof(b));return b;}
public:
  constexpr Text(const char* p=nullptr):data_(p){}
  static constexpr Text encoded(unsigned offset) {return Text(Encoded{offset+1});}
  bool packed() const {const uintptr_t value=bits();return value!=0&&value<limit;}
  const char* plain() const {return packed()?nullptr:data_.plain;}
  unsigned offset() const {return unsigned(bits()-1);}
  explicit operator bool() const {return bits()!=0;}
  friend bool operator==(Text value,decltype(nullptr)) {return !bool(value);}
  friend bool operator!=(Text value,decltype(nullptr)) {return bool(value);}
};
class Reader {
  const char* plain_;
  unsigned bit_,pending_=0;
  uint16_t stack_[MAX_PAIR_DEPTH+1];
  bool packed_,ended_=false;
  unsigned symbol();
public:
  explicit Reader(Text value):plain_(value.plain()),bit_(value.offset()),packed_(value.packed()){}
  uint8_t next();
};
size_t copy(char* out,size_t capacity,Text text);
#else
using Text=const char*;
inline size_t copy(char* out,size_t capacity,Text text) {
  size_t n=0;
  if(text)while(text[n]){if(n+1<capacity)out[n]=text[n];++n;}
  if(capacity)out[n<capacity?n:capacity-1]=0;
  return n;
}
#endif
}
#if MK61_PACKED_TEXT_ENABLED
#define PT(source) ([]() -> ::packed_text::Text { \
  constexpr unsigned offset=::packed_text::literal_offset(source,false); \
  static_assert(offset!=::packed_text::INVALID_OFFSET,"regenerate packed text catalog"); \
  return ::packed_text::Text::encoded(offset); }())
#define MP8(source) ([]() -> ::packed_text::Text { \
  constexpr unsigned offset=::packed_text::literal_offset(source,true); \
  static_assert(offset!=::packed_text::INVALID_OFFSET,"regenerate packed text catalog"); \
  return ::packed_text::Text::encoded(offset); }())
#else
#define PT(source) source
#define MP8(source) M8(source)
#endif
#endif
