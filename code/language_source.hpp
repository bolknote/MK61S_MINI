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
  mutable uint16_t begin_ = 0, end_ = 0;
  mutable bool good_ = true;
  // Fits the old Reader's trailing padding; no additional page allocation.
  uint16_t window_size_ = PAGE_SIZE;
  // A span is consumed synchronously, before any subsequent cache refill.
  const uint8_t* span(uint16_t at) const {
    if(!good_ || at >= size()) return nullptr;
    auto* page = memory_ ? (uint8_t*)memory_ : page_;
    if(at < begin_ || at >= end_) {
      // Keep the old page grid even for a wider window. Small backwards
      // parser lookups must not force a fresh decode for every byte.
      begin_ = uint16_t(at / PAGE_SIZE * PAGE_SIZE);
      unsigned count = size()-begin_;
      if(count > window_size_) count = window_size_;
      end_ = uint16_t(begin_+count);
      if(!input_.read(input_.context,begin_,page,uint16_t(count))) { good_=false;return nullptr; }
    }
    return page+(at-begin_);
  }
public:
  Reader(const char* memory, uint16_t size) : input_{nullptr,nullptr,size}, memory_(memory), end_(size) {
    good_ = memory != nullptr && size <= MAX_SIZE;
  }
  explicit Reader(Input input, void* buffer = nullptr, size_t capacity = 0) : input_(input) {
    // The caller lends otherwise-unused workspace for this reader's lifetime.
    // A full read verifies/decompresses a small source only once. Otherwise
    // reuse the loan as a bounded window, not an unused full-source buffer.
    // A missing/small loan keeps the stack page; I/O errors never fall back.
    good_ = input.read != nullptr && input.size <= MAX_SIZE;
    if(buffer && (input.size <= capacity || capacity > PAGE_SIZE)) {
      memory_ = static_cast<const char*>(buffer);
      if(input.size <= capacity) {
        good_ = good_ && input.read(input.context,0,static_cast<uint8_t*>(buffer),input.size);
        end_ = input.size;
      } else window_size_ = uint16_t(capacity);
    }
  }
  uint16_t size() const { return input_.size; }
  bool good() const { return good_; }
  bool read(uint16_t at, void* output, size_t count) const {
    if(!good_ || at > size() || count > unsigned(size()-at) || (!output && count)) return false;
    auto* bytes = static_cast<uint8_t*>(output);
    while(count) {
      const auto* page = span(at);
      if(!page) return false;
      size_t n = end_-at;
      if(n>count) n=count;
      memcpy(bytes,page,n);
      at=uint16_t(at+n);bytes+=n;count-=n;
    }
    return true;
  }
  char at(uint16_t position) const {
    const auto* value = span(position);
    return value ? char(*value) : 0;
  }
  bool contains_nul() const {
    for(unsigned at=0;at<size();) {
      const auto* bytes=span(uint16_t(at));
      if(!bytes) return true;
      const unsigned n=end_-at;
      if(memchr(bytes,0,n)) return true;
      at+=n;
    }
    return false;
  }
  uint32_t checksum() const {
    uint32_t crc=~uint32_t(0);
    for(unsigned at=0;at<size();) {
      const auto* bytes=span(uint16_t(at));
      if(!bytes) return 0;
      const unsigned n=end_-at;
      for(unsigned i=0;i<n;++i) {
        crc^=bytes[i];
        for(unsigned bit=0;bit<8;++bit) crc=(crc>>1)^(0xEDB88320U & (0U-(crc&1U)));
      }
      at+=n;
    }
    return ~crc;
  }
  unsigned line_end(unsigned at, unsigned end) const {
    const unsigned start=at;
    while(at<end) {
      const auto* bytes = span(uint16_t(at));
      if(!bytes) return at-start;
      unsigned n=end_-at;
      if(n>end-at) n=end-at;
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
