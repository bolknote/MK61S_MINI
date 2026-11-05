#ifndef Z80_Z80_H_
#define Z80_Z80_H_

#include <stdio.h>
#include <stdint.h>
#include <stdbool.h>

typedef struct z80 z80;
struct z80 {
  uint8_t (*read_byte)(void*, uint16_t);
  void (*write_byte)(void*, uint16_t, uint8_t);
  uint8_t (*port_in)(z80*, uint16_t);
  void (*port_out)(z80*, uint16_t, uint8_t);
  void* userdata;
  void (*m1)(void*,uint16_t,bool); /* Local: opcode-fetch paging, before/after. */
  uint16_t m1_start,m1_limit; /* Local: notify if (uint16_t)(PC-start)<=limit. */
  const uint8_t* read_map[4]; /* Local: direct 16K windows; NULL uses callbacks. */
  uint8_t* write_map[4];

  unsigned long cyc; // cycle count (t-states)

  uint16_t pc, sp, ix, iy; // special purpose registers
  uint16_t mem_ptr; // "wz" register
#if defined(__BYTE_ORDER__) && __BYTE_ORDER__ != __ORDER_LITTLE_ENDIAN__
#error "Native register pairs require a little-endian target"
#endif
  uint8_t a;
  union { struct { uint8_t c, b; }; uint16_t bc; };
  union { struct { uint8_t e, d; }; uint16_t de; };
  union { struct { uint8_t l, h; }; uint16_t hl; };
  uint8_t a_;
  union { struct { uint8_t c_, b_; }; uint16_t bc_; };
  union { struct { uint8_t e_, d_; }; uint16_t de_; };
  union { struct { uint8_t l_, h_; }; uint16_t hl_; };
  uint8_t f_;
  uint8_t i, r; // interrupt vector, memory refresh

  // flags: sign, zero, yf, half-carry, xf, parity/overflow, negative, carry
  union {
    uint8_t f;
    struct { bool cf : 1, nf : 1, pf : 1, xf : 1, hf : 1, yf : 1, zf : 1, sf : 1; };
  };

  uint8_t iff_delay;
  uint8_t interrupt_mode;
  uint8_t int_data;
  bool iff1 : 1, iff2 : 1;
  bool halted : 1;
  bool int_pending : 1, nmi_pending : 1;
  /* Optional 1K pages when a 16K window is absent. Indices 0..15 mirror
   * 0000..3FFF, 16..31 mirror C000..FFFF; direct windows take priority. */
  const uint8_t* read_pages[32];
  uint8_t* write_pages[32];
  /* Optional LDIR batching deadline in virtual cycles; zero disables it.
   * Caller caps it before the next interrupt edge and clears it after a run. */
  uint32_t ldir_until;
};

void z80_init(z80* const z);
void z80_step(z80* const z);
void z80_debug_output(z80* const z);
void z80_gen_nmi(z80* const z);
void z80_gen_int(z80* const z, uint8_t data);

#endif // Z80_Z80_H_
