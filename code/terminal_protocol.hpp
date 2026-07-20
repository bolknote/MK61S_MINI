#ifndef TERMINAL_PROTOCOL_HPP
#define TERMINAL_PROTOCOL_HPP

#include "rust_types.h"

namespace terminal_protocol {

enum class ResultKind : u8 {
  OK,
  ERROR,
  KEY,
  RUN_PROGRAM,
  OPEN_FILE,
  LOAD_SLOT,
  GOTO_LABEL
};

struct Result {
  ResultKind kind;
  i32 key;
  const char* args;

  static Result ok(void) { return {ResultKind::OK, -1, ""}; }
  static Result error(void) { return {ResultKind::ERROR, -1, ""}; }
  static Result keyboard(i32 value) { return {ResultKind::KEY, value, ""}; }
  static Result action(ResultKind kind, const char* args) { return {kind, -1, args == 0 ? "" : args}; }
};

} // пространство имён terminal_protocol

#endif
