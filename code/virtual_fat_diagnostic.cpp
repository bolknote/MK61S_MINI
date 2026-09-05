#include "virtual_fat_diagnostic.hpp"
#include <stdio.h>
#include <string.h>

namespace virtual_fat {
namespace {

static void copy_subject(Diagnostic& value, const char* text) {
  if(text == nullptr) return;
  usize out = 0;
  while(*text != 0) {
    const u8 lead = (u8) text[0];
    usize width = lead < 0x80 ? 1 : lead >= 0xC2 && lead <= 0xDF ? 2
        : lead >= 0xE0 && lead <= 0xEF ? 3
        : lead >= 0xF0 && lead <= 0xF4 ? 4 : 0;
    bool valid = width != 0;
    for(usize i = 1; valid && i < width; ++i) {
      const u8 byte = (u8) text[i];
      valid = (byte & 0xC0) == 0x80;
      if(i == 1) {
        valid = valid && !(lead == 0xE0 && byte < 0xA0) &&
            !(lead == 0xED && byte >= 0xA0) &&
            !(lead == 0xF0 && byte < 0x90) &&
            !(lead == 0xF4 && byte >= 0x90);
      }
    }
    if(!valid) width = 1;
    if(out + width >= sizeof(value.subject)) {
      value.flags |= SUBJECT_TRUNCATED;
      break;
    }
    if(!valid || lead < 0x20 || lead == 0x7F || lead == '/' || lead == '\\') {
      value.subject[out++] = '?';
      ++text;
    } else {
      memcpy(value.subject + out, text, width);
      out += width;
      text += width;
    }
  }
  value.subject[out] = 0;
}

} // namespace

void DiagnosticState::begin_attempt() { recorded = false; }
void DiagnosticState::clear() { value = {}; recorded = false; }

bool DiagnosticState::record_simple(u16 descriptor) {
  return record(descriptor, 0, 0, nullptr);
}

bool DiagnosticState::record(u16 descriptor, u32 actual, u32 limit,
                             const char* subject) {
  const u8 flags = (descriptor & 0x8000U) != 0 ? RETRYABLE : 0;
  if(!recorded) {
    value = {};
    value.code = (ErrorCode) (descriptor & 0x7FFU);
    value.phase = (Phase) ((descriptor >> 11) & 0xFU);
    value.flags = flags;
    value.actual = actual;
    value.limit = limit;
    copy_subject(value, subject);
    recorded = true;
  }
  // Cleanup/apply can make retry necessary without changing the first cause.
  value.flags |= flags;
  return false;
}

bool format_diagnostic(const Diagnostic& value, char* output, usize capacity) {
  if(output == nullptr || capacity == 0) return false;
  const int prefix = snprintf(output, capacity,
      "VFAT v=1 code=%u phase=%u flags=%u actual=%lu limit=%lu subject=",
      (unsigned) value.code, (unsigned) value.phase, (unsigned) value.flags,
      (unsigned long) value.actual, (unsigned long) value.limit);
  if(prefix < 0 || (usize) prefix >= capacity) return false;
  usize pos = (usize) prefix;
  static constexpr char HEX[] = "0123456789ABCDEF";
  for(usize i = 0; i < sizeof(value.subject) && value.subject[i] != 0; ++i) {
    if(capacity - pos <= 2) { output[pos] = 0; return false; }
    const u8 byte = (u8) value.subject[i];
    output[pos++] = HEX[byte >> 4];
    output[pos++] = HEX[byte & 15];
  }
  output[pos] = 0;
  return true;
}

void format_error_code(ErrorCode code, char (&output)[10]) {
  if(code == ErrorCode::NONE) {
    memcpy(output, "USB error", sizeof(output));
    return;
  }
  unsigned number = (unsigned) code;
  memcpy(output, "USB E0000", sizeof(output));
  for(u8 column = 8; column >= 5; --column) {
    output[column] = (char) ('0' + number % 10);
    number /= 10;
  }
}

} // namespace virtual_fat
