/* Compare the on-device cache builder with the independent host output. */
#include "mk61_app.h"
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static const char *directory;
static uint8_t *storage;
static uint32_t storage_size;
static bool deny_write, published;
const mk61_app_api *mk61_api;
uint32_t mk61_app_image_crc, mk61_app_current_kind;
int another_cache_builder_main(void);
static void service(void) {}
static uint32_t call(uint32_t op, uint32_t action, uint32_t b, uint32_t c, void *payload) {
    (void)b; (void)c;
    if (op == MK61_SERVICE_CAPABILITIES) return MK61_SERVICE_CAP_BUFFERS | MK61_SERVICE_CAP_EXTERNAL_BUFFERS |
        MK61_SERVICE_CAP_FILE_BYTES | MK61_SERVICE_CAP_FILE_WRITE_SOURCE;
    if (op == MK61_SERVICE_BUFFER) {
        mk61_service_buffer *r = payload;
        if (action == MK61_BUFFER_ACQUIRE) {
            assert(!storage && r->access == MK61_BUFFER_EXTERNAL);
            storage = calloc(1, r->size); storage_size = r->size; r->handle = 1; r->data = NULL;
            return storage != NULL;
        }
        if (!storage || r->handle != 1) return 0;
        if (action == MK61_BUFFER_RELEASE) { free(storage); storage = NULL; return 1; }
        if (r->offset > storage_size || r->size > storage_size - r->offset || r->size > 4096) return 0;
        if (action == MK61_BUFFER_READ) memcpy(r->data, storage + r->offset, r->size);
        else if (action == MK61_BUFFER_WRITE) memcpy(storage + r->offset, r->data, r->size);
        else return 0;
        return 1;
    }
    if (op == MK61_SERVICE_FILE_BYTES && action == MK61_FILE_BYTES_WRITE_SOURCE) {
        mk61_service_write_source *r = payload;
        if (deny_write) return 0;
        assert(!strcmp(r->name, "AWCACHE.BIN") && r->read && r->size > 0);
        char path[1024]; assert(snprintf(path, sizeof(path), "%s/AWCACHE.BIN", directory) < (int)sizeof(path));
        FILE *file = fopen(path, "rb"); assert(file);
        assert(!fseek(file, 0, SEEK_END) && (uint32_t)ftell(file) == r->size);
        uint8_t expected[997], actual[997];
        for (uint32_t end = r->size; end;) {
            const uint32_t n = end < sizeof(actual) ? end : sizeof(actual), at = end - n;
            assert(!fseek(file, at, SEEK_SET) && fread(expected, 1, n, file) == n);
            assert(r->read(r->context, at, actual, n) && !memcmp(expected, actual, n));
            end = at;
        }
        assert(!r->read(r->context, r->size, actual, 1));
        fclose(file); published = true; return 1;
    }
    if (op == MK61_SERVICE_FILE_BYTES) {
        mk61_service_file_bytes *r = payload; char path[1024];
        if (!r->path || snprintf(path, sizeof(path), "%s/%s", directory, r->path) >= (int)sizeof(path)) return 0;
        FILE *file = fopen(path, "rb"); if (!file) return 0;
        bool ok = false;
        if (action == MK61_FILE_BYTES_STAT) {
            mk61_service_file_info *info = r->data;
            if (!fseek(file, 0, SEEK_END)) { memset(info, 0, sizeof(*info)); info->size = (uint32_t)ftell(file); ok = true; }
        } else if (action == MK61_FILE_BYTES_READ && r->size <= 4096)
            ok = !fseek(file, r->offset, SEEK_SET) && fread(r->data, 1, r->size, file) == r->size;
        fclose(file); return ok;
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
    if (argc != 2 && argc != 3) return 2;
    directory = argv[1]; deny_write = argc == 3 && !strcmp(argv[2], "deny");
    if (argc == 3 && !deny_write) return 2;
    mk61_app_api api = {0}; api.magic = MK61_APP_API_MAGIC; api.version = MK61_APP_API_VERSION;
    api.struct_size = sizeof(api); api.service = service; api.query_service = query; mk61_api = &api;
    assert(another_cache_builder_main() == (deny_write ? 1 : 0));
    assert(!storage && published == !deny_write);
    puts(deny_write ? "Device cache builder: failed publish released resources" :
                      "Device cache builder: full output matches host cache in reverse chunks");
    return 0;
}
