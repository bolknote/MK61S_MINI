#ifndef MK61_LANGUAGE_VM_FLOW_HPP
#define MK61_LANGUAGE_VM_FLOW_HPP
#include "app_flow.h"
#include "language_vm_abi.hpp"
#include <new>

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
  union {
    InputRequest input;
    // Only before START: publication epoch for optional cache persistence.
    // FLOW_RUN clears input.size before INPUT begins, then binds InputRequest.
    uint32_t file_cache_revision;
    struct {
      uint32_t revision;
      mk61_app_flow_target next; // APP-selected continuation after publication.
    } publication;
  };
  uint32_t failure_status;
  // Resident-owned across INPUT/compiler/executor APP replacement. Call
  // arguments may occupy the whole program stack, so none of it is scratch.
  alignas(InputWorkspace) uint8_t input_storage[sizeof(InputWorkspace)];
};

inline void reset_flow_context(FlowContext& context) {
  // Start the union member's lifetime without clearing dead INPUT storage on
  // every RUN. The input compiler initializes exactly its published image.
  static_assert(std::is_trivially_copyable<FlowContext>::value,"data-only flow");
  ::new (static_cast<void*>(&context)) FlowContext;
  memset(&context,0,offsetof(FlowContext,input_storage));
}

#if UINTPTR_MAX == UINT32_MAX
static_assert(sizeof(FlowContext)==744 && offsetof(FlowContext,input)==184,"paged VM flow ABI");
#endif
// Compiler APPs call private resident Program passes synchronously. Reject a
// mismatched System set before either side can enter those passes.
static constexpr uint32_t FLOW_CONTEXT_MAGIC = 0x42564C47UL;
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
