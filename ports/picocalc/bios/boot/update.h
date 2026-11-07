#ifndef MK61_M3_BOOT_UPDATE_H
#define MK61_M3_BOOT_UPDATE_H
#include "protocol.h"
typedef struct {
  void *context;
  const uint8_t *(*read)(void *, uint32_t address, uint32_t bytes);
  int (*erase)(void *, uint32_t page);
  int (*program)(void *, uint32_t address, const uint8_t *, uint32_t bytes);
} m3b_flash;
typedef struct {
  m3b_flash flash;
  uint8_t header[M3B_HEADER];
  uint32_t received;
  uint8_t active, run;
} m3b_update;
void m3b_init(m3b_update *, const m3b_flash *);
int m3b_valid(m3b_update *);
/* Returns payload length including the status word. Request and reply must
 * not overlap; flash erases/programs are only issued by this state machine. */
unsigned m3b_command(m3b_update *, uint8_t, const uint8_t *, unsigned,
                     uint8_t *);
#endif
