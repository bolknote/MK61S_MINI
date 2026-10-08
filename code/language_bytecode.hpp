#ifndef MK61_LANGUAGE_BYTECODE_HPP
#define MK61_LANGUAGE_BYTECODE_HPP

#include <stddef.h>
#include <stdint.h>
#include "language_value.hpp"

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
  EXPECTED_PAREN
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
  CHECK,
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
  FLOOR_DIV
};
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
  ROWS
};
static constexpr uint16_t HEADER_SIZE = 32;
static constexpr uint16_t VERSION = 2;
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
  uint16_t size;
  uint16_t line;
  uint16_t source_offset;
  uint8_t stack;
};
struct View {
  const uint8_t* bytes;
  uint16_t size, code, lines, source_size;
  uint8_t stack;
  Language language;
  bool expression;
  bool requires_rf;
  uint16_t end = 0; // instruction boundary; source-backed recipes follow it
};
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
  RESOURCE_INPUT
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
};
struct CallFrame {
  uint16_t resume, end;
  uint8_t loops;
  bool group;
};
struct LoopFrame {
  Value limit, step, value;
  uint16_t body, end;
  uint16_t variable;
};
// Pointer-free control state survives replacement/relocation of a native APP.
struct Continuation {
  CallFrame calls[MAX_CALLS];
  LoopFrame loops[MAX_LOOPS];
  uint16_t pc, data_pc, data_index;
  uint8_t sp, call_count, loop_count;
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
  uint16_t pc;
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
CompileResult compile_expression(Language, const char*, uint16_t, uint8_t*, uint16_t);
// No output buffer means validation/sizing only, with identical grammar.
Error inspect(const uint8_t* bytes, uint16_t length, View& output);
RunResult run(const View&, State&, const Services&, uint32_t step_limit = 0,
              bool resume = false);
RunResult run(const View&, Continuation&, const Bindings&, const Services&,
              uint32_t step_limit = 0, bool resume = false);
uint32_t checksum(const uint8_t*, size_t);
uint32_t source_line(const View&, uint16_t pc);
uint16_t source_column(const View&, uint16_t pc);
uint16_t line_pc(const View&, uint32_t number);
const char* error_name(Error);
}  // namespace language_vm
#endif
