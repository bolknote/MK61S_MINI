#ifndef MK61_BASIC_GRAPHICS_CLIENT_HPP
#define MK61_BASIC_GRAPHICS_CLIENT_HPP
#include "basic_graphics.hpp"
#include "language_bytecode.hpp"
#include <string.h>
#if defined(MK61_BUILD_PORTABLE_SYSTEM)
namespace basic_graphics {
inline Result dispatch(Request &request) {
  const auto value =
      portable_system::call(MK61_SERVICE_BASIC_GRAPHICS, 0, 0, sizeof(request), &request);
  return value && value <= (unsigned)Result::IO + 1 ? (Result)(value - 1) : Result::UNAVAILABLE;
}
} // namespace basic_graphics
#endif
namespace basic_graphics {
inline Result command(Operation op) {
#if defined(MK61_BUILD_PORTABLE_SYSTEM)
  const auto value =
      portable_system::call(MK61_SERVICE_BASIC_GRAPHICS, (unsigned)op, 0, 0, nullptr);
  return value && value <= (unsigned)Result::IO + 1 ? (Result)(value - 1) : Result::UNAVAILABLE;
#else
  Request request = {};
  request.operation = op;
  return dispatch(request);
#endif
}
inline double dimension(Operation op) {
#if defined(MK61_BUILD_PORTABLE_SYSTEM)
  return portable_system::call(MK61_SERVICE_BASIC_GRAPHICS, (unsigned)op, 0, 0, nullptr);
#else
  Request request = {};
  request.operation = op;
  return dispatch(request) == Result::OK ? request.value : 0;
#endif
}
inline language_vm::Error error(Result result) {
  using language_vm::Error;
  switch (result) {
  case Result::OK:
    return Error::NONE;
  case Result::UNAVAILABLE:
    return Error::GRAPHICS_UNAVAILABLE;
  case Result::CHANGED:
    return Error::GRAPHICS_CHANGED;
  case Result::FULL:
    return Error::FULL;
  case Result::ARGUMENT:
    return Error::GRAPHICS_ARGUMENT;
  default:
    return Error::IO;
  }
}
inline Result capture(uint8_t first, uint8_t count) {
  Request request = {};
  request.operation = Operation::TEXT_ROWS;
  request.count = 2;
  request.args[0] = first;
  request.args[1] = count;
  return dispatch(request);
}
inline bool active() { return dimension(Operation::ACTIVE) != 0; }
inline Result push_print(const PrintPosition &position, const char *output, uint8_t cursor) {
  Request r = {};
  r.operation = Operation::SAVE_PRINT;
  r.count = 5;
  r.text = output;
  r.length = (uint16_t)strlen(output);
  r.args[0] = position.x;
  r.args[1] = position.y;
  r.args[2] = position.positioned ? 1 : 0;
  r.args[3] = cursor;
  r.args[4] = position.owns_context ? 1 : 0;
  return dispatch(r);
}
inline Result pop_print(PrintPosition &position, char *output, uint8_t &cursor) {
  Request r = {};
  r.operation = Operation::RESTORE_PRINT;
  r.text = output;
  r.length = 96;
  const auto result = dispatch(r);
  if (result == Result::OK && r.value) {
    position = {r.args[0], r.args[1], r.args[2] != 0, r.args[4] != 0};
    cursor = (uint8_t)r.args[3];
  }
  return result;
}
inline Result print_at(PrintPosition &position, char *output, uint8_t &cursor,
                       const Request &coordinates) {
  const auto result = push_print(position, output, cursor);
  if (result != Result::OK)
    return result;
  position = {coordinates.args[0], coordinates.args[1], true, true};
  output[0] = 0;
  cursor = 0;
  return Result::OK;
}
inline Result flush_at(PrintPosition &position, char *output, uint8_t &cursor) {
  Request r = {};
  r.operation = Operation::TEXT;
  r.count = 2;
  r.args[0] = position.x;
  r.args[1] = position.y;
  r.text = output;
  r.length = (uint16_t)strlen(output);
  const bool owns = position.owns_context;
  auto result = dispatch(r);
  position.positioned = position.owns_context = false;
  output[0] = 0;
  cursor = 0;
  if (result == Result::OK && owns)
    result = pop_print(position, output, cursor);
  return result;
}
inline Result flow(const char *text, uint16_t length, uint8_t first, uint8_t maximum, bool empty,
                   uint8_t &written) {
  Request r = {};
  r.operation = Operation::TEXT_FLOW;
  r.text = text;
  r.length = length;
  r.count = 3;
  r.args[0] = first;
  r.args[1] = maximum;
  r.args[2] = empty ? 1 : 0;
  const auto result = dispatch(r);
  written = (uint8_t)r.value;
  return result;
}
} // namespace basic_graphics
#endif
