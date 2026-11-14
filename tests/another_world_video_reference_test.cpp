/* Optional pixel comparison against the unmodified Raw Video implementation. */
extern "C" {
#include "../examples/portable-apps/ANOTHER/video.h"
}
#include "video.h"
#include <cstdio>
#include <cstdlib>
#include <cstring>

static uint8_t storage[8192 + 4 * AW_VIDEO_PAGE_BYTES];
static uint8_t framebuffer[AW_VIDEO_PAGE_BYTES];
static bool bank(void *, uint8_t, uint32_t, void *, uint32_t) { return false; }
static bool rd(void *, uint32_t offset, void *out, uint32_t size) {
    if (offset > sizeof(storage) || size > sizeof(storage) - offset) return false;
    memcpy(out, storage + offset, size); return true;
}
static bool wr(void *, uint32_t offset, const void *in, uint32_t size) {
    if (offset > sizeof(storage) || size > sizeof(storage) - offset) return false;
    memcpy(storage + offset, in, size); return true;
}
static bool present(void *, const uint8_t *, const uint16_t *) { return true; }

int main() {
    uint8_t list[21] = {}; list[7] = 1; list[14] = 0x20; list[18] = 0x20; list[20] = 0xFF;
    aw_assets a; aw_video v;
    if (!aw_assets_init(&a, list, sizeof(list), sizeof(storage), nullptr, bank, rd, wr) ||
        !aw_video_init(&v, &a, 8192, framebuffer, present, nullptr)) return 1;
    Video reference(nullptr, nullptr); reference.init();
    reference.fillPage(0, 3); reference.fillPage(2, 1); reference.changePagePtr1(2);
    if (!aw_video_fill(&v, 0, 3) || !aw_video_fill(&v, 2, 1) || !aw_video_select(&v, 2)) return 1;
    for (int n = 0; n < 480; ++n) {
        const uint8_t width = (uint8_t)(4 + n % 96), height = (uint8_t)(2 + n % 75);
        const uint8_t color = (uint8_t)(n % 18);
        uint8_t shape[] = {(uint8_t)(0xC0 | color), width, height, 4,
                           width, 0, width, height, 0, height, 0, 0};
        const int x = (n * 37 % 370) - 25, y = (n * 23 % 240) - 20;
        reference.setDataBuffer(shape, 0); reference.readAndDrawPolygon(0xFF, 64, Point(x, y));
        if (!aw_assets_write(&a, 0, shape, sizeof(shape)) ||
            !aw_video_polygon(&v, 0, sizeof(shape), 0, 64, (int16_t)x, (int16_t)y) ||
            memcmp(reference._curPagePtr1, framebuffer, AW_VIDEO_PAGE_BYTES)) {
            fprintf(stderr, "polygon %d differs (color %u, x %d, y %d)\n", n, color, x, y);
            return 1;
        }
    }
    free(reference._pages[0]);
    puts("480 polygons match Raw");
    return 0;
}
