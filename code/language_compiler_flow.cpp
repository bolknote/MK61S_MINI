#include "language_compiler_flow.hpp"
#include <string.h>

namespace language_vm {
uint32_t flow_compile(mk61_app_flow* flow, CompileFrontend frontend) {
  using C = loadable_module::Command;
  if(!mk61_app_flow_compatible(flow) || flow->context_size != sizeof(CompilerContext) ||
     !frontend) return 0;
  auto& c = *(CompilerContext*)flow->context;
  if(c.vm.magic != FLOW_CONTEXT_MAGIC || !c.values || c.prepared ||
     (c.language != Language::BASIC && c.language != Language::FOCAL)) return 0;
  const bool basic = c.language == Language::BASIC;
  const unsigned index = basic ? 0 : 1;
  auto& request = c.compiler;
  if(flow->current.phase == FLOW_COMPILE_SOURCE) {
    const C command = (C)c.command;
    if(command == (basic ? C::TINYBASIC_RUN_INDEX : C::FOCAL_RUN_INDEX)) {
      if(c.argument0 || c.values->selected[index] == 0xFFFF) {
        mk61_app_flow_exit(flow, basic ? 0 : 4, MK61_FLOW_OK); return 1;
      }
      c.argument0 = c.values->selected[index];
      c.command = (uint32_t)(basic ? C::TINYBASIC_RUN_ID : C::FOCAL_RUN_ID);
    }
    request = {};
    request.size = sizeof(request); request.version = REQUEST_VERSION;
    request.capacity = MAX_IMAGE; request.source_id = 0xFFFF;
    request.language = (uint8_t)c.language;
    uint32_t result = 0;
    const auto status = frontend((C)c.command, c.argument0, c.argument1, &request, result);
    if(status != MK61_FLOW_OK) {
      mk61_app_flow_exit(flow, 0, status); return 1;
    }
    if(request.source_id != 0xFFFF) c.values->selected[index] = request.source_id;
    if(request.clear_requested) {
      memset(c.values->variables[index], 0, sizeof(c.values->variables[index]));
      if(basic) memset(c.values->array, 0, sizeof(c.values->array));
    }
    if(!request.run_requested) {
      mk61_app_flow_exit(flow, result, MK61_FLOW_OK); return 1;
    }
    if(request.compiled.error != Error::NONE || request.compiled.size < HEADER_SIZE ||
       request.compiled.size > MAX_IMAGE) {
      mk61_app_flow_exit(flow, 0, MK61_FLOW_CORRUPT); return 1;
    }
    c.transfer.size = request.compiled.size;
    c.transfer.prefix = sizeof(ExecutionState);
    c.transfer.next = mk61_app_flow_to(MK61_APP_KIND_LANGUAGE_INPUT,
        MK61_APP_FLOW_SYSTEM_FILE, FLOW_VALIDATE_PROGRAM);
    mk61_app_flow_call(flow, mk61_app_flow_to(MK61_APP_FLOW_HOST,
        MK61_APP_FLOW_SYSTEM_FILE, app_flow::RESERVE_IMAGE), FLOW_EMIT_SOURCE);
    return 1;
  }
  if(flow->current.phase != FLOW_EMIT_SOURCE) return 0;
  if(flow->status != MK61_FLOW_OK) {
    mk61_app_flow_exit(flow, 0, flow->status); return 1;
  }
  if(!c.transfer.image || c.transfer.size != request.compiled.size) return 0;
  request.output = c.transfer.image; request.capacity = c.transfer.size;
  request.run_requested = 0;
  uint32_t result = 0;
  const auto emitted = frontend(C::LANGUAGE_COMPILER_EMIT, 0, 0, &request, result);
  if(emitted != MK61_FLOW_OK) {
    mk61_app_flow_exit(flow, 0, emitted); return 1;
  }
  if(!request.run_requested || request.compiled.error != Error::NONE ||
     request.compiled.size != c.transfer.size) {
    mk61_app_flow_exit(flow, 0, MK61_FLOW_CORRUPT); return 1;
  }
  c.execution = {};
  c.execution.size = sizeof(c.execution); c.execution.version = REQUEST_VERSION;
  c.execution.variables = c.values->variables[index];
  c.execution.array = basic ? c.values->array : nullptr;
  c.execution.array_count = basic ? 385 : 0; c.execution.mode = request.mode;
  // Tail handoff: never reload/initialize the compiler after its prefix is
  // reused for executable bytecode and continuation state.
  mk61_app_flow_next(flow, mk61_app_flow_to(MK61_APP_FLOW_HOST,
      MK61_APP_FLOW_SYSTEM_FILE, app_flow::COMMIT_IMAGE));
  return 1;
}

bool prepare_compiled_flow(mk61_app_flow* flow) {
  if(!mk61_app_flow_compatible(flow)) return false;
  if(flow->context_size == sizeof(FlowContext)) return true;
  if(flow->context_size != sizeof(CompilerContext)) return false;
  auto& c = *(CompilerContext*)flow->context;
  if(c.prepared) return true;
  if(c.vm.magic != FLOW_CONTEXT_MAGIC || !c.transfer.image || !c.transfer.workspace ||
     c.transfer.workspace_size < sizeof(ExecutionState) ||
     c.transfer.size != c.compiler.compiled.size || c.compiler.compiled.error != Error::NONE)
    return false;
  c.execution.image = c.transfer.image; c.execution.image_size = c.transfer.size;
  auto* state = (ExecutionState*)c.transfer.workspace;
  *state = {}; state->language = c.language;
  c.vm.program = {sizeof(OverlayRequest), REQUEST_VERSION, &c.execution,
      state, &c.vm.program_validated, OverlayAction::START, {0,0,0}};
  c.prepared = true;
  return true;
}
}
