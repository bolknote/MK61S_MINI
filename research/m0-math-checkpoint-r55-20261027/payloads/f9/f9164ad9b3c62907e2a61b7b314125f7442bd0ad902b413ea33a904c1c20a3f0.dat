#ifndef TERMINAL_FILE_TRANSFER_HPP
#define TERMINAL_FILE_TRANSFER_HPP

#include "rust_types.h"

namespace terminal_file_transfer {

// 96 байт превращаются в 192 hex-символа и вместе с `fsput data`, смещением
// и завершающим нулём гарантированно помещаются в 240-байтовую строку терминала.
static constexpr usize CHUNK_SIZE = 96;

inline u32 checksum_update(u32 crc, u8 value) {
  crc ^= (u32) value << 24;
  for(u8 bit = 0; bit < 8; bit++) {
    crc = (crc & 0x80000000u) != 0
        ? (crc << 1) ^ 0x04C11DB7u
        : crc << 1;
  }
  return crc;
}

inline u32 checksum_finish(u32 crc, usize length) {
  usize remaining = length;
  while(remaining != 0) {
    crc = checksum_update(crc, (u8) (remaining & 0xFF));
    remaining >>= 8;
  }
  return ~crc;
}

// Алгоритм утилиты POSIX `cksum`: CRC-32 дополняется байтами длины файла
// от младшего к старшему, затем инвертируется. Поэтому хосту не нужна своя
// нестандартная реализация ни в shell, ни в будущем PowerShell-порте.
inline u32 checksum(const u8* data, usize length) {
  u32 crc = 0;
  for(usize i = 0; i < length; i++) crc = checksum_update(crc, data[i]);
  return checksum_finish(crc, length);
}

inline int hex_digit(char c) {
  if(c >= '0' && c <= '9') return c - '0';
  if(c >= 'a' && c <= 'f') return c - 'a' + 10;
  if(c >= 'A' && c <= 'F') return c - 'A' + 10;
  return -1;
}

inline char hex_char(u8 value) {
  return value < 10 ? (char) ('0' + value) : (char) ('A' + value - 10);
}

inline bool decode_hex(const char* text, u8* out, usize capacity,
                       usize& out_length) {
  out_length = 0;
  if(text == nullptr || out == nullptr) return false;
  while(text[0] != 0) {
    if(text[1] == 0 || out_length >= capacity) return false;
    const int high = hex_digit(text[0]);
    const int low = hex_digit(text[1]);
    if(high < 0 || low < 0) return false;
    out[out_length++] = (u8) ((high << 4) | low);
    text += 2;
  }
  return true;
}

} // пространство имён terminal_file_transfer

#endif
