#ifndef MK61_LANGUAGE_SOURCE_HPP
#define MK61_LANGUAGE_SOURCE_HPP
#include "language_source_scan.hpp"
#include <stdint.h>
#include <stddef.h>
#include <string.h>

namespace language_vm {
namespace source {
// Source positions and C9 lengths are unsigned 16-bit values. Reserve 65535
// for stale/invalid positions; this is a wire-format bound, not a RAM quota.
static constexpr uint16_t MAX_SIZE = 65534;
static constexpr unsigned PAGE_SIZE = 256;
struct Input {
  void* context;
  bool (*read)(void*, uint16_t, uint8_t*, uint16_t);
  uint16_t size;
};
class Reader {
  Input input_{};
  const char* memory_ = nullptr;
  mutable uint8_t page_[PAGE_SIZE];
  mutable uint16_t begin_ = 0, count_ = 0;
  mutable bool good_ = true;
public:
  Reader(const char* memory, uint16_t size) : input_{nullptr,nullptr,size}, memory_(memory) {
    good_ = memory != nullptr && size <= MAX_SIZE;
  }
  explicit Reader(Input input) : input_(input) {
    good_ = input.read != nullptr && input.size <= MAX_SIZE;
  }
  uint16_t size() const { return input_.size; }
  bool good() const { return good_; }
  bool read(uint16_t at, void* output, size_t count) const {
    if(!good_ || at > size() || count > unsigned(size()-at) || (!output && count)) return false;
    auto* bytes = static_cast<uint8_t*>(output);
    while(count) {
      if(memory_) { memcpy(bytes,memory_+at,count); return true; }
      if(at < begin_ || unsigned(at-begin_) >= count_) {
        begin_ = uint16_t(at / PAGE_SIZE * PAGE_SIZE);
        count_ = uint16_t(size()-begin_);
        if(count_ > PAGE_SIZE) count_ = PAGE_SIZE;
        if(!input_.read(input_.context,begin_,page_,count_)) { good_=false;return false; }
      }
      size_t n = count_-(at-begin_);
      if(n>count) n=count;
      memcpy(bytes,page_+(at-begin_),n);
      at=uint16_t(at+n);bytes+=n;count-=n;
    }
    return true;
  }
  char at(uint16_t position) const {
    char value=0;
    if(position < size()) (void)read(position,&value,1);
    return value;
  }
  bool contains_nul() const {
    uint8_t bytes[64];
    for(unsigned at=0;at<size();) {
      const unsigned n=size()-at<sizeof(bytes)?size()-at:sizeof(bytes);
      if(!read(uint16_t(at),bytes,n) || memchr(bytes,0,n)) return true;
      at+=n;
    }
    return false;
  }
  uint32_t checksum() const {
    uint32_t crc=~uint32_t(0);
    uint8_t bytes[64];
    for(unsigned at=0;at<size();) {
      const unsigned n=size()-at<sizeof(bytes)?size()-at:sizeof(bytes);
      if(!read(uint16_t(at),bytes,n)) return 0;
      for(unsigned i=0;i<n;++i) {
        crc^=bytes[i];
        for(unsigned bit=0;bit<8;++bit) crc=(crc>>1)^(0xEDB88320U & (0U-(crc&1U)));
      }
      at+=n;
    }
    return ~crc;
  }
  unsigned line_end(unsigned at, unsigned end) const {
    uint8_t bytes[64];
    const unsigned start=at;
    while(at<end) {
      unsigned n=end-at<sizeof(bytes)?end-at:sizeof(bytes);
      if(!read(uint16_t(at),bytes,n)) return at-start;
      const auto found=source_scan::line_end(bytes,n);
      at+=found;
      if(found<n) break;
    }
    return at-start;
  }
};

// A compiler runs synchronously in the foreground. Its scoped reader lets a
// cursor retain only an offset (one ARM register), never a cache pointer. Raw
// pointers to native dictionary/prompt bytes occupy the disjoint >64-KiB range.
// Nested compiles restore the outer reader on every return, including errors.
class CursorScope {
  inline static const Reader* active_=nullptr;
  const Reader* previous_;
public:
  explicit CursorScope(const Reader& reader):previous_(active_) {active_=&reader;}
  ~CursorScope(){active_=previous_;}
  static const Reader* active(){return active_;}
};
class Cursor {
  uintptr_t value_=UINTPTR_MAX;
  bool streamed() const {return value_<=UINT16_MAX;}
public:
  Cursor() = default;
  Cursor(decltype(nullptr)) {}
  Cursor(const char* memory):value_(memory?reinterpret_cast<uintptr_t>(memory):UINTPTR_MAX) {}
  Cursor(const Reader&,unsigned at=0):value_(at) {}
  explicit operator bool() const {return value_!=UINTPTR_MAX;}
  bool from(const Reader& reader) const {return streamed() && CursorScope::active()==&reader;}
  char operator*() const {return streamed()?CursorScope::active()->at(uint16_t(value_)):*reinterpret_cast<const char*>(value_);}
  char operator[](ptrdiff_t n) const {return *(*this+n);}
  Cursor& operator+=(ptrdiff_t n) {value_+=n;return *this;}
  Cursor& operator-=(ptrdiff_t n) {return *this+=-n;}
  Cursor operator+(ptrdiff_t n) const {Cursor p=*this;return p+=n;}
  Cursor operator-(ptrdiff_t n) const {return *this+-n;}
  Cursor& operator++(){return *this+=1;}
  Cursor operator++(int){Cursor p=*this;++*this;return p;}
  Cursor& operator--(){return *this-=1;}
  ptrdiff_t operator-(Cursor other) const {return ptrdiff_t(value_)-ptrdiff_t(other.value_);}
  bool operator==(Cursor p) const {return value_==p.value_;}
  bool operator!=(Cursor p) const {return value_!=p.value_;}
  bool operator<(Cursor p) const {return value_<p.value_;}
  bool operator>(Cursor p) const {return value_>p.value_;}
  bool operator<=(Cursor p) const {return value_<=p.value_;}
  bool operator>=(Cursor p) const {return value_>=p.value_;}
  bool copy(void* output,size_t n) const {
    if(streamed())return CursorScope::active()->read(uint16_t(value_),output,n);
    memcpy(output,reinterpret_cast<const char*>(value_),n);return true;
  }
  unsigned line_end(Cursor end) const {
    return streamed()?CursorScope::active()->line_end(unsigned(value_),unsigned(end.value_)):
        source_scan::line_end(reinterpret_cast<const uint8_t*>(value_),size_t(end-*this));
  }
};
__attribute__((noinline)) inline bool equal(Cursor a,Cursor b,unsigned n) {
  // The two cursors can share one paged reader. Copy a bounded left span
  // before reading the right one, avoiding a Flash page reload per byte.
  uint8_t bytes[64];
  while(n) {
    const unsigned count=n<sizeof(bytes)?n:sizeof(bytes);
    if(!a.copy(bytes,count))return false;
    for(unsigned i=0;i<count;++i)if(bytes[i]!=uint8_t(b[i]))return false;
    a+=count;b+=count;n-=count;
  }
  return true;
}
}
}
#endif
