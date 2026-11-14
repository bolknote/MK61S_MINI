#ifndef MK61_ANOTHER_ASSETS_H
#define MK61_ANOTHER_ASSETS_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

/* DOS MEMLIST.BIN entries and ByteKiller-compressed BANK resources.
 * The backing store may be non-addressable PSRAM; its callbacks are called
 * only from the foreground. All offsets are relative to that store. */
#define AW_ASSET_LIMIT 150u
#define AW_ASSET_PAGE 1024u
#ifndef AW_ASSET_CACHE_SLOTS
#define AW_ASSET_CACHE_SLOTS 5u
#endif
#define AW_ASSET_MAX_TRANSFER 4096u
#define AW_PREFETCH_INPUT_BYTES 256u

typedef bool (*aw_asset_bank_read)(void *ctx, uint8_t bank, uint32_t offset,
                                   void *data, uint32_t size);
typedef bool (*aw_asset_store_read)(void *ctx, uint32_t offset,
                                    void *data, uint32_t size);
typedef bool (*aw_asset_store_write)(void *ctx, uint32_t offset,
                                     const void *data, uint32_t size);

typedef struct {
    uint32_t bank_offset, store_offset;
    uint16_t packed_size, size;
    uint8_t type, rank, bank, decoded;
} aw_asset_entry;

typedef struct {
    uint32_t page, age;
    bool valid, dirty;
    uint8_t data[AW_ASSET_PAGE];
} aw_asset_cache;

typedef struct aw_assets aw_assets;
typedef struct {
    aw_assets *assets;
    aw_asset_entry *entry;
    uint8_t *input;
    uint32_t input_base, input_size, input_capacity, cursor, output, bits, crc;
    bool input_valid, failed, active, compressed;
} aw_asset_prefetch;

struct aw_assets {
    void *ctx;
    aw_asset_bank_read bank_read;
    aw_asset_store_read store_read;
    aw_asset_store_write store_write;
    void (*progress)(void *ctx);
    void *progress_ctx;
    uint32_t capacity, used, clock;
    uint16_t count;
    bool fault;
    aw_asset_cache *recent;
    aw_asset_entry entries[AW_ASSET_LIMIT];
    aw_asset_cache cache[AW_ASSET_CACHE_SLOTS];
    uint8_t input[AW_PREFETCH_INPUT_BYTES];
    aw_asset_prefetch prefetch;
    uint16_t prefetch_next;
};

/* Parse the complete MEMLIST file. The terminator must be present. */
bool aw_assets_init(aw_assets *assets, const uint8_t *memlist, size_t bytes,
                    uint32_t capacity, void *ctx, aw_asset_bank_read bank_read,
                    aw_asset_store_read store_read, aw_asset_store_write store_write);
/* Decode a resource at most once. Failure never marks it as decoded. */
bool aw_assets_load(aw_assets *assets, unsigned id);
/* Advance at most one decode operation or one raw transfer. Speculative
 * failures leave the entry undecoded for the ordinary on-demand path. */
bool aw_assets_prefetch_step(aw_assets *assets);
bool aw_assets_read(aw_assets *assets, uint32_t offset, void *out, uint32_t size);
bool aw_assets_write(aw_assets *assets, uint32_t offset, const void *in, uint32_t size);
bool aw_assets_flush(aw_assets *assets);
/* Called only between complete cache operations; callbacks must not start a
 * nested resource load or use the shared compressed-input scratch buffer. */
void aw_assets_progress(aw_assets *assets);

#endif
