#include "language_vm_abi.hpp"
#include <array>
#include <cassert>
#include <cstdio>
#include <cstring>
#include <string>
#include <vector>

using namespace language_vm;
namespace {
struct Snapshot {
  std::vector<uint64_t> events, results, values;
  std::string text;
  unsigned services = 0, inputs = 0;
  bool operator==(const Snapshot& other) const {
    return events == other.events && results == other.results &&
           values == other.values && text == other.text &&
           services == other.services && inputs == other.inputs;
  }
};
struct Host { Snapshot* output; unsigned cancel_after; };
bool service(void* raw) {
  auto& h = *static_cast<Host*>(raw);
  return ++h.output->services <= h.cancel_after;
}
bool event(void* raw, Event kind, const char* text, uint16_t length, double& value) {
  auto& out = *static_cast<Host*>(raw)->output;
  out.events.push_back(static_cast<uint8_t>(kind));
  out.events.push_back(length);
  out.events.push_back(mk_math::binary64_bits(value));
  if(text && length) out.text.append(text, length);
  return true;
}
void result(Snapshot& out, const RunResult& r, const View& view) {
  out.results.insert(out.results.end(), {static_cast<uint64_t>(r.error), r.pc,
      r.line, r.steps, source_column(view, r.pc)});
}
Snapshot execute(Language language, const char* source, uint8_t poison,
                 unsigned cancel_after) {
  uint8_t image[MAX_MODULE];
  const auto compiled = compile(language, source, static_cast<uint16_t>(strlen(source)),
                                image, sizeof(image));
  if(compiled.error != Error::NONE) {
    std::fprintf(stderr, "reset fixture compile error %u line %u: %s\n",
                 unsigned(compiled.error), compiled.line, source);
    assert(false);
  }
  Value variables[26] = {}, array[385] = {};
  ExecutionState state;
  memset(static_cast<void*>(&state), poison, sizeof(state));
  state.language = language; // Cold validation may inspect only this field first.
  ExecuteRequest request = {};
  request.size = sizeof(request); request.version = REQUEST_VERSION;
  request.image = image; request.image_size = compiled.size;
  request.variables = variables; request.array = array; request.array_count = 385;
  request.mode = 1;
  ValidatedImage certificate = {};
  OverlayRequest payload = {sizeof(payload), REQUEST_VERSION, &request, &state,
                             &certificate, OverlayAction::START, {0, 0, 0}};
  assert(validate_execution(&payload) == 1 && request.result.error == Error::NONE);
  assert(state.language == language && !state.control.pc && !state.control.data_pc &&
         !state.control.data_index && !state.control.sp && !state.control.call_count &&
         !state.control.loop_count && !state.steps && !state.prompt_offset &&
         !state.prompt_length && !state.row && !state.width && !state.precision &&
         !state.output_cursor && !state.cancelled && !state.normal_stop &&
         state.failure == Error::NONE && state.input_value.representation() == 0);
  for(char c : state.output) assert(c == 0);
  // Qualify the fixture: stale slots must still be poisoned when run() starts,
  // otherwise an accidental full clear would turn both runs into the same test.
  const auto* raw = reinterpret_cast<const uint8_t*>(&state.control);
  for(size_t i = 0; i < offsetof(Continuation, pc); ++i) assert(raw[i] == poison);
  raw = reinterpret_cast<const uint8_t*>(state.stack);
  for(size_t i = 0; i < sizeof(state.stack); ++i) assert(raw[i] == poison);
  View view; assert(validated_view(payload, view));
  const Bindings bindings = {variables, array, state.array_count, state.stack, MAX_STACK};
  Snapshot out;
  Host host = {&out, cancel_after};
  Services services = {};
  services.context = &host; services.service = service;
  services.event = event; services.yield_input = true;
  bool resume = false;
  for(unsigned phase = 0; ; ++phase) {
    assert(phase < 8);
    const auto r = run(view, state.control, bindings, services, 1000, resume);
    result(out, r, view);
    if(r.error != Error::YIELDED) break;
    ++out.inputs;
    if(language == Language::BASIC) {
      const char* expression = "2+3*4";
      uint8_t* temporary = input_image_storage(state);
      const auto expr = compile_expression(language, expression,
          static_cast<uint16_t>(strlen(expression)), temporary, INPUT_IMAGE_CAPACITY);
      assert(expr.error == Error::NONE);
      View input; assert(inspect(temporary, expr.size, input) == Error::NONE);
      const auto evaluated = evaluate_input(input, state, bindings, services);
      result(out, evaluated, input);
      if(evaluated.error != Error::NONE) {
        // ESC may be observed while the INPUT expression borrows the stack.
        assert(evaluated.error == Error::STOPPED);
        break;
      }
    } else state.input_value = 14;
    assert(state.control.sp < MAX_STACK);
    state.stack[state.control.sp++] = state.input_value;
    resume = true;
  }
  for(const auto& v : variables) out.values.push_back(v.representation());
  for(const auto& v : array) out.values.push_back(v.representation());
  out.results.insert(out.results.end(), {state.control.pc, state.control.data_pc,
      state.control.data_index, state.control.sp, state.control.call_count,
      state.control.loop_count});
  return out;
}
}
int main() {
  struct Case { Language language; const char* source; };
  const Case corpus[] = {
    {Language::BASIC, "10 FOR I=1 TO 3\n20 GOSUB 100\n30 NEXT I\n40 END\n100 A=A+I\n110 RETURN\n"},
    {Language::BASIC, "10 READ A,B\n20 RESTORE\n30 READ C\n40 PRINT A;B;C\n50 DATA -2,3.5\n60 END\n"},
    {Language::BASIC, "10 FOR I=1 TO 2\n20 GOSUB 100\n30 NEXT I\n40 END\n100 INPUT @(I)\n110 A=A+@(I)\n120 RETURN\n"},
    {Language::BASIC, "10 A=1/0\n"},
    {Language::BASIC, "10 RETURN\n"},
    {Language::BASIC, "10 FOR I=1 TO 3\n20 NEXT J\n"},
    {Language::BASIC, "10 GOTO 10\n"},
    {Language::FOCAL, "1.10 FOR I=1,1,3; SET A=A+I\n1.20 PRINT A\n1.30 EXIT\n"},
    {Language::FOCAL, "1.10 DO 2\n1.20 PRINT A\n1.30 EXIT\n2.10 SET A=A+2\n"},
    {Language::FOCAL, "1.10 ASK A\n1.20 SET B=A+1\n1.30 EXIT\n"},
    {Language::FOCAL, "1.10 DO 2,10; EXIT\n2.10 SET A=CALL(3,2)+ARG(1); RETURN\n3.10 RETURN ARG(1)*2\n"},
    {Language::FOCAL, "1.10 S A=1/0\n"},
    {Language::FOCAL, "1.10 R\n"}
  };
  unsigned comparisons = 0;
  for(const auto& c : corpus) {
    for(unsigned cancel_after : {0U, 1U, 10000U}) {
      const auto clean = execute(c.language, c.source, 0, cancel_after);
      for(uint8_t poison : {uint8_t(1), uint8_t(0x5a), uint8_t(0xa5), uint8_t(0xff)}) {
        const auto dirty = execute(c.language, c.source, poison, cancel_after);
        if(!(dirty == clean)) {
          std::fprintf(stderr, "reset differential mismatch language=%u poison=%u cancel=%u: %s\n",
                       unsigned(c.language), unsigned(poison), cancel_after, c.source);
          assert(false);
        }
        ++comparisons;
      }
    }
  }
  std::printf("language_vm reset: %u poisoned/zero comparisons, BASIC/FOCAL control, DATA, INPUT/resume, errors/limits/ESC, exact values/events/diagnostics PASS\n", comparisons);
}
