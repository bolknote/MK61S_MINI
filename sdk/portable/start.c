#include "mk61_app.h"

const mk61_app_api* mk61_api;
extern int main(void);
#if defined(MK61_APP_SHARED_RUNTIME)
extern int mk61_app_bind_runtime(const mk61_app_api* api);
#endif

__attribute__((weak)) uint32_t mk61_app_open_file(uint32_t file_id) {
  (void) file_id;
  return MK61_APP_INVALID_FILE;
}

__attribute__((used, section(".mk61_module_entry")))
uint32_t mk61_module_entry(uint32_t command, uint32_t argument0,
                           uint32_t argument1, uint32_t argument2,
                           uint32_t argument3) {
  (void) argument2;
  (void) argument3;
  const mk61_app_api* api = (const mk61_app_api*) (uintptr_t) argument0;
  if(!mk61_app_api_compatible(api, sizeof(*api), 0))
    return MK61_APP_RUNTIME_ERROR;
  mk61_api = api;
  switch(command) {
    case MK61_APP_INITIALIZE:
#if defined(MK61_APP_SHARED_RUNTIME)
      if(!mk61_app_bind_runtime(api)) return MK61_APP_RUNTIME_ERROR;
#endif
      return MK61_APP_OK;
    case MK61_APP_RUN: return (uint32_t) main();
    case MK61_APP_FILE_OPEN: return mk61_app_open_file(argument1);
    default: return MK61_APP_RUNTIME_ERROR;
  }
}
