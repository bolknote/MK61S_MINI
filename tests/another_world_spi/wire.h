#pragma once
#include <stdint.h>
#include <stdbool.h>
typedef struct {
    uint32_t us, edges, selected, gaps, blind, bytes, rects;
} WirePoint;
typedef struct {
    uint32_t words[8];
    unsigned n, bits;
} WireBurst;
#ifdef AW_TRACE_HOST
static bool wire_begin(void) { return true; }
static void wire_end(void) {}
static void wire_arm(unsigned bits) { (void)bits; }
static void wire_collect(WireBurst *w, unsigned bits) { w->bits = bits; }
static void wire_point(WirePoint *p) { p->us = trace_time(); }
#else
#define PICO_NO_HARDWARE 1
#include "wire.pio.h"
#define IO32(a) (*(volatile uint32_t *)(uintptr_t)(a))
#define PIO(o) IO32(0x50200000u + (o))
#define SM(n, o) PIO(0xc8u + (n) * 0x18u + (o))
#define EXEC(n, i) (SM(n, 16) = (i))
#define NOW IO32(0x40054028u)
#define RESET_PIO0 (1u << 10)
static bool wire_owned, wire_was_reset;
static uint32_t blind_us;
static void wire_end(void) {
    if (!wire_owned) return;
    PIO(0) = 0;
    IO32(0x4000e000u) = RESET_PIO0; // RESETS atomic SET
    if (!wire_was_reset) {
        IO32(0x4000f000u) = RESET_PIO0; // atomic CLR
        const uint32_t start = NOW;
        while (!(IO32(0x4000c008u) & RESET_PIO0) && NOW - start < 100) {
        }
    }
    wire_owned = false;
}
static bool wire_begin(void) {
    wire_was_reset = (IO32(0x4000c000u) & RESET_PIO0) != 0;
    if (wire_was_reset) {
        IO32(0x4000f000u) = RESET_PIO0;
        const uint32_t start = NOW;
        while (!(IO32(0x4000c008u) & RESET_PIO0)) {
            if (NOW - start > 100) {
                IO32(0x4000e000u) = RESET_PIO0;
                return false;
            }
        }
    }
    // Only use an unused, reset-default PIO block. No GPIO function or direction writes.
    bool empty = !PIO(0) && PIO(4) == 0x0f000f00u && !PIO(12) && !PIO(0x30) && !PIO(0x38) && !PIO(0x3c) &&
                 !PIO(0x40) && !PIO(0x12c) && !PIO(0x130) && !PIO(0x138) && !PIO(0x13c);
    for (unsigned n = 0; n < 4; ++n)
        empty = empty && SM(n, 0) == 0x10000 && SM(n, 4) == 0x1f000 && SM(n, 8) == 0xc0000 && !SM(n, 12) &&
                SM(n, 20) == 0x14000000;
    if (!empty) {
        if (wire_was_reset) IO32(0x4000e000u) = RESET_PIO0;
        return false;
    }
    wire_owned = true;
    for (unsigned i = 0; i < sizeof(wire_program_instructions) / sizeof(uint16_t); ++i)
        PIO(0x48 + i * 4) = wire_program_instructions[i];
    const unsigned pc[] = {wire_offset_edge, wire_offset_selected, wire_offset_gap, wire_offset_raw};
    for (unsigned n = 0; n < 4; ++n) {
        const unsigned pin = n == 2 ? 10 : 13;
        const unsigned low = n == 3 ? wire_offset_sample : pc[n];
        const unsigned high = n == 3 ? wire_offset_sample : pc[n + 1] - 1;
        SM(n, 4) = (pin << 24) | (low << 7) | (high << 12);
        SM(n, 20) = (n == 2 ? 13u : 10u) << 15;
        SM(n, 8) = 0;
        EXEC(n, 0xa02b); // MOV X, ~NULL
        EXEC(n, pc[n]);
    }
    PIO(0) = 7;
    return true;
}
static void wire_arm(unsigned bits) {
    PIO(0) = 7;
    SM(3, 8) = 0;                       // toggling FJOIN_RX flushes the old waveform
    SM(3, 8) = (1u << 31) | (1u << 16); // join RX, push on 32 bits, shift left
    PIO(0) = (1u << 7) | 7;             // restart SM3 shift counters and stalled IN only
    PIO(0x48 + 4 * wire_offset_sample) = 0x4000u | bits;
    EXEC(3, wire_offset_raw);
    PIO(0) = 15;
}
static void wire_collect(WireBurst *w, unsigned bits) {
    PIO(0) = 7;
    w->bits = bits;
    w->n = 0;
    while (w->n < 8 && !(PIO(4) & (1u << 11)))
        w->words[w->n++] = PIO(0x2c);
}
static uint32_t read_x(unsigned n) {
    // The normal SM PC stays at the next instruction. Preserve the gap classifier's ISR.
    uint32_t saved = 0;
    if (n == 2) {
        EXEC(n, 0x8000);
        saved = PIO(0x20 + n * 4);
    }
    EXEC(n, 0xa0c1); // MOV ISR, X
    EXEC(n, 0x8000); // PUSH NOBLOCK
    const uint32_t v = ~PIO(0x20 + n * 4);
    if (n == 2) {
        PIO(0x10 + n * 4) = saved;
        EXEC(n, 0x8080);
        EXEC(n, 0xa0c7); // PULL; MOV ISR, OSR
    }
    return v;
}
static void wire_point(WirePoint *p) {
    const unsigned raw = PIO(0) & 8;
    const uint32_t start = NOW;
    PIO(0) = raw;
    p->edges = read_x(0);
    p->selected = read_x(1);
    p->gaps = read_x(2);
    PIO(0) = raw | 7;
    const uint32_t end = NOW;
    p->us = start;
    p->blind = blind_us;
    blind_us += end - start;
}
#endif
