#ifndef MK61_APP_FLOW_H
#define MK61_APP_FLOW_H

#include <stddef.h>
#include <stdint.h>
#include "loadable_app_api.h"

/* Cooperative APP calls. Every step returns before another image is loaded.
 * The caller owns context for the entire flow, outside any APP image/BSS or
 * APP native stack. Context is opaque to the loader; no payload is copied.
 * Commands 3/4 extend the existing INITIALIZE/RUN/FILE_OPEN prefix. */
#define MK61_APP_FLOW_MAGIC 0x31574C46UL
#define MK61_APP_FLOW_VERSION 1U
#define MK61_APP_FLOW_INFO 3U
#define MK61_APP_FLOW_STEP 4U
#define MK61_APP_FLOW_HOST 0U
#define MK61_APP_FLOW_SYSTEM_FILE 0xFFFFU
#define MK61_APP_FLOW_MAX_DEPTH 4U
#define MK61_APP_FLOW_USER_CONTEXT_SIZE 64U
#define MK61_APP_FLOW_DIRECT 1U

/* These wire values match loadable_module::RuntimeStatus, not APP exit codes. */
enum mk61_app_flow_status {
  MK61_FLOW_OK = 0, MK61_FLOW_DISABLED, MK61_FLOW_UNAVAILABLE,
  MK61_FLOW_INVALID_MODULE, MK61_FLOW_INCOMPATIBLE, MK61_FLOW_CORRUPT,
  MK61_FLOW_BUSY, MK61_FLOW_IO_ERROR
};
enum mk61_app_flow_action {
  MK61_FLOW_INVALID = 0, MK61_FLOW_NEXT, MK61_FLOW_CALL,
  MK61_FLOW_RETURN, MK61_FLOW_EXIT
};
typedef struct mk61_app_flow_target {
  uint16_t file_id;
  /* 0 = cooperative STEP; odd = existing command, four u32 arguments at
   * context + 4*(flags>>1). This also calls older APP without new entry code. */
  uint8_t kind, flags;
  uint32_t phase;
} mk61_app_flow_target;
typedef struct mk61_app_flow {
  uint32_t size, version;
  void* context;
  uint32_t context_size;
  mk61_app_flow_target current, next;
  uint32_t action, resume_phase;
  /* Input: preceding child result/status. Output for RETURN/EXIT: result/status
   * delivered to the parent, or to the resident caller at the root. */
  uint32_t result, status;
} mk61_app_flow;

static inline int mk61_app_flow_compatible(const mk61_app_flow* flow) {
  return flow && flow->size == sizeof(*flow) &&
      flow->version == MK61_APP_FLOW_VERSION &&
      ((flow->context != NULL) == (flow->context_size != 0));
}
static inline mk61_app_flow_target mk61_app_flow_to(
    uint8_t kind, uint16_t file_id, uint32_t phase) {
  mk61_app_flow_target target = {file_id, kind, 0, phase};
  return target;
}
static inline mk61_app_flow_target mk61_app_flow_direct(
    uint8_t kind, uint16_t file_id, uint32_t command, uint8_t argument_word) {
  mk61_app_flow_target target = {file_id, kind,
      (uint8_t)(argument_word < 128
          ? MK61_APP_FLOW_DIRECT | (argument_word << 1) : 2U), command};
  return target;
}
static inline void mk61_app_flow_next(
    mk61_app_flow* flow, mk61_app_flow_target target) {
  flow->next = target; flow->action = MK61_FLOW_NEXT;
}
static inline void mk61_app_flow_call(
    mk61_app_flow* flow, mk61_app_flow_target target, uint32_t resume_phase) {
  flow->next = target; flow->resume_phase = resume_phase;
  flow->action = MK61_FLOW_CALL;
}
static inline void mk61_app_flow_return(
    mk61_app_flow* flow, uint32_t result, uint32_t status) {
  flow->result = result; flow->status = status; flow->action = MK61_FLOW_RETURN;
}
static inline void mk61_app_flow_exit(
    mk61_app_flow* flow, uint32_t result, uint32_t status) {
  flow->result = result; flow->status = status; flow->action = MK61_FLOW_EXIT;
}
#if UINTPTR_MAX == UINT32_MAX
#ifdef __cplusplus
static_assert(sizeof(mk61_app_flow_target) == 8 && sizeof(mk61_app_flow) == 48,
              "APP flow wire layout changed");
#else
_Static_assert(sizeof(mk61_app_flow_target) == 8 && sizeof(mk61_app_flow) == 48,
               "APP flow wire layout changed");
#endif
#endif

#endif
