#include "language_compiler_flow.hpp"
#include <assert.h>
#include <stdio.h>
#include <string.h>
#include <initializer_list>

using namespace language_vm;
using C = loadable_module::Command;
namespace {
PersistentValues values;
uint8_t image[MAX_IMAGE];
alignas(8) uint8_t workspace[sizeof(ExecutionState)];
unsigned calls;
uint32_t frontend_status;
bool no_run, clear_values, bad_emit;
uint16_t compiled_size = HEADER_SIZE;
uint32_t unexpected_execute(OverlayRequest*) {
  assert(false && "VM cannot read the compiler union member"); return 0;
}
uint32_t frontend(C command, uint32_t a, uint32_t, Request* r, uint32_t& result) {
  ++calls; result = 77;
  assert(r->size == sizeof(*r) && r->version == REQUEST_VERSION);
  if(frontend_status) return frontend_status;
  if(command == C::LANGUAGE_COMPILER_EMIT) {
    assert(r->output == image && r->capacity == compiled_size);
    if(bad_emit) ++r->compiled.size;
  } else {
    assert(a == 42 && !r->output && r->capacity == MAX_IMAGE);
    r->compiled = {}; r->compiled.size = compiled_size;
    r->source_id = 42; r->clear_requested = clear_values;
  }
  r->run_requested = !no_run; r->mode = 1;
  return MK61_FLOW_OK;
}
CompilerContext make(Language language = Language::BASIC) {
  CompilerContext c = {};
  c.compile.magic = FLOW_CONTEXT_MAGIC; c.compile.values = &values;
  c.language = language; c.compile.argument0 = 42;
  c.compile.command = (uint32_t)(language == Language::BASIC ? C::TINYBASIC_RUN_ID : C::FOCAL_RUN_ID);
  c.compile.original_command = c.compile.command;
  return c;
}
mk61_app_flow step(CompilerContext& c, uint32_t phase = FLOW_COMPILE_SOURCE) {
  mk61_app_flow f = {};
  f.size = sizeof(f); f.version = MK61_APP_FLOW_VERSION;
  f.context = &c; f.context_size = sizeof(c);
  f.current = mk61_app_flow_to(c.language == Language::BASIC ? 2 : 1, 0xFFFF, phase);
  return f;
}
}
int main() {
  static_assert(offsetof(CompilerContext, compile) == offsetof(CompilerContext, vm),
                "compiler and VM phases must reuse the same memory");
  values.selected[0] = values.selected[1] = 0xFFFF;
#if defined(MK61_BUILD_TINYBASIC_MODULE) || defined(MK61_BUILD_FOCAL_MODULE)
  #if defined(MK61_BUILD_TINYBASIC_MODULE)
  constexpr Language language = Language::BASIC, other = Language::FOCAL;
  #else
  constexpr Language language = Language::FOCAL, other = Language::BASIC;
  #endif
  constexpr bool basic = language == Language::BASIC;
  constexpr unsigned index = basic ? 0 : 1;
  auto c = make(other); auto f = step(c);
  assert(!flow_compile(&f, frontend) && !calls);
  c = make(language); f = step(c);
  assert(!flow_vm(&f, unexpected_execute));
  c.compile.command = (uint32_t)(basic ? C::TINYBASIC_RUN_INDEX : C::FOCAL_RUN_INDEX);
  c.compile.original_command = c.compile.command; c.compile.argument0 = 0;
  assert(flow_compile(&f, frontend) && f.action == MK61_FLOW_EXIT && !calls);
  assert(f.result == (basic ? 0U : 4U));
  values.selected[index] = 42;
  values.variables[0][0] = values.variables[1][0] = values.array[0] = 42;
  clear_values = true; f = step(c);
  assert(flow_compile(&f, frontend) && f.action == MK61_FLOW_CALL);
  assert(values.variables[index][0] == 0 && values.variables[1-index][0] == 42);
  assert(values.array[0] == (basic ? 0 : 42));
  assert(c.compile.command == (uint32_t)(basic ? C::TINYBASIC_RUN_ID : C::FOCAL_RUN_ID));
  c.compile.transfer.image = image; f = step(c, FLOW_EMIT_SOURCE);
  assert(flow_compile(&f, frontend) && f.action == MK61_FLOW_NEXT);
  c.compile.transfer.workspace = workspace; c.compile.transfer.workspace_size = sizeof(workspace);
  assert(prepare_compiled_flow(&f) && c.prepared);
  assert(c.source_id == 42 && c.clear_requested && c.vm.program.state->language == language);
  assert(c.execution.variables == values.variables[index]);
  assert(c.execution.array == (basic ? values.array : nullptr));
  assert(c.vm.original_command == (uint32_t)(basic ? C::TINYBASIC_RUN_INDEX : C::FOCAL_RUN_INDEX));
  assert(!flow_compile(&f, frontend));
  c = make(language); no_run = true; f = step(c);
  assert(flow_compile(&f, frontend) && f.action == MK61_FLOW_EXIT && f.result == 77);
  puts(basic ? "compiler BASIC specialization: wrong language, index, clear, tail handoff PASS"
             : "compiler FOCAL specialization: wrong language, index, clear, tail handoff PASS");
#else
  auto c = make(); auto f = step(c);
  assert(!flow_vm(&f, unexpected_execute));
  f.context_size--;
  assert(!flow_compile(&f, frontend) && !calls);
  assert(!prepare_compiled_flow(nullptr));
  f = step(c); c.language = (Language)99;
  assert(!flow_compile(&f, frontend));
  c = make(); c.compile.command = (uint32_t)C::TINYBASIC_RUN_INDEX; c.compile.argument0 = 0;
  f = step(c);
  assert(flow_compile(&f, frontend) && f.action == MK61_FLOW_EXIT && f.result == 0 && !calls);
  c = make(Language::FOCAL); c.compile.command = (uint32_t)C::FOCAL_RUN_INDEX; c.compile.argument0 = 0;
  f = step(c);
  assert(flow_compile(&f, frontend) && f.result == 4 && !calls);
  values.selected[0] = 42;
  c = make(); c.compile.command = (uint32_t)C::TINYBASIC_RUN_INDEX; c.compile.argument0 = 0;
  c.compile.original_command = c.compile.command;
  f = step(c);
  assert(flow_compile(&f, frontend) && f.action == MK61_FLOW_CALL && f.next.kind == MK61_APP_FLOW_HOST);
  assert(c.compile.command == (uint32_t)C::TINYBASIC_RUN_ID && c.compile.argument0 == 42);
  assert(f.resume_phase == FLOW_EMIT_SOURCE && c.compile.transfer.prefix == sizeof(ExecutionState));
  f = step(c, FLOW_EMIT_SOURCE); f.status = MK61_FLOW_BUSY;
  assert(flow_compile(&f, frontend) && f.action == MK61_FLOW_EXIT && f.status == MK61_FLOW_BUSY);

  c = make(); no_run = clear_values = true;
  values.variables[0][0] = values.variables[1][0] = values.array[0] = 42;
  f = step(c);
  assert(flow_compile(&f, frontend) && f.action == MK61_FLOW_EXIT && f.result == 77);
  assert(!values.variables[0][0] && !values.array[0] && values.variables[1][0] == 42);
  no_run = clear_values = false; frontend_status = MK61_FLOW_IO_ERROR;
  c = make(); f = step(c);
  assert(flow_compile(&f, frontend) && f.status == MK61_FLOW_IO_ERROR);
  frontend_status = 0;
  for(auto length : {uint16_t(HEADER_SIZE - 1), uint16_t(MAX_IMAGE + 1)}) {
    compiled_size = length; c = make(); f = step(c);
    assert(flow_compile(&f, frontend) && f.action == MK61_FLOW_EXIT && f.status == MK61_FLOW_CORRUPT);
  }
  compiled_size = HEADER_SIZE; c = make(); f = step(c);
  assert(flow_compile(&f, frontend) && f.action == MK61_FLOW_CALL);
  c.compile.transfer.image = image;
  f = step(c, FLOW_EMIT_SOURCE); bad_emit = true;
  assert(flow_compile(&f, frontend) && f.action == MK61_FLOW_EXIT && f.status == MK61_FLOW_CORRUPT);
  bad_emit = false; c = make(); f = step(c);
  assert(flow_compile(&f, frontend)); c.compile.transfer.image = image;
  f = step(c, FLOW_EMIT_SOURCE);
  assert(flow_compile(&f, frontend) && f.action == MK61_FLOW_NEXT && f.next.kind == MK61_APP_FLOW_HOST);
  assert(f.next.phase == app_flow::COMMIT_IMAGE && !c.prepared);
  c.compile.transfer.workspace = workspace; c.compile.transfer.workspace_size = sizeof(workspace);
  // Deliberately retain metadata that differs from the overwritten VM bytes.
  c.compile.original_command = (uint32_t)C::TINYBASIC_RUN_INDEX;
  c.compile.request.clear_requested = 1;
  assert(prepare_compiled_flow(&f) && c.prepared);
  assert(c.execution.image == image && c.execution.image_size == HEADER_SIZE);
  assert(c.execution.variables == values.variables[0] && c.execution.array == values.array);
  assert(c.source_id == 42 && c.clear_requested == 1);
  assert(c.vm.original_command == (uint32_t)C::TINYBASIC_RUN_INDEX);
  assert(c.vm.program.state->language == Language::BASIC && c.vm.program.execution == &c.execution);
  assert(!flow_compile(&f, frontend));
  c.vm.program.state->control.sp = 7;
  memset(&c.vm.expression, 0xCC, sizeof(c.vm.expression));
  memset(&c.vm.input, 0xDD, sizeof(c.vm.input));
  assert(prepare_compiled_flow(&f) && c.vm.program.state->control.sp == 7);
  assert(c.source_id == 42 && c.clear_requested == 1 && c.execution.image == image);
  puts("compiler APP flow: selection, clear, no-run, sizing/emit errors, reserve resume, tail commit and one-time state preparation PASS");
#endif
}
