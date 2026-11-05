#if defined(__GNUC__) && !defined(__clang__)
#pragma GCC optimize("Oz")
#endif
#include "pack.hpp"
#include "../zx0.hpp"
#include <string.h>

namespace urq {
char* copy_string(char* out, const char* text) { memcpy(out, text, strlen(text) + 1); return out; }
char* join_string(char* out, const char* text) { copy_string(out + strlen(out), text); return out; }
const char* find_string(const char* text, const char* needle) {
  const size_t n = strlen(needle);
  for(; *text; ++text) if(!strncmp(text, needle, n)) return text;
  return n ? nullptr : text;
}
uint16_t le16(const uint8_t* p) { return uint16_t(p[0] | uint16_t(p[1]) << 8); }
uint32_t le32(const uint8_t* p) { return le16(p) | uint32_t(le16(p + 2)) << 16; }
void put16(uint8_t* p, uint16_t v) { p[0] = uint8_t(v); p[1] = uint8_t(v >> 8); }
void put32(uint8_t* p, uint32_t v) { put16(p, uint16_t(v)); put16(p + 2, uint16_t(v >> 16)); }
uint32_t crc32(const uint8_t* p, uint32_t n, uint32_t crc) {
  crc = ~crc;
  while(n--) {
    crc ^= *p++;
    for(unsigned b = 0; b < 8; ++b) crc = (crc >> 1) ^ (0xEDB88320U & (0U - (crc & 1U)));
  }
  return ~crc;
}
uint8_t lower(uint8_t c) {
  if((c >= 'A' && c <= 'Z') || (c >= 0xC0 && c <= 0xDF)) return uint8_t(c + 32);
  return c == 0xA8 ? 0xB8 : c;
}
uint32_t hash_name(const char* text) {
  uint32_t h = 2166136261U;
  while(*text) h = (h ^ lower(uint8_t(*text++))) * 16777619U;
  return h;
}
bool equal_name(const char* a, const char* b) {
  return compare_name(a, b) == 0;
}
int compare_name(const char* a, const char* b) {
  for(;; ++a, ++b) {
    const int x = lower(uint8_t(*a)), y = lower(uint8_t(*b));
    if(x != y || !x) return x - y;
  }
}
bool Pack::open(Reader reader) {
  reader_ = reader; data_ = reader.cache; error_ = Error::FORMAT; invalidate();
  uint8_t h[64];
  if(!reader.read || !reader.size || reader.size(reader.context, 0) < sizeof(h) ||
     !reader.read(reader.context, 0, 0, h, sizeof(h))) { error_ = Error::IO; return false; }
  if(memcmp(h, "MK61URQ", 8) || le16(h + 8) != PACK_VERSION || h[10] > 3 ||
     h[11] > 3 || le16(h + 42) != PAGE_BYTES || crc32(h, 60) != le32(h + 60)) return false;
  html_ = (h[11]&1) != 0;resources_ = (h[11]&2) != 0;
  logical_ = le32(h + 12); lines_ = le32(h + 16); labels_ = le32(h + 20);
  line_table_ = le32(h + 24); label_table_ = le32(h + 28);
  metadata_ = le32(h + 32);
  pages_ = le32(h + 36); parts_ = le16(h + 40); mode_ = Mode(h[10]);
  memcpy(id_, h + 44, 16);
  const uint32_t bytes = reader.size(reader.context, 0);
  if(!logical_ || !lines_ || !parts_ || logical_ > UINT32_MAX - PAGE_BYTES ||
     pages_ != (logical_ + PAGE_BYTES - 1) / PAGE_BYTES || pages_ > (FILE_BYTES - 64) / 16 ||
     bytes != 64 + pages_ * 16 || line_table_ > logical_ || lines_ > (logical_ - line_table_) / 4 ||
     label_table_ > logical_ || labels_ > (logical_ - label_table_) / 12 || metadata_ >= logical_) return false;
  error_ = Error::NONE; return true;
}
bool Pack::page(uint32_t index) {
  if(!data_) { error_ = Error::MEMORY; return false; }
  if(index == page_) return true;
  if(index >= pages_) { error_ = Error::FORMAT; return false; }
  uint8_t d[16], h[32], packed[PAGE_BYTES];
  if(!reader_.read(reader_.context, 0, 64 + index * 16, d, sizeof(d))) {
    error_ = Error::IO; return false;
  }
  const uint16_t part = le16(d), at = le16(d + 2), stored = le16(d + 4), raw = le16(d + 6);
  if(part >= parts_ || at < 32 || !stored || !raw || stored > raw || raw > PAGE_BYTES ||
     raw != (index + 1 == pages_ ? logical_ - index * PAGE_BYTES : PAGE_BYTES)) {
    error_ = Error::FORMAT; return false;
  }
  const uint32_t size = reader_.size(reader_.context, uint16_t(part + 1));
  if(size < 32 || size > FILE_BYTES || at > size || stored > size - at ||
     !reader_.read(reader_.context, uint16_t(part + 1), 0, h, sizeof(h)) ||
     !reader_.read(reader_.context, uint16_t(part + 1), at, packed, stored)) {
    error_ = Error::IO; return false;
  }
  if(memcmp(h, "URQD", 4) || le16(h + 4) != PACK_VERSION || le16(h + 6) != part ||
     memcmp(h + 8, id_, 16) || le32(h + 28) != size - 32 ||
     crc32(packed, stored) != le32(d + 12)) { error_ = Error::CRC; return false; }
  if(stored == raw) memcpy(data_, packed, raw);
  else {
    struct Source { const uint8_t* bytes; uint16_t at, size; } source{packed, 0, stored};
    uint32_t written = 0;
    if(!zx0::decode({&source, [](void* p, uint8_t& b) {
          auto& s = *static_cast<Source*>(p);
          if(s.at == s.size) return false;
          b = s.bytes[s.at++]; return true;
        }}, stored, data_, raw, written) || written != raw) {
      error_ = Error::FORMAT; return false;
    }
  }
  if(crc32(data_, raw) != le32(d + 8)) { error_ = Error::CRC; return false; }
  page_ = index; valid_ = raw; return true;
}
bool Pack::read(uint32_t offset, void* output, uint32_t size) {
  if(offset > logical_ || size > logical_ - offset || (!output && size)) {
    error_ = Error::FORMAT; return false;
  }
  auto* out = static_cast<uint8_t*>(output);
  while(size) {
    const uint32_t index = offset / PAGE_BYTES, within = offset % PAGE_BYTES;
    if(!page(index) || within >= valid_) return false;
    uint32_t n = valid_ - within; if(n > size) n = size;
    memcpy(out, data_ + within, n); out += n; offset += n; size -= n;
  }
  return true;
}
bool Pack::string(uint32_t offset, char* out, uint16_t capacity) {
  if(!out || !capacity) { error_ = Error::LIMIT; return false; }
  for(uint16_t i = 0; i < capacity; ++i) {
    if(!read(offset++, out + i, 1)) return false;
    if(!out[i]) return true;
  }
  out[capacity - 1] = 0; error_ = Error::LIMIT; return false;
}
bool Pack::line(uint32_t index, char* out, uint16_t capacity) {
  if(index >= lines_) { error_ = Error::FORMAT; return false; }
  uint8_t p[4];
  return read(line_table_ + index * 4, p, 4) && string(le32(p), out, capacity);
}
bool Pack::info(uint8_t field, char* out, uint16_t capacity) {
  uint32_t at = metadata_;
  do {
    if(!string(at, out, capacity)) return false;
    at += strlen(out) + 1;
  } while(field--);
  return true;
}
bool Pack::resource(const char* name,char* out,uint16_t capacity,bool url) {
  if(!capacity) return false;
  *out=0;if(!resources_) return true;
  uint32_t at=metadata_;uint8_t byte;
  for(unsigned field=0;field<4;++field) do { if(!read(at++,&byte,1)) return false; } while(byte);
  uint8_t count[2],record[8];if(!read(at,count,2)) return false;at+=2;
  char normalized[128];unsigned n=0;
  while(*name==' ' || *name=='/' || *name=='\\') ++name;
  while(*name) { if(n+1==sizeof(normalized)) { error_=Error::LIMIT;return false; }
    normalized[n++]=*name=='\\'?'/':*name;++name; }
  while(n && normalized[n-1]==' ') --n;
  normalized[n]=0;
  for(unsigned index=0;index<le16(count);++index) {
    char candidate[128];if(!read(at+index*8,record,8) || !string(le32(record),candidate,sizeof(candidate))) return false;
    if(strcmp(candidate,normalized)) continue;
    return string(le32(record+(url?0:4)),out,capacity);
  }
  return true;
}
bool Pack::label_at(uint32_t index, char* name, uint16_t capacity, uint32_t& line) {
  if(index >= labels_) return false;
  uint8_t record[12];
  if(!read(label_table_ + index * 12, record, sizeof(record))) return false;
  line = le32(record + 8);
  if(line >= lines_) { error_ = Error::FORMAT; return false; }
  return string(le32(record + 4), name, capacity);
}
bool Pack::label(const char* name, uint32_t& line) {
  const uint32_t hash = hash_name(name);
  uint32_t lo = 0, hi = labels_;
  uint8_t record[12];
  char candidate[128];
  while(lo < hi) {
    const uint32_t mid = lo + (hi - lo) / 2;
    if(!read(label_table_ + mid * 12, record, 12)) return false;
    int order = le32(record) < hash ? -1 : le32(record) > hash ? 1 : 0;
    if(!order) {
      if(!string(le32(record + 4), candidate, sizeof(candidate))) return false;
      order = compare_name(candidate, name);
    }
    if(!order) {
      line = le32(record + 8);
      if(line < lines_) return true;
      error_ = Error::FORMAT; return false;
    }
    if(order < 0) lo = mid + 1; else hi = mid;
  }
  return false;
}
}
