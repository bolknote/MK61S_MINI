#define main another_unused_app_main
#include "../examples/portable-apps/ANOTHER/main.c"
#undef main
#include <assert.h>
#include <stdio.h>

const mk61_app_api *mk61_api;
uint32_t mk61_app_image_crc, mk61_app_current_kind;
static unsigned calls;
static uint32_t clock_ms;
static uint16_t gram[2][AW_VIDEO_WIDTH * AW_VIDEO_HEIGHT];
static bool paging, scroll_open, scroll_valid;
static unsigned selected, visible, write_offset, visible_offset;
static uint8_t store[2 * AW_VIDEO_PAGE_BYTES], borrowed[12800];

static uint32_t now(void) { return ++clock_ms; }
static void service(void) { ++clock_ms; }
static bool read_store(void *ctx, uint32_t at, void *out, uint32_t size) {
    (void)ctx; assert(at <= sizeof(store) && size <= sizeof(store) - at);
    memcpy(out, store + at, size); return true;
}
static bool write_store(void *ctx, uint32_t at, const void *in, uint32_t size) {
    (void)ctx; assert(at <= sizeof(store) && size <= sizeof(store) - at);
    memcpy(store + at, in, size); return true;
}
static uint32_t color_service(uint32_t op, uint32_t a, uint32_t b, uint32_t bytes, void *payload) {
    (void)b; (void)bytes;
    if (op == MK61_SERVICE_KEYBOARD) { memset(payload, 0, 32); return 1; }
    assert(op == MK61_SERVICE_COLOR_DISPLAY);
    switch (a) {
    case MK61_COLOR_PAGES_BEGIN_V2:
        assert(!paging && !scroll_valid && !scroll_open); paging = true; return 1;
    case MK61_COLOR_PAGES_END:
        assert(paging); paging = false; scroll_valid = false; return 1;
    case MK61_COLOR_PAGE_SELECT: selected = *(uint32_t *)payload; assert(selected < 2); return 1;
    case MK61_COLOR_PAGE_SHOW: visible = *(uint32_t *)payload; assert(visible < 2); return 1;
    case MK61_COLOR_SCROLL_BEGIN: {
        const mk61_service_color_scroll *r = payload;
        assert(!paging && !scroll_open && r->top == 60 && r->height == AW_VIDEO_HEIGHT);
        const bool reuse = scroll_valid && r->previous == visible_offset;
        write_offset = r->offset; scroll_open = true; return reuse ? 1 : 3;
    }
    case MK61_COLOR_SCROLL_END:
        assert(scroll_open); visible_offset = write_offset; scroll_open = false; scroll_valid = true; return 1;
    case MK61_COLOR_END: scroll_open = scroll_valid = false; visible_offset = write_offset = 0; return 1;
    case MK61_COLOR_SPI_HZ: return 24000000;
    case MK61_COLOR_PRESENT: {
        const mk61_service_color_frame *f = payload;
        assert(paging || scroll_open);
        assert(f->y >= 60 && f->y + f->height <= 260 && f->x + f->width <= AW_VIDEO_WIDTH);
        for (unsigned y = 0; y < f->height; ++y) for (unsigned x = 0; x < f->width; ++x) {
            const unsigned row = (f->y - 60 + y + (paging ? 0 : write_offset)) % AW_VIDEO_HEIGHT;
            const uint8_t pair = f->pixels[y * (f->width / 2) + x / 2];
            gram[paging ? selected : 0][row * AW_VIDEO_WIDTH + f->x + x] = f->palette[(pair >> (x & 1 ? 0 : 4)) & 15];
        }
        return 1;
    }
    default: assert(false); return 0;
    }
}

static uint32_t unavailable(uint32_t operation, uint32_t a, uint32_t b, uint32_t bytes, void *payload) {
    (void)b; (void)bytes; (void)payload;
    assert(operation == MK61_SERVICE_COLOR_DISPLAY);
    assert(a == (calls++ ? MK61_COLOR_END : MK61_COLOR_SCROLL_BEGIN));
    return 0;
}

static void leave_intro(unsigned shown, bool retained) {
    const mk61_app_services mock = {.call = unavailable};
    aw_vm machine = {.part = AW_STORM_PART + 1};
    aw_video frame = {.front_page = 2};
    aw_display_storm cache = {.at = shown, .ready = true};
    uint8_t pixels[AW_VIDEO_PAGE_BYTES] = {0};
    uint16_t palette[16] = {0};
    services = &mock; vm = &machine; video = &frame; storm = &cache;
    scroll_ready = true; compact_ready = pages_ready = false; calls = 0;
    /* The scroll path returns before the ordinary two-page branch. Its
     * first failure still has to invalidate a previously shown intro cache. */
    assert(!present(NULL, pixels, palette));
    assert(calls == 2 && cache.ready == retained);
}

static void game_intro_game(void) {
    const mk61_app_api api = {.millis_ms = now, .service = service};
    const mk61_app_services mock = {.call = color_service};
    aw_assets memory = {.capacity = sizeof(store), .store_read = read_store, .store_write = write_store};
    aw_display_pages pages;
    aw_vm machine = {0};
    aw_video frame = {.front_page = 2};
    aw_display_storm cache = {.at = 2400, .ready = true};
    uint8_t pixels[AW_VIDEO_PAGE_BYTES];
    uint16_t palette[16];
    for (unsigned i = 0; i < 16; ++i) palette[i] = (uint16_t)(i * 0x1111);
    mk61_api = &api; services = &mock; vm = &machine; video = &frame; storm = &cache;
    pages_display = &pages;
    assert(aw_display_compact_init(&compact_display, &memory, 0, borrowed, sizeof(borrowed), borrowed, sizeof(borrowed)));
    assert(aw_display_pages_init(&pages, &compact_display, AW_VIDEO_PAGE_BYTES));
    pages_available = pages_ready = compact_ready = paging = true;
    scroll_ready = scroll_disabled = pump_failed = audio_open = scroll_open = scroll_valid = false;
    input = (aw_input){0}; last_frame = next_keys = clock_ms = 0;
    const uint16_t parts[] = {AW_STORM_PART + 1, AW_STORM_PART, AW_STORM_PART + 1};
    for (unsigned step = 0; step < 3; ++step) {
        machine.part = parts[step];
        for (unsigned i = 0; i < AW_VIDEO_PAGE_BYTES; ++i) pixels[i] = (uint8_t)((i / AW_VIDEO_STRIDE + step) * 17u);
        frame.page_scroll[frame.front_page] = (uint8_t)(step * 2);
        assert(present(NULL, pixels, palette));
        assert(!cache.ready && paging == (step == 1) && scroll_ready == (step != 1));
        for (unsigned i = 0; i < AW_VIDEO_WIDTH * AW_VIDEO_HEIGHT; ++i) {
            const unsigned y = i / AW_VIDEO_WIDTH;
            const unsigned at = paging ? i : ((y + visible_offset) % AW_VIDEO_HEIGHT) * AW_VIDEO_WIDTH + i % AW_VIDEO_WIDTH;
            const unsigned index = (pixels[i / 2] >> (i & 1 ? 0 : 4)) & 15;
            assert(gram[paging ? visible : 0][at] == palette[index]);
        }
    }
    assert(end_scroll());
}

int main(void) {
    leave_intro(2400, false);
    leave_intro(0, true);
    game_intro_game();
    puts("Another World interrupted-intro cache invalidation passed");
    return 0;
}
