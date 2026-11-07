#include "update.h"
#include <string.h>
static const uint8_t *read_at(m3b_update *u, uint32_t at, uint32_t n) {
  return u->flash.read(u->flash.context, at, n);
}
void m3b_init(m3b_update *u, const m3b_flash *f) {
  memset(u, 0, sizeof(*u));
  u->flash = *f;
}
int m3b_valid(m3b_update *u) {
  const uint8_t *h = read_at(u, M3B_META, M3B_HEADER + 4);
  if (!h || m3b_get(h + M3B_HEADER) != M3B_VALID || !m3b_header_ok(h))
    return 0;
  const uint32_t n = m3b_get(h + 16);
  const uint8_t *image = read_at(u, M3B_APP, n);
  return image && m3b_vectors_ok(image, n) &&
         m3b_crc(image, n) == m3b_get(h + 20);
}
static unsigned command(m3b_update *u, uint8_t op, const uint8_t *in,
                        unsigned n, uint8_t *out, unsigned *used) {
  switch (op) {
  case M3B_INFO: {
    if (n)
      return M3B_ARGUMENT;
    const uint8_t *h = read_at(u, M3B_META, M3B_HEADER + 4);
    const uint8_t *boot = read_at(u, M3B_FLASH, M3B_APP - M3B_FLASH);
    const uint32_t v[10] = {1,
                            M3B_TARGET,
                            M3B_APP,
                            M3B_LIMIT,
                            M3B_META,
                            (uint32_t)m3b_valid(u),
                            h && m3b_header_ok(h) ? m3b_get(h + 16) : 0,
                            h && m3b_header_ok(h) ? m3b_get(h + 20) : 0,
                            u->received,
                            boot ? m3b_crc(boot, M3B_APP - M3B_FLASH) : 0};
    for (unsigned i = 0; i < 10; ++i)
      m3b_put(out + 4 * i, v[i]);
    *used = 40;
    return M3B_OK;
  }
  case M3B_BEGIN: {
    if (n != M3B_HEADER || !m3b_header_ok(in))
      return M3B_ARGUMENT;
    u->active = 0;
    u->run = 0;
    u->received = 0;
    /* Invalidate BEFORE any application page can change. If power is lost
     * during this erase, the old valid application has not been touched. */
    if (!u->flash.erase(u->flash.context, M3B_META))
      return M3B_FLASH_ERROR;
    const uint8_t *marker = read_at(u, M3B_META, M3B_HEADER + 4);
    if (!marker || m3b_get(marker + M3B_HEADER) != ~0u)
      return M3B_FLASH_ERROR;
    memcpy(u->header, in, M3B_HEADER);
    const uint32_t size = m3b_get(in + 16);
    for (uint32_t p = M3B_APP; p < M3B_APP + size; p += M3B_PAGE)
      if (!u->flash.erase(u->flash.context, p))
        return M3B_FLASH_ERROR;
    u->active = 1;
    return M3B_OK;
  }
  case M3B_WRITE: {
    if (!u->active)
      return M3B_STATE;
    if (n < 6 || n > 4 + M3B_CHUNK || ((n - 4) & 1))
      return M3B_SIZE;
    const uint32_t at = m3b_get(in), count = n - 4,
                   size = m3b_get(u->header + 16);
    if ((at & 1) || at > size || count > size - at || at > u->received)
      return M3B_SIZE;
    if (at < u->received) {
      if (count > u->received - at)
        return M3B_SIZE;
      const uint8_t *old = read_at(u, M3B_APP + at, count);
      if (!old || memcmp(old, in + 4, count))
        return M3B_ARGUMENT;
    } else {
      if (!u->flash.program(u->flash.context, M3B_APP + at, in + 4, count))
        return M3B_FLASH_ERROR;
      const uint8_t *saved = read_at(u, M3B_APP + at, count);
      if (!saved || memcmp(saved, in + 4, count))
        return M3B_FLASH_ERROR;
      u->received += count;
    }
    m3b_put(out, u->received);
    *used = 4;
    return M3B_OK;
  }
  case M3B_COMMIT: {
    if (n)
      return M3B_ARGUMENT;
    /* An ACK may be lost after committing. A fresh COMMIT is harmless. */
    if (!u->active)
      return m3b_valid(u) ? M3B_OK : M3B_STATE;
    const uint32_t size = m3b_get(u->header + 16);
    if (u->received != size)
      return M3B_STATE;
    const uint8_t *image = read_at(u, M3B_APP, size);
    if (!image || m3b_crc(image, size) != m3b_get(u->header + 20))
      return M3B_CRC;
    if (!m3b_vectors_ok(image, size))
      return M3B_VECTOR;
    if (!u->flash.program(u->flash.context, M3B_META, u->header, M3B_HEADER))
      return M3B_FLASH_ERROR;
    uint8_t marker[4];
    m3b_put(marker, M3B_VALID);
    if (!u->flash.program(u->flash.context, M3B_META + M3B_HEADER, marker, 4))
      return M3B_FLASH_ERROR;
    if (!m3b_valid(u))
      return M3B_FLASH_ERROR;
    u->active = 0;
    return M3B_OK;
  }
  case M3B_RUN:
    if (n)
      return M3B_ARGUMENT;
    if (!m3b_valid(u))
      return M3B_STATE;
    u->run = 1;
    return M3B_OK;
  case M3B_READ: {
    if (n != 8)
      return M3B_ARGUMENT;
    const uint32_t at = m3b_get(in), count = m3b_get(in + 4);
    if (at < M3B_FLASH || at > M3B_META + M3B_PAGE ||
        count > M3B_META + M3B_PAGE - at || count > M3B_CHUNK)
      return M3B_SIZE;
    const uint8_t *data = read_at(u, at, count);
    if (!data)
      return M3B_ARGUMENT;
    memcpy(out, data, count);
    *used = count;
    return M3B_OK;
  }
  default:
    return M3B_ARGUMENT;
  }
}
unsigned m3b_command(m3b_update *u, uint8_t op, const uint8_t *in, unsigned n,
                     uint8_t *out) {
  unsigned used = 0;
  const unsigned status = command(u, op, in, n, out + 4, &used);
  m3b_put(out, status);
  return status ? 4 : 4 + used;
}
