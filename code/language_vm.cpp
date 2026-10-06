#include <string.h>

#include "language_bytecode.hpp"
#include "mk_math.hpp"

namespace language_vm {
namespace {
uint16_t word(const uint8_t* p) { return (uint16_t)(p[0] | ((uint16_t)p[1] << 8)); }
uint32_t dword(const uint8_t* p) {
  return (uint32_t)word(p) | ((uint32_t)word(p + 2) << 16);
}
uint8_t stride(const View& v) { return v.language == Language::BASIC ? 4 : 6; }
uint16_t record_pc(const View& v, uint16_t i) {
  return word(v.bytes + HEADER_SIZE + i * stride(v) + stride(v) - 2);
}
uint32_t record_number(const View& v, uint16_t i) {
  const uint8_t* p = v.bytes + HEADER_SIZE + i * stride(v);
  return v.language == Language::BASIC ? word(p) : dword(p);
}
uint16_t next(const View& v, uint16_t pc) {
  if (pc >= v.size) return 0;
  const uint8_t op = v.bytes[pc++];
  uint16_t n = 0;
  if (op >= (uint8_t)Op::CONST_0 && op <= (uint8_t)Op::CONST_15) return pc;
  switch ((Op)op) {
    case Op::CONST_I8:
    case Op::LOAD:
    case Op::STORE:
    case Op::LOAD_REF:
    case Op::STORE_REF:
    case Op::TARGET_REF:
    case Op::FUNCTION:
    case Op::NEXT_BASIC:
    case Op::PRINT_SEPARATOR:
    case Op::PRINT_END:
      n = 1;
      break;
    case Op::CONST_I16:
    case Op::CONST_DEC8:
    case Op::JUMP:
    case Op::JUMP_FALSE:
      n = 2;
      break;
    case Op::CONST_DEC16:
      n = 3;
      break;
    case Op::CONST_F64:
      n = 8;
      break;
    case Op::DO_FOCAL:
    case Op::FOR_FOCAL:
      n = 4;
      break;
    case Op::FOR_BASIC:
      n = 1;
      break;
    case Op::BRANCH:
      n = 6;
      break;
    case Op::PRINT_TEXT:
    case Op::READ_INPUT:
      if (v.size - pc < 2) return 0;
      n = word(v.bytes + pc);
      pc += 2;
      break;
    case Op::HALT:
    case Op::LINE:
    case Op::LOAD_ARRAY:
    case Op::STORE_ARRAY:
    case Op::NEG:
    case Op::NOT:
    case Op::ADD:
    case Op::SUB:
    case Op::MUL:
    case Op::DIV:
    case Op::POW:
    case Op::MOD:
    case Op::EQ:
    case Op::NE:
    case Op::LT:
    case Op::LE:
    case Op::GT:
    case Op::GE:
    case Op::AND:
    case Op::OR:
    case Op::XOR:
    case Op::CHECK:
    case Op::GOTO:
    case Op::GOSUB:
    case Op::RETURN:
    case Op::NEXT_FOCAL:
    case Op::PRINT_BEGIN:
    case Op::PRINT_NUMBER:
    case Op::PRINT_FORMAT:
    case Op::PRINT_FLUSH:
    case Op::WAIT:
    case Op::READ_KEY:
    case Op::CLEAR:
    case Op::TARGET_ARRAY:
      break;
    default:
      return 0;
  }
  return n <= v.size - pc ? (uint16_t)(pc + n) : (uint16_t)0;
}
bool array_index(double value, uint16_t capacity, uint16_t& index) {
  if (!mk_math::is_finite(value) || value < 0) return false;
  const double n = mk_math::floor(value + .5);
  if (n >= capacity || mk_math::fabs(value - n) > 1e-7) return false;
  index = (uint16_t)n;
  return true;
}
}  // namespace

Error inspect(const uint8_t* bytes, uint16_t length, View& out) {
  out = {};
  if (!bytes || length < HEADER_SIZE || length > MAX_IMAGE ||
      memcmp(bytes, "LBV1", 4) || bytes[4] != VERSION ||
      (bytes[5] != (uint8_t)Language::BASIC && bytes[5] != (uint8_t)Language::FOCAL) ||
      bytes[6] == 0 || bytes[6] > MAX_STACK || bytes[7] > 3 ||
      word(bytes + 8) != length)
    return Error::INVALID_IMAGE;
  for (uint8_t i = 24; i < HEADER_SIZE; ++i)
    if (bytes[i]) return Error::INVALID_IMAGE;
  View v = {bytes,
            length,
            word(bytes + 10),
            word(bytes + 12),
            word(bytes + 14),
            bytes[6],
            (Language)bytes[5],
            (bytes[7] & 1) != 0,
            (bytes[7] & 2) != 0};
  if ((v.expression
           ? v.lines != 0 || v.source_size > (v.language == Language::BASIC ? 64 : 111)
           : !v.lines) ||
      v.lines > (v.language == Language::BASIC ? 192 : 80) ||
      v.code != HEADER_SIZE + v.lines * stride(v) || v.code >= length ||
      !v.source_size || v.source_size > (v.language == Language::BASIC ? 3584 : 1536) ||
      checksum(bytes + HEADER_SIZE, length - HEADER_SIZE) != dword(bytes + 20))
    return Error::INVALID_IMAGE;
  uint8_t boundaries[(MAX_IMAGE + 7) / 8] = {};
  for (uint16_t pc = v.code; pc < length;) {
    boundaries[pc >> 3] |= (uint8_t)(1U << (pc & 7));
    const uint16_t following = next(v, pc);
    if (!following) return Error::INVALID_IMAGE;
    const Op op = (Op)bytes[pc];
    // Expression images share the opcode space, but must be side-effect-free
    // with respect to program variables and control frames. This permits the
    // hot INPUT evaluator to borrow the suspended program's stack safely.
    if (v.expression && op != Op::HALT && op != Op::CONST_I8 &&
        op != Op::CONST_I16 && op != Op::CONST_F64 && op != Op::CONST_DEC8 &&
        op != Op::CONST_DEC16 && op != Op::LOAD && op != Op::LOAD_REF &&
        op != Op::LOAD_ARRAY && !(op >= Op::NEG && op <= Op::CHECK) &&
        !(op >= Op::CONST_0 && op <= Op::CONST_15)) return Error::INVALID_IMAGE;
    if (((op == Op::LOAD || op == Op::STORE || op == Op::NEXT_BASIC ||
          op == Op::FOR_BASIC || op == Op::FOR_FOCAL) &&
         bytes[pc + 1] >= 26) ||
        ((op == Op::LOAD_REF || op == Op::STORE_REF || op == Op::TARGET_REF) &&
         bytes[pc + 1] >= 20) ||
        (op == Op::FUNCTION && bytes[pc + 1] > (uint8_t)Function::ROWS) ||
        (op == Op::READ_KEY && (v.expression || v.language != Language::BASIC)) ||
        (op == Op::PRINT_SEPARATOR && bytes[pc + 1] > 2) ||
        (op == Op::PRINT_END && bytes[pc + 1] > 1) ||
        (op == Op::FOR_FOCAL && bytes[pc + 4] > 1))
      return Error::INVALID_IMAGE;
    pc = following;
  }
  auto target = [&](uint16_t pc) {
    return pc == 0xFFFF ||
           (pc >= v.code && pc < length && (boundaries[pc >> 3] & (1U << (pc & 7))));
  };
  for (uint16_t i = 0; i < v.lines; ++i) {
    const uint32_t number = record_number(v, i);
    if (!number || number > (v.language == Language::BASIC ? 32767U : 999999U) ||
        (i && number <= record_number(v, (uint16_t)(i - 1))) ||
        !target(record_pc(v, i)) || record_pc(v, i) == 0xFFFF ||
        (!i && record_pc(v, i) != v.code) ||
        (i && record_pc(v, i) <= record_pc(v, (uint16_t)(i - 1))))
      return Error::INVALID_IMAGE;
  }
  for (uint16_t pc = v.code; pc < length; pc = next(v, pc)) {
    const Op op = (Op)bytes[pc];
    if ((op == Op::JUMP || op == Op::JUMP_FALSE) && !target(word(bytes + pc + 1)))
      return Error::INVALID_IMAGE;
    if (op == Op::DO_FOCAL &&
        (!target(word(bytes + pc + 1)) ||
         !target(word(bytes + pc + 3) == 0xFFFF
                     ? 0xFFFF
                     : (uint16_t)(word(bytes + pc + 3) & 0x7FFF))))
      return Error::INVALID_IMAGE;
    if (op == Op::FOR_FOCAL && !target(word(bytes + pc + 2)))
      return Error::INVALID_IMAGE;
    if (op == Op::BRANCH)
      for (uint8_t i = 0; i < 3; ++i)
        if (!target(word(bytes + pc + 1 + i * 2))) return Error::INVALID_IMAGE;
  }
  out = v;
  return Error::NONE;
}

uint16_t line_pc(const View& v, uint32_t number) {
  for (uint16_t i = 0; i < v.lines; ++i)
    if (record_number(v, i) == number) return record_pc(v, i);
  return 0xFFFF;
}
uint32_t source_line(const View& v, uint16_t pc) {
  uint32_t number = 0;
  for (uint16_t i = 0; i < v.lines && record_pc(v, i) <= pc; ++i)
    number = record_number(v, i);
  return number;
}

RunResult run(const View& v, State& s, const Services& host, uint32_t limit,
              bool resume) {
  return run(v, static_cast<Continuation&>(s), static_cast<const Bindings&>(s),
             host, limit, resume);
}
RunResult run(const View& v, Continuation& s, const Bindings& data,
              const Services& host, uint32_t limit, bool resume) {
  if (!v.bytes || !data.variables || !data.stack || data.stack_capacity < v.stack ||
      data.stack_capacity > MAX_STACK)
    return {Error::INVALID_IMAGE, 0, 0, 0};
  if (!resume) {
    s.pc = v.code;
    s.sp = s.call_count = s.loop_count = 0;
  } else if (s.pc < v.code || s.pc >= v.size || s.sp > data.stack_capacity ||
             s.call_count > (v.language == Language::BASIC ? MAX_CALLS : 8) ||
             s.loop_count > MAX_LOOPS) {
    return {Error::INVALID_IMAGE, 0, 0, 0};
  }
  if (resume) {
    for (uint8_t i = 0; i < s.call_count; ++i) {
      const auto& f = s.calls[i];
      if (f.resume < v.code || f.resume >= v.size || f.loops > MAX_LOOPS ||
          (f.end && (f.end < v.code || f.end >= v.size)))
        return {Error::INVALID_IMAGE, 0, 0, 0};
    }
    for (uint8_t i = 0; i < s.loop_count; ++i) {
      const auto& f = s.loops[i];
      if (f.variable >= 26 || f.body < v.code || f.body >= v.size ||
          (f.end && (f.end < v.code || f.end >= v.size)))
        return {Error::INVALID_IMAGE, 0, 0, 0};
    }
  }
  Error error = Error::NONE;
  uint32_t steps = 0;
  uint16_t instruction = s.pc;
  auto push = [&](double value) {
    if (s.sp >= data.stack_capacity)
      error = Error::STACK;
    else
      data.stack[s.sp++] = value;
  };
  auto pop = [&]() -> double {
    if (!s.sp) {
      error = Error::STACK;
      return 0;
    }
    return data.stack[--s.sp];
  };
  auto event = [&](Event e, const char* p, uint16_t n, double& value) {
    if (!host.event || !host.event(host.context, e, p, n, value)) error = Error::IO;
  };
  auto jump = [&](uint16_t to) {
    if (to < v.code || to >= v.size)
      error = Error::LINE;
    else
      s.pc = to;
  };
  auto call = [&](uint16_t to, uint16_t end) {
    const uint8_t maximum = v.language == Language::BASIC ? MAX_CALLS : 8;
    if (s.call_count >= maximum)
      error = Error::STACK;
    else {
      s.calls[s.call_count++] = {s.pc, (uint16_t)(end & 0x7FFF), s.loop_count,
                                 (end & 0x8000) != 0};
      jump(to);
    }
  };
  while (error == Error::NONE) {
    if (s.call_count && s.calls[s.call_count - 1].end &&
        s.pc >= s.calls[s.call_count - 1].end) {
      const auto frame = s.calls[--s.call_count];
      s.pc = frame.resume;
      s.loop_count = frame.loops;
    }
    if (s.pc >= v.size) {
      error = Error::INVALID_IMAGE;
      break;
    }
    instruction = s.pc;
    if (limit && steps == limit) {
      error = Error::LIMIT;
      break;
    }
    if ((steps++ & 31U) == 0 && host.service && !host.service(host.context)) {
      error = Error::STOPPED;
      break;
    }
    const uint16_t after = next(v, s.pc);
    if (!after) {
      error = Error::INVALID_IMAGE;
      break;
    }
    const uint8_t* p = v.bytes + s.pc + 1;
    const Op op = (Op)v.bytes[s.pc];
    s.pc = after;
    if (op >= Op::CONST_0 && op <= Op::CONST_15) {
      push((uint8_t)op - (uint8_t)Op::CONST_0);
      continue;
    }
    double a = 0, b = 0, value = 0;
    switch (op) {
      case Op::HALT: {
        if (s.sp != (v.expression ? 1 : 0))
          error = Error::STACK;
        else if (!v.expression && host.event)
          event(Event::FINISH, nullptr, 0, value);
        return {error, instruction, source_line(v, instruction), steps};
      }
      case Op::LINE:
        if (s.sp) error = Error::STACK;
        if (host.service && !host.service(host.context)) error = Error::STOPPED;
        break;
      case Op::CONST_I8:
        push((int8_t)*p);
        break;
      case Op::CONST_I16:
        push((int16_t)word(p));
        break;
      case Op::CONST_DEC8:
      case Op::CONST_DEC16: {
        value = op == Op::CONST_DEC8 ? *p : word(p);
        const int exponent = (int8_t)p[op == Op::CONST_DEC8 ? 1 : 2];
        if (exponent < 0)
          value /= mk_math::pow10_int(-exponent);
        else
          value *= mk_math::pow10_int(exponent);
        push(value);
        break;
      }
      case Op::CONST_F64: {
        uint64_t bits = 0;
        for (uint8_t i = 0; i < 8; ++i) bits |= (uint64_t)p[i] << (i * 8);
        memcpy(&value, &bits, 8);
        push(value);
        break;
      }
      case Op::LOAD:
        if (*p >= 26)
          error = Error::INVALID_IMAGE;
        else
          push(data.variables[*p]);
        break;
      case Op::STORE:
        value = pop();
        if (*p >= 26)
          error = Error::INVALID_IMAGE;
        else if (error == Error::NONE)
          data.variables[*p] = value;
        break;
      case Op::LOAD_REF:
      case Op::STORE_REF:
        if (op == Op::STORE_REF) value = pop();
        if (error == Error::NONE &&
            (!host.reference ||
             !host.reference(host.context, op == Op::STORE_REF, *p, value)))
          error = Error::REGISTER;
        if (op == Op::LOAD_REF && error == Error::NONE) push(value);
        break;
      case Op::LOAD_ARRAY:
      case Op::STORE_ARRAY: {
        if (op == Op::STORE_ARRAY) value = pop();
        a = pop();
        uint16_t index = 0;
        if (!data.array || !array_index(a, data.array_count, index)) error = Error::VARIABLE;
        if (error == Error::NONE) {
          if (op == Op::STORE_ARRAY)
            data.array[index] = value;
          else
            push(data.array[index]);
        }
        break;
      }
      case Op::TARGET_ARRAY: {
        uint16_t index = 0;
        if (!s.sp)
          error = Error::STACK;
        else if (!data.array || !array_index(data.stack[s.sp - 1], data.array_count, index))
          error = Error::VARIABLE;
        break;
      }
      case Op::TARGET_REF:
        value = *p;
        event(Event::TARGET_REF, nullptr, 0, value);
        break;
      case Op::NEG:
        a = pop();
        push(-a);
        break;
      case Op::NOT:
        a = pop();
        push(a == 0);
        break;
      case Op::CHECK:
        if (!s.sp)
          error = Error::STACK;
        else if (!mk_math::is_finite(data.stack[s.sp - 1]))
          error = Error::MATH;
        break;
      case Op::ADD:
      case Op::SUB:
      case Op::MUL:
      case Op::DIV:
      case Op::POW:
      case Op::MOD:
      case Op::EQ:
      case Op::NE:
      case Op::LT:
      case Op::LE:
      case Op::GT:
      case Op::GE:
      case Op::AND:
      case Op::OR:
      case Op::XOR:
        b = pop();
        a = pop();
        switch (op) {
          case Op::ADD:
            value = a + b;
            break;
          case Op::SUB:
            value = a - b;
            break;
          case Op::MUL:
            value = a * b;
            break;
          case Op::DIV:
            if (b == 0)
              error = Error::MATH;
            else
              value = a / b;
            break;
          case Op::POW:
            if (host.math)
              value = host.math(host.context, (Function)255, a, b);
            else
              error = Error::MATH;
            break;
          case Op::MOD:
            if (b == 0)
              error = Error::MATH;
            else
              value = a - mk_math::floor(a / b) * b;
            break;
          case Op::EQ:
            value = a == b;
            break;
          case Op::NE:
            value = a != b;
            break;
          case Op::LT:
            value = a < b;
            break;
          case Op::LE:
            value = a <= b;
            break;
          case Op::GT:
            value = a > b;
            break;
          case Op::GE:
            value = a >= b;
            break;
          case Op::AND:
            value = a != 0 && b != 0;
            break;
          case Op::OR:
            value = a != 0 || b != 0;
            break;
          case Op::XOR:
            value = (a != 0) != (b != 0);
            break;
          default:
            break;
        }
        if (error == Error::NONE) push(value);
        break;
      case Op::FUNCTION: {
        const Function f = (Function)*p;
        if (f != Function::RND && f != Function::PI_VALUE && f < Function::SIZE) a = pop();
        if (f == Function::MAX) {
          b = a;
          a = pop();
        }
        switch (f) {
          case Function::ABS:
            value = mk_math::fabs(a);
            break;
          case Function::INT:
            value = mk_math::floor(a);
            break;
          case Function::FRAC:
            value = mk_math::frac(a);
            break;
          case Function::ROUND:
            value = mk_math::round_half(a);
            break;
          case Function::SGN:
            value = a > 0 ? 1 : a < 0 ? -1 : 0;
            break;
          case Function::MAX:
            value = a > b ? a : b;
            break;
          case Function::RND:
          case Function::RND_LIMIT:
            if (f == Function::RND_LIMIT && (!(a >= 1) || !mk_math::is_finite(a))) {
              error = Error::MATH;
              break;
            }
            if (!host.random) {
              error = Error::IO;
              break;
            }
            value = host.random(host.context);
            if (f == Function::RND_LIMIT)
              value = 1 + mk_math::floor(value * mk_math::floor(a));
            break;
          case Function::PI_VALUE:
            value = 3.14159265358979323846;
            break;
          case Function::SIZE:
          case Function::COLS:
          case Function::ROWS:
            if (!host.value)
              error = Error::IO;
            else
              value = host.value(host.context, f);
            break;
          default:
            if (!host.math)
              error = Error::MATH;
            else
              value = host.math(host.context, f, a, 0);
            break;
        }
        if (error == Error::NONE) push(value);
        break;
      }
      case Op::JUMP:
        if (word(p) < v.code || word(p) >= v.size) {
          error = Error::LINE;
          break;
        }
        if (v.language == Language::FOCAL) {
          bool swallowed = false;
          while (s.call_count) {
            const auto frame = s.calls[--s.call_count];
            s.loop_count = frame.loops;
            if (!frame.group) {
              s.pc = frame.resume;
              swallowed = true;
              break;
            }
          }
          if (!swallowed) {
            s.loop_count = 0;
            jump(word(p));
          }
        } else
          jump(word(p));
        break;
      case Op::JUMP_FALSE:
        a = pop();
        if (error == Error::NONE && !a) jump(word(p));
        break;
      case Op::GOTO:
      case Op::GOSUB:
        a = pop();
        b = mk_math::floor(a + .5);
        if (!mk_math::is_finite(a) || a < 1 || a > 32767 || mk_math::fabs(a - b) > 1e-7)
          error = Error::LINE;
        else if (error == Error::NONE) {
          const uint16_t to = line_pc(v, (uint32_t)b);
          if (op == Op::GOTO)
            jump(to);
          else
            call(to, 0);
        }
        break;
      case Op::RETURN:
        if (!s.call_count)
          error = Error::RETURN;
        else {
          const auto frame = s.calls[--s.call_count];
          s.pc = frame.resume;
          if (v.language == Language::FOCAL) s.loop_count = frame.loops;
        }
        break;
      case Op::DO_FOCAL:
        call(word(p), word(p + 2));
        break;
      case Op::BRANCH:
        a = pop();
        if (error == Error::NONE) {
          const uint16_t to = word(p + (a < 0 ? 0 : a == 0 ? 2 : 4));
          if (to < v.code || to >= v.size) {
            error = Error::LINE;
            break;
          }
          bool swallowed = false;
          while (s.call_count) {
            const auto frame = s.calls[--s.call_count];
            s.loop_count = frame.loops;
            if (!frame.group) {
              s.pc = frame.resume;
              swallowed = true;
              break;
            }
          }
          if (!swallowed) {
            s.loop_count = 0;
            jump(word(p + (a < 0 ? 0 : a == 0 ? 2 : 4)));
          }
        }
        break;
      case Op::FOR_BASIC:
      case Op::FOR_FOCAL: {
        double step = pop(), end = pop(), start = pop();
        if (op == Op::FOR_FOCAL && p[3]) {
          const double temp = step;
          step = end;
          end = temp;
        }
        const uint8_t var = *p;
        if (var >= 26) {
          error = Error::INVALID_IMAGE;
          break;
        }
        if (error != Error::NONE) break;
        if (op == Op::FOR_FOCAL && step == 0) {
          error = Error::FOR;
          break;
        }
        bool outside = step < 0 ? start < end : start > end;
        if (outside && op == Op::FOR_FOCAL) {
          jump(word(p + 1));
          break;
        }
        data.variables[var] = start;
        if (outside) {
          uint16_t scan = s.pc;
          uint8_t depth = 0;
          uint8_t vars[MAX_LOOPS] = {};
          bool found = false;
          while (scan < v.size && error == Error::NONE) {
            const Op candidate = (Op)v.bytes[scan];
            const uint16_t following = next(v, scan);
            if (!following) {
              error = Error::INVALID_IMAGE;
              break;
            }
            if (candidate == Op::FOR_BASIC) {
              if (depth == MAX_LOOPS) {
                error = Error::FOR;
                break;
              }
              vars[depth++] = v.bytes[scan + 1];
            }
            if (candidate == Op::NEXT_BASIC) {
              const uint8_t variable = v.bytes[scan + 1];
              if (depth) {
                if (vars[depth - 1] != variable) {
                  error = Error::FOR;
                  break;
                }
                --depth;
              } else {
                if (variable != var)
                  error = Error::FOR;
                else {
                  found = true;
                  s.pc = following;
                }
                break;
              }
            }
            scan = following;
          }
          if (!found && error == Error::NONE) error = Error::FOR;
          break;
        }
        if (op == Op::FOR_BASIC)
          for (uint8_t i = s.loop_count; i; i--)
            if (s.loops[i - 1].variable == var) {
              s.loop_count = (uint8_t)(i - 1);
              break;
            }
        if (s.loop_count == MAX_LOOPS) {
          error = Error::STACK;
          break;
        }
        s.loops[s.loop_count++] = {
            end, step, start, s.pc, op == Op::FOR_FOCAL ? word(p + 1) : (uint16_t)0,
            var};
        break;
      }
      case Op::NEXT_BASIC:
      case Op::NEXT_FOCAL: {
        if (host.service && !host.service(host.context)) {
          error = Error::STOPPED;
          break;
        }
        if (op == Op::NEXT_BASIC)
          while (s.loop_count && s.loops[s.loop_count - 1].variable != *p)
            --s.loop_count;
        if (!s.loop_count) {
          error = Error::FOR;
          break;
        }
        LoopFrame& frame = s.loops[s.loop_count - 1];
        const double old =
            op == Op::NEXT_FOCAL ? frame.value : data.variables[frame.variable];
        const double following = old + frame.step;
        if (op == Op::NEXT_FOCAL && old == frame.limit) {
          --s.loop_count;
          break;
        }
        if (op == Op::NEXT_FOCAL &&
            (!mk_math::is_finite(following) || following == old)) {
          error = Error::FOR;
          break;
        }
        const bool inside =
            frame.step < 0 ? following >= frame.limit : following <= frame.limit;
        if (op == Op::NEXT_BASIC || inside) data.variables[frame.variable] = following;
        if (inside) {
          frame.value = following;
          s.pc = frame.body;
        } else
          --s.loop_count;
        break;
      }
      case Op::PRINT_BEGIN:
        event(Event::PRINT_BEGIN, nullptr, 0, value);
        break;
      case Op::PRINT_TEXT:
        event(Event::TEXT, (const char*)p + 2, word(p), value);
        break;
      case Op::PRINT_NUMBER:
        value = pop();
        if (error == Error::NONE) event(Event::NUMBER, nullptr, 0, value);
        break;
      case Op::PRINT_FORMAT:
        value = pop();
        if (error == Error::NONE) event(Event::FORMAT, nullptr, 0, value);
        break;
      case Op::PRINT_SEPARATOR:
        event(Event::SEPARATOR, nullptr, *p, value);
        break;
      case Op::PRINT_FLUSH:
        event(Event::FLUSH, nullptr, 0, value);
        break;
      case Op::PRINT_END:
        event(Event::PRINT_END, nullptr, *p, value);
        break;
      case Op::READ_INPUT:
        if (host.yield_input)
          return {Error::YIELDED, instruction, source_line(v, instruction), steps};
        event(Event::READ_INPUT, (const char*)p + 2, word(p), value);
        if (error == Error::NONE) push(value);
        break;
      case Op::READ_KEY:
        event(Event::READ_KEY, nullptr, 0, value);
        if (error == Error::NONE) push(value);
        break;
      case Op::WAIT:
        event(Event::WAIT, nullptr, 0, value);
        break;
      case Op::CLEAR:
        event(Event::CLEAR, nullptr, 0, value);
        break;
      default:
        error = Error::INVALID_IMAGE;
        break;
    }
  }
  return {error, instruction, source_line(v, instruction), steps};
}

const char* error_name(Error e) {
  static const char* const names[] = {
      "OK",       "SYNTAX",        "LINE",   "FULL",    "VARIABLE",
      "FUNCTION", "FOR",           "RETURN", "STACK",   "MATH",
      "REGISTER", "INVALID_IMAGE", "IO",     "STOPPED", "LIMIT", "YIELDED"};
  return (uint8_t)e < sizeof(names) / sizeof(names[0]) ? names[(uint8_t)e] : "UNKNOWN";
}
}  // namespace language_vm
