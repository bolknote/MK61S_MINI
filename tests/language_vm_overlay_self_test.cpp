#include "language_vm_resident.hpp"
#include "shared_memory.hpp"
#include "workspace_swap.hpp"
#include "display_buffer_loan.hpp"
#include <assert.h>
#include <stdio.h>
#include <string.h>
#include <vector>
#include <string>

using namespace language_vm;
using namespace loadable_module;
namespace {
const char* source;
bool legacy, input_legacy, input_missing, cancel;
bool vm_legacy, corrupt_input_stack;
bool expect_large;
bool fail_emit;
bool edit_after_failure;
unsigned edits;
shared_memory::Lease* usb_session;
bool drop_usb_on_input;
bool usb_live() { return usb_session && usb_session->ok(); }
void check_usb() {
  if(!usb_live()) return;
  assert(shared_memory::active_owner(shared_memory::Arena::OVERLAY) ==
         shared_memory::Owner::USB_SCREEN);
  for(size_t i=0;i<usb_session->size();++i) assert(usb_session->data()[i]==0xB7);
}
#if MK61_SCREEN_BUFFER_LOAN
constexpr size_t SCREEN_CAPACITY = MK61_ENABLE_USB_SCREEN ? 1344 : 192;
uint8_t screen_storage[SCREEN_CAPACITY+32];
bool screen_unavailable, loan_live;
unsigned screen_loans;
#endif
uint8_t mode = 1;
std::vector<const char*> entries;
unsigned position, swaps, starts, resumes, expressions, retries, validations, finishes;
Kind cached = (Kind)0;
ExecutionState* suspended;
uint16_t inode = 42;
bool event(void*, Event, const char*, uint16_t, double&) { return true; }
}
#if MK61_SCREEN_BUFFER_LOAN
bool DisplayBufferLoan::acquire(usize required) {
  assert(!ok());
  if(screen_unavailable || loan_live || !required || required>SCREEN_CAPACITY) return false;
  memory_=screen_storage+16; display_=nullptr;
  loan_live=true; ++screen_loans; return true;
}
void DisplayBufferLoan::reset() {
  if(memory_) { assert(loan_live); loan_live=false; }
  display_=nullptr; memory_=nullptr;
}
DisplayBufferLoan::~DisplayBufferLoan() { reset(); }
#endif
namespace loadable_module {
RuntimeStatus evict_cached() { cached = (Kind)0; return RuntimeStatus::OK; }
}
namespace language_vm_test {
RuntimeStatus frontend(Kind kind, Command command, uint32_t a, uint32_t b,
                       Request* request, uint32_t& result) {
  check_usb();
  if (command == Command::LANGUAGE_COMPILER_INFO) {
    result = legacy ? 0 : COMPILER_MAGIC; return RuntimeStatus::OK;
  }
  if(command==Command::TINYBASIC_EDIT_ID) {
    assert(kind==Kind::TINYBASIC && a==inode && b==((10U<<16)|7U));
    assert(shared_memory::snapshot(shared_memory::Arena::APP).high_water==0);
    ++edits; result=1; return RuntimeStatus::OK;
  }
  assert(command == Command::LANGUAGE_COMPILER_EMIT || a == inode);
  shared_memory::Lease workspace;
  const auto owner = kind == Kind::TINYBASIC ? shared_memory::Owner::TINYBASIC
                                            : shared_memory::Owner::FOCAL;
  assert(shared_memory::workspace_partitioned());
  assert(workspace_swap::acquire(owner, COMPILER_WORKSPACE_SIZE, workspace_swap::AcquireMode::REQUIRED,
                                 workspace));
  if(command != Command::LANGUAGE_COMPILER_EMIT)
    assert(shared_memory::active_owner(shared_memory::Arena::OVERLAY) ==
           (usb_live() ? shared_memory::Owner::USB_SCREEN : shared_memory::Owner::NONE));
  else {
    const auto lower = shared_memory::snapshot(shared_memory::Arena::OVERLAY);
    assert(lower.high_water <= MAX_IMAGE); // Image only, never a 3504-byte backup.
  }
  if (command != Command::LANGUAGE_COMPILER_EMIT)
    memset(workspace.data(), 0xA5, workspace.size());
  if (command == Command::LANGUAGE_COMPILER_EMIT)
    assert(request->output && request->capacity == request->compiled.size);
  else assert(!request->output && request->capacity == MAX_IMAGE);
#if MK61_SCREEN_BUFFER_LOAN
  for(unsigned i=0;i<16;++i) assert(screen_storage[i]==0xDD &&
                                   screen_storage[SCREEN_CAPACITY+16+i]==0xDD);
  if(command == Command::LANGUAGE_COMPILER_EMIT && loan_live) {
    assert(request->output==screen_storage+16 && request->capacity<=SCREEN_CAPACITY);
    assert(shared_memory::active_owner(shared_memory::Arena::OVERLAY)==shared_memory::Owner::NONE);
  }
#endif
  if (command == Command::LANGUAGE_COMPILER_EMIT && fail_emit) return RuntimeStatus::IO_ERROR;
  const Language language = kind == Kind::TINYBASIC ? Language::BASIC : Language::FOCAL;
  request->compiled = compile(language, source, (uint16_t)strlen(source),
                               request->output, (uint16_t)request->capacity);
  if (request->compiled.error != Error::NONE)
    fprintf(stderr, "compile error %s at %u: %s\n", error_name(request->compiled.error),
            request->compiled.source_offset, source);
  assert(request->compiled.error == Error::NONE);
  request->run_requested = 1; request->source_id = inode;
  request->language = (uint8_t)language; request->mode = mode;
  result = 1; return RuntimeStatus::OK;
}
RuntimeStatus overlay(Kind kind, Command command, void* payload, uint32_t& result) {
  check_usb();
#if MK61_SCREEN_BUFFER_LOAN
  assert(!loan_live); // Image must be copied before VM/UI/USB can take over.
  memset(screen_storage+16,0xCD,SCREEN_CAPACITY);
#endif
  if (kind != cached) { ++swaps; cached = kind; }
  if (input_missing && kind == Kind::LANGUAGE_INPUT) return RuntimeStatus::INVALID_MODULE;
  if (command == Command::LANGUAGE_VM_INFO) {
    result = kind == Kind::LANGUAGE_VM ? vm_legacy ? 0x34564D4CUL : OVERLAY_MAGIC
                                      : input_legacy ? 0x34494D4CUL : INPUT_MAGIC;
    return RuntimeStatus::OK;
  }
  result = 1;
  if (command == Command::LANGUAGE_VM_VALIDATE) {
    assert(kind == Kind::LANGUAGE_INPUT); ++validations;
    result = validate_execution((OverlayRequest*)payload);
    return RuntimeStatus::OK;
  }
  if (command == Command::LANGUAGE_VM_FINISH) {
    assert(kind == Kind::LANGUAGE_INPUT); ++finishes;
    auto& p = *(OverlayRequest*)payload;
    if (p.state->cancelled)
      p.execution->result.error = p.state->normal_stop ? Error::NONE : Error::STOPPED;
    else if (p.state->failure != Error::NONE) p.execution->result.error = p.state->failure;
    if(edit_after_failure && p.execution->mode==0 && p.execution->result.error!=Error::NONE) {
      p.execution->edit_requested=1;
      edit_after_failure=false;
    }
    return RuntimeStatus::OK;
  }
  if (kind == Kind::LANGUAGE_INPUT) {
    auto& input = *(InputRequest*)payload;
    assert(command == Command::LANGUAGE_INPUT && input.capacity == INPUT_IMAGE_CAPACITY);
    assert(suspended && input.image == input_image_storage(*suspended));
    assert(suspended->control.sp < INPUT_STACK_CAPACITY);
    if(drop_usb_on_input) { usb_session->reset(); drop_usb_on_input=false; }
    const Continuation control = suspended->control;
    std::vector<uint8_t> prefix((uint8_t*)suspended->stack,
                               (uint8_t*)(suspended->stack+suspended->control.sp));
    if (input.invalid) ++retries;
    if (cancel) { input.result = InputResult::CANCELLED; return RuntimeStatus::OK; }
    assert(position < entries.size());
    const char* text = entries[position++];
    if (input.language == Language::FOCAL) {
      input.value = position * 10; input.result = InputResult::VALUE;
    } else {
      const auto compiled = compile_expression(Language::BASIC, text,
          (uint16_t)strlen(text), input.image, input.capacity);
      assert(compiled.error == Error::NONE);
      input.image_size = compiled.size; input.result = InputResult::EXPRESSION;
    }
    assert(!memcmp(&control, &suspended->control, sizeof(control)));
    assert(prefix.empty() || !memcmp(prefix.data(), suspended->stack, prefix.size()));
    return RuntimeStatus::OK;
  }
  auto& overlay = *(OverlayRequest*)payload;
  auto& execution = *overlay.execution;
  auto& state = *overlay.state;
  View view;
  assert(execution_compatible(&overlay) && validated_view(overlay, view));
  if (overlay.action == OverlayAction::ABORT) {
    execution.result.error = state.cancelled ? Error::STOPPED : Error::IO;
    return RuntimeStatus::OK;
  }
  if (overlay.action == OverlayAction::EXPRESSION) {
    ++expressions;
    const Bindings bindings = {execution.variables, execution.array, state.array_count,
                               state.stack, MAX_STACK};
    uint8_t saved_image[INPUT_IMAGE_CAPACITY];
    memcpy(saved_image, input_image_storage(state), sizeof(saved_image));
    execution.result = evaluate_input(view, state, bindings, {});
    assert(!memcmp(saved_image, input_image_storage(state), sizeof(saved_image)));
    return RuntimeStatus::OK;
  }
  const bool resume = overlay.action == OverlayAction::RESUME;
  if (resume) { ++resumes; state.stack[state.control.sp++] = state.input_value; }
  else {
    ++starts; assert(!state.control.sp && !state.control.loop_count);
    assert(!shared_memory::contains(shared_memory::Arena::WORKSPACE,
                                    execution.image, execution.image_size) == expect_large);
  }
  const Bindings bindings = {execution.variables, execution.array,
                              (uint16_t)execution.array_count, state.stack, MAX_STACK};
  Services services = {}; services.event = event; services.yield_input = true;
  execution.result = run(view, state.control, bindings, services, 10000, resume);
  execution.error_column=source_column(view,execution.result.pc);
  if (execution.result.error == Error::YIELDED) {
    suspended = &state;
    const uint8_t* p = view.bytes + execution.result.pc + 1;
    state.prompt_offset = execution.result.pc + 3;
    state.prompt_length = (uint16_t)(p[0] | ((uint16_t)p[1] << 8));
    if (corrupt_input_stack) state.control.sp = INPUT_STACK_CAPACITY;
  } else assert(execution.result.error==Error::NONE || edit_after_failure);
  return RuntimeStatus::OK;
}
}
int main() {
  static_assert(sizeof(ExecutionState) == 1520, "measurement needs updating");
  uint32_t result;
#if MK61_SCREEN_BUFFER_LOAN
  memset(screen_storage,0xDD,sizeof(screen_storage));
#endif
  source = "10 S=0\n20 FOR I=1 TO 3\n30 GOSUB 100\n40 NEXT I\n"
           "50 IF S<>60 GOTO 999\n60 END\n100 INPUT @(I)\n110 S=S+@(I);RETURN\n";
  entries = {"I*10", "1/0", "I*10", "I*10"};
  assert(invoke_resident(Language::BASIC, Command::TINYBASIC_RUN_ID, inode, 0, result)
         == RuntimeStatus::OK && result == 1);
  assert(starts == 1 && resumes == 3 && expressions == 4 && retries == 1 && swaps >= 8);
  assert(validations == 5 && finishes == 0); // one per immutable image, not per resume
  source = "10 IF @(1)<>10 GOTO 999\n20 IF @(3)<>30 GOTO 999\n";
  assert(invoke_resident(Language::BASIC, Command::TINYBASIC_RUN_INDEX, 0, 0, result)
         == RuntimeStatus::OK && result == 1);
  source = "1.10 D 2\n1.20 E\n2.10 F I=1,3; A X\n2.20 S A=X\n";
  entries = {"10", "20", "30"}; position = 0;
  assert(invoke_resident(Language::FOCAL, Command::FOCAL_RUN_ID, inode, 0, result)
         == RuntimeStatus::OK && result == 0);
  assert(resumes == 6);
  source = "1.10 B (A-30) 9.10,2.10,9.10\n2.10 E\n9.10 S A=1/0\n";
  assert(invoke_resident(Language::FOCAL, Command::FOCAL_RUN_INDEX, 0, 0, result)
         == RuntimeStatus::OK && result == 0);
  std::string large = "10 A=0\n";
  for (unsigned i = 0; i < 120; ++i) {
    char line[64]; snprintf(line, sizeof(line), "%u A=A+A+A+A+A+A+A\n", 20+i*10);
    large += line;
  }
  large += "2000 INPUT @(2)\n2010 IF @(2)<>2 GOTO 9999\n2020 END\n";
  entries = {"1+1"}; position = 0;
  source = large.c_str(); expect_large = true;
  assert(invoke_resident(Language::BASIC, Command::TINYBASIC_RUN_ID, inode, 0, result)
         == RuntimeStatus::OK && result == 1);
  expect_large = false;
  source = "10 INPUT @(2)\n20 IF @(2)<>16 GOTO 999\n";
  std::string deepest = "1";
  for (unsigned i=1; i<16; ++i) deepest = "1+("+deepest+")";
  entries = {deepest.c_str()}; position = 0;
  assert(invoke_resident(Language::BASIC, Command::TINYBASIC_RUN_ID, inode, 0, result)
         == RuntimeStatus::OK && result == 1);
  source = "10 IF @(2)<>16 GOTO 999\n";
  assert(invoke_resident(Language::BASIC, Command::TINYBASIC_RUN_ID, inode, 0, result)
         == RuntimeStatus::OK && result == 1);
  // RESUME may use the former INPUT-image slots again: a normal program
  // still has the full 96-value stack, not the input-only lower 64 slots.
  std::string wide = "1";
  for (unsigned i=0; i<INPUT_STACK_CAPACITY; ++i) wide = "1+("+wide+")";
  const std::string wide_source = "10 INPUT @(2)\n20 A="+wide+
      "\n30 IF A<>65 GOTO 999\n40 A=0\n";
  source = wide_source.c_str(); entries = {"2"}; position = 0;
  assert(invoke_resident(Language::BASIC, Command::TINYBASIC_RUN_ID, inode, 0, result)
         == RuntimeStatus::OK && result == 1);
  source = "10 INPUT A\n"; corrupt_input_stack = true;
  const unsigned before_bad_input = expressions;
  assert(invoke_resident(Language::BASIC, Command::TINYBASIC_RUN_ID, inode, 0, result)
         == RuntimeStatus::CORRUPT_MODULE && expressions == before_bad_input);
  corrupt_input_stack = false;
  source = "10 IF A<>0 GOTO 999\n";
  fail_emit = true;
  assert(invoke_resident(Language::BASIC, Command::TINYBASIC_RUN_ID, inode, 0, result)
         == RuntimeStatus::IO_ERROR);
  fail_emit = false;
  assert(invoke_resident(Language::BASIC, Command::TINYBASIC_RUN_ID, inode, 0, result)
         == RuntimeStatus::OK && result == 1);
  source = "10 INPUT A\n20 A=999\n";
  cancel = true;
  assert(invoke_resident(Language::BASIC, Command::TINYBASIC_RUN_ID_STATUS, inode, 1, result)
         == RuntimeStatus::OK && result == 2);
  mode = 0;
  assert(invoke_resident(Language::BASIC, Command::TINYBASIC_RUN_ID_STATUS, inode, 0, result)
         == RuntimeStatus::OK && result == 1);
  cancel = false; mode = 1; input_missing = true;
  assert(invoke_resident(Language::BASIC, Command::TINYBASIC_RUN_ID, inode, 0, result)
         == RuntimeStatus::INVALID_MODULE);
  input_missing = false; input_legacy = true;
  assert(invoke_resident(Language::BASIC, Command::TINYBASIC_RUN_ID, inode, 0, result)
         == RuntimeStatus::INCOMPATIBLE_FIRMWARE);
  input_legacy = false; legacy = true;
  assert(invoke_resident(Language::BASIC, Command::TINYBASIC_RUN_ID, inode, 0, result)
         == RuntimeStatus::INCOMPATIBLE_FIRMWARE);
  legacy = false; vm_legacy = true;
  assert(invoke_resident(Language::BASIC, Command::TINYBASIC_RUN_ID, inode, 0, result)
         == RuntimeStatus::INCOMPATIBLE_FIRMWARE);
#if MK61_SCREEN_BUFFER_LOAN
  vm_legacy=false; source="10 A=0\n";
  assert(screen_loans && !loan_live);
  const unsigned before_fallback=screen_loans;
  screen_unavailable=true;
  assert(invoke_resident(Language::BASIC, Command::TINYBASIC_RUN_ID, inode, 0, result)
         == RuntimeStatus::OK && result==1 && screen_loans==before_fallback);
  screen_unavailable=false;
  assert(!loan_live);
  for(unsigned i=0;i<16;++i) assert(screen_storage[i]==0xDD &&
                                   screen_storage[SCREEN_CAPACITY+16+i]==0xDD);
#endif
  vm_legacy=false;
#if MK61_ENABLE_USB_SCREEN
  {
    // The live USB session (including its immutable frame snapshot) must
    // survive both compiler passes and every hot/cold APP switch. Active USB
    // cannot lend its framebuffer, so even a tiny program needs real staging.
    shared_memory::Lease session(shared_memory::Arena::OVERLAY,
                                shared_memory::Owner::USB_SCREEN, 2793);
    assert(session.ok()); memset(session.data(),0xB7,session.size());
    usb_session=&session;
#if MK61_SCREEN_BUFFER_LOAN
    screen_unavailable=true;
#endif
    source="10 FOR I=1 TO 2\n20 INPUT @(I)\n30 NEXT I\n"
           "40 IF @(1)+@(2)<>30 GOTO 999\n50 END\n";
    entries={"10","20"}; position=0;
    assert(invoke_resident(Language::BASIC, Command::TINYBASIC_RUN_ID, inode, 0, result)
           == RuntimeStatus::OK && result==1);
    check_usb(); assert(shared_memory::validate_invariants());
    source="1.10 F I=1,2; A X\n1.20 B (X-20) 9.10,2.10,9.10\n2.10 E\n";
    entries={"10","20"}; position=0;
    assert(invoke_resident(Language::FOCAL, Command::FOCAL_RUN_ID, inode, 0, result)
           == RuntimeStatus::OK && result==0);
    check_usb();
    // Large image stays live during INPUT even when USB exits and releases
    // the earlier OVERLAY allocation. Neither pointer may move or overlap.
    source=large.c_str(); entries={"1+1"}; position=0; expect_large=true;
    assert(invoke_resident(Language::BASIC, Command::TINYBASIC_RUN_ID, inode, 0, result)
           == RuntimeStatus::OK && result==1);
    check_usb();
    entries={"1+1"}; position=0; drop_usb_on_input=true;
    assert(invoke_resident(Language::BASIC, Command::TINYBASIC_RUN_ID, inode, 0, result)
           == RuntimeStatus::OK && result==1 && !session.ok());
    expect_large=false;
    assert(shared_memory::validate_invariants());
    // Failures must return their staging allocation without releasing USB.
    assert(session.acquire(shared_memory::Arena::OVERLAY,
                           shared_memory::Owner::USB_SCREEN,2793));
    memset(session.data(),0xB7,session.size()); source="10 END\n"; fail_emit=true;
    assert(invoke_resident(Language::BASIC, Command::TINYBASIC_RUN_ID, inode, 0, result)
           == RuntimeStatus::IO_ERROR);
    fail_emit=false; check_usb(); usb_session=nullptr;
#if MK61_SCREEN_BUFFER_LOAN
    screen_unavailable=false;
#endif
  }
#endif
  source="10 A=1/0\n"; mode=0; edit_after_failure=true;
  uint32_t edit_run_result=1;
  assert(invoke_resident(Language::BASIC,Command::TINYBASIC_RUN_ID,inode,0,edit_run_result)
         ==RuntimeStatus::OK && edit_run_result==0);
  assert(edits==1 && !edit_after_failure);
  mode=1;
  assert(shared_memory::validate_invariants());
  assert(shared_memory::active_owner(shared_memory::Arena::WORKSPACE) == shared_memory::Owner::NONE);
  assert(shared_memory::active_owner(shared_memory::Arena::OVERLAY) == shared_memory::Owner::NONE);
  assert(!shared_memory::workspace_partitioned());
  assert(shared_memory::capacity(shared_memory::Arena::WORKSPACE) == 8192);
  {
    shared_memory::Lease transfer(shared_memory::Arena::OVERLAY,
        shared_memory::Owner::LOADABLE_MODULE, 64);
    shared_memory::Lease app(shared_memory::Arena::APP,
        shared_memory::Owner::LOADABLE_MODULE, 12288);
    assert(app.ok()); app.data()[0] = 91;
    auto* pointer = transfer.data(); pointer[0] = 42;
    assert(transfer.resize_to(4096) && transfer.data() == pointer && pointer[0] == 42);
    assert(!transfer.resize_to(65536) && transfer.size() == 4096);
    assert(!transfer.resize_to(22000) && app.data()[0] == 91);
    assert(transfer.shrink_to(64) && pointer[0] == 42);
    assert(shared_memory::validate_invariants());
  }
  puts("language_vm_overlay: loops/calls/array INPUT, retries, cancellation, failures PASS");
}
