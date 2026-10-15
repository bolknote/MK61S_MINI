#include "basic_native_io.hpp"
#include "basic_graphics_client.hpp"
#include "mk_math.hpp"
#include "tinybasic_syntax.hpp"
#include "tinybasic_text.hpp"
#include <string.h>

namespace basic_graphics {
namespace {
using language_vm::Error;
constexpr unsigned output_size = 96;
bool fail(NativeRequest &r, Error code, const char *at = nullptr) {
  r.error = code;
  r.error_at = at;
  return false;
}
bool applied(NativeRequest &r, Result result) {
  return result == Result::OK || fail(r, error(result));
}
bool append(NativeRequest &r, const char *text, size_t length) {
  if (r.execute && length)
    *r.pause_is_final = false;
  return !r.execute || tinybasic_text::append(r.output, output_size, *r.cursor, text, length) ||
         fail(r, Error::FULL);
}
bool spaces(NativeRequest &r, unsigned count) {
  while (count--)
    if (!append(r, " ", 1))
      return false;
  return true;
}
bool flush(NativeRequest &r) {
  *r.pause_is_final = false;
  const auto length = (uint16_t)strlen(r.output);
  bool result = true;
  if (*r.positioned) {
    Request text = {};
    text.operation = Operation::TEXT;
    text.count = 2;
    text.args[0] = *r.at_x;
    text.args[1] = *r.at_y;
    text.text = r.output;
    text.length = length;
    result = applied(r, dispatch(text));
  } else {
    const uint8_t rows = native_text_rows();
    const uint8_t maximum = *r.row < rows ? (uint8_t)(rows - *r.row) : 0;
    uint8_t written = 0;
    if (active())
      result = applied(r, flow(r.output, length, *r.row, maximum, true, written));
    else {
      const int count = native_text_flow(r.output, length, *r.row, maximum);
      if (count < 0)
        result = fail(r, Error::IO);
      else
        written = (uint8_t)count;
    }
    if (written && rows) {
      const unsigned next = *r.row + written;
      *r.row = (uint8_t)(next < rows ? next : rows - 1);
    }
  }
  r.output[0] = 0;
  *r.cursor = 0;
  return result;
}
bool items(NativeRequest &r, const char *p) {
  char trailing = 0;
  unsigned width = 0;
  uint8_t precision = 10;
  if (tinybasic_syntax::skip(p, r.end) == r.end)
    return !r.execute || flush(r);
  while (p < r.end) {
    p = tinybasic_syntax::skip(p, r.end);
    if (p == r.end)
      break;
    if (*p == ',' || *p == ';') {
      trailing = *p++;
      if (trailing == ',' && !spaces(r, 1))
        return false;
      continue;
    }
    bool format = false, carriage = false;
    if (*p == '"' || *p == '\'') {
      const char quote = *p++;
      const char *begin = p;
      while (p < r.end && *p != quote)
        ++p;
      if (p == r.end)
        return fail(r, Error::UNTERMINATED_STRING, p);
      if (!append(r, begin, (size_t)(p - begin)))
        return false;
      ++p;
    } else if (*p == '_' || *p == '^') {
      char control = '\r';
      if (*p++ == '^') {
        if (p == r.end || !tinybasic_syntax::alpha(*p))
          return fail(r, Error::SYNTAX, p);
        control = (char)(tinybasic_syntax::upper(*p++) ^ 0x40);
      }
      carriage = control == '\r';
      if (!append(r, &control, 1))
        return false;
    } else {
      unsigned literal_width = 0, digits = 0;
      const char *after = tinybasic_syntax::print_precision(p, r.end, literal_width, digits);
      if (after) {
        if (literal_width > 63 || !digits || digits > 15)
          return fail(r, Error::FORMAT, p);
        width = literal_width;
        precision = (uint8_t)digits;
        p = after;
        format = true;
      } else {
        format = *p == '#';
        if (format)
          ++p;
        double value = 0;
        if (!r.evaluate(r, p, r.end, value, p))
          return false;
        if (r.execute && format) {
          const double rounded = mk_math::floor(value + .5);
          if (value < 0 || value > 63 || mk_math::fabs(value - rounded) > .0000001)
            return fail(r, Error::FORMAT, p);
          width = (unsigned)rounded;
        } else if (r.execute) {
          char number[24];
          r.format(value, number, precision);
          const size_t length = strlen(number);
          if ((width > length && !spaces(r, (unsigned)(width - length))) ||
              !append(r, number, length))
            return false;
        }
      }
    }
    p = tinybasic_syntax::skip(p, r.end);
    if (p < r.end && (*p == ',' || *p == ';')) {
      trailing = *p++;
      if (!format && !carriage && trailing == ',' && !spaces(r, 8 - *r.cursor % 8))
        return false;
      continue;
    }
    if (p < r.end)
      return fail(r, Error::SYNTAX, p);
    trailing = 0;
    break;
  }
  return !r.execute || trailing || flush(r);
}
bool print(NativeRequest &r) {
  const char *p = tinybasic_syntax::skip(r.begin, r.end);
  const char *after = nullptr;
  const bool positioned = tinybasic_syntax::word(p, r.end, "AT", 2, &after);
  double x = 0, y = 0;
  if (positioned) {
    p = after;
    if (!r.evaluate(r, p, r.end, x, p))
      return false;
    p = tinybasic_syntax::skip(p, r.end);
    if (p == r.end || *p++ != ',')
      return fail(r, Error::SYNTAX, p);
    if (!r.evaluate(r, p, r.end, y, p))
      return false;
    p = tinybasic_syntax::skip(p, r.end);
    if (p == r.end || *p++ != ';')
      return fail(r, Error::SYNTAX, p);
    p = tinybasic_syntax::skip(p, r.end);
    if (p == r.end)
      return fail(r, Error::SYNTAX, p);
  }
  struct Restore {
    NativeRequest &r;
    char output[output_size];
    uint8_t cursor;
    double x, y;
    bool positioned, restore;
    Restore(NativeRequest &request, bool at, double px, double py)
        : r(request), cursor(*r.cursor), x(*r.at_x), y(*r.at_y),
          positioned(*r.positioned), restore(r.execute && (at || positioned)) {
      if (restore) {
        memcpy(output, r.output, output_size);
        r.output[0] = 0;
        *r.cursor = 0;
      }
      if (r.execute) {
        *r.positioned = at;
        *r.at_x = px;
        *r.at_y = py;
      }
    }
    ~Restore() {
      if (restore) {
        memcpy(r.output, output, output_size);
        *r.cursor = cursor;
      }
      *r.positioned = positioned;
      *r.at_x = x;
      *r.at_y = y;
    }
  } restore(r, positioned, x, y);
  return items(r, positioned ? p : r.begin) &&
         (!r.execute || !positioned || !r.output[0] || flush(r));
}
bool arguments(NativeRequest &r) {
  Request request = {};
  request.operation = r.primitive;
  const char *p = tinybasic_syntax::skip(r.begin, r.end);
  while (p < r.end) {
    if (request.count == maximum(r.primitive))
      return fail(r, Error::SYNTAX, p);
    if (!r.evaluate(r, p, r.end, request.args[request.count++], p))
      return false;
    p = tinybasic_syntax::skip(p, r.end);
    if (p == r.end)
      break;
    if (*p++ != ',' || tinybasic_syntax::skip(p, r.end) == r.end)
      return fail(r, Error::SYNTAX, p);
  }
  if (request.count < minimum(r.primitive))
    return fail(r, Error::SYNTAX, p);
  return !r.execute || applied(r, dispatch(request));
}
bool graph(NativeRequest &r) {
  const char *comma = tinybasic_syntax::parameter_separator(r.begin, r.end);
  if (comma == r.end)
    return fail(r, Error::SYNTAX, comma);
  struct Restore {
    NativeRequest &r;
    double x;
    bool pure, execute, restore_x = false;
    Restore(NativeRequest &request) : r(request), x(0), pure(*r.pure), execute(r.execute) {}
    ~Restore() {
      if (restore_x)
        *r.x_variable = x;
      *r.pure = pure;
      r.execute = execute;
      r.skip_domain = false;
    }
  } restore(r);
  *r.pure = true;
  r.execute = false;
  double ignored = 0;
  const char *p = r.begin;
  if (!r.evaluate(r, p, comma, ignored, p))
    return false;
  if (tinybasic_syntax::skip(p, comma) != comma)
    return fail(r, Error::SYNTAX, p);
  *r.pure = restore.pure;
  r.execute = restore.execute;
  double bounds[4];
  p = comma + 1;
  for (unsigned i = 0; i < 4; ++i) {
    if (!r.evaluate(r, p, r.end, bounds[i], p))
      return false;
    p = tinybasic_syntax::skip(p, r.end);
    if (i < 3 && (p == r.end || *p++ != ','))
      return fail(r, Error::SYNTAX, p);
  }
  if (p != r.end)
    return fail(r, Error::SYNTAX, p);
  if (!r.execute)
    return true;
  if (!(bounds[0] < bounds[1]) || !(bounds[2] < bounds[3]) ||
      !mk_math::is_finite(bounds[1] - bounds[0]) || !mk_math::is_finite(bounds[3] - bounds[2]))
    return fail(r, Error::GRAPHICS_ARGUMENT);
  Request point = {};
  point.operation = Operation::PSET;
  point.count = 2;
  point.args[0] = point.args[1] = -1;
  if (!applied(r, dispatch(point)))
    return false;
  const unsigned width = (unsigned)dimension(Operation::WIDTH),
                 height = (unsigned)dimension(Operation::HEIGHT);
  restore.x = *r.x_variable;
  restore.restore_x = true;
  *r.pure = true;
  r.skip_domain = true;
  for (unsigned col = 0; col < width; ++col) {
    if (!r.poll(r))
      return false;
    *r.x_variable =
        bounds[0] + (bounds[1] - bounds[0]) * (width > 1 ? (double)col / (width - 1) : 0);
    double y = 0;
    p = r.begin;
    if (!r.evaluate(r, p, comma, y, p)) {
      if (r.error == Error::MATH || r.error == Error::DIV_ZERO) {
        r.error = Error::NONE;
        continue;
      }
      return false;
    }
    if (y < bounds[2] || y > bounds[3])
      continue;
    point.args[0] = col;
    point.args[1] = (bounds[3] - y) / (bounds[3] - bounds[2]) * (height - 1);
    if (!applied(r, dispatch(point)))
      return false;
  }
  return true;
}
} // namespace
bool process_native(NativeRequest &r) {
  r.error = Error::NONE;
  r.error_at = nullptr;
  switch (r.operation) {
  case NativeOperation::PRINT:
    return print(r);
  case NativeOperation::GRAPH:
    return graph(r);
  case NativeOperation::ARGUMENTS:
    return arguments(r);
  case NativeOperation::FLUSH:
    return flush(r);
  }
  return fail(r, Error::SYNTAX);
}
} // namespace basic_graphics
