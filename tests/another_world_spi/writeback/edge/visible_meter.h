#pragma once
#include "wire.h"

static struct {
    WirePoint visible_wire[5];
    unsigned mode, latches, black_latches, color_count[3];
    unsigned interval, early[2], sequence_start, sequence_end;
    bool writing;
} wb;

static void wb_boundary(unsigned frame) {
    wb.interval = frame;
    if (frame == TRACE_FIRST) wb.sequence_start = trace_time();
    if (frame == TRACE_LAST + 1) wb.sequence_end = trace_time();
}
void wb_visible_done(unsigned index) {
    if (index < 3 && intro == 2439 + index) {
        ++wb.color_count[index];
        wire_point(&wb.visible_wire[index + 1]);
    }
}
void wb_copy_begin(void) {}
void wb_copy_end(void) {}
static void wb_store(uint32_t offset, unsigned size) {
    (void)offset;
    if (wb.writing) wb.early[wb.interval - 2439] += size;
}
static bool wb_accept(unsigned x, unsigned y, unsigned width, unsigned height) {
    (void)x; (void)y; (void)width; (void)height;
    if (!storm->tail.writeback_batches) return true;
    if (wb.interval < 2439 || wb.interval > 2440) return false;
    wb.writing = true;
    const bool ok = aw_video_write_displayed(video, storm->tail.writeback_batches);
    wb.writing = false;
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

static void wb_print(void) {
    report("EDGE MID %u %u %u %u %u %u %u\n", wb.latches, wb.color_count[0], wb.color_count[1],
           wb.color_count[2], wb.black_latches, wb.early[0], wb.early[1]);
    for (unsigned i = 0; i < 4; ++i) {
        const WirePoint *s = &wb.visible_wire[i];
        report("WB VW %u %u %u %u\n", 2439 + i, s[1].us - s[0].us, s[1].edges - s[0].edges,
               s[1].selected - s[0].selected);
    }
    report("EDGE SEQUENCE %u\n", wb.sequence_end - wb.sequence_start);
}
