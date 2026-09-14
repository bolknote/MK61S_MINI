#include "mk61_app.h"

const mk61_app_api* mk61_api;
uint32_t mk61_app_image_crc;
uint32_t mk61_app_current_kind;
extern int main(void) __attribute__((weak));
#if defined(MK61_APP_SHARED_RUNTIME)
extern int mk61_app_bind_runtime(const mk61_app_api* api);
#endif

__attribute__((weak)) uint32_t mk61_app_initialize(
    const mk61_app_api* api, uint32_t image_crc, uint32_t kind) {
  (void) api;
  (void) image_crc;
  (void) kind;
  return MK61_APP_OK;
}

__attribute__((weak)) uint32_t mk61_app_open_file(uint32_t file_id) {
  (void) file_id;
  return MK61_APP_INVALID_FILE;
}

__attribute__((weak)) uint32_t mk61_app_command(
    uint32_t command, uint32_t argument0, uint32_t argument1,
    uint32_t argument2, uint32_t argument3) {
  (void) argument0;
  (void) argument2;
  (void) argument3;
  if(command == MK61_APP_RUN)
    return main ? (uint32_t) main() : MK61_APP_RUNTIME_ERROR;
  if(command == MK61_APP_FILE_OPEN)
    return mk61_app_open_file(argument1);
  return MK61_APP_RUNTIME_ERROR;
}

__attribute__((used, section(".mk61_module_entry")))
uint32_t mk61_module_entry(uint32_t command, uint32_t argument0,
                           uint32_t argument1, uint32_t argument2,
                           uint32_t argument3) {
  if(command == MK61_APP_INITIALIZE) {
    const mk61_app_api* api = (const mk61_app_api*) (uintptr_t) argument0;
    if(!mk61_app_api_compatible(api, sizeof(*api), 0))
      return MK61_APP_RUNTIME_ERROR;
    mk61_api = api;
    mk61_app_image_crc = argument1;
    mk61_app_current_kind = argument2;
#if defined(MK61_APP_SHARED_RUNTIME)
    if(!mk61_app_bind_runtime(api)) return MK61_APP_RUNTIME_ERROR;
#endif
    return mk61_app_initialize(api, argument1, argument2);
  }
  if(!mk61_api) return MK61_APP_RUNTIME_ERROR;
  return mk61_app_command(command, argument0, argument1,
                          argument2, argument3);
}
