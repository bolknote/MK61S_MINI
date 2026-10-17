#ifndef MK61_LANGUAGE_VM_ABI_HPP
#define MK61_LANGUAGE_VM_ABI_HPP
#include "language_bytecode.hpp"
#include "basic_graphics_protocol.hpp"
#include <string.h>

namespace language_vm {
static constexpr uint32_t REQUEST_VERSION = 13;
static constexpr uint32_t COMPILER_MAGIC = 0x424D5643UL;
static constexpr uint16_t VALUES_SIZE = 4016;
static constexpr uint16_t COMPILER_WORKSPACE_SIZE = 8192 - VALUES_SIZE;
// Frontend selection/printing lives below this fixed offset. Flash writers
// use the rest of the existing compiler prefix instead of the MCU stack.
static constexpr uint16_t FLASH_FRONTEND_BYTES = 512;
static constexpr uint16_t FLASH_CACHE_BYTES = flash::WRITE_BYTES;
static constexpr uint16_t FLASH_COMPILER_WORKSPACE_SIZE = COMPILER_WORKSPACE_SIZE-FLASH_CACHE_BYTES;
// Resident-owned, synchronous request. Output survives compiler eviction;
// none of the pointers may point into the native compiler's APP allocation.
struct Request {
  uint32_t size, version;
  uint8_t* output;
  uint32_t capacity;
  CompileResult compiled;
  uint16_t source_id;
  uint8_t language, mode, run_requested, clear_requested;
  ResourceMode resources;
  uint8_t retained_source;
  uint8_t edit_requested, reserved;
  uint32_t source_revision;
  flash::IO* storage;
};
struct ExecuteRequest {
  uint32_t size, version;
  const uint8_t* image;
  uint32_t image_size;
  Value* variables;
  Value* array;
  uint32_t array_count;
  uint8_t mode, pause_final;
  uint16_t reserved;
  uint16_t error_column;
  uint8_t edit_requested, reserved2;
  RunResult result;
  flash::Input paged;
  flash::IO* storage;
};
static constexpr uint32_t OVERLAY_MAGIC = 0x41564D4CUL;
static constexpr uint32_t INPUT_MAGIC = 0x41494D4CUL;
static constexpr uint32_t VALIDATED_MAGIC = 0x4149424CUL;
// BASIC keyboard expressions are <=64 source bytes. Even if every two-byte
// fraction needs F64 (9 bytes), 21 leaves + 20 operators + header/CHECK/HALT
// use 243 bytes; remaining unary/group syntax cannot exceed the 256 ceiling.
// The bound is tested both with and without compact decimal recipes.
static constexpr uint16_t INPUT_IMAGE_CAPACITY = 256;
// While a program is suspended for INPUT, the upper 32 number slots hold
// its temporary bytecode instead of a second buffer on the resident C stack.
// A 64-byte expression has at most 32 leaves; even with a suspended array
// index it fits below the 64-slot boundary. Ordinary RUN still has 96 slots.
static constexpr uint8_t INPUT_STACK_CAPACITY =
    MAX_STACK - INPUT_IMAGE_CAPACITY / sizeof(Value);
static_assert(INPUT_IMAGE_CAPACITY % sizeof(Value) == 0 &&
              INPUT_STACK_CAPACITY >= 33 && INPUT_STACK_CAPACITY < MAX_STACK,
              "INPUT bytecode and value stack must be disjoint");
enum class OverlayAction : uint8_t { START, RESUME, EXPRESSION, ABORT };
// Only values/bytecode offsets, never compiler or executor pointers. The
// executor binds a fresh State and callback table on every invocation.
struct ExecutionState {
  Continuation control;
  Value stack[MAX_STACK];
  char output[96];
  Value input_value;
  uint32_t steps;
  uint32_t prompt_offset;
  uint16_t prompt_length, array_count;
  char prompt[96];
  Language language;
  uint8_t row, width, output_cursor, precision;
  bool cancelled, normal_stop;
  Error failure;
  basic_graphics::PrintPosition position;
};
inline void reset_execution_state(ExecutionState& state) {
#if defined(LANGUAGE_VM_TEST_STATE_RESETS)
  extern void language_vm_test_state_reset(ExecutionState&);
  language_vm_test_state_reset(state);
#endif
  static_assert(std::is_trivially_copyable<ExecutionState>::value,
                "continuation must support in-place byte initialization");
  static_assert(std::is_standard_layout<ExecutionState>::value &&
                std::is_standard_layout<Continuation>::value,
                "reset ranges require standard-layout continuation fields");
  // Counts hide inactive call/loop frames and the operand stack. Each slot is
  // completely written before its count grows; INPUT bytecode is likewise
  // bounded by its emitted image size. Do not clear those dead scratch banks.
  // Keep every live cursor and the whole I/O/scalar tail at their old zero
  // representation, including input_value, flags, padding and the output NUL.
  // In-place ranges also avoid a full ExecutionState stack temporary.
  memset(reinterpret_cast<uint8_t*>(&state.control) + offsetof(Continuation, pc),
         0, sizeof(Continuation) - offsetof(Continuation, pc));
  memset(reinterpret_cast<uint8_t*>(&state) + offsetof(ExecutionState, output),
         0, sizeof(ExecutionState) - offsetof(ExecutionState, output));
}
inline uint8_t* input_image_storage(ExecutionState& state) {
  return reinterpret_cast<uint8_t*>(state.stack + INPUT_STACK_CAPACITY);
}
// Produced by the cold verifier, held by the resident for the immutable image
// lifetime. This is an internal, data-only certificate, not a trust boundary
// for arbitrary native APPs. It contains no pointers into an unloaded APP.
struct ValidatedImage {
  uint32_t magic;
  uint32_t size, code;
  uint16_t source_size;
  uint32_t end;
  uint16_t lines;
  uint8_t stack, flags;
  Language language;
  bool wide;
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
  return r.size == sizeof(r) && r.version == REQUEST_VERSION &&
         (r.paged.read ? r.storage && r.paged.size==r.image_size : r.image && r.image_size<=MAX_MODULE) &&
         r.image_size >= HEADER_SIZE && r.variables &&
         r.array_count <= 385 && (!r.array_count || r.array) && r.mode <= 1 && !r.reserved &&
         !r.reserved2 && r.edit_requested <= 1 &&
         (p->state->language == Language::BASIC || p->state->language == Language::FOCAL);
}
inline bool validated_view(const OverlayRequest& p, View& v,const flash::Reader* reader=nullptr) {
  const auto& m = *p.validated;
  const auto& r = *p.execution;
  const bool basic = m.language == Language::BASIC;
  if (m.magic != VALIDATED_MAGIC || m.size != r.image_size ||
      m.language != p.state->language || m.flags > 15 || (uint8_t)(m.stack - 1) >= MAX_STACK ||
      m.code != HEADER_SIZE + uint32_t(m.lines) * (m.wide?8:basic ? 4 : 6) || m.code >= m.end || (!m.wide && m.end > MAX_IMAGE) || m.end > m.size ||
      (uint16_t)(m.source_size - 1) >= source::MAX_SIZE ||
      (!m.wide && m.lines > (basic ? 192 : 80)) ||
      ((m.flags & 1) ? m.lines || m.source_size > (basic ? 64 : 111) : !m.lines))
    return false;
  v = {r.image, m.size, m.code, m.lines, m.source_size, m.stack, m.language,
       (m.flags & 1) != 0, (m.flags & 2) != 0, m.end, m.wide?reader:nullptr,m.wide};
  if(m.wide && r.storage) {v.lookup_context=r.storage->context;v.lookup=r.storage->lookup;}
  return v.expression == (p.action == OverlayAction::EXPRESSION);
}
inline void initialize_validated_state(const ExecuteRequest& r, const ValidatedImage& image,
                                       ExecutionState& s) {
  reset_execution_state(s); s.language = image.language; s.array_count = (uint16_t)r.array_count;

}
// Cold module owns full decoding/CRC/branch checks. A valid START also resets
// continuation; array storage is independent of source-file size. No UI here.
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
  const uint32_t pc = s.control.pc;
  const uint32_t data_pc = s.control.data_pc, data_index = s.control.data_index;
  const uint8_t sp = s.control.sp, calls = s.control.call_count, loops = s.control.loop_count;
  const Bindings expression = {program.variables, program.array, program.array_count,
                               s.stack + sp, (uint8_t)(INPUT_STACK_CAPACITY - sp)};
  Services local = services; local.yield_input = false;
  const auto result = run(view, s.control, expression, local);
  if (result.error == Error::NONE) s.input_value = expression.stack[0];
  s.control.pc = pc; s.control.sp = sp;
  s.control.data_pc = data_pc;
  s.control.data_index = data_index;
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
  uint8_t reserved[3];
  const uint8_t* resource_image;
};
inline bool compatible(const Request* r) {
  return r && r->size == sizeof(*r) && r->version == REQUEST_VERSION &&
         r->capacity >= HEADER_SIZE && (r->storage || r->capacity <= MAX_MODULE) &&
         r->resources <= ResourceMode::EMBEDDED && r->retained_source <= 1 && r->edit_requested <= 1 && !r->reserved;
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
static_assert(sizeof(Request)==52 && offsetof(Request,storage)==48,"Flash compiler request ABI");
static_assert(sizeof(ExecuteRequest)==68 && offsetof(ExecuteRequest,paged)==52,"paged executor ABI");
static_assert(sizeof(ValidatedImage)==28 && sizeof(OverlayRequest)==24,"32-bit image certificate ABI");
static_assert(sizeof(ExecutionState)==1992 && sizeof(Continuation)==976,"32-bit continuation ABI");
static_assert(sizeof(InputRequest)==40,"INPUT protocol ABI");
#endif
}  // namespace language_vm
#endif
