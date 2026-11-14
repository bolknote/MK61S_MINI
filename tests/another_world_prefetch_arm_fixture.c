#include "../examples/portable-apps/ANOTHER/assets.h"
#include <stddef.h>
#include <stdint.h>

uint8_t fixture_bank[65536], fixture_store[65536], fixture_list[21];
aw_assets fixture_assets;
void *memcpy(void *d, const void *s, size_t n) {
    uint8_t *dst = d; const uint8_t *src = s; for (size_t i = 0; i < n; ++i) dst[i] = src[i]; return d;
}
void *memset(void *d, int c, size_t n) {
    uint8_t *dst = d; for (size_t i = 0; i < n; ++i) dst[i] = (uint8_t)c; return d;
}
static bool bank(void *ctx, uint8_t id, uint32_t at, void *out, uint32_t n) {
    (void)ctx; if (id != 1 || at > 65536 || n > 65536 - at) return false;
    memcpy(out, fixture_bank + at, n); return true;
}
static bool rd(void *ctx, uint32_t at, void *out, uint32_t n) {
    (void)ctx; if (at > 65536 || n > 65536 - at) return false;
    memcpy(out, fixture_store + at, n); return true;
}
static bool wr(void *ctx, uint32_t at, const void *in, uint32_t n) {
    (void)ctx; if (at > 65536 || n > 65536 - at) return false;
    memcpy(fixture_store + at, in, n); return true;
}
int fixture_run(uint32_t demand_midway) {
    if (!aw_assets_init(&fixture_assets, fixture_list, sizeof(fixture_list), 65536, 0, bank, rd, wr)) return 2;
    for (unsigned step = 0; step < 1000000 && !fixture_assets.entries[0].decoded; ++step) {
        if (demand_midway && fixture_assets.prefetch.active &&
            fixture_assets.prefetch.output < fixture_assets.entries[0].size / 2)
            return aw_assets_load(&fixture_assets, 0) ? 0 : 3;
        if (!aw_assets_prefetch_step(&fixture_assets)) return 4;
        if (!(step % 37)) {
            uint8_t value = (uint8_t)step, got = 0;
            if (!aw_assets_write(&fixture_assets, 65535, &value, 1) ||
                !aw_assets_read(&fixture_assets, 65535, &got, 1) || got != value) return 5;
        }
    }
    return fixture_assets.entries[0].decoded ? 0 : 6;
}
