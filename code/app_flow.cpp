#include "app_flow.hpp"
#include "loadable_app_api.h"

namespace app_flow {
namespace {
bool valid(Target target) {
  return (!target.flags || (target.flags & MK61_APP_FLOW_DIRECT)) &&
      target.kind <= MK61_APP_KIND_LANGUAGE_INPUT &&
      (target.kind == MK61_APP_KIND_APPLICATION || target.file_id == MK61_APP_FLOW_SYSTEM_FILE) &&
      (target.kind != MK61_APP_FLOW_HOST || !target.flags);
}
bool same(Target a, Target b) {
  return a.kind == b.kind && a.file_id == b.file_id && a.phase == b.phase &&
      a.flags == b.flags;
}
}

Status run(Target current, void* context, uint32_t size, uint32_t& result,
           Invoke invoke, void* backend) {
  result = 0;
  if(!invoke || !valid(current) || ((context != nullptr) != (size != 0)) ||
     (size && (uintptr_t)context > UINTPTR_MAX - size))
    return MK61_FLOW_INVALID_MODULE;
  Target parents[MK61_APP_FLOW_MAX_DEPTH];
  unsigned depth = 0;
  uint32_t previous_result = 0, previous_status = MK61_FLOW_OK;
  for(;;) {
    Step step = {sizeof(Step), MK61_APP_FLOW_VERSION, context, size,
                 current, {}, MK61_FLOW_INVALID, 0, previous_result, previous_status};
    const Status called = invoke(backend, current, step);
    if(called < MK61_FLOW_OK || called > MK61_FLOW_IO_ERROR) return MK61_FLOW_CORRUPT;
    if(called != MK61_FLOW_OK) {
      if(!depth) return called;
      current = parents[--depth];
      previous_result = 0; previous_status = called;
      continue;
    }
    if(!mk61_app_flow_compatible(&step) || step.context != context ||
       step.context_size != size || !same(step.current, current) ||
       step.status > MK61_FLOW_IO_ERROR) return MK61_FLOW_CORRUPT;
    switch(step.action) {
      case MK61_FLOW_CALL:
        if(!valid(step.next)) return MK61_FLOW_CORRUPT;
        if(depth == MK61_APP_FLOW_MAX_DEPTH) {
          current.phase = step.resume_phase;
          previous_result = 0; previous_status = MK61_FLOW_BUSY;
          break;
        }
        parents[depth] = current;
        parents[depth++].phase = step.resume_phase;
        current = step.next; previous_result = 0; previous_status = MK61_FLOW_OK;
        break;
      case MK61_FLOW_NEXT:
        if(!valid(step.next)) return MK61_FLOW_CORRUPT;
        current = step.next; previous_result = 0; previous_status = MK61_FLOW_OK;
        break;
      case MK61_FLOW_RETURN:
        if(depth) {
          current = parents[--depth];
          previous_result = step.result; previous_status = step.status;
          break;
        }
        [[fallthrough]];
      case MK61_FLOW_EXIT:
        result = step.result;
        return (Status)step.status;
      default: return MK61_FLOW_CORRUPT;
    }
  }
}
}
