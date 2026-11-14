#ifndef MK61_ANOTHER_PACING_H
#define MK61_ANOTHER_PACING_H

#include <stdint.h>

/* Keep the game's 50 Hz clock across frames. A short overrun is repaid from
 * later idle time, while long I/O stalls cannot trigger an unbounded burst. */
#define AW_FRAME_SLICE_MS 20u
#define AW_FRAME_MAX_LAG_MS 1500u
static inline uint32_t aw_frame_deadline(uint32_t previous, uint32_t now, unsigned slices) {
    const uint32_t deadline = previous + slices * AW_FRAME_SLICE_MS;
    return (int32_t)(now - deadline) > (int32_t)AW_FRAME_MAX_LAG_MS
        ? now - AW_FRAME_MAX_LAG_MS : deadline;
}

#endif
