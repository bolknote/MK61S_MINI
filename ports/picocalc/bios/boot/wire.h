#ifndef MK61_M3_BOOT_WIRE_H
#define MK61_M3_BOOT_WIRE_H
#include "update.h"
#define M3B_FRAME 272u
typedef struct {
  m3b_update update;
  uint8_t rx[M3B_FRAME], tx[M3B_FRAME];
  unsigned received, tx_bytes;
  uint32_t last_crc;
  uint16_t last_sequence;
  uint8_t last_command, have_reply, overflow;
} m3b_link;
unsigned m3b_encode(const uint8_t *, unsigned, uint8_t *, unsigned);
unsigned m3b_decode(uint8_t *, unsigned);
unsigned m3b_packet(uint8_t version, uint8_t command, uint16_t sequence,
                    const uint8_t *payload, unsigned bytes, uint8_t *out);
void m3b_link_init(m3b_link *, const m3b_flash *);
/* Zero means incomplete/ignored. Reply stays valid until next input byte. */
unsigned m3b_feed(m3b_link *, uint8_t);
#endif
