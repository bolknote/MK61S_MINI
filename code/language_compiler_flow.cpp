#include "language_compiler_flow.hpp"
#include <string.h>

namespace language_vm {
uint32_t flow_compile(mk61_app_flow* flow, CompileFrontend frontend) {
  using C = loadable_module::Command;
  if(!mk61_app_flow_compatible(flow) || flow->context_size != sizeof(CompilerContext) ||
     !frontend) return 0;
  auto& c = *(CompilerContext*)flow->context;
#if defined(MK61_BUILD_TINYBASIC_MODULE) && defined(MK61_BUILD_FOCAL_MODULE)
  #error "A compiler APP must select exactly one language"
#elif defined(MK61_BUILD_TINYBASIC_MODULE)
  constexpr Language language = Language::BASIC;
#elif defined(MK61_BUILD_FOCAL_MODULE)
  constexpr Language language = Language::FOCAL;
#else
  // The shared host harness exercises both policies. Actual compiler APPs
  // use their existing build-kind macro, so all opposite-language branches
  // fold away without a second implementation or a changed bytecode format.
  const Language language = c.language;
#endif
  if(c.prepared || c.compile.magic != FLOW_CONTEXT_MAGIC || !c.compile.values ||
     c.language != language ||
     (language != Language::BASIC && language != Language::FOCAL)) return 0;
  auto& stage = c.compile;
  const bool basic = language == Language::BASIC;
  const unsigned index = basic ? 0 : 1;
  auto& request = stage.request;
  if(flow->current.phase == FLOW_COMPILE_SOURCE) {
    const C command = (C)stage.command;
    if(command == (basic ? C::TINYBASIC_RUN_INDEX : C::FOCAL_RUN_INDEX)) {
      if(stage.argument0 || stage.values->selected[index] == 0xFFFF) {
        mk61_app_flow_exit(flow, basic ? 0 : 4, MK61_FLOW_OK); return 1;
      }
      stage.argument0 = stage.values->selected[index];
      stage.command = (uint32_t)(basic ? C::TINYBASIC_RUN_ID : C::FOCAL_RUN_ID);
    }
    request = {};
    request.size = sizeof(request); request.version = REQUEST_VERSION;
    request.capacity = MAX_IMAGE; request.source_id = 0xFFFF;
    request.language = (uint8_t)language;
    uint32_t result = 0;
    const auto status = frontend((C)stage.command, stage.argument0, stage.argument1, &request, result);
    if(status != MK61_FLOW_OK) {
      mk61_app_flow_exit(flow, 0, status); return 1;
    }
    if(request.source_id != 0xFFFF) stage.values->selected[index] = request.source_id;
    if(request.clear_requested) {
      for(auto& value : stage.values->variables[index]) value=Value(0);
      if(basic) for(auto& value : stage.values->array) value=Value(0);
    }
    if(!request.run_requested) {
      mk61_app_flow_exit(flow, result, MK61_FLOW_OK); return 1;
    }
    if(request.compiled.error != Error::NONE || request.compiled.size < HEADER_SIZE ||
       request.compiled.size > MAX_IMAGE) {
      mk61_app_flow_exit(flow, 0, MK61_FLOW_CORRUPT); return 1;
    }
    stage.transfer.size = request.compiled.size;
    stage.transfer.prefix = sizeof(ExecutionState);
    stage.transfer.next = mk61_app_flow_to(MK61_APP_KIND_LANGUAGE_INPUT,
        MK61_APP_FLOW_SYSTEM_FILE, FLOW_VALIDATE_PROGRAM);
    mk61_app_flow_call(flow, mk61_app_flow_to(MK61_APP_FLOW_HOST,
        MK61_APP_FLOW_SYSTEM_FILE, app_flow::RESERVE_IMAGE), FLOW_EMIT_SOURCE);
    return 1;
  }
  if(flow->current.phase != FLOW_EMIT_SOURCE) return 0;
  if(flow->status != MK61_FLOW_OK) {
    mk61_app_flow_exit(flow, 0, flow->status); return 1;
  }
  if(!stage.transfer.image || stage.transfer.size != request.compiled.size) return 0;
  request.output = stage.transfer.image; request.capacity = stage.transfer.size;
  request.run_requested = 0;
  uint32_t result = 0;
  const auto emitted = frontend(C::LANGUAGE_COMPILER_EMIT, 0, 0, &request, result);
  if(emitted != MK61_FLOW_OK) {
    mk61_app_flow_exit(flow, 0, emitted); return 1;
  }
  if(!request.run_requested || request.compiled.error != Error::NONE ||
     request.compiled.size != stage.transfer.size) {
    mk61_app_flow_exit(flow, 0, MK61_FLOW_CORRUPT); return 1;
  }
  c.execution = {};
  c.execution.size = sizeof(c.execution); c.execution.version = REQUEST_VERSION;
  c.execution.variables = stage.values->variables[index];
  c.execution.array = basic ? stage.values->array : nullptr;
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
  const auto& stage = c.compile;
  if(stage.magic != FLOW_CONTEXT_MAGIC || !stage.transfer.image || !stage.transfer.workspace ||
     stage.transfer.workspace_size < sizeof(ExecutionState) ||
     stage.transfer.size != stage.request.compiled.size || stage.request.compiled.error != Error::NONE)
    return false;
  const uint32_t original = stage.original_command;
  c.source_id = stage.request.source_id; c.clear_requested = stage.request.clear_requested;
  c.execution.image = stage.transfer.image; c.execution.image_size = stage.transfer.size;
  auto* state = (ExecutionState*)stage.transfer.workspace;
  reset_execution_state(*state); state->language = c.language;
  // Start the VM member's lifetime only after consuming every compiler field.
  // The persistent execution request and final metadata are outside the union.
  c.vm = {}; c.vm.magic = FLOW_CONTEXT_MAGIC; c.vm.original_command = original;
  c.vm.program = {sizeof(OverlayRequest), REQUEST_VERSION, &c.execution,
      state, &c.vm.program_validated, OverlayAction::START, {0,0,0}};
  c.prepared = true;
  return true;
}
}
