/* Instrument the real game page and the two outside LCD flips. */
static struct {
    uint32_t base, early_bytes, copy_bytes, early_us, copy_us, copy_start;
    uint32_t first_show, last_show, copies, before_count, after_count, calls;
    int32_t slack_before_ms, slack_after_ms;
    unsigned batches;
    bool in_interval, saving, copying;
} edge;

void edge_unexpected_text(unsigned id) {
    report("EDGE unexpected text %u at %u\n", id, intro);
    pump_failed = true;
}

bool edge_prewrite(void) {
    if (intro != 2438 || !edge.in_interval || !video->resident_valid ||
        !video->spare_valid || !video->bands || video->resident_page != 2) return false;
    ++edge.calls;
    edge.base = video->page_base + AW_VIDEO_PAGE_BYTES * video->store_slot[2];
    edge.slack_before_ms = (int32_t)(last_frame - mk61_api->millis_ms());
    const uint32_t start = trace_time();
    edge.saving = true;
    const bool ok = aw_video_write_displayed(video, edge.batches);
    edge.saving = false;
    edge.early_us += trace_time() - start;
    edge.slack_after_ms = (int32_t)(last_frame - mk61_api->millis_ms());
    return ok;
}

void edge_copy_begin(void) {
    if (!edge.in_interval || !edge.calls) return;
    ++edge.copies;
    edge.copying = true;
    edge.copy_start = trace_time();
}

void edge_copy_end(void) {
    if (!edge.copying) return;
    edge.copy_us += trace_time() - edge.copy_start;
    edge.copying = false;
}

static void edge_store(uint32_t offset, unsigned bytes) {
    if ((!edge.saving && !edge.copying) || offset < edge.base || offset - edge.base >= AW_VIDEO_PAGE_BYTES) return;
    if (edge.saving) edge.early_bytes += bytes;
    else edge.copy_bytes += bytes;
}

static void edge_show(unsigned frame) {
    if (frame == 2437) { edge.first_show = trace_time(); ++edge.before_count; }
    if (frame == 2443) { edge.last_show = trace_time(); ++edge.after_count; }
}

#ifdef AW_EDGE_LEAD
static struct {
    uint32_t time[3][3];
    unsigned lead[3], bias;
#ifdef AW_EDGE_ROWS
    unsigned row_cut;
#endif
    int32_t slack[3];
} color_clock;

unsigned edge_lead_bias(void) { return color_clock.bias; }
void edge_mark_color(unsigned index, unsigned phase, unsigned lead) {
    if (index >= 3 || phase >= 3) return;
    color_clock.time[index][phase] = trace_time();
    if (phase == 0) {
        color_clock.lead[index] = lead;
        color_clock.slack[index] = (int32_t)(last_frame - mk61_api->millis_ms());
    }
}

#endif

static void edge_print(void) {
#ifdef AW_EDGE_LEAD
#ifdef AW_EDGE_ROWS
    report("EDGE CUT %u\n", color_clock.row_cut);
#endif
    report("EDGE BIAS %u\n", color_clock.bias);
    for (unsigned i = 0; i < 3; ++i) {
        const uint32_t *t = color_clock.time[i];
        report("EDGE W %u %u %d %u %u\n", 2439u + i, color_clock.lead[i], (int)color_clock.slack[i],
               t[1] - t[0], t[2] - t[1]);
    }
#endif
    report("EDGE BYTES %u %u %u %u %u\n", edge.batches, edge.calls, edge.copies, edge.early_bytes, edge.copy_bytes);
    report("EDGE TIME %d %d %u %u\n", (int)edge.slack_before_ms, (int)edge.slack_after_ms, edge.early_us, edge.copy_us);
    report("EDGE OUTER %u %u %u %u\n", edge.before_count, edge.after_count,
           wb.visible_wire[0].us - edge.first_show, edge.last_show - wb.visible_wire[4].us);
}
