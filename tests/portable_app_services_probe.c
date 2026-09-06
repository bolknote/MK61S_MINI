#include "mk61_app.h"

static volatile double a = 7.0, b = 2.0;
static volatile uint64_t numerator = UINT64_C(0x123456789abcdef0);
static volatile uint64_t denominator = 97;

static uint32_t editor_hook(uint32_t operation, mk61_service_edit_hook* event) {
  (void) event;
  return operation == MK61_EDIT_INSERT ? (uint32_t) (uintptr_t) "1" : 0;
}

int main(void) {
  const mk61_app_services* s = mk61_app_get_services(mk61_api,
      MK61_SERVICE_CAP_FILES | MK61_SERVICE_CAP_MEMORY |
      MK61_SERVICE_CAP_MATH | MK61_SERVICE_CAP_FORMAT | MK61_SERVICE_CAP_EDITOR);
  if(!s) return MK61_APP_RUNTIME_ERROR;
  if(mk61_api->query_service(0xFFFFFFFFU, 1) ||
      mk61_api->query_service(MK61_APP_SERVICE_COMMON, 2)) return 10;
  if(a/b != 3.5 || a*b+a-b != 19.0 ||
      numerator / denominator != UINT64_C(13523386262513302) ||
      numerator % denominator != 26) return 11;
  if(s->math(MK61_SERVICE_SQRT, 144.0, 0) != 12.0) return 12;
  char output[48];
  int length = mk61_app_snprintf(s, output, sizeof(output), "APP %u", (unsigned) (a*b+a-b));
  if(length != 6 || output[4] != '1' || output[5] != '9') return 13;

  mk61_service_lease workspace = {0}, scratch = {0};
  if(!s->call(MK61_SERVICE_MEMORY_ACQUIRE, MK61_SERVICE_WORKSPACE,
      MK61_SERVICE_OWNER_APP, 128, &workspace)) return 14;
  if(!s->call(MK61_SERVICE_MEMORY_ACQUIRE, MK61_SERVICE_SCRATCH,
      MK61_SERVICE_OWNER_APP, 32, &scratch)) {
    s->call(MK61_SERVICE_MEMORY_RELEASE, MK61_SERVICE_WORKSPACE, 0, 0, &workspace);
    return 15;
  }
  workspace.data[0] = 0x61;
  scratch.data[0] = 0xA4;
  int result = 0;
  mk61_service_write file = {"APITEST", (const uint8_t*) output, (uint32_t) length,
                              MK61_SERVICE_INVALID_ID};
  /* Release the shared scratch before file I/O; C5 may need that same arena. */
  s->call(MK61_SERVICE_MEMORY_RELEASE, MK61_SERVICE_SCRATCH, 0, 0, &scratch);
  s->call(MK61_SERVICE_MEMORY_RELEASE, MK61_SERVICE_WORKSPACE, 0, 0, &workspace);
  if(!s->call(MK61_SERVICE_FILE_WRITE, MK61_SERVICE_ROOT_ID,
      MK61_SERVICE_INVALID_ID, MK61_SERVICE_FILE_TEXT, &file)) return 16;
  uint8_t copy[6];
  if(mk61_api->file_size(file.id) != sizeof(copy) ||
      mk61_api->file_read(file.id, 0, copy, sizeof(copy)) != sizeof(copy)) result = 17;
  for(unsigned i = 0; !result && i < sizeof(copy); ++i)
    if(copy[i] != (uint8_t) output[i]) result = 18;
  if(!s->call(MK61_SERVICE_FILE_REMOVE, file.id, 0, 0, NULL)) result = 19;

  /* Execute the resident editor from an ordinary C APP, without adapters. */
  char source[16] = "";
  mk61_service_edit_key editor = {0};
  editor.source = source;
  editor.capacity = sizeof(source);
  editor.key = s->keyboard_mapping->digit[1];
  editor.hook = editor_hook;
  editor.hook_mask = 1U << MK61_EDIT_INSERT;
  for(unsigned i = 0; i < 13; ++i) editor.keys[i] = -1;
  editor.backspace_key = -1;
  s->call(MK61_SERVICE_EDITOR_KEY, 0, 0, 0, &editor);
  if(editor.length != 1 || source[0] != '1') result = 20;
  return result;
}
