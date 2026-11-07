#include "wire.h"
#include <string.h>
unsigned m3b_encode(const uint8_t *in, unsigned n, uint8_t *out, unsigned cap) {
  if (!cap)
    return 0;
  unsigned at = 1, code_at = 0;
  uint8_t code = 1;
  for (unsigned i = 0; i < n; ++i) {
    if (!in[i]) {
      out[code_at] = code;
      code_at = at++;
      code = 1;
      if (at > cap)
        return 0;
    } else {
      if (at >= cap)
        return 0;
      out[at++] = in[i];
      if (++code == 255) {
        out[code_at] = code;
        code_at = at++;
        code = 1;
        if (at > cap)
          return 0;
      }
    }
  }
  out[code_at] = code;
  return at;
}
unsigned m3b_decode(uint8_t *bytes, unsigned n) {
  unsigned at = 0, i = 0;
  while (i < n) {
    const unsigned code = bytes[i++];
    if (!code || code - 1 > n - i)
      return 0;
    for (unsigned j = 1; j < code; ++j) {
      if (!bytes[i])
        return 0;
      bytes[at++] = bytes[i++];
    }
    if (code != 255 && i < n)
      bytes[at++] = 0;
  }
  return at;
}
unsigned m3b_packet(uint8_t version, uint8_t command, uint16_t sequence,
                    const uint8_t *payload, unsigned bytes, uint8_t *out) {
  if (bytes > 256)
    return 0;
  uint8_t raw[268];
  raw[0] = version;
  raw[1] = command;
  raw[2] = (uint8_t)sequence;
  raw[3] = (uint8_t)(sequence >> 8);
  raw[4] = (uint8_t)bytes;
  raw[5] = (uint8_t)(bytes >> 8);
  raw[6] = raw[7] = 0;
  if (bytes)
    memcpy(raw + 8, payload, bytes);
  m3b_put(raw + 8 + bytes, m3b_crc(raw, 8 + bytes));
  out[0] = 0;
  const unsigned n = m3b_encode(raw, 12 + bytes, out + 1, M3B_FRAME - 2);
  if (!n)
    return 0;
  out[n + 1] = 0;
  return n + 2;
}
void m3b_link_init(m3b_link *l, const m3b_flash *f) {
  memset(l, 0, sizeof(*l));
  m3b_init(&l->update, f);
}
unsigned m3b_feed(m3b_link *l, uint8_t v) {
  if (v) {
    if (l->received < sizeof(l->rx))
      l->rx[l->received++] = v;
    else
      l->overflow = 1;
    return 0;
  }
  if (!l->received && !l->overflow)
    return 0;
  const unsigned n = l->overflow ? 0 : m3b_decode(l->rx, l->received);
  l->received = l->overflow = 0;
  if (n < 12 || l->rx[0] != M3B_WIRE_VERSION || !l->rx[1] || (l->rx[1] & 128) ||
      l->rx[6] || l->rx[7])
    return 0;
  const unsigned bytes = (unsigned)l->rx[4] | (unsigned)l->rx[5] << 8;
  if (bytes > 256 || n != 12 + bytes ||
      m3b_crc(l->rx, n - 4) != m3b_get(l->rx + n - 4))
    return 0;
  const uint16_t sequence =
      (uint16_t)((unsigned)l->rx[2] | (unsigned)l->rx[3] << 8);
  const uint8_t command = l->rx[1];
  const uint32_t crc = m3b_get(l->rx + n - 4);
  if (l->have_reply && sequence == l->last_sequence)
    return command == l->last_command && crc == l->last_crc ? l->tx_bytes : 0;
  uint8_t answer[256];
  const unsigned size =
      m3b_command(&l->update, command, l->rx + 8, bytes, answer);
  l->tx_bytes = m3b_packet(M3B_WIRE_VERSION, (uint8_t)(command | 128), sequence,
                           answer, size, l->tx);
  l->last_sequence = sequence;
  l->last_command = command;
  l->last_crc = crc;
  l->have_reply = 1;
  return l->tx_bytes;
}
