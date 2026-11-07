#ifndef MK61_M3_BOOT_PROTOCOL_H
#define MK61_M3_BOOT_PROTOCOL_H
#include <stddef.h>
#include <stdint.h>
#define M3B_FLASH 0x08000000u
#define M3B_APP 0x08002000u
#define M3B_META 0x0800f400u
#define M3B_SETTINGS 0x0800f800u
#define M3B_LIMIT (M3B_META - M3B_APP)
#define M3B_PAGE 1024u
#define M3B_TARGET 0x410u
#define M3B_MAGIC 0x3155334du /* M3U1 */
#define M3B_VALID 0xc001cafeu
#define M3B_HEADER 32u
#define M3B_WIRE_VERSION 0x42u
#define M3B_ENTER 0x30u
#define M3B_ENTER_MAGIC 0x544f4f42u
#define M3B_MAILBOX 0x20004fe0u
#define M3B_FORCE 0x5542334du
#define M3B_KEEP 0x5045454bu
#define M3B_BAUD 115200u
#define M3B_CHUNK 240u
/* All words on disk/wire are little endian. No packed native structs. */
enum { M3B_INFO = 1, M3B_BEGIN, M3B_WRITE, M3B_COMMIT, M3B_RUN, M3B_READ };
enum {
  M3B_OK,
  M3B_ARGUMENT,
  M3B_STATE,
  M3B_SIZE,
  M3B_CRC,
  M3B_FLASH_ERROR,
  M3B_VECTOR
};
static inline uint32_t m3b_get(const uint8_t *p) {
  return (uint32_t)p[0] | (uint32_t)p[1] << 8 | (uint32_t)p[2] << 16 |
         (uint32_t)p[3] << 24;
}
static inline void m3b_put(uint8_t *p, uint32_t v) {
  for (unsigned i = 0; i < 4; ++i)
    p[i] = (uint8_t)(v >> (8 * i));
}
static inline uint32_t m3b_crc_step(uint32_t v, const uint8_t *p, size_t n) {
  while (n--) {
    v ^= *p++;
    for (unsigned i = 0; i < 8; ++i)
      v = (v >> 1) ^ (0xedb88320u & (0u - (v & 1)));
  }
  return v;
}
static inline uint32_t m3b_crc(const uint8_t *p, size_t n) {
  return ~m3b_crc_step(~0u, p, n);
}
static inline int m3b_header_ok(const uint8_t *h) {
  const uint32_t size = m3b_get(h + 16);
  return m3b_get(h) == M3B_MAGIC && m3b_get(h + 4) == 1 &&
         m3b_get(h + 8) == M3B_TARGET && m3b_get(h + 12) == M3B_APP &&
         size >= 8 && size <= M3B_LIMIT && !(size & 3) &&
         m3b_get(h + 28) == m3b_crc(h, 28);
}
static inline int m3b_vectors_ok(const uint8_t *image, uint32_t size) {
  const uint32_t sp = m3b_get(image), entry = m3b_get(image + 4);
  return sp > 0x20000000u && sp <= M3B_MAILBOX && !(sp & 7) && (entry & 1) &&
         (entry & ~1u) >= M3B_APP && (entry & ~1u) - M3B_APP < size;
}
#endif
