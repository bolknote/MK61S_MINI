#include <string.h>

#include "language_bytecode.hpp"
#include "mk_math.hpp"

namespace language_vm {
#if defined(LANGUAGE_VM_TRACE)
// Host-only instrumentation. No callback, counters or ABI fields are shipped.
void trace_instruction(const View&, uint16_t, uint32_t);
#endif
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
// Total wire widths: zero denotes an invalid opcode, 255 a bounded variable
// record. A single indexed read replaces a second opcode switch in the hot loop.
constexpr uint8_t wire_widths[] = {
  1,1,2,3,9,2,2,2,2,1,1,1,1,1,1,1, // 0..15
  1,1,1,1,1,1,1,1,1,1,1,1,2,0,3,3, // 16..31 (29: retired CHECK)
  1,1,1,2,2,5,5,1,7,1,255,1,1,2,1,2, // 32..47
  255,1,1,2,1,3,4,1,0,0,0,0,0,0,0,0, // 48..63
  1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1, // 64..79
  255,1,1,255,255,1,1,3,3,3,5,1,3,3,3,4,3, // 80..96
  2,7,1,1,1,3 // 97..102
};
static_assert(sizeof(wire_widths)==(unsigned)Op::PRINT_PRECISION+1,"opcode width table changed");
uint16_t next(const View& v, uint16_t pc) {
  if(pc>=v.end) return 0;
  const uint8_t op=v.bytes[pc];
  if(op>=sizeof(wire_widths)) return 0;
  const uint8_t width=wire_widths[op];
  const uint16_t remaining=(uint16_t)(v.end-pc);
  if(width!=255) return width && width<=remaining ? (uint16_t)(pc+width) : 0;
  if(remaining<3) return 0;
  const uint16_t count=word(v.bytes+pc+1);
  if((Op)op==Op::ON_GOTO || (Op)op==Op::ON_GOSUB) {
    if(!count || count>(remaining-3)/2) return 0;
    return (uint16_t)(pc+3+count*2);
  }
  if((Op)op==Op::DATA && !count) return 0;
  return count<=remaining-3 ? (uint16_t)(pc+3+count) : 0;
}
bool constant_value(const View& v, uint16_t pc, Value& value) {
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
    case Op::CONST_I32:
      value = (int32_t)dword(p);
      return true;
    case Op::CONST_DEC8:
    case Op::CONST_DEC16: {
      double decoded = op == Op::CONST_DEC8 ? *p : word(p);
      const int exponent = (int8_t)p[op == Op::CONST_DEC8 ? 1 : 2];
      if (exponent < 0)
        decoded /= mk_math::pow10_int(-exponent);
      else
        decoded *= mk_math::pow10_int(exponent);
      value = decoded;
      return true;
    }
    case Op::CONST_F64: {
      uint64_t bits = 0;
      for (uint8_t i = 0; i < 8; ++i) bits |= (uint64_t)p[i] << (i * 8);
      value = mk_math::bit_copy<double>(bits);
      return true;
    }
    default:
      return false;
  }
}
bool data_value(const View& v,uint16_t at,uint16_t end,Value& value,uint16_t& following) {
  following=next(v,at);
  if(!following || following>end || !constant_value(v,at,value)) return false;
  if(following<end && (Op)v.bytes[following]==Op::NEG) {
    value=-value;
    ++following;
  }
  return value.finite();
}
bool array_index(Value value, uint16_t capacity, uint16_t& index) {
  if(value.integer()) {
    const int32_t n=value.integer_value();
    if(n < 0 || (uint32_t)n >= capacity) return false;
    index=(uint16_t)n; return true;
  }
  const double number=value.number();
  if (!mk_math::is_finite(number) || number < 0) return false;
  const double n = mk_math::floor(number + .5);
  if (n >= capacity || mk_math::fabs(number - n) > 1e-7) return false;
  index = (uint16_t)n;
  return true;
}
__attribute__((noinline)) bool comparison(Value a,Value b,uint8_t mask) {
  // Four order states also preserve unordered IEEE comparisons. No floating
  // reassociation or replacement with single precision is involved.
  unsigned order;
  if(a.integer() && b.integer()) {
    const int32_t x=a.integer_value(),y=b.integer_value();
    order=x<y ? 0 : x==y ? 1 : 2;
  } else {
    const double x=a.number(),y=b.number();
    order=x<y ? 0 : x==y ? 1 : x>y ? 2 : 3;
  }
  return (mask&(1U<<order))!=0;
}
Error update_local(Value* variables,uint8_t index,uint8_t encoded) {
  const uint8_t rhs=encoded&0x3F;
  if(index>=26 || ((encoded&0x40) && rhs>=26)) return Error::INVALID_IMAGE;
  const Value a=variables[index];
  if(!a.finite()) return Error::MATH;
  Value b=rhs;
  if(encoded&0x40) {b=variables[rhs];if(!b.finite()) return Error::MATH;}
  const Value result=(encoded&0x80) ? a-b : a+b;
  if(!result.finite()) return Error::MATH;
  variables[index]=result;return Error::NONE;
}
}  // namespace

