#ifndef MK61_LANGUAGE_COMPILER_FLOW_HPP
#define MK61_LANGUAGE_COMPILER_FLOW_HPP
#include "language_vm_flow.hpp"
#include "app_flow_transfer_abi.hpp"
#include "loadable_module_abi.hpp"
namespace language_vm {
struct PersistentValues {
  uint32_t magic;
  uint16_t selected[2];
  Value variables[2][26];
  Value array[385];
};
static_assert(sizeof(PersistentValues) == VALUES_SIZE, "retained values layout changed");
struct CompilerStage {
  // Common initial sequence with FlowContext, including the original command
  // that must survive index normalization and the transition into RUN.
  uint32_t magic, original_command;
  Request request;
  app_flow::ImageTransfer transfer;
  PersistentValues* values;
  uint32_t command, argument0, argument1;
};
struct CompilerContext {
  union {
    CompilerStage compile; // Active through SOURCE/EMIT/HOST commit.
    FlowContext vm;        // Active after cold prepare, including INPUT.
  };
  ExecuteRequest execution;
  // These are the only compiler results needed after the union is reused.
  uint16_t source_id;
  Language language;
  uint8_t clear_requested;
  bool prepared;
  uint8_t reserved[3];
};
#if UINTPTR_MAX == UINT32_MAX
static_assert(sizeof(CompilerStage) == 84 && offsetof(CompilerStage, request) == 8 &&
              offsetof(CompilerStage, transfer) == 40 && offsetof(CompilerStage, values) == 68 &&
              sizeof(CompilerContext) == 240 && offsetof(CompilerContext, execution) == 184 &&
              offsetof(CompilerContext, source_id) == 232,
              "compiler flow wire layout changed");
#endif
enum CompilerPhase : uint32_t { FLOW_COMPILE_SOURCE = 0x100, FLOW_EMIT_SOURCE };
using CompileFrontend = uint32_t (*)(loadable_module::Command, uint32_t, uint32_t,
                                     Request*, uint32_t& result);
uint32_t flow_compile(mk61_app_flow*, CompileFrontend);
bool prepare_compiled_flow(mk61_app_flow*);
}
#endif
