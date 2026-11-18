#pragma once
#include "wire.h"

enum { WB_FRAME = 2440, WB_FIRST = 2438, WB_LAST = 2442 };
typedef struct {
    uint32_t base, geometry, accepted, visible_count, bytes, displayed_page;
    uint32_t early_writes, early_bytes, copy_writes, copy_bytes, other_bytes;
    uint32_t early_us, copy_started, copy_us, copies, copy_ended;
} WritebackPage;
static struct {
    uint32_t boundaries[TRACE_LAST - TRACE_FIRST + 2], visible[3];
    WirePoint wire[WB_LAST - WB_FIRST + 2];
#ifdef AW_PAGE_PAIR
    WirePoint visible_wire[5]; // The three color fences, between the latches at 2438 and 2442.
    unsigned latches, black_latches;
#endif
    WritebackPage pages[2], *current;
    unsigned mode;
    bool writing, copying;
} wb;

static void wb_boundary(unsigned frame) {
    if (frame < TRACE_FIRST || frame > TRACE_LAST + 1) return;
    wb.boundaries[frame - TRACE_FIRST] = trace_time();
    if (frame >= WB_FIRST && frame <= WB_LAST + 1) wire_point(&wb.wire[frame - WB_FIRST]);
    wb.current = NULL;
    if (frame == WB_FRAME) wb.current = &wb.pages[1];
#ifdef AW_PAGE_PAIR
    if (frame == WB_FRAME - 1) wb.current = &wb.pages[0];
#endif
}

// At 125 MHz the renderer fences the final visible window before checking
// the deadline. The CPU can see completion a little later than the last bit.
void wb_visible_done(unsigned index) {
    if (index >= 3 || intro != WB_FRAME - 1 + index) return;
#ifdef AW_PAGE_PAIR
    WirePoint *point = &wb.visible_wire[index + 1];
    wire_point(point);
    wb.visible[index] = point->us;
#else
    wb.visible[index] = trace_time();
#endif
}

void wb_copy_begin(void) {
    if (!wb.current) return;
    ++wb.current->copies;
    wb.current->copy_started = trace_time();
    wb.copying = true;
}

void wb_copy_end(void) {
    if (!wb.copying) return;
    wb.current->copy_ended = trace_time();
    wb.current->copy_us += wb.current->copy_ended - wb.current->copy_started;
    wb.copying = false;
}

// Count successful writes to the backing slot selected before the eviction.
static void wb_store(uint32_t offset, unsigned bytes) {
    WritebackPage *p = wb.current;
    if (!p || !p->visible_count || offset < p->base || offset - p->base >= AW_VIDEO_PAGE_BYTES) return;
    if (wb.writing) {
        ++p->early_writes;
        p->early_bytes += bytes;
    } else if (wb.copying) {
        ++p->copy_writes;
        p->copy_bytes += bytes;
    } else {
        p->other_bytes += bytes;
    }
}

static bool wb_accept(unsigned x, unsigned y, unsigned width, unsigned height) {
    WritebackPage *p = wb.current;
    if (!p) return true;
    ++p->accepted;
    const unsigned area = width * height;
    p->bytes += area * 2;
    p->geometry = (p->geometry * 16777619u ^ ((x << 16) | y)) * 16777619u ^ ((width << 16) | height);
    if (width == AW_VIDEO_WIDTH) return true;
    if (!p->visible_count) {
        p->displayed_page = video->resident_page;
        p->base = video->page_base + video->store_slot[p->displayed_page] * AW_VIDEO_PAGE_BYTES;
    }
    ++p->visible_count;
#ifdef AW_PAGE_PAIR
    const unsigned batches = storm->tail.writeback_batches;
#elif defined(AW_WRITE_LARGE_WINDOWS_ONLY)
    const unsigned batches = wb.mode && area >= 5000 ? area / 2000 : 0;
#else
    const unsigned batches = wb.mode ? 2 : 0;
#endif
    if (!batches) return true;
    const uint32_t start = trace_time();
    wb.writing = true;
    const bool ok = aw_video_write_displayed(video, batches);
    wb.writing = false;
    p->early_us += trace_time() - start;
    return ok;
}

