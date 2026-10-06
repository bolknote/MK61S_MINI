#ifndef MK61_LANGUAGE_VM_ABI_HPP
#define MK61_LANGUAGE_VM_ABI_HPP
#include "language_bytecode.hpp"

namespace language_vm {
static constexpr uint32_t REQUEST_VERSION = 1;
static constexpr uint32_t COMPILER_MAGIC = 0x354D5643UL;
static constexpr uint16_t VALUES_SIZE = 3504;
static constexpr uint16_t COMPILER_WORKSPACE_SIZE = 8192 - VALUES_SIZE;
// Resident-owned, synchronous request. Output survives compiler eviction;
// none of the pointers may point into the native compiler's APP allocation.
struct Request {
  uint32_t size, version;
  uint8_t* output;
  uint32_t capacity;
  CompileResult compiled;
  uint16_t source_id;
  uint8_t language, mode, run_requested, clear_requested;
};
struct ExecuteRequest {
  uint32_t size, version;
  const uint8_t* image;
  uint32_t image_size;
  double* variables;
  double* array;
  uint32_t array_count;
  uint8_t mode, pause_final;
  uint16_t reserved;
  RunResult result;
};
static constexpr uint32_t OVERLAY_MAGIC = 0x36564D4CUL;
static constexpr uint32_t INPUT_MAGIC = 0x36494D4CUL;
static constexpr uint32_t VALIDATED_MAGIC = 0x3649424CUL;
// BASIC keyboard expressions are <=64 source bytes. Even if every two-byte
// fraction needs F64 (9 bytes), 21 leaves + 20 operators + header/CHECK/HALT
// use 243 bytes; remaining unary/group syntax cannot exceed the 256 ceiling.
// The bound is tested both with and without compact decimal recipes.
static constexpr uint16_t INPUT_IMAGE_CAPACITY = 256;
// While a program is suspended for INPUT, the upper 32 double slots hold
// its temporary bytecode instead of a second buffer on the resident C stack.
// A 64-byte expression has at most 32 leaves; even with a suspended array
// index it fits below the 64-slot boundary. Ordinary RUN still has 96 slots.
static constexpr uint8_t INPUT_STACK_CAPACITY =
    MAX_STACK - INPUT_IMAGE_CAPACITY / sizeof(double);
static_assert(INPUT_IMAGE_CAPACITY % sizeof(double) == 0 &&
              INPUT_STACK_CAPACITY >= 33 && INPUT_STACK_CAPACITY < MAX_STACK,
              "INPUT bytecode and value stack must be disjoint");
enum class OverlayAction : uint8_t { START, RESUME, EXPRESSION, ABORT };
// Only values/bytecode offsets, never compiler or executor pointers. The
// executor binds a fresh State and callback table on every invocation.
struct ExecutionState {
  Continuation control;
  double stack[MAX_STACK];
  char output[96];
  double input_value;
  uint32_t steps;
  uint16_t prompt_offset, prompt_length, array_count;
  Language language;
  uint8_t row, width;
  bool cancelled, normal_stop;
  Error failure;
};
inline uint8_t* input_image_storage(ExecutionState& state) {
  return reinterpret_cast<uint8_t*>(state.stack + INPUT_STACK_CAPACITY);
}
// Produced by the cold verifier, held by the resident for the immutable image
// lifetime. This is an internal, data-only certificate, not a trust boundary
// for arbitrary native APPs. It contains no pointers into an unloaded APP.
struct ValidatedImage {
  uint32_t magic;
  uint16_t size, code, lines, source_size;
  uint8_t stack, flags;
  Language language;
  uint8_t reserved;
};
struct OverlayRequest {
  uint32_t size, version;
  ExecuteRequest* execution;
  ExecutionState* state;
  ValidatedImage* validated;
  OverlayAction action;
  uint8_t reserved[3];
};
inline bool execution_compatible(const OverlayRequest* p) {
  if (!p || p->size != sizeof(*p) || p->version != REQUEST_VERSION ||
      !p->state || !p->execution || !p->validated || p->action > OverlayAction::ABORT ||
      p->reserved[0] || p->reserved[1] || p->reserved[2]) return false;
  const auto& r = *p->execution;
  return r.size == sizeof(r) && r.version == REQUEST_VERSION && r.image &&
         r.image_size >= HEADER_SIZE && r.image_size <= MAX_IMAGE && r.variables &&
         r.array_count <= 385 && (!r.array_count || r.array) && r.mode <= 1 && !r.reserved &&
         (p->state->language == Language::BASIC || p->state->language == Language::FOCAL);
}
inline bool validated_view(const OverlayRequest& p, View& v) {
  const auto& m = *p.validated;
  const auto& r = *p.execution;
  const bool basic = m.language == Language::BASIC;
  if (m.magic != VALIDATED_MAGIC || m.reserved || m.size != r.image_size ||
      m.language != p.state->language || m.flags > 3 || !m.stack || m.stack > MAX_STACK ||
      m.code != HEADER_SIZE + m.lines * (basic ? 4 : 6) || m.code >= m.size ||
      !m.source_size || m.source_size > (basic ? 3584 : 1536) ||
      m.lines > (basic ? 192 : 80) ||
      ((m.flags & 1) ? m.lines || m.source_size > (basic ? 64 : 111) : !m.lines))
    return false;
  v = {r.image, m.size, m.code, m.lines, m.source_size, m.stack, m.language,
       (m.flags & 1) != 0, (m.flags & 2) != 0};
  return v.expression == (p.action == OverlayAction::EXPRESSION);
}
// Cold module owns full decoding/CRC/branch checks. A valid START also resets
// continuation and derives the original BASIC array quota; no UI here.
uint32_t validate_execution(OverlayRequest*);
// Requires a verified expression-only View. Such images cannot mutate
// control frames or variables, so only the scalar cursor fields need
// saving. Values borrow the lower unused stack tail, never the upper INPUT
// image slots. Reject an overlapping cursor here; run() also checks the
// certificate's declared stack need against this bound before mutating state.
inline RunResult evaluate_input(const View& view, ExecutionState& s,
                                const Bindings& program, const Services& services) {
  if (!view.expression || s.control.sp >= INPUT_STACK_CAPACITY)
    return {Error::INVALID_IMAGE, 0, 0, 0};
  const uint16_t pc = s.control.pc;
  const uint8_t sp = s.control.sp, calls = s.control.call_count, loops = s.control.loop_count;
  const Bindings expression = {program.variables, program.array, program.array_count,
                               s.stack + sp, (uint8_t)(INPUT_STACK_CAPACITY - sp)};
  Services local = services; local.yield_input = false;
  const auto result = run(view, s.control, expression, local);
  if (result.error == Error::NONE) s.input_value = expression.stack[0];
  s.control.pc = pc; s.control.sp = sp;
  s.control.call_count = calls; s.control.loop_count = loops;
  return result;
}
enum class InputResult : uint8_t { NONE, VALUE, EXPRESSION, CANCELLED };
struct InputRequest {
  uint32_t size, version;
  const char* prompt;
  uint8_t* image;
  double value;
  uint16_t prompt_length, capacity, image_size;
  Language language;
  InputResult result;
  bool invalid;
  uint8_t reserved[7];
};
inline bool compatible(const Request* r) {
  return r && r->size == sizeof(*r) && r->version == REQUEST_VERSION &&
         r->capacity >= HEADER_SIZE && r->capacity <= MAX_IMAGE;
}
// Bound by each compiler APP command, reset before returning to the resident.
extern Request* frontend_request;
// Each compiler supplies its current persistent source inode, not a pointer
// to its source/AST. Resident RUN_INDEX can restore selection after eviction.
uint16_t frontend_source_id(void);
// Emit the previously sized, still-resident source, without opening the
// editor or repeating file/name selection. Used only by compiler-only APPs.
bool frontend_emit(void);
#if UINTPTR_MAX == UINT32_MAX
static_assert(sizeof(Request) == 32, "compiler request ARM ABI changed");
static_assert(sizeof(ExecuteRequest) == 44, "execution request ARM ABI changed");
static_assert(sizeof(OverlayRequest) == 24, "overlay request ARM ABI changed");
static_assert(sizeof(ValidatedImage) == 16, "validated descriptor ARM ABI changed");
static_assert(sizeof(InputRequest) == 40, "input request ARM ABI changed");
static_assert(sizeof(ExecutionState) == 1504, "continuation layout changed; update measurements");
#endif
}  // namespace language_vm
#endif
