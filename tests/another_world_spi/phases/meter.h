#pragma once
#include "hooks.h"
#include "wire.h"

// The foreground keeps a disjoint ledger. SM1 integrates physical CS-low
// time on core 1's SPI bus, including while the foreground is reading PSRAM.
typedef struct {
    uint32_t us, low;
} PhasePoint;
typedef struct {
    unsigned x, y, w, h, fill, preps, attempts, accepted;
    unsigned prep_start, submit_start, submit_end;
} PhaseRect;
typedef struct {
    unsigned lead, loops;
    int slack;
    PhasePoint elapsed;
} PhaseWait;
typedef struct {
    WirePoint first, last;
    PhasePoint prev, buckets[PH_COUNT];
    PhaseRect rect[8];
    PhaseWait waits[4];
    unsigned current, nrect, nwait, points, invalid, bytes, accepted, cost_us;
    bool detail, active;
} PhaseMeter;
static PhaseMeter *ph;

static inline PhasePoint ph_delta(PhasePoint b, PhasePoint a) { return (PhasePoint){b.us - a.us, b.low - a.low}; }
static PhasePoint ph_point(void) {
    ++ph->points;
#ifdef AW_TRACE_HOST
    return (PhasePoint){trace_time(), 0};
#else
    // SM1 has no WAIT, touches neither ISR nor its FIFO and runs at clk_sys.
    // MOV ISR,X and PUSH can run live. The other three SMs keep counting.
    const uint32_t us = NOW;
    return (PhasePoint){us, read_x(1)};
#endif
}
static void ph_charge(PhasePoint p) {
    PhasePoint dt = ph_delta(p, ph->prev);
    ph->buckets[ph->current].us += dt.us;
    ph->buckets[ph->current].low += dt.low;
    ph->prev = p;
}
unsigned ph_enter(unsigned phase) {
    if (!ph || !ph->active || !ph->detail)
        return PH_COUNT;
    const unsigned saved = ph->current;
    if (saved != phase) {
        ph_charge(ph_point());
        ph->current = phase;
    }
    return saved;
}
void ph_leave(unsigned saved) {
    if (saved < PH_COUNT)
        (void)ph_enter(saved);
}
static unsigned ph_find(unsigned x, unsigned y, unsigned w, unsigned h) {
    for (unsigned i = 0; i < ph->nrect; ++i) {
        const PhaseRect *r = ph->rect + i;
        if (r->x == x && r->y == y && r->w == w && r->h == h)
            return i;
    }
    if (ph->nrect == 8) {
        ++ph->invalid;
        return 8;
    }
    const unsigned i = ph->nrect++;
    ph->rect[i] = (PhaseRect){.x = x, .y = y, .w = w, .h = h};
    return i;
}
unsigned ph_prepare(unsigned x, unsigned y, unsigned w, unsigned h, unsigned fill) {
    if (!ph || !ph->active || !ph->detail)
        return PH_COUNT;
    unsigned i = ph_find(x, y, w, h);
    if (i == 8)
        return PH_COUNT;
    const unsigned saved = ph_enter(PH_PREP + i);
    PhaseRect *r = ph->rect + i;
    if (!r->preps++)
        r->prep_start = ph->prev.us - ph->first.us;
    r->fill = fill;
    return saved;
}
static unsigned ph_queue(unsigned x, unsigned y, unsigned w, unsigned h) {
    if (!ph->active || !ph->detail)
        return PH_COUNT;
    unsigned i = ph_find(x, y, w, h);
    return i < 8 ? ph_enter(PH_QUEUE + i) : PH_COUNT;
}
static void ph_attempt(unsigned result, unsigned x, unsigned y, unsigned w, unsigned h, PhasePoint start) {
    if (!ph->active)
        return;
    if (result == 1) {
        ++ph->accepted;
        ph->bytes += w * h * 2;
    }
    if (!ph->detail && result != 1)
        return;
    const PhasePoint end = ph->detail && result == 1 ? ph_point() : (PhasePoint){0, 0};
    unsigned i = ph_find(x, y, w, h);
    if (i == 8)
        return;
    PhaseRect *r = ph->rect + i;
    ++r->attempts;
    if (result != 1)
        return;
    ++r->accepted;
    if (!ph->detail)
        return;
    // Only the successful PRESENT call copies the indexed pixels into the
    // driver's snapshot. Busy calls stay in the enclosing queue interval.
    ph_charge(end);
    PhasePoint dt = ph_delta(end, start);
    ph->buckets[ph->current].us -= dt.us;
    ph->buckets[ph->current].low -= dt.low;
    ph->buckets[PH_SUBMIT + i].us += dt.us;
    ph->buckets[PH_SUBMIT + i].low += dt.low;
    r->submit_start = start.us - ph->first.us;
    r->submit_end = end.us - ph->first.us;
}
static unsigned ph_wait_begin(unsigned lead, uint32_t deadline, PhasePoint *begin) {
    if (!ph->active || !ph->detail)
        return PH_COUNT;
    if (ph->nwait == 4) {
        ++ph->invalid;
        return PH_COUNT;
    }
    unsigned saved = ph_enter(PH_TIMER);
    *begin = ph->prev;
    PhaseWait *w = ph->waits + ph->nwait;
    w->lead = lead;
    w->slack = (int32_t)(deadline - mk61_api->millis_ms());
    return saved;
}
static void ph_wait_end(unsigned saved, PhasePoint begin, unsigned loops) {
    if (saved == PH_COUNT)
        return;
    ph_leave(saved);
    PhaseWait *w = ph->waits + ph->nwait++;
    w->elapsed = ph_delta(ph->prev, begin);
    w->loops = loops;
}
static void ph_boundary(unsigned frame) {
    if (frame == 2440) {
        wire_point(&ph->first);
        ph->prev = (PhasePoint){ph->first.us, ph->first.selected};
        ph->current = PH_FRAME;
        ph->active = true;
    } else if (frame == 2441) {
        wire_point(&ph->last);
        ph_charge((PhasePoint){ph->last.us, ph->last.selected});
        ph->active = false;
    }
}
static bool ph_calibrate(void) {
    (void)wire_arm;
    (void)wire_collect;
    if (!wire_begin())
        return false;
    WirePoint a = {0}, b = {0};
    const uint32_t begin = trace_time();
    for (unsigned n = 0; n < 256; ++n)
        (void)ph_point();
    ph->cost_us = trace_time() - begin;
    ph->points = 0;
    wire_point(&a);
    uint16_t colors[16] = {0, 0xffff};
    if (!present_rect(NULL, 0, 1, 80, 64, screen.data, colors, false) || !page_select(NULL, 0))
        return false;
    wire_point(&b);
    report("PH CAL %u %u %u %u %u\n", b.us - a.us, b.selected - a.selected, b.edges - a.edges, b.blind - a.blind,
           ph->cost_us);
    return true;
}
static void ph_print(void) {
    report("PH FRAME %u %u %u %u %u %u %u %u %u\n", (unsigned)ph->detail, ph->last.us - ph->first.us,
           ph->last.selected - ph->first.selected, ph->last.edges - ph->first.edges, ph->bytes, ph->accepted,
           ph->points, ph->invalid, ph->last.blind - ph->first.blind);
    for (unsigned j = 0; j < PH_COUNT; ++j)
        report("PH B %u %u %u\n", j, ph->buckets[j].us, ph->buckets[j].low);
    for (unsigned i = 0; i < ph->nrect; ++i) {
        const PhaseRect *r = ph->rect + i;
        report("PH R %u %u %u %u %u %u %u %u %u %u %u %u\n", i, r->x, r->y, r->w, r->h, r->fill, r->preps, r->attempts,
               r->accepted, r->prep_start, r->submit_start, r->submit_end);
    }
    for (unsigned i = 0; i < ph->nwait; ++i) {
        const PhaseWait *w = ph->waits + i;
        report("PH T %u %d %u %u %u\n", w->lead, w->slack, w->loops, w->elapsed.us, w->elapsed.low);
    }
}
