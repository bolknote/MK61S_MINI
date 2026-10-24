#ifndef MK61_LANGUAGE_VM_CACHED_EXECUTION_HPP
#define MK61_LANGUAGE_VM_CACHED_EXECUTION_HPP
#include "language_compiler_flow.hpp"

namespace language_vm {
// Bind an already acquired workspace to an immutable, certified cache image.
// The caller first fills execution (including raw/paged storage and banks).
// No compiler union member is live after this point. Keep the same resident
// certificate checks as the ordinary compiler handoff and a fresh I/O state.
inline bool prepare_cached_execution(CompilerContext& context,
                                     const ValidatedImage& certificate,
                                     ExecutionState& state,
                                     loadable_module::Command command) {
  static_assert(sizeof(ExecutionState)<COMPILER_WORKSPACE_SIZE,
                "cached execution must fit inside the protected prefix");
  context.vm={};context.vm.magic=FLOW_CONTEXT_MAGIC;
  context.vm.original_command=(uint32_t)command;
  context.vm.program_validated=certificate;
  context.vm.program={sizeof(OverlayRequest),REQUEST_VERSION,&context.execution,
      &state,&context.vm.program_validated,OverlayAction::START,{0,0,0}};
  state.language=context.language;
  View view;
  if(!validated_view(context.vm.program,view))return false;
  initialize_validated_state(context.execution,certificate,state);
  context.prepared=true;
  return true;
}
}
#endif
