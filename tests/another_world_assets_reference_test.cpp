/* Optional integration test against the unmodified Raw Bank implementation.
 * Usage: another_world_assets_reference_test /path/to/DOS/data
 * The test does not distribute any game data. */
extern "C" {
#include "../examples/portable-apps/ANOTHER/assets.h"
#include "../examples/portable-apps/ANOTHER/prepared.h"
}
#include "bank.h"
#include "resource.h"
#include <cstdio>
#include <cstdlib>
#include <cstring>

struct Context {
    const char *directory;
    uint8_t *store;
    uint32_t size;
    aw_assets *assets;
    uint32_t stable_offset, progress_calls;
    uint8_t stable[16];
    bool armed;
    FILE *prepared;
};

static bool bank_read(void *opaque, uint8_t bank, uint32_t offset, void *out, uint32_t size) {
    Context *ctx = (Context *)opaque;
    char path[1024];
    if (snprintf(path, sizeof(path), "%s/BANK%02X", ctx->directory, bank) >= (int)sizeof(path)) return false;
    FILE *f = fopen(path, "rb");
    if (!f) return false;
    const bool ok = fseek(f, offset, SEEK_SET) == 0 && fread(out, 1, size, f) == size;
    fclose(f);
    return ok;
}
static bool prepared_read(void *opaque, uint32_t offset, void *out, uint32_t size) {
    Context *ctx = (Context *)opaque;
    return ctx->prepared && fseek(ctx->prepared, offset, SEEK_SET) == 0 &&
           fread(out, 1, size, ctx->prepared) == size;
}
static bool store_read(void *opaque, uint32_t offset, void *out, uint32_t size) {
    Context *ctx = (Context *)opaque;
    if (offset > ctx->size || size > ctx->size - offset) return false;
    memcpy(out, ctx->store + offset, size);
    return true;
}
static bool store_write(void *opaque, uint32_t offset, const void *in, uint32_t size) {
    Context *ctx = (Context *)opaque;
    if (offset > ctx->size || size > ctx->size - offset) return false;
    memcpy(ctx->store + offset, in, size);
    return true;
}
static void progress(void *opaque) {
    Context *ctx = (Context *)opaque;
    if (!ctx->armed) return;
    uint8_t check[16];
    if (!aw_assets_read(ctx->assets, ctx->stable_offset, check, sizeof(check)) ||
        memcmp(check, ctx->stable, sizeof(check))) {
        fprintf(stderr, "cache corruption during cooperative load\n"); abort();
    }
    ++ctx->progress_calls;
}

