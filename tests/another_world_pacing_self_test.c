#include "../examples/portable-apps/ANOTHER/pacing.h"
#include <assert.h>
#include <stdio.h>

int main(void) {
    assert(aw_frame_deadline(1000, 1015, 2) == 1040);
    assert(aw_frame_deadline(1000, 1047, 2) == 1040);
    assert(aw_frame_deadline(1040, 1070, 2) == 1080);
    assert(aw_frame_deadline(0, 1000, 2) == 40);
    assert(aw_frame_deadline(0, 3000, 2) == 1500);
    assert(aw_frame_deadline(UINT32_MAX - 19u, UINT32_MAX - 9u, 2) == 20u);

    /* Alternating expensive and cheap frames must finish at game-clock time:
     * the old policy permanently added every individual overrun. */
    uint32_t now = 0, deadline = 0;
    for (unsigned i = 0; i < 200; ++i) {
        now += i % 2 ? 20 : 110;
        deadline = aw_frame_deadline(deadline, now, 5);
        if ((int32_t)(deadline - now) > 0) now = deadline;
    }
    assert(now == 20000);
    now = deadline = 0;
    for (unsigned i = 0; i < 200; ++i) {
        now += i == 50 ? 410 : 10;
        deadline = aw_frame_deadline(deadline, now, 5);
        if ((int32_t)(deadline - now) > 0) now = deadline;
    }
    assert(now == 20000);
    puts("Another World frame pacing tests passed"); return 0;
}