static bool wb_calibrate(void) {
    (void)wire_arm;
    (void)wire_collect;
    if (!wire_begin()) return false;
    WirePoint before = {0}, after = {0};
    uint16_t palette[16] = {0, 0xffff};
    wire_point(&before);
    if (!present_rect(NULL, 0, 1, 80, 64, screen.data, palette, false) || !page_select(NULL, 0)) return false;
    wire_point(&after);
    report("WB CAL %u %u %u\n", after.us - before.us, after.edges - before.edges, after.selected - before.selected);
    return true;
}

static void wb_print_page(const char *label, const WritebackPage *p) {
    report("WB %s %u %u %u %u %u %u %u %u %u %u %u\n", label, p->displayed_page, p->copies, p->early_writes,
           p->early_bytes, p->copy_writes, p->copy_bytes, p->other_bytes, p->early_us, p->copy_us,
           p->visible_count, p->accepted);
}

static void wb_print(void) {
#ifdef AW_PAGE_PAIR
    report("WB PAIR %u %u\n", storm->tail.writeback[0].min_pixels, storm->tail.writeback[1].min_pixels);
    report("WB ROUND %u %u\n", storm->tail.writeback[0].round_pixels, storm->tail.writeback[1].round_pixels);
    report("WB BLACK_ROWS %u %u %u\n", storm->tail.black_before_rows[0], storm->tail.black_before_rows[1],
           storm->tail.black_before_rows[2]);
    wb_print_page("PREVIOUS", &wb.pages[0]);
    report("WB PREVLCD %u %08X\n", wb.pages[0].bytes, wb.pages[0].geometry);
    for (unsigned i = 0; i < 2; ++i) {
        const unsigned f = WB_FRAME - 1 + i;
        const uint32_t start = wb.boundaries[f - TRACE_FIRST];
        report("WB COPY %u %u %u\n", f, wb.pages[i].copy_started - start, wb.pages[i].copy_ended - start);
    }
    report("WB LATCH %u %u\n", wb.latches, wb.visible_wire[0].us - wb.boundaries[2438 - TRACE_FIRST]);
    report("WB BLACK %u %u\n", wb.black_latches, wb.visible_wire[4].us - wb.boundaries[2442 - TRACE_FIRST]);
    for (unsigned i = 0; i < 4; ++i) {
        const WirePoint *p = &wb.visible_wire[i];
        report("WB VW %u %u %u %u\n", WB_FRAME - 1 + i, p[1].us - p[0].us, p[1].edges - p[0].edges,
               p[1].selected - p[0].selected);
    }
#elif defined(AW_WRITE_LARGE_WINDOWS_ONLY)
    report("WB MIN_PIXELS 5000\n");
#endif
    wb_print_page("PAGE", &wb.pages[1]);
    report("WB LCD %u %08X\n", wb.pages[1].bytes, wb.pages[1].geometry);
    for (unsigned f = TRACE_FIRST; f <= TRACE_LAST; ++f) {
        const uint32_t *b = &wb.boundaries[f - TRACE_FIRST];
        report("WB F %u %u\n", f, b[1] - b[0]);
    }
    for (unsigned f = WB_FIRST; f <= WB_LAST; ++f) {
        const WirePoint *p = &wb.wire[f - WB_FIRST];
        report("WB W %u %u %u %u\n", f, p[1].us - p[0].us, p[1].edges - p[0].edges,
               p[1].selected - p[0].selected);
    }
    for (unsigned i = 0; i < 3; ++i) {
        const unsigned f = WB_FRAME - 1 + i;
        report("WB V %u %u %u\n", f, wb.visible[i] - wb.boundaries[f - TRACE_FIRST],
               i ? wb.visible[i] - wb.visible[i - 1] : 0);
    }
}