int main(int argc, char **argv) {
    if (argc != 2) { fprintf(stderr, "usage: %s DATA_DIR\n", argv[0]); return 2; }
    char path[1024];
    snprintf(path, sizeof(path), "%s/MEMLIST.BIN", argv[1]);
    FILE *f = fopen(path, "rb");
    if (!f) { perror(path); return 1; }
    uint8_t list[4096];
    const size_t bytes = fread(list, 1, sizeof(list), f);
    fclose(f);
    Context ctx = {}; ctx.directory = argv[1]; ctx.store = (uint8_t *)calloc(1, 2 * 1024 * 1024); ctx.size = 2 * 1024 * 1024;
    aw_assets *assets = (aw_assets *)calloc(1, sizeof(aw_assets));
    uint8_t *expected = (uint8_t *)malloc(65536);
    uint8_t *actual = (uint8_t *)malloc(65536);
    if (!ctx.store || !assets || !expected || !actual ||
        !aw_assets_init(assets, list, bytes, ctx.size, &ctx, bank_read, store_read, store_write)) {
        fprintf(stderr, "cannot initialize assets\n"); return 1;
    }
    ctx.assets = assets; assets->progress = progress; assets->progress_ctx = &ctx;
    unsigned checked = 0;
    for (unsigned id = 0; id < assets->count; ++id) {
        aw_asset_entry *e = &assets->entries[id];
        if (!e->bank || !e->size || !e->packed_size) continue;
        MemEntry reference = {};
        reference.bankId = e->bank; reference.bankOffset = e->bank_offset;
        reference.packedSize = e->packed_size; reference.size = e->size;
        memset(expected, 0, 65536);
        Bank original(argv[1]);
        if (!original.read(&reference, expected) || !aw_assets_load(assets, id) ||
            !aw_assets_read(assets, e->store_offset, actual, e->size) ||
            memcmp(expected, actual, e->size)) {
            fprintf(stderr, "resource %u does not match Raw: bank=%u packed=%u size=%u\n",
                    id, e->bank, e->packed_size, e->size);
            return 1;
        }
        if (!ctx.armed && e->size >= sizeof(ctx.stable)) {
            ctx.stable_offset = e->store_offset;
            memcpy(ctx.stable, expected, sizeof(ctx.stable)); ctx.armed = true;
        }
        ++checked;
    }
    printf("matched %u resources; %u bytes in PSRAM; %u cooperative cache checks\n", checked, assets->used, ctx.progress_calls);
    snprintf(path, sizeof(path), "%s/AWCACHE.BIN", argv[1]);
    ctx.prepared = fopen(path, "rb");
    if (ctx.prepared) {
        if (fseek(ctx.prepared, 0, SEEK_END)) return 1;
        const long cache_size = ftell(ctx.prepared);
        uint8_t table[AW_ASSET_LIMIT * 12]; aw_prepared_cache prepared = {};
        ctx.armed = false;
        if (cache_size < 0 || !aw_assets_init(assets, list, bytes, ctx.size, &ctx, bank_read, store_read, store_write) ||
            !aw_prepared_open(&prepared, list, bytes, assets->count, (uint32_t)cache_size,
                              table, sizeof(table), &ctx, prepared_read)) return 1;
        assets->progress = progress; assets->progress_ctx = &ctx;
        unsigned sounds = 0;
        for (unsigned id = 0; id < assets->count; ++id) {
            aw_asset_entry *e = &assets->entries[id];
            if (e->type || !e->bank || !e->size || !e->packed_size) continue;
            MemEntry reference = {}; reference.bankId = e->bank; reference.bankOffset = e->bank_offset;
            reference.packedSize = e->packed_size; reference.size = e->size; Bank original(argv[1]);
            if (!original.read(&reference, expected) || !aw_prepared_load(&prepared, assets, id) ||
                !aw_assets_read(assets, e->store_offset, actual, e->size) || memcmp(expected, actual, e->size)) {
                fprintf(stderr, "prepared sound %u does not match Raw\n", id); return 1;
            }
            if (!ctx.armed && e->size >= sizeof(ctx.stable)) {
                ctx.stable_offset = e->store_offset; memcpy(ctx.stable, expected, sizeof(ctx.stable)); ctx.armed = true;
            }
            ++sounds;
        }
        printf("matched %u prepared sounds against Raw\n", sounds);
        fclose(ctx.prepared);
    }
    ctx.armed = false;
    if (!aw_assets_init(assets, list, bytes, ctx.size, &ctx, bank_read, store_read, store_write)) return 1;
    unsigned steps = 0;
    while (assets->prefetch.active || assets->prefetch_next < assets->count) {
        if (++steps > 2000000 || !aw_assets_prefetch_step(assets)) return 1;
        if (!(steps % 37)) {
            const uint8_t marker = (uint8_t)steps; uint8_t observed = 0;
            if (!aw_assets_write(assets, assets->used, &marker, 1) ||
                !aw_assets_read(assets, assets->used, &observed, 1) || marker != observed) return 1;
        }
    }
    unsigned prefetched = 0;
    for (unsigned id = 0; id < assets->count; ++id) {
        aw_asset_entry *e = &assets->entries[id];
        if (!e->bank || !e->size || !e->packed_size) continue;
        MemEntry reference = {}; reference.bankId = e->bank; reference.bankOffset = e->bank_offset;
        reference.packedSize = e->packed_size; reference.size = e->size; Bank original(argv[1]);
        if (!e->decoded || !original.read(&reference, expected) ||
            !aw_assets_read(assets, e->store_offset, actual, e->size) || memcmp(expected, actual, e->size)) {
            fprintf(stderr, "prefetched resource %u does not match Raw\n", id); return 1;
        }
        ++prefetched;
    }
    printf("matched %u incrementally prefetched resources against Raw\n", prefetched);
    free(actual); free(expected); free(assets); free(ctx.store);
    return checked && ctx.progress_calls ? 0 : 1;
}
