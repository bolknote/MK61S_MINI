#include "mk61_app.h"
#include <string.h>

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
      MK61_SERVICE_CAP_MATH | MK61_SERVICE_CAP_FORMAT | MK61_SERVICE_CAP_EDITOR |
      MK61_SERVICE_CAP_NUMBER_IO);
  if(!s) return MK61_APP_RUNTIME_ERROR;
  if(mk61_api->query_service(0xFFFFFFFFU, 1) ||
      mk61_api->query_service(MK61_APP_SERVICE_COMMON,
                              MK61_APP_SERVICES_VERSION + 1U)) return 10;
  if(a/b != 3.5 || a*b+a-b != 19.0 ||
      numerator / denominator != UINT64_C(13523386262513302) ||
      numerator % denominator != 26) return 11;
  if(s->math(MK61_SERVICE_SQRT, 144.0, 0) != 12.0) return 12;
  char output[48];
  int length = mk61_app_snprintf(s, output, sizeof(output), "APP %u", (unsigned) (a*b+a-b));
  if(length != 6 || output[4] != '1' || output[5] != '9') return 13;
  char number[24];
  mk61_service_number_format number_request = {
      1.0 / 3.0, number, sizeof(number), 10};
  if(!s->call(MK61_SERVICE_NUMBER_FORMAT, 0, 0, 0, &number_request) ||
     strncmp(number, "0.3333333333", sizeof(number)) != 0) return 21;
  const char parsed_text[] = "-12.5E2X";
  mk61_service_number_parse parse_request = {0.0, parsed_text, 0};
  if(!s->call(MK61_SERVICE_NUMBER_PARSE, 0, 0, 0, &parse_request) ||
     parse_request.value != -1250.0 || parse_request.consumed != 7) return 22;
  mk61_service_ref_parse ref_request = {{'R', 'E', 0, 0}, 0, 0};
  if(!s->call(MK61_SERVICE_REF_PARSE, 0, 0, 0, &ref_request) ||
     ref_request.kind != MK61_SERVICE_REF_R || ref_request.reg != 14) return 23;

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
  char default_source[4] = "";
  mk61_service_edit_key default_editor = {0};
  default_editor.source = default_source;
  default_editor.capacity = sizeof(default_source);
  default_editor.key = s->keyboard_mapping->digit[2];
  default_editor.options = 8U | 16U;
  default_editor.backspace_key = -1;
  s->call(MK61_SERVICE_EDITOR_KEY, 0, 0, 0, &default_editor);
  if(default_editor.length != 1 || default_source[0] != '2') result = 24;
  default_editor.shift = 1; /* text_editor::Shift::ALPHA */
  default_editor.key = s->keyboard_mapping->cx;
  s->call(MK61_SERVICE_EDITOR_KEY, 0, 0, 0, &default_editor);
  if(default_editor.length != 0 || default_source[0] != 0) result = 25;
  return result;
}
