#include "language_vm_flow.hpp"
#include "loadable_app_api.h"
#include "loadable_module_abi.hpp"

namespace language_vm {
namespace {
uint32_t run_status(Language language, loadable_module::Command command, Error error) {
  using C = loadable_module::Command;
  if (language == Language::BASIC) {
    if (command == C::TINYBASIC_RUN_ID_STATUS)
      return error == Error::NONE ? 1 : error == Error::STOPPED ? 2 : 4;
    if (command == C::TINYBASIC_RUN_ID || command == C::TINYBASIC_RUN_NAME)
      return error == Error::NONE || error == Error::STOPPED;
    return error == Error::NONE;
  }
  if (command == C::FOCAL_RUN_INDEX || command == C::FOCAL_RUN_ID ||
      command == C::FOCAL_RUN_NAME)
    return error == Error::NONE ? 0 : error == Error::STOPPED ? 1 : 3;
  return error == Error::NONE;
}
void completed(mk61_app_flow* flow, const FlowContext& c) {
  const auto result = run_status(c.program.state->language,
      (loadable_module::Command)c.original_command, c.program.execution->result.error);
  mk61_app_flow_return(flow, result, c.failure_status);
}
FlowContext* context(mk61_app_flow* flow) {
  if(!mk61_app_flow_compatible(flow) || flow->context_size != sizeof(FlowContext))
    return nullptr;
  auto* c = (FlowContext*)flow->context;
  return c->magic == FLOW_CONTEXT_MAGIC && execution_compatible(&c->program) ? c : nullptr;
}
mk61_app_flow_target target(uint8_t kind, uint32_t phase) {
  return mk61_app_flow_to(kind, MK61_APP_FLOW_SYSTEM_FILE, phase);
}
void returned(mk61_app_flow* flow, uint32_t result = 1,
              uint32_t status = MK61_FLOW_OK) {
  mk61_app_flow_return(flow, result, status);
}
bool prepare_input(FlowContext& c) {
  const auto& r = *c.program.execution;
  auto& s = *c.program.state;
  if(s.prompt_offset > r.image_size || s.prompt_length > r.image_size - s.prompt_offset ||
     s.control.sp >= INPUT_STACK_CAPACITY) return false;
  c.input = {};
  c.input.size = sizeof(c.input); c.input.version = REQUEST_VERSION;
  c.input.prompt = (const char*)r.image + s.prompt_offset;
  c.input.prompt_length = s.prompt_length;
  c.input.image = input_image_storage(s);
  c.input.capacity = INPUT_IMAGE_CAPACITY; c.input.language = s.language;
  return true;
}
}

uint32_t flow_vm(mk61_app_flow* flow, FlowExecute execute) {
  auto* c = context(flow);
  if(!c || !execute) return 0;
  auto& p = c->program;
  auto& r = *p.execution;
  auto& s = *p.state;
  switch(flow->current.phase) {
    case FLOW_EVALUATE_EXPRESSION:
      returned(flow, execute(&c->expression_request));
      return 1;
    case FLOW_AFTER_INPUT:
      if(flow->status != MK61_FLOW_OK || flow->result != 1) {
        c->failure_status = flow->status != MK61_FLOW_OK ? flow->status : (uint32_t)MK61_FLOW_CORRUPT;
        p.action = OverlayAction::ABORT;
      } else p.action = s.cancelled ? OverlayAction::ABORT : OverlayAction::RESUME;
      [[fallthrough]];
    case FLOW_RUN_PROGRAM:
      if(!execute(&p)) {
        returned(flow, 0, MK61_FLOW_CORRUPT); return 1;
      }
      if(r.result.error == Error::YIELDED) {
        if(!prepare_input(*c)) {
          c->failure_status = MK61_FLOW_CORRUPT;
          p.action = OverlayAction::ABORT;
          (void)execute(&p);
        } else {
          mk61_app_flow_call(flow, target(MK61_APP_KIND_LANGUAGE_INPUT, FLOW_EDIT_INPUT),
                              FLOW_AFTER_INPUT);
          return 1;
        }
      }
      // A successful M61 BASIC part needs no cold finish UI. Retain the hot
      // executor for the next cached part; errors and interactive runs finish normally.
      if(r.mode == 1 && s.language == Language::BASIC && r.result.error == Error::NONE &&
         !s.cancelled && s.failure == Error::NONE) completed(flow, *c);
      else mk61_app_flow_next(flow, target(MK61_APP_KIND_LANGUAGE_INPUT, FLOW_FINISH));
      return 1;
    default: return 0;
  }
}

uint32_t flow_input(mk61_app_flow* flow, FlowExecute validate,
                    FlowInput input, FlowExecute finish) {
  auto* c = context(flow);
  if(!c || !validate || !input || !finish) return 0;
  auto& s = *c->program.state;
  switch(flow->current.phase) {
    case FLOW_VALIDATE_PROGRAM:
      if(!validate(&c->program)) { returned(flow, 0, MK61_FLOW_CORRUPT); return 1; }
      if(c->program.execution->result.error != Error::NONE) completed(flow, *c);
      else mk61_app_flow_next(flow, target(MK61_APP_KIND_LANGUAGE_VM, FLOW_RUN_PROGRAM));
      return 1;
    case FLOW_FINISH:
      if(!finish(&c->program)) { returned(flow, 0, MK61_FLOW_CORRUPT); return 1; }
      completed(flow, *c);
      return 1;
    case FLOW_AFTER_EXPRESSION:
      if(flow->status != MK61_FLOW_OK || flow->result != 1) {
        returned(flow, 0, flow->status != MK61_FLOW_OK ? flow->status : (uint32_t)MK61_FLOW_CORRUPT);
        return 1;
      }
      if(s.cancelled || c->expression.result.error == Error::NONE) {
        returned(flow); return 1;
      }
      c->input.invalid = true;
      [[fallthrough]];
    case FLOW_EDIT_INPUT:
      if(!input(&c->input)) { returned(flow, 0, MK61_FLOW_CORRUPT); return 1; }
      if(c->input.result == InputResult::CANCELLED) {
        s.cancelled = true;
        s.normal_stop = s.language == Language::BASIC && c->program.execution->mode == 0;
        returned(flow); return 1;
      }
      if(c->input.result == InputResult::VALUE && s.language == Language::FOCAL) {
        s.input_value = c->input.value; returned(flow); return 1;
      }
      if(c->input.result != InputResult::EXPRESSION || s.language != Language::BASIC ||
         c->input.image_size < HEADER_SIZE || c->input.image_size > INPUT_IMAGE_CAPACITY) {
        returned(flow, 0, MK61_FLOW_CORRUPT); return 1;
      }
      c->expression = *c->program.execution;
      c->expression.image = c->input.image; c->expression.image_size = c->input.image_size;
      c->expression_request = {sizeof(OverlayRequest), REQUEST_VERSION, &c->expression,
                               &s, &c->expression_validated, OverlayAction::EXPRESSION, {0,0,0}};
      if(!validate(&c->expression_request) || c->expression.result.error != Error::NONE) {
        returned(flow, 0, MK61_FLOW_CORRUPT); return 1;
      }
      mk61_app_flow_call(flow, target(MK61_APP_KIND_LANGUAGE_VM, FLOW_EVALUATE_EXPRESSION),
                          FLOW_AFTER_EXPRESSION);
      return 1;
    default: return 0;
  }
}
}
