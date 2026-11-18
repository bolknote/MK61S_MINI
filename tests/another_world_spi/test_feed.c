#include <assert.h>
#include <stdint.h>
#include <stdlib.h>
#include <stdio.h>
static uint32_t dma[12][16], spi_regs[16], gpio, tm;
static uint32_t *reg(uint32_t a) {
    if (a >= 0x50000000u && a < 0x50000300u) return &dma[(a - 0x50000000u) / 64][(a % 64) / 4];
    if (a >= 0x40040000u && a < 0x40040040u) return &spi_regs[(a % 64) / 4];
    if (a == 0xd0000004u) return &gpio;
    if (a == 0x40054028u) return &tm;
    abort();
}
#define REG(a) (*reg(a))
#include "feed.h"
int main(void) {
    FeedFrame frames[5] = {0};
    feed_frames = frames;
    FeedFrame *r = frames;
    assert(!feed_init());
    dma[6][4] = (18u << 15) | (9u << 11) | 4 | 16 | 1;
    dma[6][1] = SPI1 + 8;
    dma[7][4] = (19u << 15) | (7u << 11) | 4 | 1;
    dma[7][0] = SPI1 + 8;
    assert(feed_init() && tx == DMA(6) && rx == DMA(7) && ctl == DMA(9));
    feed_accept(320, 32);
    gpio = 1u << 14;
    spi_regs[0] = 15;
    spi_regs[3] = 1;
    dma[7][4] |= 1u << 24;
    dma[7][2] = 9280;
    uint32_t *regs[] = {&gpio,        &spi_regs[0], &dma[7][4], &dma[7][2], &dma[7][2],
                        &spi_regs[3], &spi_regs[3], &dma[6][4], &dma[9][4], &dma[6][2]};
    const uint32_t reject[] = {3u << 13, 7, 0, 0, 10240, 17, 0, 1u << 24, 1u << 24, 1};
    for (unsigned i = 0; i < sizeof(regs) / sizeof(*regs); ++i) {
        const uint32_t old = *regs[i];
        *regs[i] = reject[i];
        feed_poll(FFIRST);
        *regs[i] = old;
        assert(!r->hits && !r->positions);
    }
    tm = 25;
    feed_poll(FFIRST);
    tm = 33;
    feed_poll(FFIRST);
    assert(r->hits == 2 && r->positions == 1 && r->stripe == 1 && r->source_zero == 1 && r->confirmed_us == 8);
    spi_regs[3] = 17;
    feed_poll(FFIRST);
    spi_regs[3] = 1;
    tm = 60;
    feed_poll(FFIRST);
    assert(r->positions == 1 && r->confirmed_us == 8);
    dma[7][2] = 8320;
    tm = 70;
    feed_poll(FFIRST);
    assert(r->positions == 2 && r->stripe == 2 && r->last == 1920);
    feed_accept(320, 32);
    dma[7][2] = 8319;
    dma[6][0] = 0x20001000;
    feed_poll(FFIRST);
    assert(r->positions == 3 && r->stripe == 2 && r->source_zero == 2);
    puts("Register gate, strip boundaries, independent windows and time lower bound passed");
}
