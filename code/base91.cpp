#include "base91.hpp"
#include <string.h>

namespace base91 {
static const char alphabet[] =
    "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789"
    "!#$%&()*+,./:;<=>?@[]^_`{|}~\"";

bool encode(const u8* bytes, usize size, const Output& output) {
  u32 queue = 0;
  u8 bits = 0;
  for(usize i = 0; i < size; ++i) {
    queue |= u32(bytes[i]) << bits;
    bits += 8;
    if(bits > 13) {
      u16 value = queue & 8191U;
      const u8 count = value > 88 ? 13 : 14;
      if(count == 14) value = queue & 16383U;
      queue >>= count;
      bits -= count;
      if(!output.put(output.context, alphabet[value % 91]) ||
         !output.put(output.context, alphabet[value / 91])) return false;
    }
  }
  if(bits != 0) {
    if(!output.put(output.context, alphabet[queue % 91])) return false;
    if((bits > 7 || queue > 90) &&
       !output.put(output.context, alphabet[queue / 91])) return false;
  }
  return true;
}

struct Compare { const char* cursor; const char* end; };
static bool compare(void* context, char value) {
  Compare& text = *static_cast<Compare*>(context);
  return text.cursor != text.end && *text.cursor++ == value;
}

bool decode(const char* text, usize size, u8* bytes, usize capacity, usize& written) {
  written = 0;
  if(text == nullptr || bytes == nullptr || size < 2) return false;
  u32 queue = 0;
  u8 bits = 0;
  int first = -1;
  for(usize i = 0; i < size; ++i) {
    const char* found = text[i] == 0 ? nullptr : strchr(alphabet, text[i]);
    if(found == nullptr) return false;
    const int digit = found - alphabet;
    if(first < 0) { first = digit; continue; }
    const u16 value = first + 91 * digit;
    first = -1;
    queue |= u32(value) << bits;
    bits += (value & 8191U) > 88 ? 13 : 14;
    while(bits >= 8) {
      if(written == capacity) return false;
      bytes[written++] = (u8) queue;
      queue >>= 8;
      bits -= 8;
    }
  }
  if(first >= 0) {
    if(written == capacity) return false;
    bytes[written++] = (u8) (queue | (u32(first) << bits));
  }
  Compare expected = {text, text + size};
  return encode(bytes, written, {&expected, compare}) && expected.cursor == expected.end;
}
} // namespace base91
