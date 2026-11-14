/* Hardware helper: create the same optional sound cache as the host tools
 * from game files already on the card. The destination must not exist. */
#include "mk61_app.h"
#include "../examples/portable-apps/ANOTHER/assets.h"
#include <string.h>

#define STORE_BYTES (2u * 1024u * 1024u)
static const mk61_app_services *services;
static mk61_service_buffer external;
static aw_assets assets;
static uint8_t list[4096], metadata[24 + AW_ASSET_LIMIT * 12], block[2048];
static uint32_t meta_size, output_size;

static void put32(uint8_t *p, uint32_t n) {
    p[0] = (uint8_t)n; p[1] = (uint8_t)(n >> 8); p[2] = (uint8_t)(n >> 16); p[3] = (uint8_t)(n >> 24);
}
static uint32_t get32(const uint8_t *p) {
    return (uint32_t)p[0] | ((uint32_t)p[1] << 8) | ((uint32_t)p[2] << 16) | ((uint32_t)p[3] << 24);
}
static uint32_t hash(uint32_t h, const uint8_t *p, uint32_t n) {
    while (n--) h = (h ^ *p++) * 16777619u;
    return h;
}
static bool file_read(const char *name, uint32_t at, void *out, uint32_t n) {
    mk61_service_file_bytes r = {name, out, at, n};
    return services->call(MK61_SERVICE_FILE_BYTES, MK61_FILE_BYTES_READ, 0, sizeof(r), &r) != 0;
}
static bool bank_read(void *ctx, uint8_t bank, uint32_t at, void *out, uint32_t n) {
    (void)ctx; static const char hex[] = "0123456789ABCDEF";
    char name[] = "BANK00"; name[4] = hex[bank >> 4]; name[5] = hex[bank & 15];
    const bool ok = file_read(name, at, out, n); mk61_api->service(); return ok;
}
static bool transfer(uint32_t operation, uint32_t at, void *data, uint32_t n) {
    mk61_service_buffer r = mk61_app_buffer_request();
    r.handle = external.handle; r.offset = at; r.data = data; r.size = n;
    return services->call(MK61_SERVICE_BUFFER, operation, 0, sizeof(r), &r) != 0;
}
static bool store_read(void *ctx, uint32_t at, void *data, uint32_t n) {
    (void)ctx; return transfer(MK61_BUFFER_READ, at, data, n);
}
static bool store_write(void *ctx, uint32_t at, const void *data, uint32_t n) {
    (void)ctx; return transfer(MK61_BUFFER_WRITE, at, (void *)data, n);
}
static void progress(void *ctx) { (void)ctx; mk61_api->service(); }

static int source(void *ctx, uint32_t at, uint8_t *out, uint32_t n) {
    (void)ctx;
    if (at > output_size || n > output_size - at) return 0;
    while (n) {
        if (at < meta_size) {
            uint32_t take = meta_size - at; if (take > n) take = n;
            memcpy(out, metadata + at, take); at += take; out += take; n -= take;
            continue;
        }
        bool found = false;
        for (unsigned id = 0; id < assets.count; ++id) {
            const aw_asset_entry *e = &assets.entries[id];
            const uint32_t begin = get32(metadata + 24 + id * 12);
            if (!begin || at < begin || at - begin >= e->size) continue;
            uint32_t take = e->size - (at - begin); if (take > n) take = n;
            if (!aw_assets_read(&assets, e->store_offset + at - begin, out, take)) return 0;
            at += take; out += take; n -= take; found = true; break;
        }
        if (!found) return 0;
    }
    return 1;
}

int main(void) {
    int result = 1; unsigned sounds = 0;
    services = mk61_app_get_services(mk61_api, MK61_SERVICE_CAP_BUFFERS | MK61_SERVICE_CAP_EXTERNAL_BUFFERS |
                                    MK61_SERVICE_CAP_FILE_BYTES | MK61_SERVICE_CAP_FILE_WRITE_SOURCE);
    if (!services || !mk61_app_buffer_acquire(services, STORE_BYTES, MK61_BUFFER_EXTERNAL, &external)) return 1;
    mk61_service_file_info info;
    mk61_service_file_bytes stat = {"MEMLIST.BIN", &info, 0, sizeof(info)};
    if (!services->call(MK61_SERVICE_FILE_BYTES, MK61_FILE_BYTES_STAT, 0, sizeof(stat), &stat) ||
        info.directory || !info.size || info.size > sizeof(list) || !file_read("MEMLIST.BIN", 0, list, info.size) ||
        !aw_assets_init(&assets, list, info.size, STORE_BYTES, NULL, bank_read, store_read, store_write)) goto done;
    assets.progress = progress;
    meta_size = 24 + assets.count * 12; output_size = meta_size;
    memcpy(metadata, "AWC1", 4); put32(metadata + 4, 1); put32(metadata + 8, assets.count);
    put32(metadata + 12, info.size); put32(metadata + 16, hash(2166136261u, list, info.size));
    put32(metadata + 20, assets.count * 12);
    for (unsigned id = 0; id < assets.count; ++id) {
        const aw_asset_entry *e = &assets.entries[id];
        if (e->type || !e->bank || !e->size || !e->packed_size) continue;
        if (!aw_assets_load(&assets, id)) goto done;
        uint32_t source_hash = 2166136261u, raw_hash = 2166136261u;
        for (uint32_t at = 0; at < e->packed_size;) {
            uint32_t n = e->packed_size - at; if (n > sizeof(block)) n = sizeof(block);
            if (!bank_read(NULL, e->bank, e->bank_offset + at, block, n)) goto done;
            source_hash = hash(source_hash, block, n); at += n;
        }
        for (uint32_t at = 0; at < e->size;) {
            uint32_t n = e->size - at; if (n > sizeof(block)) n = sizeof(block);
            if (!aw_assets_read(&assets, e->store_offset + at, block, n)) goto done;
            raw_hash = hash(raw_hash, block, n); at += n; mk61_api->service();
        }
        uint8_t *record = metadata + 24 + id * 12;
        put32(record, output_size); put32(record + 4, source_hash); put32(record + 8, raw_hash);
        output_size += e->size; ++sounds;
    }
    if (!sounds) goto done;
    mk61_service_write_source request = {"AWCACHE.BIN", NULL, source, output_size, 0};
    if (!services->call(MK61_SERVICE_FILE_BYTES, MK61_FILE_BYTES_WRITE_SOURCE, 0, sizeof(request), &request)) goto done;
    result = 0;
done:
    if (external.handle) mk61_app_buffer_release(services, external.handle);
    return result;
}
