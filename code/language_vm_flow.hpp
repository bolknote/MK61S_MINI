#ifndef MK61_LANGUAGE_VM_FLOW_HPP
#define MK61_LANGUAGE_VM_FLOW_HPP
#include "app_flow.h"
#include "language_vm_abi.hpp"

namespace language_vm {
// Resident-owned data only. Both APPs may disappear after any phase.
struct FlowContext {
  uint32_t magic;
  uint32_t original_command;
  OverlayRequest program;
  ValidatedImage program_validated;
  ExecuteRequest expression;
  ValidatedImage expression_validated;
  OverlayRequest expression_request;
  InputRequest input;
  uint32_t failure_status;
};
#if UINTPTR_MAX == UINT32_MAX
static_assert(sizeof(FlowContext) == 184 && offsetof(FlowContext, input) == 136,
              "VM cooperative context ARM layout changed");
#endif
// Request growth moved compiler-stage fields without changing its total
// union size. Reject older language APPs before they read those offsets.
static constexpr uint32_t FLOW_CONTEXT_MAGIC = 0x34564C46UL;
enum FlowPhase : uint32_t {
  FLOW_VALIDATE_PROGRAM = 0, FLOW_RUN_PROGRAM, FLOW_AFTER_INPUT,
  FLOW_EDIT_INPUT, FLOW_AFTER_EXPRESSION, FLOW_EVALUATE_EXPRESSION, FLOW_FINISH
};
using FlowExecute = uint32_t (*)(OverlayRequest*);
using FlowInput = uint32_t (*)(InputRequest*);
uint32_t flow_vm(mk61_app_flow*, FlowExecute);
uint32_t flow_input(mk61_app_flow*, FlowExecute validate, FlowInput, FlowExecute finish);
}
#endif
