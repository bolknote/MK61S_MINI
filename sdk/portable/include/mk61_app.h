#ifndef MK61_APP_H
#define MK61_APP_H

#include "loadable_app_api.h"
#include "loadable_app_services.h"

#ifdef __cplusplus
extern "C" {
#endif

extern const mk61_app_api* mk61_api;

/* Query MK61_SERVICE_CAP_FORMAT first. Compact firmware provides integer,
 * string and character formatting; floating conversions are not promised. */
static inline int mk61_app_snprintf(const mk61_app_services* services,
    char* output, uint32_t size, const char* format, ...) {
  va_list args;
  va_start(args, format);
  const int result = services->format(output, size, format, args);
  va_end(args);
  return result;
}

enum mk61_app_command {
  MK61_APP_INITIALIZE = 0,
  MK61_APP_RUN = 1,
  MK61_APP_FILE_OPEN = 2
};

enum mk61_app_result {
  MK61_APP_OK = 0,
  MK61_APP_INVALID_FILE,
  MK61_APP_UNSUPPORTED_DISPLAY,
  MK61_APP_BUSY,
  MK61_APP_IO_ERROR,
  MK61_APP_RUNTIME_ERROR
};

/* Optional file-handler hook. main() is called for a direct APP launch. */
uint32_t mk61_app_open_file(uint32_t file_id);

#ifdef __cplusplus
}
#endif
#endif
