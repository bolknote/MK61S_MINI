#include "app_flow.hpp"
#include "loadable_app_api.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>
#include <vector>

using namespace app_flow;
struct Context { unsigned value = 0, resumes = 0; };
struct Backend {
  bool active = false;
  unsigned calls = 0;
  unsigned mode = 0;
  std::vector<unsigned> trace;
  unsigned char image[256] = {};
};
static Target target(unsigned kind, unsigned phase) {
  return mk61_app_flow_to((uint8_t)kind, MK61_APP_FLOW_SYSTEM_FILE, phase);
}
static Status actor(void* raw, const Target& next, Step& step) {
  auto& backend = *(Backend*)raw;
  assert(!backend.active && ++backend.calls < 100);
  backend.active = true;
  memset(backend.image, 0xCD, sizeof(backend.image)); // Previous native globals gone.
  backend.trace.push_back(next.kind * 100 + next.phase);
  auto& context = *(Context*)step.context;
  assert(step.context_size == sizeof(context));
  Status status = MK61_FLOW_OK;
  switch(backend.mode) {
    case 1: // Missing child returns an error to its explicit continuation.
      if(next.phase == 1) {
        assert(step.status == MK61_FLOW_UNAVAILABLE && !step.result);
        ++context.resumes;
        mk61_app_flow_return(&step, 99, MK61_FLOW_OK);
      } else if(next.kind == MK61_APP_KIND_LANGUAGE_INPUT) status = MK61_FLOW_UNAVAILABLE;
      else mk61_app_flow_call(&step, target(MK61_APP_KIND_LANGUAGE_INPUT, 0), 1);
      break;
    case 2: // Depth exhaustion is recoverable; no suspended native stacks.
      if(next.phase == 1) {
        ++context.resumes;
        mk61_app_flow_return(&step, 5, step.status);
      } else mk61_app_flow_call(&step, target(next.kind, 0), 1);
      break;
    case 3: step.context = backend.image; mk61_app_flow_return(&step, 0, MK61_FLOW_OK); break;
    case 4: step.current.phase++; mk61_app_flow_return(&step, 0, MK61_FLOW_OK); break;
    case 5: step.version++; mk61_app_flow_return(&step, 0, MK61_FLOW_OK); break;
    case 6: mk61_app_flow_next(&step, target(255, 0)); break;
    case 7: break; // Unsupported step must fail closed, not repeat forever.
    case 8: mk61_app_flow_exit(&step, 7, MK61_FLOW_IO_ERROR); break;
    default:
      if(next.kind == MK61_APP_KIND_TINYBASIC) {
        context.value = 42;
        mk61_app_flow_next(&step, target(MK61_APP_KIND_LANGUAGE_VM, 0));
      } else if(next.kind == MK61_APP_KIND_LANGUAGE_VM && next.phase == 0) {
        mk61_app_flow_call(&step, target(MK61_APP_KIND_LANGUAGE_INPUT, 0), 1);
      } else if(next.kind == MK61_APP_KIND_LANGUAGE_INPUT && next.phase == 0) {
        mk61_app_flow_call(&step, target(MK61_APP_KIND_LANGUAGE_VM, 2), 1);
      } else if(next.kind == MK61_APP_KIND_LANGUAGE_VM && next.phase == 2) {
        context.value += 15;
        mk61_app_flow_return(&step, 15, MK61_FLOW_OK);
      } else if(next.kind == MK61_APP_KIND_LANGUAGE_INPUT) {
        assert(step.result == 15 && step.status == MK61_FLOW_OK);
        ++context.resumes;
        mk61_app_flow_return(&step, context.value, MK61_FLOW_OK);
      } else {
        assert(next.kind == MK61_APP_KIND_LANGUAGE_VM && next.phase == 1);
        assert(step.result == 57 && step.status == MK61_FLOW_OK);
        ++context.resumes;
        mk61_app_flow_exit(&step, 57, MK61_FLOW_OK);
      }
      break;
  }
  backend.active = false;
  return status;
}
int main() {
  uint32_t result = 0;
  Context context;
  Backend backend;
  assert(run(target(MK61_APP_KIND_TINYBASIC, 0), &context, sizeof(context), result,
             actor, &backend) == MK61_FLOW_OK);
  assert(result == 57 && context.value == 57 && context.resumes == 2 && backend.calls == 6);
  assert((backend.trace == std::vector<unsigned>{200,1000,1100,1002,1101,1001}));
  for(unsigned mode = 1; mode <= 8; ++mode) {
    context = {}; backend = {}; backend.mode = mode;
    const Status status = run(target(MK61_APP_KIND_TINYBASIC, 0), &context,
                              sizeof(context), result, actor, &backend);
    if(mode == 1) assert(status == MK61_FLOW_OK && result == 99 && context.resumes == 1);
    else if(mode == 2) assert(status == MK61_FLOW_BUSY && context.resumes == 5);
    else if(mode == 8) assert(status == MK61_FLOW_IO_ERROR && result == 7);
    else assert(status == MK61_FLOW_CORRUPT);
    assert(!backend.active);
  }
  assert(run(target(255, 0), &context, sizeof(context), result, actor, &backend) == MK61_FLOW_INVALID_MODULE);
  assert(run(target(2, 0), nullptr, 5, result, actor, &backend) == MK61_FLOW_INVALID_MODULE);
  assert(run(target(2, 0), &context, sizeof(context), result, nullptr) == MK61_FLOW_INVALID_MODULE);
  puts("APP flow: tail, nested calls, resumptions, errors and immutable context PASS");
}
