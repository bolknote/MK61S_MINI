/* Host replay only. Exercise bounded writes of the displayed VM page while
 * its seven LCD windows are being submitted. Host time is synthetic. */
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>

static uint8_t displayed_pixels[AW_VIDEO_PAGE_BYTES];
static unsigned displayed_page, windows_seen, bytes_early, writes_early, bytes_at_copy;
static bool inside_copy;

static unsigned stale_bands(const aw_video *v, unsigned page) {
    unsigned count = 0;
    for (unsigned i = 0; i < AW_VIDEO_BANDS; ++i)
        count += v->bands->page[page][i] != v->bands->stored[page][i];
    return count;
}

void copy_replay_window(aw_video *v) {
    assert(v->bands && v->resident_valid && v->spare_valid);
    if (!windows_seen) {
        displayed_page = v->resident_page;
        memcpy(displayed_pixels, v->pixels, sizeof(displayed_pixels));
    }
    ++windows_seen;
    assert(displayed_page == v->resident_page);
    assert(!memcmp(displayed_pixels, v->pixels, sizeof(displayed_pixels)));
    if (!getenv("AW_TEST_EARLY_PAGE_WRITE"))
        return;
    // Two service opportunities per visible window in this functional replay.
    for (unsigned i = 0; i < 2; ++i) {
        unsigned before = stale_bands(v, displayed_page);
        assert(store_page(v, displayed_page, v->pixels, &v->dirty, true));
        unsigned bands = before - stale_bands(v, displayed_page);
        assert(bands <= 2);
        bytes_early += bands * BAND_BYTES;
        writes_early += bands != 0;
    }
}

static void copy_replay_transfer(aw_video *v, bool write, uint32_t offset, const uint8_t *data, uint32_t bytes) {
    if (!inside_copy)
        return;
    uint32_t base = page_at(v, displayed_page);
    assert(write && offset >= base && offset - base <= AW_VIDEO_PAGE_BYTES);
    assert(bytes <= AW_VIDEO_PAGE_BYTES - (offset - base));
    assert(!memcmp(displayed_pixels + (offset - base), data, bytes));
    bytes_at_copy += bytes;
}

static void copy_replay_begin(const aw_video *v, uint8_t src, uint8_t dst, int16_t scroll) {
    assert(windows_seen == 7 && displayed_page == 2 && src == 0x40 && dst == 0xff && scroll == 0 && v->back_page == 1 &&
           v->spare_page == 0);
    inside_copy = true;
}

static void copy_replay_end(void) {
    inside_copy = false;
    unsigned expected_early = getenv("AW_TEST_EARLY_PAGE_WRITE") ? AW_VIDEO_PAGE_BYTES : 0;
    assert(bytes_early == expected_early && bytes_at_copy == AW_VIDEO_PAGE_BYTES - expected_early);
    printf("VM_COPY src=0 dst=1 evicted=%u visible_windows=%u "
           "early_writes=%u early_bytes=%u synchronous_bytes=%u\n",
           displayed_page, windows_seen, writes_early, bytes_early, bytes_at_copy);
}
