#ifndef MK61_APP_H
#define MK61_APP_H

#include "loadable_app_api.h"
#include "app_flow.h"
#include "loadable_app_services.h"

#ifdef __cplusplus
extern "C" {
#endif

extern const mk61_app_api* mk61_api;
extern uint32_t mk61_app_image_crc;
extern uint32_t mk61_app_current_kind;

/* CPU work hint, optional on ABI6. Blocking waits may lower the frequency;
 * callers keep normal timers/frame pacing. Tokens must end in reverse order
 * and remain valid only for the current logical APP/flow invocation. */
static inline uint32_t mk61_app_compute_begin(const mk61_app_services* services) {
  if(!services || !services->call ||
      services->call(MK61_SERVICE_COMPUTE,MK61_COMPUTE_PROBE,0,0,NULL)!=MK61_COMPUTE_MAGIC)return 0;
  return services->call(MK61_SERVICE_COMPUTE,MK61_COMPUTE_BEGIN,0,0,NULL);
}
static inline uint32_t mk61_app_compute_end(const mk61_app_services* services,uint32_t token) {
  return token && services && services->call ?
      services->call(MK61_SERVICE_COMPUTE,MK61_COMPUTE_END,token,0,NULL):0;
}
static inline uint32_t mk61_app_compute_hz(const mk61_app_services* services) {
  if(!services || !services->call ||
      services->call(MK61_SERVICE_COMPUTE,MK61_COMPUTE_PROBE,0,0,NULL)!=MK61_COMPUTE_MAGIC)return 0;
  return services->call(MK61_SERVICE_COMPUTE,MK61_COMPUTE_HZ,0,0,NULL);
}

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

/* Optional indirect buffers. Query CAP_BUFFERS before use. These helpers
 * preserve ABI 6 and return 0 when a firmware lacks the capability. */
static inline uint32_t mk61_app_buffer_call(const mk61_app_services* services,
    uint32_t operation, mk61_service_buffer* request) {
  if(!services || !services->call || !request ||
      !(services->call(MK61_SERVICE_CAPABILITIES,0,0,0,NULL)&MK61_SERVICE_CAP_BUFFERS)) return 0;
  return services->call(MK61_SERVICE_BUFFER,operation,0,sizeof(*request),request);
}
static inline mk61_service_buffer mk61_app_buffer_request(void) {
  mk61_service_buffer request={0,0,0,NULL,0,0,0,0};return request;
}
static inline uint32_t mk61_app_buffer_acquire(const mk61_app_services* services,
    uint32_t bytes,uint32_t access,mk61_service_buffer* out) {
  if(!out) return 0;
  *out=mk61_app_buffer_request();out->size=bytes;out->access=access;
  return mk61_app_buffer_call(services,MK61_BUFFER_ACQUIRE,out);
}
static inline uint32_t mk61_app_buffer_read(const mk61_app_services* services,
    uint32_t handle,uint32_t offset,void* target,uint32_t bytes) {
  mk61_service_buffer r=mk61_app_buffer_request();r.handle=handle;r.offset=offset;r.size=bytes;r.data=(uint8_t*)target;
  return mk61_app_buffer_call(services,MK61_BUFFER_READ,&r);
}
static inline uint32_t mk61_app_buffer_write(const mk61_app_services* services,
    uint32_t handle,uint32_t offset,const void* source,uint32_t bytes) {
  mk61_service_buffer r=mk61_app_buffer_request();r.handle=handle;r.offset=offset;r.size=bytes;r.data=(uint8_t*)source;
  return mk61_app_buffer_call(services,MK61_BUFFER_WRITE,&r);
}
static inline uint32_t mk61_app_buffer_release(const mk61_app_services* services,uint32_t handle) {
  mk61_service_buffer r=mk61_app_buffer_request();r.handle=handle;
  return mk61_app_buffer_call(services,MK61_BUFFER_RELEASE,&r);
}

/* One consumer owns the keyboard until TEXT_END. POLL returns 1 for a copied
 * M8/editing event, 0 for no event. Begin/end discard the causal handoff key. */
static inline uint32_t mk61_app_text_input(const mk61_app_services* services,
    uint32_t operation, uint32_t russian, mk61_service_text_event* event) {
  if(!services || !services->call ||
      !(services->call(MK61_SERVICE_CAPABILITIES,0,0,0,NULL)&MK61_SERVICE_CAP_TEXT_INPUT)) return 0;
  if(operation == MK61_TEXT_BEGIN && event) { event->layout=russian;event->reserved=0; }
  return services->call(MK61_SERVICE_TEXT_INPUT,operation,russian,
      event ? sizeof(*event) : 0,event);
}
/* Synchronous and atomic. Callback data/context must remain valid until return.
 * On failure the previous file is retained; no RAM-sized copy is required. */
static inline uint32_t mk61_app_file_write_source(const mk61_app_services* services,
    uint32_t parent,uint32_t preferred,uint32_t type,mk61_service_write_source* source) {
  if(!services || !services->call || !source ||
      !(services->call(MK61_SERVICE_CAPABILITIES,0,0,0,NULL)&MK61_SERVICE_CAP_FILE_WRITE_SOURCE)) return 0;
  return services->call(MK61_SERVICE_FILE_WRITE_SOURCE,parent,preferred,type,source);
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
/* Optional: defining this hook advertises cooperative APP flow support.
 * Return 1 after filling the next action; 0 rejects a malformed request. */
uint32_t mk61_app_flow_step(mk61_app_flow* flow);
uint32_t mk61_app_file_flow(void);

/* Advanced hooks shared by ordinary and canonical System APP. The SDK owns
 * mk61_module_entry and validates/binds the host before either hook runs.
 * Most APP only implement main() and optionally mk61_app_open_file(). */
uint32_t mk61_app_initialize(const mk61_app_api* api,
                             uint32_t image_crc, uint32_t kind);
uint32_t mk61_app_command(uint32_t command, uint32_t argument0,
                          uint32_t argument1, uint32_t argument2,
                          uint32_t argument3);

#ifdef __cplusplus
}
#endif
#endif