Error inspect(const uint8_t* bytes, uint16_t length, View& out) {
  out = {};
  if (!bytes || length < HEADER_SIZE || length > MAX_MODULE ||
      memcmp(bytes, "LBV1", 4) || bytes[4] != VERSION ||
      (bytes[5] != (uint8_t)Language::BASIC && bytes[5] != (uint8_t)Language::FOCAL) ||
      bytes[6] == 0 || bytes[6] > MAX_STACK || bytes[7] > 15 ||
      word(bytes + 8) != length)
    return Error::INVALID_IMAGE;
  if (bytes[7] & 4) {
    if ((bytes[7] & 1) || (!(bytes[7] & OWNED_RESOURCE_FLAG) && word(bytes + 24) == 0xFFFF))
      return Error::INVALID_IMAGE;
    if(bytes[7] & OWNED_RESOURCE_FLAG)
      for(uint8_t i=24;i<30;++i) if(bytes[i]) return Error::INVALID_IMAGE;
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
  if (v.end > MAX_IMAGE || v.end > length || ((bytes[7] & 4) && v.end == length) ||
      ((bytes[7] & OWNED_RESOURCE_FLAG) && !(bytes[7] & RESOURCE_FLAG)) ||
      (!(bytes[7] & OWNED_RESOURCE_FLAG) && length > MAX_IMAGE)) return Error::INVALID_IMAGE;
  if ((v.expression
           ? v.lines != 0 || v.source_size > (v.language == Language::BASIC ? 64 : 111)
           : !v.lines) ||
      v.lines > (v.language == Language::BASIC ? 192 : 80) ||
      v.code != HEADER_SIZE + v.lines * stride(v) || v.code >= v.end ||
      !v.source_size || v.source_size > (v.language == Language::BASIC ? 3584 : 1536) ||
      checksum(bytes + HEADER_SIZE, length - HEADER_SIZE) != dword(bytes + 20))
    return Error::INVALID_IMAGE;
  uint8_t boundaries[(MAX_IMAGE + 7) / 8] = {};
  // Only code needs a bitmap. Resource boundaries are scanned once here and
  // looked up in the bounded directory, keeping the verifier stack unchanged.
  for (uint16_t at = v.end; at < length;) {
    if(bytes[7] & OWNED_RESOURCE_FLAG) {
      if(length-at<2 || word(bytes+at)>length-at-2) return Error::INVALID_IMAGE;
      at += (uint16_t)(2+word(bytes+at)); continue;
    }
    if (length - at < 3 || bytes[at + 2] > (length - at - 3) / 3)
      return Error::INVALID_IMAGE;
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
  auto resource_boundary = [&](uint16_t wanted) {
    for(uint16_t at=v.end;at<length;) {
      if(at==wanted) return true;
      at += (uint16_t)((bytes[7] & OWNED_RESOURCE_FLAG) ? 2+word(bytes+at) : 3+bytes[at+2]*3);
    }
    return false;
  };
  for (uint16_t pc = v.code; pc < v.end;) {
    boundaries[pc >> 3] |= (uint8_t)(1U << (pc & 7));
    const uint16_t following = next(v, pc);
    if (!following) return Error::INVALID_IMAGE;
    const Op op = (Op)bytes[pc];
    // Expression images share the opcode space, but must be side-effect-free
    // with respect to program variables and control frames. This permits the
    // hot INPUT evaluator to borrow the suspended program's stack safely.
    if (v.expression && op != Op::HALT && op != Op::CONST_I8 &&
        op != Op::CONST_I16 && op != Op::CONST_I32 && op != Op::CONST_F64 && op != Op::CONST_DEC8 &&
        op != Op::CONST_DEC16 && op != Op::LOAD && op != Op::LOAD_REF &&
        op != Op::LOAD_ARRAY && op != Op::ARRAY_CELL && op != Op::LOAD_ARRAY_FIXED && !(op >= Op::NEG && op <= Op::CHECK) && op != Op::FLOOR_DIV &&
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
        (op == Op::COMPARE_FALSE && bytes[pc+1]>15) ||
        (op == Op::UPDATE_LOCAL && (bytes[pc+1]>=26 ||
            ((bytes[pc+2]&0x40) && (bytes[pc+2]&0x3F)>=26))) ||
        (op == Op::FOR_FOCAL && bytes[pc + 4] > 1))
      return Error::INVALID_IMAGE;
    if (op >= Op::DATA && op < Op::SOURCE_POS && v.language != Language::BASIC)
      return Error::INVALID_IMAGE;
    if((op==Op::GOTO_DIRECT || op==Op::GOSUB_DIRECT) && v.language!=Language::BASIC)
      return Error::INVALID_IMAGE;
    if (op == Op::PRINT_RESOURCE || op == Op::INPUT_RESOURCE) {
      const uint32_t at = (uint32_t)v.end + word(bytes + pc + 1);
      if (!(bytes[7] & 4) || at >= length ||
          !resource_boundary((uint16_t)at) ||
          (op == Op::INPUT_RESOURCE && word(bytes + at) > 95))
        return Error::INVALID_IMAGE;
    }
    if ((op == Op::ARRAY_CELL && bytes[pc+1]>=26) ||
        (op == Op::CALL_PARAMS && (bytes[pc+5]>4 || bytes[pc+6]>1)) ||
        (op == Op::PRINT_PRECISION && (bytes[pc+1]>64 || !bytes[pc+2] || bytes[pc+2]>15)) ||
        (op >= Op::ARRAY_CELL && op <= Op::PRINT_PRECISION && v.language != Language::FOCAL))
      return Error::INVALID_IMAGE;
    if (op == Op::DATA) {
      const uint16_t end = (uint16_t)(pc + 3 + word(bytes + pc + 1));
      for (uint16_t at = (uint16_t)(pc + 3); at < end;) {
        uint16_t following=0;
        Value value=0;
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
    if ((op == Op::JUMP || op == Op::JUMP_FALSE || op==Op::GOTO_DIRECT || op==Op::GOSUB_DIRECT) &&
        !target(word(bytes + pc + 1)))
      return Error::INVALID_IMAGE;
    if(op==Op::COMPARE_FALSE && !target(word(bytes+pc+2))) return Error::INVALID_IMAGE;
    if (op == Op::DO_FOCAL &&
        (!target(word(bytes + pc + 1)) ||
         !target(word(bytes + pc + 3) == 0xFFFF
                     ? 0xFFFF
                     : (uint16_t)(word(bytes + pc + 3) & 0x7FFF))))
      return Error::INVALID_IMAGE;
    if (op == Op::FOR_FOCAL && !target(word(bytes + pc + 2)))
      return Error::INVALID_IMAGE;
    if (op == Op::CALL_PARAMS &&
        (!target(word(bytes+pc+1)) || !target(word(bytes+pc+3)) ||
         (word(bytes+pc+1)!=0xFFFF && (word(bytes+pc+3)==0xFFFF || word(bytes+pc+3)<=word(bytes+pc+1))))) return Error::INVALID_IMAGE;
    if (op == Op::BRANCH)
      for (uint8_t i = 0; i < 3; ++i)
        if (!target(word(bytes + pc + 1 + i * 2))) return Error::INVALID_IMAGE;
  }
  out = v;
  return Error::NONE;
}

uint16_t line_pc(const View& v, uint32_t number) {
  uint16_t first=0,last=v.lines;
  while(first<last) {
    const uint16_t middle=(uint16_t)(first+(last-first)/2);
    const uint32_t found=record_number(v,middle);
    if(found==number) return record_pc(v,middle);
    if(found<number) first=(uint16_t)(middle+1); else last=middle;
  }
  return 0xFFFF;
}
uint32_t source_line(const View& v, uint16_t pc) {
  uint16_t first=0,last=v.lines;
  while(first<last) {
    const uint16_t middle=(uint16_t)(first+(last-first)/2);
    if(record_pc(v,middle)<=pc) first=(uint16_t)(middle+1); else last=middle;
  }
  return first ? record_number(v,(uint16_t)(first-1)) : 0;
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
        Value value=0;
        const uint16_t end=(uint16_t)(s.data_pc+3+word(v.bytes+s.data_pc+1));
        if(!data_value(v,at,end,value,following)) return {Error::INVALID_IMAGE,0,0,0};
        at=following;
      }
      if (at != target) return {Error::INVALID_IMAGE, 0, 0, 0};
    }
    for (uint8_t i = 0; i < s.call_count; ++i) {
      const auto& f = s.calls[i];
      if (f.resume < v.code || f.resume >= v.end || f.loops > MAX_LOOPS ||
          f.mode>3 || f.arguments>4 || unsigned(f.base)+f.arguments>data.stack_capacity ||
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
  // Compact decimal constants are exact wire recipes. Decode each hot recipe
  // once instead of repeating soft-double pow10/division in a loop. Eight
  // direct-mapped entries are bounded stack scratch, never part of an image
  // or a continuation; INPUT/resume simply starts a fresh cache.
  Value decimal_values[8];
  uint16_t decimal_pcs[8]={0xFFFF,0xFFFF,0xFFFF,0xFFFF,0xFFFF,0xFFFF,0xFFFF,0xFFFF};
  auto push = [&](Value value) {
    if (!value.finite())
      error = Error::MATH;
    else if (s.sp >= data.stack_capacity)
      error = Error::STACK;
    else
      data.stack[s.sp++] = value;
  };
  auto pop = [&]() -> Value {
    if (!s.sp) {
      error = Error::STACK;
      return 0;
    }
    return data.stack[--s.sp];
  };
  auto event = [&](Event e, const char* p, uint16_t n, Value& value) {
    double external=value.number();
    if (!host.event || !host.event(host.context, e, p, n, external)) error = Error::IO;
    value=external;
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
      if(frame.mode) {
        if(frame.mode & 2) {error=Error::RETURN;break;}
        s.sp=frame.base;
      }
    }
    // SOURCE_POS is a diagnostic prefix, not work for the evaluator. Its
    // bytes remain available to source_column() even after a jump/resume.
    // Skip it before dispatch/service accounting; useful instructions still
    // poll at most 32 apart, and this bounded scan never follows a branch.
    while(s.pc<v.end && (Op)v.bytes[s.pc]==Op::SOURCE_POS) {
      instruction=s.pc;
      if(v.end-s.pc<3) {error=Error::INVALID_IMAGE;break;}
      s.pc=(uint16_t)(s.pc+3);
    }
    if(error!=Error::NONE) break;
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
    const Op op = (Op)v.bytes[s.pc];
#if defined(LANGUAGE_VM_TRACE)
    trace_instruction(v, s.pc, steps);
#endif
    // Metadata needs no operand decoder, constant decoder or value scratch.
    // Keep logical steps/service cadence and the original safety checks.
    if(op==Op::LINE) {
      ++s.pc;
      const uint8_t base=s.call_count && s.calls[s.call_count-1].mode
          ? (uint8_t)(s.calls[s.call_count-1].base+s.calls[s.call_count-1].arguments) : 0;
      if(s.sp!=base) error=Error::STACK;
      continue;
    }
    if(op>=Op::CONST_0 && op<=Op::CONST_15) {
      ++s.pc;push(Value((uint8_t)op-(uint8_t)Op::CONST_0));continue;
    }
    // The opcode is already loaded. Fixed-width instructions need neither a
    // second opcode fetch nor a call to the cold/variable-record decoder.
    const uint8_t width=(unsigned)op<sizeof(wire_widths) ? wire_widths[(unsigned)op] : 0;
    const uint16_t after=width==255 ? next(v,s.pc) :
        width && width<=v.end-s.pc ? (uint16_t)(s.pc+width) : 0;
    if (!after) {
      error = Error::INVALID_IMAGE;
      break;
    }
    const uint8_t* p = v.bytes + s.pc + 1;
    s.pc = after;
    Value a = 0, b = 0, value = 0;
    switch (op) {
      case Op::CONST_I8:
      case Op::CONST_I16:
      case Op::CONST_I32:
      case Op::CONST_F64:
        (void)constant_value(v,instruction,value);push(value);
        break;
      case Op::CONST_DEC8:
      case Op::CONST_DEC16: {
        const uint8_t slot=(instruction>>2)&7;
        if(decimal_pcs[slot]!=instruction) {
          (void)constant_value(v,instruction,decimal_values[slot]);
          decimal_pcs[slot]=instruction;
        }
        push(decimal_values[slot]);
        break;
      }
      case Op::HALT: {
        const uint8_t expected=v.expression?1:s.call_count && s.calls[s.call_count-1].mode
            ? (uint8_t)(s.calls[s.call_count-1].base+s.calls[s.call_count-1].arguments):0;
        if(s.sp!=expected)error=Error::STACK;
        else if(v.language==Language::FOCAL && !v.expression)s.sp=s.call_count=s.loop_count=0;
        if(error==Error::NONE && !v.expression && host.event)
          event(Event::FINISH, nullptr, 0, value);
        return {error, instruction, source_line(v, instruction), steps};
      }
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
        b = (a + Value(.5)).floor();
        if (error != Error::NONE) break;
        if (!a.finite() || a < 0 || a > 32767 || mk_math::fabs((a - b).number()) > 1e-7) {
          error = Error::LINE_NUMBER;
          break;
        }
        const uint16_t to = a == 0 ? v.code : line_pc(v, (uint32_t)b.number());
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
        if (!a.finite() || a < 0 || a != a.floor()) {
          error = Error::ON_INDEX;
          break;
        }
        const uint16_t count = word(p);
        if (a == 0 || a > count) break;
        const uint16_t to = line_pc(v, word(p + 2 + ((uint16_t)a.number() - 1) * 2));
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
      case Op::UPDATE_LOCAL:
        error=update_local(data.variables,*p,p[1]);
        break;
      case Op::LOAD_REF:
      case Op::STORE_REF:
        if (op == Op::STORE_REF) value = pop();
        if(error == Error::NONE) {
          double external=value.number();
          if(!host.reference || !host.reference(host.context, op == Op::STORE_REF, *p, external))
            error=Error::REGISTER;
          value=external;
        }
        if (op == Op::LOAD_REF && error == Error::NONE) push(value);
        break;
      case Op::LOAD_ARRAY:
      case Op::STORE_ARRAY:
      case Op::LOAD_ARRAY_FIXED: {
        if (op == Op::STORE_ARRAY) value = pop();
        uint16_t index = 0;
        bool valid;
        if(op==Op::LOAD_ARRAY_FIXED) {index=word(p);valid=data.array && index<data.array_count;}
        else {a=pop();valid=data.array && array_index(a,data.array_count,index);}
        if (!valid)
          error = v.language == Language::BASIC ? Error::ARRAY_RANGE : Error::VARIABLE;
        if (error == Error::NONE) {
          if (op == Op::STORE_ARRAY)
            data.array[index] = value;
          else
            push(data.array[index]);
        }
        break;
      }
      case Op::ARRAY_CELL: {
        b=pop();a=pop();
        if(error!=Error::NONE) break;
        const double i=a.number(),j=b.number();
        if(!data.array || i<0 || i>32767 || j<0 || j>32767 ||
           mk_math::trunc(i)!=i || mk_math::trunc(j)!=j) {error=Error::ARRAY_RANGE;break;}
        const double wanted=1.0+double(*p)*1073741824.0+i*32768.0+j;
        uint16_t cell=0xFFFF,free=0xFFFF;
        for(uint16_t n=0;n+1<data.array_count;n=(uint16_t)(n+2)) {
          if(data.array[n].number()==wanted) {cell=n;break;}
          if(data.array[n].zero() && free==0xFFFF) free=n;
        }
        if(cell==0xFFFF) {
          if(free==0xFFFF) {error=Error::FULL;break;}
          cell=free;data.array[cell]=wanted;data.array[cell+1]=0;
        }
        push((int32_t)(cell+1));break;
      }
      case Op::LOAD_PARAMETER:
        a=pop();
        if(error!=Error::NONE)break;
        if(!s.call_count || !s.calls[s.call_count-1].mode || a<1 ||
           a.number()>s.calls[s.call_count-1].arguments || a!=a.floor()) error=Error::VARIABLE;
        else push(data.stack[s.calls[s.call_count-1].base+(uint8_t)a.number()-1]);
        break;
      case Op::CALL_PARAMS: {
        const uint8_t count=p[4];
        if(s.sp<count || count>4 || p[5]>1) {error=Error::STACK;break;}
        const uint8_t base=(uint8_t)(s.sp-count);
        call(word(p),word(p+2));
        if(error==Error::NONE) {
          auto& f=s.calls[s.call_count-1];f.base=base;f.arguments=count;f.mode=(uint8_t)(1|(p[5]?2:0));
        }
        break;
      }
      case Op::RETURN_VALUE: {
        value=pop();
        if(!s.call_count) {error=Error::RETURN;break;}
        const auto frame=s.calls[--s.call_count];
        if(!frame.mode) {error=Error::RETURN;break;}
        s.pc=frame.resume;s.loop_count=frame.loops;s.sp=frame.base;
        if(error==Error::NONE && (frame.mode&2))push(value);
        break;
      }
      case Op::DROP: (void)pop();break;
      case Op::PRINT_PRECISION:
        value=*p;event(Event::PRECISION,nullptr,p[1],value);break;
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
        push((int32_t)a.zero());
        break;
      case Op::ADD:
      case Op::SUB:
      case Op::MUL:
      case Op::DIV:
      case Op::FLOOR_DIV:
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
      case Op::XOR: {
        if(s.sp<2) {error=Error::STACK;break;}
        b=data.stack[s.sp-1];a=data.stack[s.sp-2];
        s.sp=(uint8_t)(s.sp-2);
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
          case Op::FLOOR_DIV:
            if (b == 0)
              error = v.language == Language::BASIC ? Error::DIV_ZERO : Error::MATH;
            else
              value = op == Op::FLOOR_DIV ? Value::floor_divide(a,b) : a / b;
            break;
          case Op::POW:
            if (host.math)
              value = host.math(host.context, (Function)255, a.number(), b.number());
            else
              error = Error::MATH;
            break;
          case Op::MOD:
            if (b == 0)
              error = v.language == Language::BASIC ? Error::DIV_ZERO : Error::MATH;
            else
              value = Value::modulo(a,b);
            break;
          case Op::EQ:
          case Op::NE:
          case Op::LT:
          case Op::LE:
          case Op::GT:
          case Op::GE:
            value=comparison(a,b,comparison_mask(op));
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
        if(error==Error::NONE) {
          // Two existing stack cells guarantee room for one result. Keep
          // The finite check, but do not pop/pop/push with three bounds.
          if(!value.finite()) error=Error::MATH;
          else data.stack[s.sp++]=value;
        }
        break;
      }
      case Op::COMPARE_FALSE:
        if(s.sp<2) error=Error::STACK;
        else {
          s.sp=(uint8_t)(s.sp-2);
          // The cold verifier rejects reserved mask bits. The hot operation
          // uses only four bounded order bits, never an unchecked table index.
          if(!comparison(data.stack[s.sp],data.stack[s.sp+1],*p)) jump(word(p+1));
        }
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
            value = a.absolute();
            break;
          case Function::INT:
            value = a.floor();
            break;
          case Function::FRAC:
            value = a.fraction();
            break;
          case Function::ROUND:
            value = a.rounded();
            break;
          case Function::SGN:
            value = a > 0 ? 1 : a < 0 ? -1 : 0;
            break;
          case Function::MAX:
            value = a > b ? a : b;
            break;
          case Function::RND:
          case Function::RND_LIMIT:
            if (f == Function::RND_LIMIT && (!(a >= 1) || !a.finite())) {
              error = Error::MATH;
              break;
            }
            if (!host.random) {
              error = Error::IO;
              break;
            }
            value = host.random(host.context);
            if (f == Function::RND_LIMIT)
              value = Value(1) + (value * a.floor()).floor();
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
              value = host.math(host.context, f, a.number(), 0);
            break;
        }
        if (error == Error::NONE) push(value);
        break;
      }
      case Op::JUMP:
        if(v.language==Language::FOCAL)
          while(s.loop_count && (word(p)<s.loops[s.loop_count-1].body || word(p)>=s.loops[s.loop_count-1].end)) --s.loop_count;
        jump(word(p));break;
      case Op::JUMP_FALSE:
        a = pop();
        if (error == Error::NONE && a.zero()) jump(word(p));
        break;
      case Op::GOTO:
      case Op::GOSUB:
        a = pop();
        b = (a + Value(.5)).floor();
        if (!a.finite() || a < 1 || a > 32767 || mk_math::fabs((a - b).number()) > 1e-7)
          error = v.language == Language::BASIC ? Error::LINE_NUMBER : Error::LINE;
        else if (error == Error::NONE) {
          const uint16_t to = line_pc(v, (uint32_t)b.number());
          if (to == 0xFFFF && v.language == Language::BASIC)
            error = Error::MISSING_LINE;
          else if (op == Op::GOTO)
            jump(to);
          else
            call(to, 0);
        }
        break;
      case Op::GOTO_DIRECT:
      case Op::GOSUB_DIRECT:
        if(word(p)==0xFFFF) error=Error::MISSING_LINE;
        else if(op==Op::GOSUB_DIRECT) call(word(p),0);
        else jump(word(p));
        break;
      case Op::RETURN:
        if (!s.call_count)
          error = Error::RETURN;
        else {
          const auto frame = s.calls[--s.call_count];
          s.pc = frame.resume;
          s.loop_count = frame.loops;
          if(frame.mode) {s.sp=frame.base;if(frame.mode&2)error=Error::RETURN;}
        }
        break;
      case Op::DO_FOCAL:
        call(word(p), word(p + 2));
        break;
      case Op::BRANCH:
        a=pop();
        if(error==Error::NONE) {
          const uint16_t to=word(p+(a<0?0:a==0?2:4));
          if(to!=0xFFFF) {
            while(s.loop_count && (to<s.loops[s.loop_count-1].body || to>=s.loops[s.loop_count-1].end)) --s.loop_count;
            jump(to);
          }
        }
        break;
      case Op::FOR_BASIC:
      case Op::FOR_ARRAY:
      case Op::FOR_FOCAL: {
        Value step = pop(), end = pop(), start = pop();
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
          const Value temp = step;
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
        Value& counter = var & 0x8000U ? data.array[var & 0x7FFFU] : data.variables[var];
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
        // The dispatch loop polls before work and every 32 instructions,
        // including empty FOR bodies. A second poll on every NEXT adds no
        // cancellation bound, but dominates short numeric loops on hardware.
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
        Value& counter = frame.variable & 0x8000U ? data.array[frame.variable & 0x7FFFU]
                                                   : data.variables[frame.variable];
        const Value old = op == Op::NEXT_FOCAL ? frame.value : counter;
        const Value following = old + frame.step;
        if (op == Op::NEXT_FOCAL && old == frame.limit) {
          --s.loop_count;
          break;
        }
        if (!following.finite() || (op == Op::NEXT_FOCAL && following == old)) {
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
        event((v.bytes[7] & OWNED_RESOURCE_FLAG) ? Event::TEXT : Event::RESOURCE_TEXT,
              (const char*)p + ((v.bytes[7] & OWNED_RESOURCE_FLAG) ? 2 : 0), word(p), value);
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
        const bool pooled = op == Op::INPUT_RESOURCE;
        const bool resource = pooled && !(v.bytes[7] & OWNED_RESOURCE_FLAG);
        p = pooled ? v.bytes + v.end + word(p) : p;
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
