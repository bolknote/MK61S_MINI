#ifndef MK61_SHEET_ENGINE_HPP
#define MK61_SHEET_ENGINE_HPP

#include <stdint.h>
#include <stddef.h>

namespace sheet {
constexpr uint8_t COLUMNS = 16, ROWS = 32, MAX_CELLS = 64;
constexpr uint16_t POOL_BYTES = 1536, FILE_BYTES = 2048;
constexpr uint8_t SOURCE_BYTES = 96;
enum class Kind : uint8_t { EMPTY, NUMBER, TEXT, FORMULA };
enum class Error : uint8_t { OK, SYNTAX, REFERENCE, TYPE, NUMBER, CYCLE, LIMIT, CANCELLED };
enum class Angle : uint8_t { DEG, RAD, GRD };
enum class Op : uint8_t {
  NUMBER, REFERENCE, ENTER, ADD, SUB, MUL, DIV, NEG, SWAP, ROLL,
  SIN, COS, TAN, ASIN, ACOS, ATAN, LN, LG, EXP, SQRT, POW,
  INV, SQR, TEN, ABS, INT, FRAC, PI
};
struct Token {
  Op op;
  uint8_t anchor; // bit 0: column; bit 1: row
  uint16_t position, begin, end;
  double number;
};
struct Cell {
  uint16_t position, offset;
  uint8_t length, kind, error, dirty;
  double value;
};
struct Book {
  Cell cells[MAX_CELLS];
  char pool[POOL_BYTES];
  uint16_t used;
  uint8_t count, angle, compact;
};
using Math = double (*)(void*, Op, double, double);
using Yield = bool (*)(void*);
struct Host { void* context; Math math; Yield yield; };
using ParseNumber = bool (*)(const char*, double&);
using FormatNumber = bool (*)(double, char*, uint16_t, uint8_t);
// The embedded build uses the resident NUMBER_IO service to save APP space.
// Native tests have the same pure SDK helpers as a fallback.
void number_io(ParseNumber parse, FormatNumber format);

void clear(Book& book);
int find(const Book& book, uint16_t position);
bool source(const Book& book, uint16_t position, char* output);
Error next(const char* source, uint16_t length, uint16_t& cursor, Token& token);
Error validate(Kind kind, const char* source, uint16_t length);
bool number(const char* source, uint16_t length, double& value);
void address(uint16_t position, uint8_t anchor, char* output);
Error set(Book& book, uint16_t position, Kind kind, const char* source, uint16_t length);
void invalidate(Book& book);
bool recalculate(Book& book, const Host& host);
Error evaluate(const Book& book, const char* source, uint16_t length,
               const Host& host, double& value);
Error translate(const char* input, uint16_t length, int columns, int rows, char* output);
uint16_t encode(const Book& book, uint8_t* output, uint16_t capacity);
// Preflight the entire stream before touching book: failed loads are atomic.
bool decode(Book& book, const uint8_t* data, uint16_t length);
void format(double value, char* output, uint16_t capacity, uint8_t digits = 8);
const char* error_text(Error error);
const char* op_text(Op op);
}
#endif
