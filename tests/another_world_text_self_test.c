/* The complete DOS text table, including duplicate IDs, must stay unchanged. */
#include "../examples/portable-apps/ANOTHER/text.h"
#include <assert.h>
#include <stdio.h>

static uint32_t fnv_byte(uint32_t hash, uint8_t value) {
    return (hash ^ value) * 16777619u;
}

int main(void) {
    uint32_t hash = 2166136261u;
    unsigned count = 0;
    for (unsigned id = 0; id <= UINT16_MAX; ++id) {
        const char *text = aw_text((uint16_t)id);
        if (!text) continue;
        hash = fnv_byte(hash, (uint8_t)id);
        hash = fnv_byte(hash, (uint8_t)(id >> 8));
        while (*text) hash = fnv_byte(hash, (uint8_t)*text++);
        hash = fnv_byte(hash, 0);
        ++count;
    }
    /* Computed from the original pointer-based table; the first duplicate
     * ID is intentionally retained, just as in the original lookup. */
    assert(count == 139 && hash == 0xA72EBEFDu);
    puts("Another World: all game texts and unknown IDs match the original table");
    return 0;
}
