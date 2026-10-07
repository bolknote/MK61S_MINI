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
  c.vm.magic = FLOW_CONTEXT_MAGIC; c.values = &values;
  c.language = language; c.argument0 = 42;
  c.command = (uint32_t)(language == Language::BASIC ? C::TINYBASIC_RUN_ID : C::FOCAL_RUN_ID);
  c.vm.original_command = c.command;
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
  values.selected[0] = values.selected[1] = 0xFFFF;
  auto c = make(); auto f = step(c);
  f.context_size--;
  assert(!flow_compile(&f, frontend) && !calls);
  assert(!prepare_compiled_flow(nullptr));
  f = step(c); c.language = (Language)99;
  assert(!flow_compile(&f, frontend));
  c = make(); c.command = (uint32_t)C::TINYBASIC_RUN_INDEX; c.argument0 = 0;
  f = step(c);
  assert(flow_compile(&f, frontend) && f.action == MK61_FLOW_EXIT && f.result == 0 && !calls);
  c = make(Language::FOCAL); c.command = (uint32_t)C::FOCAL_RUN_INDEX; c.argument0 = 0;
  f = step(c);
  assert(flow_compile(&f, frontend) && f.result == 4 && !calls);
  values.selected[0] = 42;
  c = make(); c.command = (uint32_t)C::TINYBASIC_RUN_INDEX; c.argument0 = 0;
  f = step(c);
  assert(flow_compile(&f, frontend) && f.action == MK61_FLOW_CALL && f.next.kind == MK61_APP_FLOW_HOST);
  assert(c.command == (uint32_t)C::TINYBASIC_RUN_ID && c.argument0 == 42);
  assert(f.resume_phase == FLOW_EMIT_SOURCE && c.transfer.prefix == sizeof(ExecutionState));
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
  c.transfer.image = image;
  f = step(c, FLOW_EMIT_SOURCE); bad_emit = true;
  assert(flow_compile(&f, frontend) && f.action == MK61_FLOW_EXIT && f.status == MK61_FLOW_CORRUPT);
  bad_emit = false; c = make(); f = step(c);
  assert(flow_compile(&f, frontend)); c.transfer.image = image;
  f = step(c, FLOW_EMIT_SOURCE);
  assert(flow_compile(&f, frontend) && f.action == MK61_FLOW_NEXT && f.next.kind == MK61_APP_FLOW_HOST);
  assert(f.next.phase == app_flow::COMMIT_IMAGE && !c.prepared);
  c.transfer.workspace = workspace; c.transfer.workspace_size = sizeof(workspace);
  assert(prepare_compiled_flow(&f) && c.prepared);
  assert(c.execution.image == image && c.execution.image_size == HEADER_SIZE);
  assert(c.execution.variables == values.variables[0] && c.execution.array == values.array);
  assert(c.vm.program.state->language == Language::BASIC && c.vm.program.execution == &c.execution);
  assert(!flow_compile(&f, frontend));
  c.vm.program.state->control.sp = 7;
  assert(prepare_compiled_flow(&f) && c.vm.program.state->control.sp == 7);
  puts("compiler APP flow: selection, clear, no-run, sizing/emit errors, reserve resume, tail commit and one-time state preparation PASS");
}
