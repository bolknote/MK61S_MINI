#ifndef MK61_ANOTHER_PREPARED_H
#define MK61_ANOTHER_PREPARED_H

#include "assets.h"

/* An optional host-generated cache; the original BANK files remain the
 * source of truth. A failed cache lookup leaves the normal loader usable. */
typedef bool (*aw_prepared_read)(void *ctx, uint32_t offset, void *data, uint32_t size);
typedef struct {
    void *ctx;
    aw_prepared_read read;
    const uint8_t *table;
    uint32_t size, count, payload;
} aw_prepared_cache;

bool aw_prepared_open(aw_prepared_cache *cache, const uint8_t *memlist, size_t memlist_bytes,
                      unsigned count, uint32_t cache_size, void *scratch, size_t scratch_size,
                      void *ctx, aw_prepared_read read);
bool aw_prepared_load(aw_prepared_cache *cache, aw_assets *assets, unsigned id);

#endif
