#ifndef Z80_Z80_H_
#define Z80_Z80_H_

#include <stdio.h>
#include <stdint.h>
#include <stdbool.h>

typedef struct z80 z80;
struct z80 {
  /* Keep the live registers/flags in the first 32 bytes on Cortex-M0+.
   * Thumb-1 byte/halfword loads can then address them without rebuilding
   * a base pointer in every opcode. This is internal state, not a file ABI. */
  unsigned long cyc; // cycle count (t-states)

  uint16_t pc, sp, ix, iy; // special purpose registers
  uint16_t mem_ptr; // "wz" register
#if defined(__BYTE_ORDER__) && __BYTE_ORDER__ != __ORDER_LITTLE_ENDIAN__
#error "Native register pairs require a little-endian target"
#endif
  uint8_t a;
  // flags: sign, zero, yf, half-carry, xf, parity/overflow, negative, carry
  union {
    uint8_t f;
    struct { bool cf : 1, nf : 1, pf : 1, xf : 1, hf : 1, yf : 1, zf : 1, sf : 1; };
  };
  union { struct { uint8_t c, b; }; uint16_t bc; };
  union { struct { uint8_t e, d; }; uint16_t de; };
  union { struct { uint8_t l, h; }; uint16_t hl; };
  uint8_t i, r; // interrupt vector, memory refresh
  uint8_t iff_delay;
  uint8_t interrupt_mode;
  uint8_t int_data;
  bool iff1 : 1, iff2 : 1;
  bool halted : 1;
  bool int_pending : 1, nmi_pending : 1;
  uint8_t a_;
  uint8_t f_;
  union { struct { uint8_t c_, b_; }; uint16_t bc_; };
  union { struct { uint8_t e_, d_; }; uint16_t de_; };
  union { struct { uint8_t l_, h_; }; uint16_t hl_; };
  uint8_t (*read_byte)(void*, uint16_t);
  void (*write_byte)(void*, uint16_t, uint8_t);
  uint8_t (*port_in)(z80*, uint16_t);
  void (*port_out)(z80*, uint16_t, uint8_t);
  void* userdata;
  void (*m1)(void*,uint16_t,bool); /* Local: opcode-fetch paging, before/after. */
  uint16_t m1_start,m1_limit; /* Local: notify if (uint16_t)(PC-start)<=limit. */
  const uint8_t* read_map[4]; /* Local: contiguous windows for LDIR batching. */
  uint8_t* write_map[4];
  /* Authoritative 1K CPU views of all 64K. NULL entries use callbacks.
   * A clean cache page keeps its write view NULL until its first store. */
  const uint8_t* read_pages[64];
  uint8_t* write_pages[64];
  /* Optional LDIR batching deadline in virtual cycles; zero disables it.
   * Caller caps it before the next interrupt edge and clears it after a run. */
  uint32_t ldir_until;
};

void z80_init(z80* const z);
void z80_step(z80* const z);
/* Run whole instructions up to a caller-supplied external interrupt edge.
 * EI/NMI/INT are still processed after every instruction. HALT returns to
 * the machine scheduler; stop may report a memory/port callback failure.
 * Spans are capped to INT32_MAX so elapsed time cannot wrap the deadline. */
uint32_t z80_run(z80* z, uint32_t cycles, const bool* stop);
void z80_debug_output(z80* const z);
void z80_gen_nmi(z80* const z);
void z80_gen_int(z80* const z, uint8_t data);

#endif // Z80_Z80_H_
