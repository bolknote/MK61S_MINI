#ifndef MK61_LANGUAGE_COMPILER_FLOW_HPP
#define MK61_LANGUAGE_COMPILER_FLOW_HPP
#include "language_vm_flow.hpp"
#include "app_flow_transfer_abi.hpp"
#include "loadable_module_abi.hpp"
namespace language_vm {
struct PersistentValues {
  uint32_t magic;
  uint16_t selected[2];
  double variables[2][26];
  double array[385];
};
static_assert(sizeof(PersistentValues) == VALUES_SIZE, "retained values layout changed");
struct CompilerContext {
  FlowContext vm; // Existing executor protocol is the prefix.
  Request compiler;
  ExecuteRequest execution;
  app_flow::ImageTransfer transfer;
  PersistentValues* values;
  uint32_t command, argument0, argument1;
  Language language;
  bool prepared;
  uint8_t reserved[2];
};
#if UINTPTR_MAX == UINT32_MAX
static_assert(sizeof(CompilerContext) == 312 && offsetof(CompilerContext, compiler) == 184 &&
              offsetof(CompilerContext, execution) == 216 && offsetof(CompilerContext, transfer) == 264 &&
              offsetof(CompilerContext, values) == 292,
              "compiler flow wire layout changed");
#endif
enum CompilerPhase : uint32_t { FLOW_COMPILE_SOURCE = 0x100, FLOW_EMIT_SOURCE };
using CompileFrontend = uint32_t (*)(loadable_module::Command, uint32_t, uint32_t,
                                     Request*, uint32_t& result);
uint32_t flow_compile(mk61_app_flow*, CompileFrontend);
bool prepare_compiled_flow(mk61_app_flow*);
}
#endif
