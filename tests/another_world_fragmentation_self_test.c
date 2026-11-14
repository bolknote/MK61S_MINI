/* Exercises the ordinary APP entry with simulated PicoCalc services and the
 * user's DOS files. No board, serial port or persistent storage is changed. */
#include "mk61_app.h"
#include "../examples/portable-apps/ANOTHER/video.h"
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static const char *directory;
static uint8_t *buffers[5], borrowed_frame[12800];
static uint32_t sizes[5], now_ms, presents, audio_samples, audio_queued, releases, graphics;
static bool busy_once, ended;
static unsigned unexpected_extra_acquisitions;
typedef struct { unsigned at, size; bool used; } arena_block;
typedef struct { unsigned count; bool resident_allocated; arena_block blocks[32]; } arena_state;
static arena_state arena;
static _Alignas(8) uint8_t arena_bytes[75000];
static bool pair_granted, background_head_granted, background_tail_granted;
static void *audio_allocation;

static void *arena_allocate(unsigned size) {
    const unsigned need = ((size + 7u) & ~7u) + 16u;
    for (unsigned i = 0; i < arena.count; ++i) if (!arena.blocks[i].used && arena.blocks[i].size >= need) {
        arena_block *b = &arena.blocks[i];
        if (b->size - need >= 16) {
            assert(arena.count < 32);
            memmove(&arena.blocks[i + 2], &arena.blocks[i + 1], (arena.count - i - 1) * sizeof(*b));
            arena.blocks[i + 1] = (arena_block){b->at + need, b->size - need, false};
            ++arena.count; b = &arena.blocks[i]; b->size = need;
        }
        b->used = true; return arena_bytes + b->at + 16;
    }
    return NULL;
}
static void arena_release(void *pointer) {
    const unsigned at = (unsigned)((uint8_t *)pointer - arena_bytes) - 16;
    unsigned i = 0; while (i < arena.count && arena.blocks[i].at != at) ++i;
    assert(i < arena.count && arena.blocks[i].used); arena.blocks[i].used = false;
    if (i && !arena.blocks[i - 1].used) {
        arena.blocks[i - 1].size += arena.blocks[i].size;
        memmove(&arena.blocks[i], &arena.blocks[i + 1], (arena.count - i - 1) * sizeof(arena.blocks[0]));
        --arena.count; --i;
    }
    if (i + 1 < arena.count && !arena.blocks[i + 1].used) {
        arena.blocks[i].size += arena.blocks[i + 1].size;
        memmove(&arena.blocks[i + 1], &arena.blocks[i + 2], (arena.count - i - 2) * sizeof(arena.blocks[0]));
        --arena.count;
    }
}
const mk61_app_api *mk61_api;
uint32_t mk61_app_image_crc, mk61_app_current_kind;
int another_app_main(void);

