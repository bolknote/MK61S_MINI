#ifndef AW_ROW_RLE_H
#define AW_ROW_RLE_H

#include "video.h"
#include <string.h>

static inline bool aw_row_run(const uint8_t *row, unsigned x) {
    return x + 2 < AW_VIDEO_STRIDE && row[x] == row[x + 1] && row[x] == row[x + 2];
}

/* Independent PackBits-style rows for both the display and background caches. */
static unsigned aw_pack_row(const uint8_t *row, uint8_t *out, unsigned capacity) {
    unsigned used = 0;
    for (unsigned x = 0; x < AW_VIDEO_STRIDE;) {
        const unsigned start = x;
        const unsigned end = x + 128 < AW_VIDEO_STRIDE ? x + 128 : AW_VIDEO_STRIDE;
        if (aw_row_run(row, x)) {
            const uint8_t value = row[x];
            x += 3;
            while (x < end && ((uintptr_t)(row + x) & 3u) && row[x] == value) ++x;
            if (!((uintptr_t)(row + x) & 3u)) {
                const uint32_t repeat = value * 0x01010101u;
                while (x + 4 <= end) {
                    uint32_t word;
                    __builtin_memcpy(&word, __builtin_assume_aligned(row + x, 4), sizeof(word));
                    if (word != repeat) break;
                    x += 4;
                }
            }
            while (x < end && row[x] == value) ++x;
            if (capacity - used < 2) return 0;
            out[used++] = (uint8_t)(0x80u | (x - start - 1));
            out[used++] = value;
        } else {
            ++x;
            while (x < end && !aw_row_run(row, x)) ++x;
            const unsigned count = x - start;
            if (capacity - used < 1 + count) return 0;
            out[used++] = (uint8_t)(count - 1);
            memcpy(out + used, row + start, count);
            used += count;
        }
    }
    return used;
}
#endif
