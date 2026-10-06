#ifndef MK61_LANGUAGE_BYTECODE_HPP
#define MK61_LANGUAGE_BYTECODE_HPP

#include <stddef.h>
#include <stdint.h>

// Experimental, relocatable bytecode. The compiler, VM and host probes share
// this wire format; no native pointers or C++ layouts are serialized.
namespace language_vm {
enum class Language : uint8_t { BASIC = 1, FOCAL = 2 };
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
  YIELDED
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
  CONST_0 = 64,
  CONST_15 = 79
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
static constexpr uint16_t VERSION = 1;
static constexpr uint16_t MAX_IMAGE = 6144;
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
  TARGET_REF
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
  double limit, step, value;
  uint16_t body, end;
  uint8_t variable;
};
// Pointer-free control state survives replacement/relocation of a native APP.
struct Continuation {
  CallFrame calls[MAX_CALLS];
  LoopFrame loops[MAX_LOOPS];
  uint16_t pc;
  uint8_t sp, call_count, loop_count;
};
struct Bindings {
  double* variables;
  double* array;
  uint16_t array_count;
  double* stack;
  uint8_t stack_capacity;
};
struct State : Continuation, Bindings {};
struct RunResult {
  Error error;
  uint16_t pc;
  uint32_t line;
  uint32_t steps;
};

CompileResult compile_basic(const char*, uint16_t, uint8_t*, uint16_t, bool);
CompileResult compile_focal(const char*, uint16_t, uint8_t*, uint16_t, bool);
inline CompileResult compile(Language language, const char* source, uint16_t length,
                             uint8_t* output, uint16_t capacity,
                             bool rf_available = true) {
  if (language == Language::BASIC)
    return compile_basic(source, length, output, capacity, rf_available);
  if (language == Language::FOCAL)
    return compile_focal(source, length, output, capacity, rf_available);
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
uint16_t line_pc(const View&, uint32_t number);
const char* error_name(Error);
}  // namespace language_vm
#endif
