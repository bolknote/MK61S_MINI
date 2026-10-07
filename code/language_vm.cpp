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
  if (pc >= v.end) return 0;
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
    case Op::SOURCE_POS:
    case Op::CONST_I16:
    case Op::CONST_DEC8:
    case Op::JUMP:
    case Op::JUMP_FALSE:
      n = 2;
      break;
    case Op::CONST_DEC16:
      n = 3;
      break;
    case Op::PRINT_RESOURCE:
    case Op::INPUT_RESOURCE:
      n = 2;
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
    case Op::DATA:
    case Op::ON_GOTO:
    case Op::ON_GOSUB: {
      if (v.end - pc < 2) return 0;
      const uint16_t count = word(v.bytes + pc);
      pc += 2;
      const uint16_t width = (Op)op == Op::DATA ? 1 : 2;
      if (count == 0 || count > (v.end - pc) / width) return 0;
      return (uint16_t)(pc + count * width);
    }
    case Op::PRINT_TEXT:
    case Op::READ_INPUT:
      if (v.end - pc < 2) return 0;
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
    case Op::READ_DATA:
    case Op::RESTORE_DATA:
    case Op::FOR_ARRAY:
    case Op::NEXT_ARRAY:
      break;
    default:
      return 0;
  }
  return n <= v.end - pc ? (uint16_t)(pc + n) : (uint16_t)0;
}
bool constant_value(const View& v, uint16_t pc, double& value) {
  const Op op = (Op)v.bytes[pc];
  const uint8_t* p = v.bytes + pc + 1;
  if (op >= Op::CONST_0 && op <= Op::CONST_15) {
    value = (uint8_t)op - (uint8_t)Op::CONST_0;
    return true;
  }
  switch (op) {
    case Op::CONST_I8:
      value = (int8_t)*p;
      return true;
    case Op::CONST_I16:
      value = (int16_t)word(p);
      return true;
    case Op::CONST_DEC8:
    case Op::CONST_DEC16: {
      value = op == Op::CONST_DEC8 ? *p : word(p);
      const int exponent = (int8_t)p[op == Op::CONST_DEC8 ? 1 : 2];
      if (exponent < 0)
        value /= mk_math::pow10_int(-exponent);
      else
        value *= mk_math::pow10_int(exponent);
      return true;
    }
    case Op::CONST_F64: {
      uint64_t bits = 0;
      for (uint8_t i = 0; i < 8; ++i) bits |= (uint64_t)p[i] << (i * 8);
      memcpy(&value, &bits, 8);
      return true;
    }
    default:
      return false;
  }
}
bool data_value(const View& v,uint16_t at,uint16_t end,double& value,uint16_t& following) {
  following=next(v,at);
  if(!following || following>end || !constant_value(v,at,value)) return false;
  if(following<end && (Op)v.bytes[following]==Op::NEG) {
    value=-value;
    ++following;
  }
  return mk_math::is_finite(value);
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
      bytes[6] == 0 || bytes[6] > MAX_STACK || bytes[7] > 7 ||
      word(bytes + 8) != length)
    return Error::INVALID_IMAGE;
  if (bytes[7] & 4) {
    if ((bytes[7] & 1) || word(bytes + 24) == 0xFFFF)
      return Error::INVALID_IMAGE;
  } else for (uint8_t i = 24; i < HEADER_SIZE; ++i)
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
  v.end = (bytes[7] & 4) ? word(bytes + 30) : length;
  if (v.end > length || ((bytes[7] & 4) && v.end == length)) return Error::INVALID_IMAGE;
  if ((v.expression
           ? v.lines != 0 || v.source_size > (v.language == Language::BASIC ? 64 : 111)
           : !v.lines) ||
      v.lines > (v.language == Language::BASIC ? 192 : 80) ||
      v.code != HEADER_SIZE + v.lines * stride(v) || v.code >= v.end ||
      !v.source_size || v.source_size > (v.language == Language::BASIC ? 3584 : 1536) ||
      checksum(bytes + HEADER_SIZE, length - HEADER_SIZE) != dword(bytes + 20))
    return Error::INVALID_IMAGE;
  uint8_t boundaries[(MAX_IMAGE + 7) / 8] = {};
  // The same bitmap covers instructions and separately delimited recipes.
  for (uint16_t at = v.end; at < length;) {
    if (length - at < 3 || bytes[at + 2] > (length - at - 3) / 3)
      return Error::INVALID_IMAGE;
    boundaries[at >> 3] |= (uint8_t)(1U << (at & 7));
    unsigned total = 0;
    for (uint8_t i = 0; i < bytes[at + 2]; ++i) {
      const auto* p = bytes + at + 3 + i * 3;
      const uint16_t offset = word(p); const uint8_t n = p[2];
      if (!n || ((offset & 0x8000) ? (offset & 0x7F00) || n != 1 :
                       offset > v.source_size || n > v.source_size - offset))
        return Error::INVALID_IMAGE;
      total += n;
    }
    if (total != word(bytes + at)) return Error::INVALID_IMAGE;
    at += (uint16_t)(3 + bytes[at + 2] * 3);
  }
  for (uint16_t pc = v.code; pc < v.end;) {
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
    if (op >= Op::DATA && op <= Op::SOURCE_POS && v.language != Language::BASIC)
      return Error::INVALID_IMAGE;
    if (op == Op::PRINT_RESOURCE || op == Op::INPUT_RESOURCE) {
      const uint32_t at = (uint32_t)v.end + word(bytes + pc + 1);
      if (!(bytes[7] & 4) || at >= length ||
          !(boundaries[at >> 3] & (1U << (at & 7))) ||
          (op == Op::INPUT_RESOURCE && word(bytes + at) > 95))
        return Error::INVALID_IMAGE;
    }
    if (op == Op::DATA) {
      const uint16_t end = (uint16_t)(pc + 3 + word(bytes + pc + 1));
      for (uint16_t at = (uint16_t)(pc + 3); at < end;) {
        uint16_t following=0;
        double value=0;
        if(!data_value(v,at,end,value,following)) return Error::INVALID_IMAGE;
        at = following;
      }
    }
    if (op == Op::SOURCE_POS && (!word(bytes + pc + 1) || word(bytes + pc + 1) > v.source_size))
      return Error::INVALID_IMAGE;
    if (op == Op::ON_GOTO || op == Op::ON_GOSUB)
      for (uint16_t i = 0; i < word(bytes + pc + 1); ++i) {
        const uint16_t line = word(bytes + pc + 3 + i * 2);
        if (!line || line > 32767) return Error::INVALID_IMAGE;
      }
    pc = following;
  }
  auto target = [&](uint16_t pc) {
    return pc == 0xFFFF ||
           (pc >= v.code && pc < v.end && (boundaries[pc >> 3] & (1U << (pc & 7))));
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
  for (uint16_t pc = v.code; pc < v.end; pc = next(v, pc)) {
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

uint16_t source_column(const View& v, uint16_t pc) {
  uint16_t column = 0;
  for (uint16_t at = v.code; at <= pc && at < v.end;) {
    const uint16_t following = next(v, at);
    if (!following) return 0;
    if ((Op)v.bytes[at] == Op::SOURCE_POS) column = word(v.bytes + at + 1);
    if ((Op)v.bytes[at] == Op::LINE) column = 0;
    at = following;
  }
  return column;
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
    s.data_pc = v.code;
    s.data_index = 0;
  } else if (s.pc < v.code || s.pc >= v.end || s.sp > data.stack_capacity ||
             s.call_count > (v.language == Language::BASIC ? MAX_CALLS : 8) ||
             s.loop_count > MAX_LOOPS || s.data_pc < v.code || s.data_pc > v.end) {
    return {Error::INVALID_IMAGE, 0, 0, 0};
  }
  if (resume) {
    uint16_t cursor = v.code;
    while (cursor < s.data_pc) {
      const uint16_t following = next(v, cursor);
      if (!following) return {Error::INVALID_IMAGE, 0, 0, 0};
      cursor = following;
    }
    if (cursor != s.data_pc ||
        (s.data_index && (cursor >= v.end || (Op)v.bytes[cursor] != Op::DATA ||
                          s.data_index > word(v.bytes + cursor + 1))))
      return {Error::INVALID_IMAGE, 0, 0, 0};
    if (s.data_index) {
      uint16_t at = (uint16_t)(s.data_pc + 3), target = (uint16_t)(at + s.data_index);
      while (at < target) {
        uint16_t following=0;
        double value=0;
        const uint16_t end=(uint16_t)(s.data_pc+3+word(v.bytes+s.data_pc+1));
        if(!data_value(v,at,end,value,following)) return {Error::INVALID_IMAGE,0,0,0};
        at=following;
      }
      if (at != target) return {Error::INVALID_IMAGE, 0, 0, 0};
    }
    for (uint8_t i = 0; i < s.call_count; ++i) {
      const auto& f = s.calls[i];
      if (f.resume < v.code || f.resume >= v.end || f.loops > MAX_LOOPS ||
          (f.end && (f.end < v.code || f.end >= v.end)))
        return {Error::INVALID_IMAGE, 0, 0, 0};
    }
    for (uint8_t i = 0; i < s.loop_count; ++i) {
      const auto& f = s.loops[i];
      if (((f.variable & 0x8000U) ? (!data.array || (f.variable & 0x7FFFU) >= data.array_count)
                                  : f.variable >= 26) ||
          f.body < v.code || f.body >= v.end || (f.end && (f.end < v.code || f.end >= v.end)))
        return {Error::INVALID_IMAGE, 0, 0, 0};
    }
  }
  Error error = Error::NONE;
  uint32_t steps = 0;
  uint16_t instruction = s.pc;
  auto push = [&](double value) {
    if (v.language == Language::BASIC && !mk_math::is_finite(value))
      error = Error::MATH;
    else if (s.sp >= data.stack_capacity)
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
    if (to < v.code || to >= v.end)
      error = Error::LINE;
    else
      s.pc = to;
  };
  auto call = [&](uint16_t to, uint16_t end) {
    const uint8_t maximum = v.language == Language::BASIC ? MAX_CALLS : 8;
    if (s.call_count >= maximum)
      error = v.language == Language::BASIC ? Error::CALL_STACK : Error::STACK;
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
    if (s.pc >= v.end) {
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
    double a = 0, b = 0, value = 0;
    if (constant_value(v, instruction, value)) {
      push(value);
      continue;
    }
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
        // The instruction loop already services USB/keyboard/watchdog before
        // the first instruction and at most 32 instructions apart. Polling
        // again on every short BASIC line repeats that work unnecessarily.
        break;
      case Op::SOURCE_POS:
      case Op::DATA:
        break;
      case Op::READ_DATA: {
        while (s.data_pc < v.end) {
          const uint16_t following = next(v, s.data_pc);
          if (!following) {
            error = Error::INVALID_IMAGE;
            break;
          }
          if ((Op)v.bytes[s.data_pc] == Op::DATA) {
            const uint16_t count = word(v.bytes + s.data_pc + 1);
            if (s.data_index < count) {
              const uint16_t literal = (uint16_t)(s.data_pc + 3 + s.data_index);
              uint16_t following=0;
              if(!data_value(v,literal,(uint16_t)(s.data_pc+3+count),value,following)) {
                error = Error::INVALID_IMAGE;
                break;
              }
              s.data_index = (uint16_t)(s.data_index + following - literal);
              push(value);
              break;
            }
          }
          s.data_pc = following;
          s.data_index = 0;
        }
        if (s.data_pc == v.end) error = Error::DATA_END;
        break;
      }
      case Op::RESTORE_DATA: {
        a = pop();
        b = mk_math::floor(a + .5);
        if (error != Error::NONE) break;
        if (!mk_math::is_finite(a) || a < 0 || a > 32767 || mk_math::fabs(a - b) > 1e-7) {
          error = Error::LINE_NUMBER;
          break;
        }
        const uint16_t to = a == 0 ? v.code : line_pc(v, (uint32_t)b);
        if (to == 0xFFFF) {
          error = Error::MISSING_LINE;
          break;
        }
        s.data_pc = to;
        s.data_index = 0;
        break;
      }
      case Op::ON_GOTO:
      case Op::ON_GOSUB: {
        a = pop();
        if (error != Error::NONE) break;
        if (!mk_math::is_finite(a) || a < 0 || a != mk_math::floor(a)) {
          error = Error::ON_INDEX;
          break;
        }
        const uint16_t count = word(p);
        if (a == 0 || a > count) break;
        const uint16_t to = line_pc(v, word(p + 2 + ((uint16_t)a - 1) * 2));
        if (to == 0xFFFF)
          error = Error::MISSING_LINE;
        else if (op == Op::ON_GOSUB)
          call(to, 0);
        else
          jump(to);
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
        if (!data.array || !array_index(a, data.array_count, index))
          error = v.language == Language::BASIC ? Error::ARRAY_RANGE : Error::VARIABLE;
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
          error = v.language == Language::BASIC ? Error::ARRAY_RANGE : Error::VARIABLE;
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
              error = v.language == Language::BASIC ? Error::DIV_ZERO : Error::MATH;
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
              error = v.language == Language::BASIC ? Error::DIV_ZERO : Error::MATH;
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
        if (word(p) < v.code || word(p) >= v.end) {
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
          error = v.language == Language::BASIC ? Error::LINE_NUMBER : Error::LINE;
        else if (error == Error::NONE) {
          const uint16_t to = line_pc(v, (uint32_t)b);
          if (to == 0xFFFF && v.language == Language::BASIC)
            error = Error::MISSING_LINE;
          else if (op == Op::GOTO)
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
          s.loop_count = frame.loops;
        }
        break;
      case Op::DO_FOCAL:
        call(word(p), word(p + 2));
        break;
      case Op::BRANCH:
        a = pop();
        if (error == Error::NONE) {
          const uint16_t to = word(p + (a < 0 ? 0 : a == 0 ? 2 : 4));
          if (to < v.code || to >= v.end) {
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
      case Op::FOR_ARRAY:
      case Op::FOR_FOCAL: {
        double step = pop(), end = pop(), start = pop();
        uint16_t var = *p;
        if (op == Op::FOR_ARRAY) {
          a = pop();
          uint16_t index = 0;
          if (!data.array || !array_index(a, data.array_count, index) || index >= 0x8000U) {
            error = Error::ARRAY_RANGE;
            break;
          }
          var = (uint16_t)(0x8000U | index);
        } else if (var >= 26) {
          error = Error::INVALID_IMAGE;
          break;
        }
        if (op == Op::FOR_FOCAL && p[3]) {
          const double temp = step;
          step = end;
          end = temp;
        }
        if (error != Error::NONE) break;
        if (op == Op::FOR_FOCAL && step == 0) {
          error = Error::FOR;
          break;
        }
        const bool outside = step < 0 ? start < end : start > end;
        if (outside && op == Op::FOR_FOCAL) {
          jump(word(p + 1));
          break;
        }
        double& counter = var & 0x8000U ? data.array[var & 0x7FFFU] : data.variables[var];
        counter = start;
        if (outside) {
          uint16_t scan = s.pc;
          uint8_t depth = 0;
          uint16_t vars[MAX_LOOPS] = {};
          bool found = false;
          while (scan < v.end && error == Error::NONE) {
            const Op candidate = (Op)v.bytes[scan];
            const uint16_t following = next(v, scan);
            if (!following) {
              error = Error::INVALID_IMAGE;
              break;
            }
            if (candidate == Op::FOR_BASIC || candidate == Op::FOR_ARRAY) {
              if (depth == MAX_LOOPS) {
                error = Error::LOOP_STACK;
                break;
              }
              vars[depth++] = candidate == Op::FOR_ARRAY ? 0x8000U : v.bytes[scan + 1];
            }
            if (candidate == Op::NEXT_BASIC || candidate == Op::NEXT_ARRAY) {
              const uint16_t variable = candidate == Op::NEXT_ARRAY ? 0x8000U : v.bytes[scan + 1];
              if (depth) {
                if (vars[depth - 1] != variable) {
                  error = Error::FOR;
                  break;
                }
                --depth;
              } else {
                if (variable != (var & 0x8000U ? 0x8000U : var))
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
          if (!found && error == Error::NONE) error = Error::NEXT_WITHOUT_FOR;
          break;
        }
        const uint8_t base =
            v.language == Language::BASIC && s.call_count ? s.calls[s.call_count - 1].loops : 0;
        if (op != Op::FOR_FOCAL)
          for (uint8_t i = s.loop_count; i > base; --i)
            if (s.loops[i - 1].variable == var) {
              s.loop_count = (uint8_t)(i - 1);
              break;
            }
        if (s.loop_count == MAX_LOOPS) {
          error = v.language == Language::BASIC ? Error::LOOP_STACK : Error::STACK;
          break;
        }
        s.loops[s.loop_count++] = {
            end, step, start, s.pc, op == Op::FOR_FOCAL ? word(p + 1) : (uint16_t)0, var};
        break;
      }
      case Op::NEXT_BASIC:
      case Op::NEXT_ARRAY:
      case Op::NEXT_FOCAL: {
        if (host.service && !host.service(host.context)) {
          error = Error::STOPPED;
          break;
        }
        uint16_t var = *p;
        if (op == Op::NEXT_ARRAY) {
          a = pop();
          uint16_t index = 0;
          if (!data.array || !array_index(a, data.array_count, index) || index >= 0x8000U) {
            error = Error::ARRAY_RANGE;
            break;
          }
          var = (uint16_t)(0x8000U | index);
        }
        const uint8_t base =
            v.language == Language::BASIC && s.call_count ? s.calls[s.call_count - 1].loops : 0;
        if (op != Op::NEXT_FOCAL)
          while (s.loop_count > base && s.loops[s.loop_count - 1].variable != var) --s.loop_count;
        if (s.loop_count == base) {
          error = v.language == Language::BASIC ? Error::NEXT_WITHOUT_FOR : Error::FOR;
          break;
        }
        LoopFrame& frame = s.loops[s.loop_count - 1];
        double& counter = frame.variable & 0x8000U ? data.array[frame.variable & 0x7FFFU]
                                                   : data.variables[frame.variable];
        const double old = op == Op::NEXT_FOCAL ? frame.value : counter;
        const double following = old + frame.step;
        if (op == Op::NEXT_FOCAL && old == frame.limit) {
          --s.loop_count;
          break;
        }
        if (!mk_math::is_finite(following) || (op == Op::NEXT_FOCAL && following == old)) {
          error = v.language == Language::BASIC ? Error::MATH : Error::FOR;
          break;
        }
        const bool inside = frame.step < 0 ? following >= frame.limit : following <= frame.limit;
        if (op != Op::NEXT_FOCAL || inside) counter = following;
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
      case Op::PRINT_RESOURCE:
        p = v.bytes + v.end + word(p);
        event(Event::RESOURCE_TEXT, (const char*)p, word(p), value);
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
      case Op::INPUT_RESOURCE: {
        if (host.yield_input)
          return {Error::YIELDED, instruction, source_line(v, instruction), steps};
        const bool resource = op == Op::INPUT_RESOURCE;
        p = resource ? v.bytes + v.end + word(p) : p;
        event(resource ? Event::RESOURCE_INPUT : Event::READ_INPUT,
              (const char*)p + (resource ? 0 : 2), word(p), value);
        if (error == Error::NONE) push(value);
        break;
      }
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
  static const char* const names[] = {"OK",
                                      "SYNTAX",
                                      "LINE",
                                      "FULL",
                                      "VARIABLE",
                                      "FUNCTION",
                                      "FOR",
                                      "RETURN",
                                      "STACK",
                                      "MATH",
                                      "REGISTER",
                                      "INVALID_IMAGE",
                                      "IO",
                                      "STOPPED",
                                      "LIMIT",
                                      "YIELDED",
                                      "DIV BY ZERO",
                                      "ARRAY INDEX",
                                      "OUT OF DATA",
                                      "ON INDEX",
                                      "CALL STACK",
                                      "LOOP STACK",
                                      "NEXT WITHOUT FOR",
                                      "NO SUCH LINE",
                                      "LINE NUMBER",
                                      "PRINT WIDTH",
                                      "UNKNOWN COMMAND",
                                      "UNCLOSED STRING",
                                      "EXPECTED )"};
  return (uint8_t)e < sizeof(names) / sizeof(names[0]) ? names[(uint8_t)e] : "UNKNOWN";
}
}  // namespace language_vm
