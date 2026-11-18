#pragma once
#include <stdint.h>
#include <stdbool.h>
enum { FFIRST = 2438, FLAST = 2442 };
typedef struct {
    uint32_t polls, selected, running, positions, confirmed_us, hits, stripe, first, last, when, source_zero;
} FeedFrame;
static FeedFrame *feed_frames;
static unsigned rect_w, rect_h, serial, last_serial, last_rem, last_seen, previous_hit;
static void feed_accept(unsigned w, unsigned h) {
    rect_w = w;
    rect_h = h;
    ++serial;
    previous_hit = 0;
}
static inline void feed_record(FeedFrame *r, unsigned rem, unsigned now, bool zero) {
    const unsigned sent = rect_w * rect_h - rem;
    ++r->hits;
    if (serial != last_serial || rem != last_rem) {
        ++r->positions;
        if (!r->first) r->first = sent;
        r->last = sent;
        if (sent % (3 * rect_w) == 0) ++r->stripe;
        if (zero) ++r->source_zero;
    } else if (previous_hit)
        r->confirmed_us += now - last_seen;
    last_serial = serial;
    last_rem = rem;
    previous_hit = 1;
    last_seen = now;
}
#ifdef AW_TRACE_HOST
static bool feed_init(void) { return true; }
static void feed_poll(unsigned f) { (void)f; }
#else
#ifndef REG
#define REG(a) (*(volatile uint32_t *)(uintptr_t)(a))
#endif
#define DMA(n) (0x50000000u + 64u * (n))
#define SPI1 0x40040000u
#define GPIOIN REG(0xd0000004u)
#define TIMER_US REG(0x40054028u)
#define COUNT(n) REG((n) + 8)
#define BUSY(n) (REG((n) + 0x10) & (1u << 24))
static uint32_t tx, rx, ctl;
static bool feed_init(void) {
    for (unsigned i = 0; i < 12; ++i) {
        const uint32_t base = DMA(i), c = REG(base + 0x10), dreq = (c >> 15) & 63u;
        if (((c >> 2) & 3) != 1) continue;
        if (dreq == 18 && REG(base + 4) == SPI1 + 8) {
            tx = base;
            ctl = DMA((c >> 11) & 15u);
        }
        if (dreq == 19 && REG(base) == SPI1 + 8) rx = base;
    }
    return tx && rx && ctl != tx && ctl <= DMA(11);
}
static __attribute__((noinline)) void feed_poll(unsigned f) {
    if (f < FFIRST || f > FLAST) return;
    FeedFrame *r = feed_frames + f - FFIRST;
    ++r->polls;
    // Both CS low and DC high; DSS 16 excludes command/parameter traffic.
    if ((GPIOIN & (3u << 13)) != (1u << 14) || (REG(SPI1) & 15) != 15 || !rect_w) goto other;
    ++r->selected;
    const unsigned a = COUNT(rx);
    if (!BUSY(rx) || !a || a >= rect_w * rect_h) goto other;
    ++r->running;
    // An armed RX request part-way through the current window; both transmit
    // channels stopped, empty TX FIFO, idle shifter, same RX count on readback.
    if ((REG(SPI1 + 12) & 17) != 1 || BUSY(tx) || BUSY(ctl) || COUNT(tx) != 0) goto other;
    const unsigned addr = REG(tx), b = COUNT(rx);
    if (a != b || !BUSY(rx) || (REG(SPI1 + 12) & 17) != 1 || (GPIOIN & (3u << 13)) != (1u << 14)) goto other;
    feed_record(r, a, TIMER_US, addr == 0);
    return;
other:
    previous_hit = 0;
}
#endif