static uint32_t now(void) { return now_ms++; }
static void service(void) { ++now_ms; if (audio_queued) --audio_queued; }
static uint32_t clear(void) { return 1; }
static uint32_t write_text(uint32_t x, uint32_t y, const char *s, uint32_t n) {
    (void)x; (void)y; fprintf(stderr, "unexpected APP error: %.*s\n", (int)n, s); return 1;
}
static int32_t key_wait(void) { return 0; }
static uint32_t graphics_begin(void) { ++graphics; return 1; }
static void graphics_end(void) { assert(graphics); --graphics; }
static uint32_t call(uint32_t op, uint32_t a, uint32_t b, uint32_t c, void *payload) {
    (void)b; (void)c;
    if (op == MK61_SERVICE_CAPABILITIES) return MK61_SERVICE_CAP_BUFFERS | MK61_SERVICE_CAP_EXTERNAL_BUFFERS |
        MK61_SERVICE_CAP_COLOR_DISPLAY | MK61_SERVICE_CAP_TEXT_COLORS | MK61_SERVICE_CAP_FILE_BYTES | MK61_SERVICE_CAP_AUDIO_STREAM;
    if (op == MK61_SERVICE_BUFFER) {
        mk61_service_buffer *r = payload;
        if (a == MK61_BUFFER_ACQUIRE) {
            const unsigned id = r->access == MK61_BUFFER_EXTERNAL ? 1 : !buffers[2] ? 2 : !buffers[3] ? 3 : 4;
            if (buffers[id]) { ++unexpected_extra_acquisitions; return 0; }
            buffers[id] = id == 1 ? calloc(1, r->size) : arena_allocate(r->size);
            if (!buffers[id]) return 0;
            sizes[id] = r->size; r->handle = id;
            if (id != 1 && r->size == 2 * AW_VIDEO_PAGE_BYTES) pair_granted = true;
            if (id != 1 && r->size == 4096) background_head_granted = true;
            if (id != 1 && r->size == 2048) background_tail_granted = true;
            r->storage = id == 1 ? MK61_BUFFER_PSRAM : MK61_BUFFER_SRAM;
            r->data = id == 1 ? NULL : buffers[id]; return buffers[id] != NULL;
        }
        if (!r->handle || r->handle > 4 || !buffers[r->handle]) return 0;
        if (a == MK61_BUFFER_RELEASE) {
            if (r->handle == 1) free(buffers[r->handle]); else arena_release(buffers[r->handle]);
            buffers[r->handle] = NULL; ++releases; return 1;
        }
        if (r->offset > sizes[r->handle] || r->size > sizes[r->handle] - r->offset || r->size > 4096) return 0;
        if (a == MK61_BUFFER_READ) memcpy(r->data, buffers[r->handle] + r->offset, r->size);
        else if (a == MK61_BUFFER_WRITE) memcpy(buffers[r->handle] + r->offset, r->data, r->size);
        else return 0;
        return 1;
    }
    if (op == MK61_SERVICE_FILE_BYTES) {
        mk61_service_file_bytes *r = payload; char path[1024];
        if (!r->path || snprintf(path, sizeof(path), "%s/%s", directory, r->path) >= (int)sizeof(path)) return 0;
        FILE *f = fopen(path, "rb"); if (!f) return 0;
        bool ok = false;
        if (a == MK61_FILE_BYTES_STAT) {
            mk61_service_file_info *info = r->data;
            if (fseek(f, 0, SEEK_END) == 0) { memset(info, 0, sizeof(*info)); info->size = (uint32_t)ftell(f); ok = true; }
        } else if (a == MK61_FILE_BYTES_READ && r->size <= 4096)
            ok = fseek(f, r->offset, SEEK_SET) == 0 && fread(r->data, 1, r->size, f) == r->size;
        fclose(f); return ok;
    }
    if (op == MK61_SERVICE_KEYBOARD && a == MK61_SERVICE_KEY_BITMAP) {
        uint8_t *map = payload; memset(map, 0, 32);
        if (presents >= 30) map[0x1B / 8] |= 1u << (0x1B & 7);
        return 1;
    }
    if (op == MK61_SERVICE_DISPLAY && a == MK61_SERVICE_DISPLAY_FRAMEBUFFER) {
        if (b != sizeof(mk61_service_framebuffer) || c || !payload || !graphics) return 0;
        *(mk61_service_framebuffer *)payload = (mk61_service_framebuffer){borrowed_frame, sizeof(borrowed_frame), 320, 320};
        return 1;
    }
    if (op == MK61_SERVICE_AUDIO_STREAM) {
        mk61_service_audio *r = payload;
        if (a == MK61_AUDIO_CLOSE) { if (audio_allocation) arena_release(audio_allocation); ended = true; return 1; }
        if (a == MK61_AUDIO_OPEN) {
            if (!r || r->rate != 25000 || r->volume != 100) return 0;
            audio_allocation = arena_allocate(1064); return audio_allocation != NULL;
        }
        if (a == MK61_AUDIO_WRITE) {
            const unsigned room = 1024 - audio_queued;
            if (r->count > room) r->count = room;
            audio_samples += r->count; audio_queued += r->count;
        } else if (a != MK61_AUDIO_STATUS) return 0;
        r->queued = audio_queued; return 1;
    }
    if (op == MK61_SERVICE_COLOR_DISPLAY) {
        if (a == MK61_COLOR_END) return 1;
        if (a != MK61_COLOR_PRESENT) return 0;
        mk61_service_color_frame *f = payload;
        if (!busy_once) { busy_once = true; return 2; }
        assert(!(f->x & 1) && !(f->width & 1) && f->x + f->width <= 320);
        assert(f->y >= 60 && f->y + f->height <= 260);
        assert(f->pixel_bytes == f->height * f->width / 2 && f->pixel_bytes <= MK61_COLOR_SNAPSHOT_BYTES);
        assert((f->format & ~MK61_COLOR_PRESERVE_OUTSIDE) == MK61_COLOR_INDEX4);
        assert(!!(f->format & MK61_COLOR_PRESERVE_OUTSIDE) == (presents != 0));
        ++presents; return 1;
    }
    return 0;
}
static const mk61_app_services services = {
    MK61_APP_SERVICES_MAGIC, MK61_APP_SERVICES_VERSION, sizeof(mk61_app_services), NULL, call, NULL, NULL, NULL
};
static const void *query(uint32_t id, uint32_t version) {
    return id == MK61_APP_SERVICE_COMMON && version == MK61_APP_SERVICES_VERSION ? &services : NULL;
}
int main(int argc, char **argv) {
    if (argc != 3) { fprintf(stderr, "usage: %s DATA_DIR STATE_FILE\n", argv[0]); return 2; }
    directory = argv[1];
    FILE *state = fopen(argv[2], "rb");
    if (state) {
        assert(fread(&arena, sizeof(arena), 1, state) == 1); fclose(state);
        assert(arena.resident_allocated);
    } else {
        /* Model observed free blocks after the APP image is loaded: there is
         * enough total RAM, but a resident allocation separates two holes. */
        arena.count = 3; arena.resident_allocated = true;
        arena.blocks[0] = (arena_block){0, 3472, false};
        arena.blocks[1] = (arena_block){3472, 16, true};
        arena.blocks[2] = (arena_block){3488, 69000, false};
    }
    arena_state saved = arena;
    assert(arena_allocate(2 * AW_VIDEO_PAGE_BYTES));
    assert(arena_allocate(1064)); /* Audio starts before the cache reservation. */
    assert(!arena_allocate(6144)); /* A single cache block does not fit. */
    assert(arena_allocate(4096) && arena_allocate(2048)); /* Two smaller blocks do. */
    arena = saved;
    mk61_app_api api = {0}; api.magic = MK61_APP_API_MAGIC; api.version = MK61_APP_API_VERSION; api.struct_size = sizeof(api);
    api.millis_ms = now; api.service = service; api.display_clear = clear; api.display_write_m8 = write_text;
    api.key_wait = key_wait; api.graphics_begin = graphics_begin; api.graphics_end = graphics_end; api.query_service = query;
    mk61_api = &api;
    assert(another_app_main() == 0);
    assert(presents >= 30 && audio_samples > 0 && releases == 4 && pair_granted && background_head_granted && background_tail_granted &&
           !unexpected_extra_acquisitions && ended && !graphics &&
           !buffers[1] && !buffers[2] && !buffers[3] && !buffers[4]);
    state = fopen(argv[2], "wb"); assert(state && fwrite(&arena, sizeof(arena), 1, state) == 1); fclose(state);
    printf("Fragmented-heap launch passed: %u display strips, split background cache active\n", presents);
    return 0;
}
