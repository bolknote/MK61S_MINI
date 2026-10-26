#ifndef MK61_LANGUAGE_BYTECODE_HPP
#define MK61_LANGUAGE_BYTECODE_HPP

#include <stddef.h>
#include <stdint.h>
#include "language_value.hpp"
#include "language_source.hpp"
#include "language_flash.hpp"

// Experimental, relocatable bytecode. The compiler, VM and host probes share
// this wire format; no native pointers or C++ layouts are serialized.
namespace language_vm {
enum class Language : uint8_t { BASIC = 1, FOCAL = 2 };
// No BASIC source can contain column 65535. The editor discards coordinates
// from an execution snapshot whose filesystem revision changed.
static constexpr uint32_t STALE_SOURCE_POSITION = UINT32_MAX;
enum class Error : uint8_t {
  NONE,
  SYNTAX,
  LINE,
  FULL,
  VARIABLE,
  FUNCTION,
  FOR,
  RETURN,
  STACK,
  MATH,
  REGISTER,
  INVALID_IMAGE,
  IO,
  STOPPED,
  LIMIT,
  YIELDED,
  DIV_ZERO,
  ARRAY_RANGE,
  DATA_END,
  ON_INDEX,
  CALL_STACK,
  LOOP_STACK,
  NEXT_WITHOUT_FOR,
  MISSING_LINE,
  LINE_NUMBER,
  FORMAT,
  UNKNOWN_COMMAND,
  UNTERMINATED_STRING,
  EXPECTED_PAREN,
  GRAPHICS_UNAVAILABLE,
  GRAPHICS_CHANGED,
  GRAPHICS_ARGUMENT
};
enum class Op : uint8_t {
  HALT,
  LINE,
  CONST_I8,
  CONST_I16,
  CONST_F64,
  LOAD,
  STORE,
  LOAD_REF,
  STORE_REF,
  LOAD_ARRAY,
  STORE_ARRAY,
  NEG,
  NOT,
  ADD,
  SUB,
  MUL,
  DIV,
  POW,
  MOD,
  EQ,
  NE,
  LT,
  LE,
  GT,
  GE,
  AND,
  OR,
  XOR,
  FUNCTION,
  CHECK, // retired in v4; wire value 29 is invalid
  JUMP,
  JUMP_FALSE,
  GOTO,
  GOSUB,
  RETURN,
  FOR_BASIC,
  NEXT_BASIC,
  DO_FOCAL,
  FOR_FOCAL,
  NEXT_FOCAL,
  BRANCH,
  PRINT_BEGIN,
  PRINT_TEXT,
  PRINT_NUMBER,
  PRINT_FORMAT,
  PRINT_SEPARATOR,
  PRINT_FLUSH,
  PRINT_END,
  READ_INPUT,
  WAIT,
  CLEAR,
  TARGET_REF,
  TARGET_ARRAY,
  CONST_DEC8,
  CONST_DEC16,
  READ_KEY,
  CONST_0 = 64,
  CONST_15 = 79,
  DATA,
  READ_DATA,
  RESTORE_DATA,
  ON_GOTO,
  ON_GOSUB,
  FOR_ARRAY,
  NEXT_ARRAY,
  SOURCE_POS,
  PRINT_RESOURCE,
  INPUT_RESOURCE,
  CONST_I32,
  FLOOR_DIV,
  GOTO_DIRECT,
  GOSUB_DIRECT,
  LOAD_ARRAY_FIXED,
  COMPARE_FALSE,
  UPDATE_LOCAL,
  ARRAY_CELL,       // name byte; two indices -> shared sparse value index
  CALL_PARAMS,      // target/end words, argument count, result flag
  LOAD_PARAMETER,   // one-based position -> current call argument
  RETURN_VALUE,
  DROP,
  PRINT_PRECISION,  // width and significant digit bytes
  BLOCK_INDEX,     // CONST_I16 layout; compiler-proven CONST_I16 / LOAD / ADD
  BLOCK_COMPARE,   // LOAD layout; compiler-proven LOAD / CONST_0..15 / COMPARE_FALSE
  INTEGER_SPAN,    // LOAD layout; start of a compiler-selected integer expression
  GRAPHICS,        // operation/count bytes; pops arguments, POINT pushes result
  PRINT_AT,        // two coordinates -> a positioned PRINT context
  GRAPH_BEGIN,     // four bounds -> temporary X; word points to GRAPH_NEXT
  GRAPH_NEXT,      // one sample -> raster point; word points to expression body
  INTEGER_SHORT    // LOAD layout; short array/ABS-to-local block, scalar LOAD fallback
};
// A block mark changes neither the first instruction's width nor its logical
// identity. Diagnostic/host traces use the original scalar opcode.
constexpr Op scalar_op(Op op) {
  return op==Op::BLOCK_INDEX ? Op::CONST_I16 :
      op==Op::BLOCK_COMPARE || op==Op::INTEGER_SPAN || op==Op::INTEGER_SHORT ? Op::LOAD : op;
}
constexpr bool index_block_shape(Op op,uint32_t pc,Op first,uint32_t first_pc,
                                 Op second,uint32_t second_pc) {
  return op==Op::ADD && first==Op::CONST_I16 && second==Op::LOAD &&
         second_pc==first_pc+3U && pc==second_pc+2U;
}
enum class Function : uint8_t {
  SIN,
  COS,
  TAN,
  ASIN,
  ACOS,
  ATAN,
  LN,
  LOG10,
  EXP,
  SQRT,
  ABS,
  INT,
  FRAC,
  ROUND,
  SGN,
  MAX,
  RND,
  RND_LIMIT,
  PI_VALUE,
  SIZE,
  COLS,
  ROWS,
  GW,
  GH
};
inline constexpr uint8_t wire_widths[] = {
  1,1,2,3,9,2,2,2,2,1,1,1,1,1,1,1, // 0..15
  1,1,1,1,1,1,1,1,1,1,1,1,2,0,3,3, // 16..31 (29: retired CHECK)
  1,1,1,2,2,5,5,1,7,1,255,1,1,2,1,2, // 32..47
  255,1,1,2,1,3,4,1,0,0,0,0,0,0,0,0, // 48..63
  1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1, // 64..79
  255,1,1,255,255,1,1,3,3,3,5,1,3,3,3,4,3, // 80..96
  2,7,1,1,1,3,3,2,2, // 97..105
  3,1,3,3,2 // GRAPHICS, PRINT_AT, GRAPH_BEGIN, GRAPH_NEXT, INTEGER_SHORT
};
static_assert(sizeof(wire_widths)==(unsigned)Op::INTEGER_SHORT+1,"opcode width table changed");
inline uint16_t instruction_end(const uint8_t* bytes, uint16_t end, uint16_t pc) {
  if(pc>=end) return 0;
  const uint8_t op=bytes[pc];
  if(op>=sizeof(wire_widths)) return 0;
  const uint8_t width=wire_widths[op];
  const uint16_t remaining=(uint16_t)(end-pc);
  if(width!=255) return width && width<=remaining ? (uint16_t)(pc+width) : 0;
  if(remaining<3) return 0;
  const uint16_t count=(uint16_t)(bytes[pc+1] | ((uint16_t)bytes[pc+2]<<8));
  if((Op)op==Op::ON_GOTO || (Op)op==Op::ON_GOSUB) {
    if(!count || count>(remaining-3)/2) return 0;
    return (uint16_t)(pc+3+count*2);
  }
  if((Op)op==Op::DATA && !count) return 0;
  return count<=remaining-3 ? (uint16_t)(pc+3+count) : 0;
}
// Full-program compilers add same-width execution hints after layout.
void mark_integer_spans(uint8_t*, uint16_t code, uint16_t end);

// Bits select less/equal/greater/unordered results of a numeric comparison.
constexpr uint8_t comparison_mask(Op op) {
  // Packed nibbles: EQ NE LT LE GT GE. Called only for that bounded range.
  return (uint8_t)((UINT32_C(0x6431D2)>>(((unsigned)op-(unsigned)Op::EQ)*4))&15);
}
static_assert(comparison_mask(Op::EQ)==2 && comparison_mask(Op::NE)==13 &&
              comparison_mask(Op::LT)==1 && comparison_mask(Op::LE)==3 &&
              comparison_mask(Op::GT)==4 && comparison_mask(Op::GE)==6,
              "comparison mask encoding changed");
static constexpr uint16_t HEADER_SIZE = 32;
static constexpr uint16_t VERSION = 13;
// LBV1 in-memory compatibility/INPUT tooling only. Stored programs use
// LBV2 Flash images with 32-bit addresses and no such image quota.
static constexpr uint16_t MAX_IMAGE = 6144;
// Keep the instruction/map budget unchanged; owned resource bytes have a
// separate bounded allowance, rather than increasing source or stack quotas.
static constexpr uint16_t MAX_MODULE = MAX_IMAGE + 3584;
static constexpr uint8_t RESOURCE_FLAG = 4, OWNED_RESOURCE_FLAG = 8;
static constexpr uint8_t MAX_STACK = 96;
static constexpr uint8_t MAX_CALLS = 16;
static constexpr uint8_t MAX_LOOPS = 16;

struct CompileResult {
  Error error;
  uint32_t size;
  uint16_t line;
  uint16_t source_offset;
  uint8_t stack;
};
struct View {
  const uint8_t* bytes;
  uint32_t size, code;
  uint16_t lines, source_size;
  uint8_t stack;
  Language language;
  bool expression;
  bool requires_rf;
  uint32_t end = 0; // instruction boundary; source-backed recipes follow it
  const flash::Reader* reader = nullptr;
  bool wide = false;
  void* lookup_context = nullptr;
  bool (*lookup)(void*,uint32_t,bool,uint32_t*) = nullptr;
  flash::Cursor at(uint32_t n) const {return {bytes,reader,n};}
#if defined(MK61_BUILD_LANGUAGE_VM_MODULE) || defined(MK61_BUILD_LANGUAGE_INPUT_MODULE)
  __attribute__((noinline))
#endif
  uint8_t byte(uint32_t n) const {return reader?reader->at(n):bytes[n];}
  // The span consumes operands before its first mutable-bank write. A trace
  // callback keeps the copying path; a reader borrow also expires on refill.
  const uint8_t* cached(uint32_t at,uint16_t n) const {return reader?reader->cached(at,n):bytes+at;}
  bool read(uint32_t at,void* out,uint16_t n) const {
    if(reader)return reader->read(at,out,n);
    memcpy(out,bytes+at,n);return true;
  }
#if defined(MK61_CORE_STANDALONE)
  __attribute__((always_inline))
#endif
  bool wide_code() const {
#if defined(MK61_BUILD_LANGUAGE_VM_MODULE) || defined(MK61_BUILD_LANGUAGE_INPUT_MODULE)
    // Shipping APPs accept LBV2 programs and branch-free LBV1 INPUT recipes.
    return true;
#else
    return wide;
#endif
  }
  uint8_t address_bytes() const {return wide_code()?4:2;}
  uint32_t address(flash::Cursor p) const {return wide_code()?flash::dword(p):flash::word(p);}
  uint32_t address(const uint8_t* p) const {return wide_code()?flash::dword(p):flash::word(p);}
  uint32_t missing() const {return wide_code()?UINT32_MAX:0xFFFF;}
  uint32_t group_bit() const {return wide_code()?UINT32_C(0x80000000):0x8000;}
  bool good() const {return !reader || reader->good();}

};
// Every program address is 32-bit. Source coordinates and line counts are
// naturally bounded by the source-file wire size, never by a RAM array.
// The reader belongs to the current APP invocation, never the continuation.
// All callbacks are supplied afresh by the currently active executor. They
// are never stored in an image or retained across unloading a native APP.
enum class Event : uint8_t {
  PRINT_BEGIN,
  TEXT,
  NUMBER,
  FORMAT,
  SEPARATOR,
  FLUSH,
  PRINT_END,
  READ_INPUT,
  WAIT,
  CLEAR,
  FINISH,
  TARGET_REF,
  READ_KEY,
  RESOURCE_TEXT,
  RESOURCE_INPUT,
  PRECISION,
  TRACE,
  PRINT_STATE, // optional query: packed width/significant digits, zero if unavailable
  GRAPHICS,
  PRINT_AT,
  PRINT_PUSH,
  PRINT_POP,
  TEXT_CONTINUE
};
struct Services {
  void* context;
  bool (*service)(void*);
  double (*math)(void*, Function, double, double);
  double (*random)(void*);
  double (*value)(void*, Function);
  bool (*reference)(void*, bool write, uint8_t reference, double& value);
  bool (*event)(void*, Event, const char*, uint16_t, double&);
  bool yield_input = false;
  bool isolate_print = false;
};
struct CallFrame {
  uint32_t resume, end;
  uint8_t loops;
  bool group;
  uint8_t base = 0, arguments = 0, mode = 0; // mode: parameter call + value result
  uint8_t print_width = 0; // fills the old padding byte; mode's high nibble saves precision
};
static_assert(sizeof(CallFrame) == 16, "call frame contains 32-bit program addresses");
struct LoopFrame {
  Value limit, step, value;
  uint32_t body, end;
  uint16_t variable;
};
struct GraphFrame {
  double bounds[4];
  Value saved_x;
  uint32_t body, next;
  uint16_t column, width, height;
  uint8_t base;
  bool active, skip;
};
// Pointer-free control state survives replacement/relocation of a native APP.
struct Continuation {
  CallFrame calls[MAX_CALLS];
  LoopFrame loops[MAX_LOOPS];
  uint32_t pc, data_pc, data_index;
  uint8_t sp, call_count, loop_count;
  GraphFrame graph;
};
struct Bindings {
  Value* variables;
  Value* array;
  uint16_t array_count;
  Value* stack;
  uint8_t stack_capacity;
};
struct State : Continuation, Bindings {};
struct RunResult {
  Error error;
  uint32_t pc;
  uint32_t line;
  uint32_t steps;
};

// Immutable M8 source doubles as the resource backing store. No native
// pointers enter the image. A source-less host expression remains standalone.
enum class ResourceMode : uint8_t { SOURCE = 0, EMBEDDED = 1 };
struct ResourceSource {
  uint16_t id;
  uint32_t revision;
  ResourceMode mode = ResourceMode::SOURCE;
};
CompileResult compile_flash_source(Language,const source::Reader&,flash::IO,bool rf_available=true,void* scratch=nullptr);
CompileResult compile_source(Language, const source::Reader&, uint8_t*, uint16_t, bool = true,
                             const ResourceSource* = nullptr);
CompileResult compile_basic(const char*, uint16_t, uint8_t*, uint16_t, bool,
                            const ResourceSource* = nullptr);
CompileResult compile_focal(const char*, uint16_t, uint8_t*, uint16_t, bool,
                            const ResourceSource* = nullptr);
inline CompileResult compile(Language language, const char* source, uint16_t length,
                             uint8_t* output, uint16_t capacity,
                             bool rf_available = true, const ResourceSource* resources = nullptr) {
  if (language == Language::BASIC)
    return compile_basic(source, length, output, capacity, rf_available, resources);
  if (language == Language::FOCAL)
    return compile_focal(source, length, output, capacity, rf_available, resources);
  return {Error::SYNTAX, 0, 0, 0, 0};
}
bool validate_focal_expression(const char*,uint16_t,bool rf_available=true);
CompileResult compile_expression(Language, const char*, uint16_t, uint8_t*, uint16_t);
// No output buffer means validation/sizing only, with identical grammar.
Error inspect(const uint8_t* bytes, uint16_t length, View& output);
Error inspect_flash(const flash::Reader&, flash::IO, View&);
uint32_t instruction_end(const View&,uint32_t);
RunResult run(const View&, State&, const Services&, uint32_t step_limit = 0,
              bool resume = false);
RunResult run(const View&, Continuation&, const Bindings&, const Services&,
              uint32_t step_limit = 0, bool resume = false);
uint32_t checksum(const uint8_t*, size_t);
uint32_t source_line(const View&, uint32_t pc);
uint16_t source_column(const View&, uint32_t pc);
uint32_t line_pc(const View&, uint32_t number);
const char* error_name(Error);
}  // namespace language_vm
#endif
