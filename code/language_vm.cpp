#include <string.h>
#include <initializer_list>

#include "language_bytecode.hpp"
#include <new>
#include "basic_graphics_protocol.hpp"
#include "mk_math.hpp"
#include "language_vm_profile.hpp"

namespace language_vm {
#ifndef MK61_VM_INTEGER_BLOCK
#if defined(MK61_APP_LOCAL_FLOAT_MATH) && MK61_APP_LOCAL_FLOAT_MATH
// The local libm variant has only 124 spare bytes in its unchanged APP gate.
#define MK61_VM_INTEGER_BLOCK 0
#else
#define MK61_VM_INTEGER_BLOCK 1
#endif
#endif
#if MK61_VM_INTEGER_BLOCK != 0 && MK61_VM_INTEGER_BLOCK != 1
#error "MK61_VM_INTEGER_BLOCK must be 0 or 1"
#endif
#ifndef MK61_VM_COMPARE_BLOCK
#if defined(MK61_APP_LOCAL_FLOAT_MATH) && MK61_APP_LOCAL_FLOAT_MATH
#define MK61_VM_COMPARE_BLOCK 0
#else
#define MK61_VM_COMPARE_BLOCK 1
#endif
#endif
#if MK61_VM_COMPARE_BLOCK != 0 && MK61_VM_COMPARE_BLOCK != 1
#error "MK61_VM_COMPARE_BLOCK must be 0 or 1"
#endif
// The cold INPUT APP has no long-running instruction stream.
#ifndef MK61_VM_INTEGER_SPAN
#if (defined(MK61_APP_LOCAL_FLOAT_MATH) && MK61_APP_LOCAL_FLOAT_MATH) || defined(MK61_BUILD_LANGUAGE_INPUT_MODULE)
#define MK61_VM_INTEGER_SPAN 0
#else
#define MK61_VM_INTEGER_SPAN 1
#endif
#endif
#if MK61_VM_INTEGER_SPAN != 0 && MK61_VM_INTEGER_SPAN != 1
#error "MK61_VM_INTEGER_SPAN must be 0 or 1"
#endif
#if defined(LANGUAGE_VM_TEST_COMPARE_BLOCK)
void compare_block_applied(uint16_t);
#endif
#if defined(LANGUAGE_VM_TEST_INTEGER_BLOCK)
void integer_block_applied(uint16_t, uint8_t);
#endif
#if defined(LANGUAGE_VM_TEST_INTEGER_SPAN)
void integer_span_applied(uint16_t, uint8_t);
#endif
#if defined(LANGUAGE_VM_TEST_INTEGER_SHORT_BLOCK)
void integer_short_block_applied(uint16_t);
#endif
#if defined(LANGUAGE_VM_TRACE)
// Host-only instrumentation. No callback, counters or ABI fields are shipped.
void trace_instruction(const View&, uint16_t, uint32_t);
#endif
namespace {
uint16_t word(const uint8_t* p) { return (uint16_t)(p[0] | ((uint16_t)p[1] << 8)); }
uint32_t dword(const uint8_t* p) {
  return (uint32_t)word(p) | ((uint32_t)word(p + 2) << 16);
}
// Keep the variable ON-table fetch outside the hot dispatch frame. Only the
// selected two-byte line number is read, regardless of table/image length.
__attribute__((noinline)) uint16_t image_word(const View& v,uint32_t at) {
  uint8_t bytes[2]={};(void)v.read(at,bytes,sizeof(bytes));return word(bytes);
}
uint8_t stride(const View& v) { return v.wide_code()?8:v.language == Language::BASIC ? 4 : 6; }
uint32_t record_pc(const View& v, uint16_t i) {
  return v.address(v.at(HEADER_SIZE + uint32_t(i) * stride(v) + stride(v) - v.address_bytes()));
}
uint32_t record_number(const View& v, uint16_t i) {
  const auto p = v.at(HEADER_SIZE + uint32_t(i) * stride(v));
  return !v.wide_code() && v.language == Language::BASIC ? word(p) : dword(p);
}
// Total wire widths: zero denotes an invalid opcode, 255 a bounded variable
// record. A single indexed read replaces a second opcode switch in the hot loop.
uint32_t next(const View& v, uint32_t pc) {return instruction_end(v,pc);}
bool decode_constant(Op op,const uint8_t* p,Value& value) {
  if (op >= Op::CONST_0 && op <= Op::CONST_15) {
    value = (uint8_t)op - (uint8_t)Op::CONST_0;
    return true;
  }
  switch (op) {
    case Op::CONST_I8:
      value = (int8_t)*p;
      return true;
    case Op::CONST_I16:
    case Op::BLOCK_INDEX:
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
      const uint64_t bits=uint64_t(dword(p))|(uint64_t(dword(p+4))<<32);
      value = mk_math::bit_copy<double>(bits);
      return true;
    }
    default:
      return false;
  }
}
bool constant_value(const View& v,uint32_t pc,Value& value) {
  uint8_t bytes[9];
  if(pc>=v.end)return false;
  const uint16_t n=uint16_t(v.end-pc<sizeof(bytes)?v.end-pc:sizeof(bytes));
  return v.read(pc,bytes,n) && decode_constant(Op(bytes[0]),bytes+1,value);
}
bool data_value(const View& v,uint32_t at,uint32_t end,Value& value,uint32_t& following) {
  following=next(v,at);
  if(!following || following>end || !constant_value(v,at,value)) return false;
  if(following<end && (Op)v.byte(following)==Op::NEG) {
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
#if MK61_VM_INTEGER_BLOCK || MK61_VM_INTEGER_SPAN || \
    ((MK61_VM_INTEGER_BLOCK || MK61_VM_COMPARE_BLOCK) && defined(LANGUAGE_VM_TRACE))
uint32_t block_next(const View& v,uint32_t pc) {
  while(pc<v.end && (Op)v.byte(pc)==Op::SOURCE_POS) {
    if(v.end-pc<3)return 0;
    pc=(pc+3);
  }
  return pc;
}
#endif
#if MK61_VM_INTEGER_BLOCK || MK61_VM_COMPARE_BLOCK || MK61_VM_INTEGER_SPAN
// Compiler marks retain the original instruction widths and all interior PCs.
// Share runtime guards and commit code for all block families. No write or
// trace occurs before every guard passes; boundaries deopt to ordinary run().
// The cold verifier checks index/compare shapes; short marks are only hints.
// Bounded runtime checks retain scalar fallback for nonmatching/truncated
// views and invalid local IDs.
__attribute__((noinline)) uint8_t compiled_block(const View& v, Continuation& s,
    const Bindings& data, uint32_t& steps, uint32_t& instruction, uint32_t limit,
    Op hint,const uint8_t* operands) {
  const uint32_t first=instruction;
  const bool short_value=hint==Op::INTEGER_SHORT;
  if(data.stack_capacity-s.sp<(short_value?1:2))return 0;
  uint32_t after,last;
  uint8_t count=3,dst=255,delta;
  Value a,b;
  const bool compare=hint==Op::BLOCK_COMPARE;
  if(short_value) {
#if MK61_VM_INTEGER_SPAN
    if(v.end-first<2 || *operands>=26)return 0;
    a=data.variables[*operands];if(!a.finite())return 0;
    const uint32_t middle=block_next(v,(first+2));
    if(!middle || middle>=v.end)return 0;
    const Op op=(Op)v.byte(middle);
    if(op==Op::LOAD_ARRAY) {
      if(!a.integer())return 0;
      const int32_t index=a.integer_value();
      if(!data.array || index<0 || (uint32_t)index>=data.array_count ||
         data.array+index==data.stack+s.sp)return 0;
      a=data.array[index];if(!a.finite())return 0;
    } else {
      if(v.end-middle<2 || op!=Op::FUNCTION || (Function)v.byte(middle+1)!=Function::ABS)return 0;
      a=a.absolute();
    }
    last=block_next(v,(middle+(op==Op::LOAD_ARRAY?1:2)));
    if(!last || v.end-last<2 || (Op)v.byte(last)!=Op::STORE || v.byte(last+1)>=26)return 0;
    dst=v.byte(last+1);after=(last+2);delta=0;
#else
    return 0;
#endif
  } else if(compare) {
#if MK61_VM_COMPARE_BLOCK
    if(v.end-first<5U+v.address_bytes() || *operands>=26)return 0;
    const uint8_t rhs=v.byte(first+2);
    if(rhs<(uint8_t)Op::CONST_0 || rhs>(uint8_t)Op::CONST_15 ||
       (Op)v.byte(first+3)!=Op::COMPARE_FALSE)return 0;
    b=(uint8_t)(rhs-(uint8_t)Op::CONST_0);
    last=(first+3);after=(first+5+v.address_bytes());
    a=data.variables[*operands];
    if(!a.integer())return 0;
    delta=2;
#else
    return 0;
#endif
  } else {
#if MK61_VM_INTEGER_BLOCK
    if(v.end-first<6)return 0;
    const uint8_t index=v.byte(first+4);
    if(index>=26)return 0;
    b=data.variables[index];
    int32_t sum;
    if(!b.integer() || __builtin_add_overflow((int32_t)(int16_t)word(operands),
                                             b.integer_value(),&sum))return 0;
    a=sum;after=(first+6);last=(first+5);
    uint32_t candidate=block_next(v,after);
    if(candidate && candidate<v.end && (Op)v.byte(candidate)==Op::LOAD_ARRAY) {
      if(!data.array || sum<0 || (uint32_t)sum>=data.array_count || !data.array[sum].integer())return 0;
      a=data.array[sum];last=candidate;after=(candidate+1);++count;
    }
    candidate=block_next(v,after);
    if(candidate && candidate<v.end && (Op)v.byte(candidate)==Op::STORE) {
      if(v.end-candidate<2 || v.byte(candidate+1)>=26)return 0;
      dst=v.byte(candidate+1);last=candidate;after=(candidate+2);++count;
    }
    delta=dst<26?0:1;
#else
    return 0;
#endif
  }
  if(((steps-1)&31U)+count>32 || (limit && count-1U>limit-steps) ||
     (s.call_count && s.calls[s.call_count-1].end && after>s.calls[s.call_count-1].end))return 0;
#if defined(LANGUAGE_VM_TRACE)
  uint32_t pc=first;
  for(uint8_t n=1;n<count;++n) {
    pc=block_next(v,next(v,pc));trace_instruction(v,pc,steps+n);
  }
#endif
  if(!v.good())return 0;
  // Match even inactive cells: INPUT, snapshots and scalar fallback retain
  // the exact same operand bank, not only the final numerical result.
  data.stack[s.sp]=a;if(!short_value)data.stack[s.sp+1]=b;
  if(dst<26)data.variables[dst]=a;
  s.sp=(uint8_t)(s.sp+delta);s.pc=after;instruction=last;steps+=count-1;
#if defined(LANGUAGE_VM_TEST_INTEGER_BLOCK)
  if(!compare && !short_value)integer_block_applied(first,count);
#endif
#if defined(LANGUAGE_VM_TEST_COMPARE_BLOCK)
  if(compare)compare_block_applied(first);
#endif
#if defined(LANGUAGE_VM_TEST_INTEGER_SPAN)
  if(short_value)integer_span_applied(first,count);
#endif
#if defined(LANGUAGE_VM_TEST_INTEGER_SHORT_BLOCK)
  if(short_value)integer_short_block_applied(first);
#endif
  return count;
}
#endif
#if MK61_VM_INTEGER_SPAN
// Execute the existing stream while its values are int32. PC and a stack
// cursor stay local; every write still preserves inactive cells and aliases.
// A rejected operation is
// left untouched for the ordinary evaluator. Its first step is already polled,
// counted and traced. No span crosses the next service/limit/call boundary.
#if defined(MK61_CORE_STANDALONE) && defined(PICO_ON_DEVICE) && PICO_ON_DEVICE
__attribute__((section(".time_critical.mk61_integer_span")))
#endif
__attribute__((noinline)) uint8_t integer_span(const View& v, Continuation& s,
    const Bindings& data, uint32_t& steps, uint32_t& instruction, uint32_t limit) {
#if defined(LANGUAGE_VM_TEST_INTEGER_SPAN) || defined(LANGUAGE_VM_TEST_INTEGER_BLOCK) || defined(LANGUAGE_VM_TEST_COMPARE_BLOCK)
  [[maybe_unused]] const Op first_hint=Op(v.byte(instruction));
#endif
  uint32_t budget=32U-((steps-1U)&31U);
  if(limit && budget>limit-steps+1U)budget=limit-steps+1U;
  if(budget<2)return 0;
  uint32_t end_offset=v.end;
  if(s.call_count && s.calls[s.call_count-1].end && s.calls[s.call_count-1].end<end_offset)
    end_offset=s.calls[s.call_count-1].end;
  uintptr_t pc=instruction,last=pc;
  Value* const bottom=data.stack;
  Value* const ceiling=bottom+data.stack_capacity;
  Value* top=bottom+s.sp;
  uint32_t remaining=budget;
#if !defined(LANGUAGE_VM_TRACE)
  const uint8_t* const raw=v.reader?nullptr:v.bytes;
  const uintptr_t origin=reinterpret_cast<uintptr_t>(raw);
#else
  constexpr uintptr_t origin=0;
#endif
  const uintptr_t end=origin+end_offset;
  pc+=origin;last+=origin;
#if defined(LANGUAGE_VM_TRACE)
#define SPAN_TRACE() do {if(remaining!=budget)trace_instruction(v,pc,steps+budget-remaining);} while(false)
#else
#define SPAN_TRACE() ((void)0)
#endif
  while(remaining && pc<end) {
    uint8_t copied[6];
#if defined(LANGUAGE_VM_TRACE)
    // A diagnostic callback may perform another reader operation.
    const uint8_t* operands=nullptr;
#else
    const uint8_t* operands=raw?reinterpret_cast<const uint8_t*>(pc):nullptr;
#endif
    if(!operands) {
      const uint16_t available=uint16_t(end-pc<sizeof(copied)?end-pc:sizeof(copied));
#if !defined(LANGUAGE_VM_TRACE)
      if(v.reader)operands=v.reader->cached(uint32_t(pc),available);
#endif
      if(!operands) {
        if(!v.read(uint32_t(pc),copied,available))goto done;
        operands=copied;
      }
    }
    Op op=Op(operands[0]);
    if(op==Op::SOURCE_POS) {
      // Ordinary instructions fetch exactly once. Only a diagnostic prefix
      // needs lookahead; leave PC at its first byte on a truncated tail/HALT,
      // matching the old post-instruction scan and scalar error location.
      uintptr_t following=pc;
      Op next_op;
      do {
        if(end-following<3)goto done;
        following+=3;
        if(following>=end)goto done;
        next_op=Op(
#if defined(LANGUAGE_VM_TRACE)
            v.byte(following)
#else
            raw?*reinterpret_cast<const uint8_t*>(following):v.byte(uint32_t(following))
#endif
            );
      } while(next_op==Op::SOURCE_POS);
      if(next_op==Op::HALT)goto done;
      pc=following;
#if !defined(LANGUAGE_VM_TRACE)
      if(raw) {
        // No callback or write occurs after lookahead. Reuse its opcode and
        // raw operand address instead of fetching the same instruction again.
        operands=reinterpret_cast<const uint8_t*>(pc);op=next_op;
      } else
#endif
      continue;
    }
    // Only supported fixed-width handlers advance PC. Multi-byte handlers
    // check their operands before reading; unsupported/variable records leave
    // the stream untouched for the scalar decoder.
    uintptr_t width=1;
    const uint8_t* p=operands+1;
    Value result;
    int32_t x,y,z;
    const uint8_t small=uint8_t(uint8_t(op)-uint8_t(Op::CONST_0));
    if(small<16) {
      if(top>=ceiling)break;
      result=small;
      SPAN_TRACE();*top++=result;
    } else switch(op) {
      case Op::CONST_I8: case Op::CONST_I16: case Op::BLOCK_INDEX: case Op::CONST_I32:
        width=op==Op::CONST_I8?2:op==Op::CONST_I32?5:3;
        if(width>(unsigned)(end-pc) || top>=ceiling)goto done;
        result=op==Op::CONST_I8?(int32_t)(int8_t)*p:
            op!=Op::CONST_I32?(int32_t)(int16_t)word(p):(int32_t)dword(p);
        SPAN_TRACE();*top++=result;break;
      case Op::LOAD: case Op::INTEGER_SPAN: case Op::INTEGER_SHORT:
      case Op::BLOCK_COMPARE: case Op::LOAD_ARRAY_FIXED:
        width=op==Op::LOAD_ARRAY_FIXED?3:2;
        if(width>(unsigned)(end-pc) || top>=ceiling)goto done;
        if(op!=Op::LOAD_ARRAY_FIXED) {
          if(*p>=26)goto done;
          result=data.variables[*p];
        } else {
          const uint16_t index=word(p);
          if(!data.array || index>=data.array_count)goto done;
          result=data.array[index];
        }
        if(!result.integer())goto done;
        SPAN_TRACE();*top++=result;break;
      case Op::LOAD_ARRAY:
        if(top==bottom || !data.array || !top[-1].integer())goto done;
        x=top[-1].integer_value();
        if(x<0 || (uint32_t)x>=data.array_count)goto done;
        result=data.array[x];if(!result.integer())goto done;
        SPAN_TRACE();top[-1]=result;break;
      case Op::STORE:
        width=2;
        if(end-pc<2 || top==bottom || *p>=26)goto done;
        SPAN_TRACE();data.variables[*p]=*--top;break;
      case Op::STORE_ARRAY:
        if((unsigned)(top-bottom)<2 || !data.array || !top[-2].integer())goto done;
        x=top[-2].integer_value();
        if(x<0 || (uint32_t)x>=data.array_count)goto done;
        SPAN_TRACE();data.array[x]=top[-1];top-=2;break;
      case Op::NEG: case Op::NOT:
        if(top==bottom || !top[-1].integer())goto done;
        x=top[-1].integer_value();
        if(op==Op::NEG) {
          if(!x || __builtin_sub_overflow(0,x,&z))goto done;
        } else z=!x;
        SPAN_TRACE();top[-1]=z;break;
      case Op::FUNCTION:
        width=2;
        if(end-pc<2 || Function(*p)!=Function::ABS || top==bottom || !top[-1].integer())goto done;
        x=top[-1].integer_value();if(x==INT32_MIN)goto done;
        SPAN_TRACE();top[-1]=x<0?-x:x;break;
      case Op::LINE: {
        const uint8_t base=s.call_count
            ?uint8_t(s.calls[s.call_count-1].base+s.calls[s.call_count-1].arguments):0;
        if(unsigned(top-bottom)!=base)goto done;
        SPAN_TRACE();break;
      }
      case Op::JUMP: case Op::GOTO_DIRECT: case Op::JUMP_FALSE: case Op::COMPARE_FALSE: {
        const bool compare=op==Op::COMPARE_FALSE,conditional=op==Op::JUMP_FALSE || compare;
        width=1U+v.address_bytes()+unsigned(compare);
        if(width>end-pc)goto done;
        unsigned consumed=conditional?(compare?2:1):0;
        if(unsigned(top-bottom)<consumed || (consumed && !top[-1].integer()) ||
           (compare && !top[-2].integer()))goto done;
        bool taken=true;
        if(compare) {
          x=top[-2].integer_value();y=top[-1].integer_value();
          taken=!(p[0]&(x<y?1:x==y?2:4));
        } else if(conditional)taken=!top[-1].integer_value();
        if(taken) {
          const uint32_t to=v.address(p+unsigned(compare));
          if(to<v.code || to>=v.end)goto done;
          // Unsigned advance also represents backward/self branches. Bounds
          // are checked before committing; the shared tail retains old PC.
          width=(origin+to)-pc;
        }
        SPAN_TRACE();top-=consumed;break;
      }
      case Op::ADD: case Op::SUB: case Op::MUL: case Op::DIV:
      case Op::FLOOR_DIV: case Op::MOD:
      case Op::EQ: case Op::NE: case Op::LT: case Op::LE: case Op::GT: case Op::GE:
      case Op::AND: case Op::OR: case Op::XOR:
        if((unsigned)(top-bottom)<2 || !top[-2].integer() || !top[-1].integer())goto done;
        x=top[-2].integer_value();y=top[-1].integer_value();
        switch(op) {
          case Op::ADD:if(__builtin_add_overflow(x,y,&z))goto done;break;
          case Op::SUB:if(__builtin_sub_overflow(x,y,&z))goto done;break;
          case Op::MUL:
            if((!x && y<0) || (!y && x<0) || __builtin_mul_overflow(x,y,&z))goto done;
            break;
          case Op::DIV:
            if(!y || (x==INT32_MIN && y==-1) || (!x && y<0) || x%y)goto done;
            z=x/y;break;
          case Op::FLOOR_DIV:
            if(!y || (x==INT32_MIN && y==-1))goto done;
            z=x/y;if(x%y && ((x<0)!=(y<0)))--z;break;
          case Op::MOD:
            if(!y)goto done;
            if(x==INT32_MIN && y==-1)z=0;
            else {z=x%y;if(z && ((z<0)!=(y<0)))z+=y;}
            break;
          case Op::EQ:z=x==y;break;case Op::NE:z=x!=y;break;
          case Op::LT:z=x<y;break;case Op::LE:z=x<=y;break;
          case Op::GT:z=x>y;break;case Op::GE:z=x>=y;break;
          case Op::AND:z=x && y;break;case Op::OR:z=x || y;break;
          default:z=(x!=0)!=(y!=0);break;
        }
        SPAN_TRACE();top[-2]=z;--top;break;
      default:goto done;
    }
    last=pc;pc=(pc+width);--remaining;
  }
done:
  const uint8_t count=uint8_t(budget-remaining);
  if(count) {
#if defined(LANGUAGE_VM_TEST_INTEGER_SPAN)
    if(first_hint==Op::INTEGER_SPAN || first_hint==Op::INTEGER_SHORT)
      integer_span_applied(instruction,count);
#endif
#if defined(LANGUAGE_VM_TEST_INTEGER_BLOCK) && MK61_VM_INTEGER_BLOCK
    if(first_hint==Op::BLOCK_INDEX && count>=3)integer_block_applied(instruction,3);
#endif
#if defined(LANGUAGE_VM_TEST_COMPARE_BLOCK) && MK61_VM_COMPARE_BLOCK
    if(first_hint==Op::BLOCK_COMPARE && count>=3)compare_block_applied(instruction);
#endif
    s.sp=(uint8_t)(top-bottom);s.pc=uint32_t(pc-origin);instruction=uint32_t(last-origin);steps+=count-1U;
  }
#undef SPAN_TRACE
  return count;
}
#endif
}  // namespace
#if defined(LANGUAGE_VM_TRACE)
uint16_t trace_following(const View& v,uint16_t pc) {return uint16_t(next(v,pc));}
#endif

namespace {
uint32_t instruction_after(const View& v,uint32_t pc,uint8_t op) {
  if(pc>=v.end)return 0;
  if(op>=sizeof(wire_widths))return 0;
  static_assert([]() constexpr {
    for(uint8_t width:wire_widths)if(width>14 && width!=255)return false;
    return true;
  }(),"fixed instruction width exceeds its packed nibble");
  static constexpr auto wide_widths=[]() constexpr {
    uint8_t widths[sizeof(wire_widths)]={};
    for(unsigned i=0;i<sizeof(wire_widths);++i)widths[i]=wire_widths[i];
    for(Op code:{Op::JUMP,Op::JUMP_FALSE,Op::GOTO_DIRECT,Op::GOSUB_DIRECT,Op::GRAPH_BEGIN,Op::GRAPH_NEXT})widths[unsigned(code)]=5;
    widths[unsigned(Op::COMPARE_FALSE)]=6;widths[unsigned(Op::DO_FOCAL)]=9;
    widths[unsigned(Op::BRANCH)]=13;widths[unsigned(Op::CALL_PARAMS)]=11;
    widths[unsigned(Op::FOR_FOCAL)]=7;
    // Widths are 0..13; 15 denotes a variable record. Two per byte recover
    // space for hot-path guards without changing any bytecode encoding.
    struct Table {uint8_t bytes[(sizeof(wire_widths)+1)/2];} table={};
    for(unsigned i=0;i<sizeof(wire_widths);++i)
      table.bytes[i>>1]|=uint8_t((widths[i]==255?15:widths[i])<<((i&1)*4));
    return table;
  }();
  const unsigned width=v.wide_code()?((wide_widths.bytes[op>>1]>>((op&1)*4))&15):wire_widths[op];
  const uint32_t remaining=v.end-pc;
  if(width!=(v.wide_code()?15:255))return width && width<=remaining?pc+width:0;
  const unsigned prefix=v.wide && Op(op)==Op::DATA?5:3;
  if(remaining<prefix)return 0;
  const uint32_t count=prefix==5?dword(v.at(pc+1)):word(v.at(pc+1));
  if(Op(op)==Op::ON_GOTO || Op(op)==Op::ON_GOSUB)
    return count && count<=(remaining-3)/2?pc+3+count*2:0;
  if(Op(op)==Op::DATA && !count)return 0;
  return count<=remaining-prefix?pc+prefix+count:0;
}
}
uint32_t instruction_end(const View& v,uint32_t pc) {
  return pc<v.end?instruction_after(v,pc,v.byte(pc)):0;
}
namespace {
class Boundaries {
  union Storage {
    // The paged Writer already owns a full 1-KiB page. Reuse the same union
    // footprint as a bitmap for small LBV2 images, not NOR scratch files.
    uint8_t raw[flash::WRITE_BYTES];
    flash::Writer output;
    Storage():raw{} {}
    ~Storage() {}
  } storage_;
  flash::IO io_;
  bool wide_,good_=true,output_=false;
public:
  Boundaries(bool wide,flash::IO io):io_(io),wide_(wide) {}
  ~Boundaries(){if(output_)storage_.output.~Writer();}
  bool prepare(uint32_t end) {
    if(!wide_)return true;
    if(end<=sizeof(storage_.raw)*8U){wide_=false;return true;}
    new(&storage_.output) flash::Writer(io_,flash::BOUNDARIES);output_=true;
    if(!io_.truncate(io_.context,flash::BOUNDARIES,0))return false;
    // Fill skipped DATA/string pages too. Corrupt targets into them must be
    // rejected as non-boundaries, never read as uninitialized Flash.
    const uint8_t zero[64]={};
    const uint32_t size=(end+7)/8;
    for(uint32_t at=0;at<size;) {
      const unsigned n=size-at<sizeof(zero)?size-at:sizeof(zero);
      if(!storage_.output.write(at,zero,n))return false;
      at+=n;
    }
    return storage_.output.flush();
  }
  bool mark(uint32_t pc) {
    if(!wide_) {storage_.raw[pc>>3]|=uint8_t(1U<<(pc&7));return true;}
    uint8_t bits;
    return storage_.output.read(pc>>3,&bits,1) && storage_.output.byte(pc>>3,uint8_t(bits|(1U<<(pc&7))));
  }
  bool flush() {return !wide_ || storage_.output.flush();}
  bool test(uint32_t pc) {
    uint8_t bits=0;
    if(wide_) {if(!storage_.output.read(pc>>3,&bits,1))good_=false;}
    else bits=storage_.raw[pc>>3];
    return (bits&(1U<<(pc&7)))!=0;
  }
  bool good() const {return good_;}
};
Error verify(const View& v, Boundaries& boundaries) {
  const uint32_t length=v.size;
  if(!boundaries.prepare(v.end))return Error::IO;
  // Only code needs a bitmap. Resource boundaries are scanned once here and
  // looked up in the bounded directory, keeping the verifier stack unchanged.
  for (uint32_t at = v.end; at < length;) {
    if(v.byte(7) & OWNED_RESOURCE_FLAG) {
      if(length-at<2 || word(v.at(at))>length-at-2) return Error::INVALID_IMAGE;
      at += (uint16_t)(2+word(v.at(at))); continue;
    }
    if (length - at < 3 || v.byte(at + 2) > (length - at - 3) / 3)
      return Error::INVALID_IMAGE;
    unsigned total = 0;
    for (uint8_t i = 0; i < v.byte(at + 2); ++i) {
      const auto p = v.at(at + 3 + i * 3);
      const uint16_t offset = word(p); const uint8_t n = p[2];
      if (n ? offset > v.source_size || n > v.source_size-offset : offset > 255)
        return Error::INVALID_IMAGE;
      total += n ? n : 1;
    }
    if (total != word(v.at(at))) return Error::INVALID_IMAGE;
    at += (uint16_t)(3 + v.byte(at + 2) * 3);
  }
  auto resource_boundary = [&](uint16_t wanted) {
    for(uint32_t at=v.end;at<length;) {
      if(at==wanted) return true;
      at += (uint16_t)((v.byte(7) & OWNED_RESOURCE_FLAG) ? 2+word(v.at(at)) : 3+v.byte(at+2)*3);
    }
    return false;
  };
  for (uint32_t pc = v.code; pc < v.end;) {
    if(!boundaries.mark(pc))return Error::IO;
    const uint32_t following = next(v, pc);
    if (!following) return Error::INVALID_IMAGE;
    const Op op = (Op)v.byte(pc);
    // Expression images share the opcode space, but must be side-effect-free
    // with respect to program variables and control frames. This permits the
    // hot INPUT evaluator to borrow the suspended program's stack safely.
    if (v.expression && op != Op::HALT && op != Op::CONST_I8 &&
        op != Op::CONST_I16 && op != Op::BLOCK_INDEX && op != Op::CONST_I32 && op != Op::CONST_F64 && op != Op::CONST_DEC8 &&
        op != Op::CONST_DEC16 && op != Op::LOAD && op != Op::INTEGER_SPAN && op != Op::INTEGER_SHORT && op != Op::LOAD_REF &&
        op != Op::LOAD_ARRAY && op != Op::ARRAY_CELL && op != Op::LOAD_ARRAY_FIXED && !(op >= Op::NEG && op <= Op::CHECK) && op != Op::FLOOR_DIV &&
        !(op >= Op::CONST_0 && op <= Op::CONST_15) &&
        !(op==Op::GRAPHICS && v.byte(pc+1)==(uint8_t)basic_graphics::Operation::POINT)) return Error::INVALID_IMAGE;
    if(op==Op::BLOCK_INDEX && (v.end-pc<6 ||
        (Op)v.byte(pc+3)!=Op::LOAD || (Op)v.byte(pc+5)!=Op::ADD))return Error::INVALID_IMAGE;
    if(op==Op::BLOCK_COMPARE) {
      const uint32_t rhs=pc+2, cmp=next(v,rhs);
      if(!cmp || v.end-cmp<2U+v.address_bytes() || (Op)v.byte(cmp)!=Op::COMPARE_FALSE ||
         !((Op)v.byte(rhs)>=Op::CONST_0 && (Op)v.byte(rhs)<=Op::CONST_15))return Error::INVALID_IMAGE;
    }
    if (((op == Op::LOAD || op == Op::INTEGER_SPAN || op == Op::INTEGER_SHORT || op == Op::BLOCK_COMPARE || op == Op::STORE || op == Op::NEXT_BASIC ||
          op == Op::FOR_BASIC || op == Op::FOR_FOCAL) &&
         v.byte(pc + 1) >= 26) ||
        ((op == Op::LOAD_REF || op == Op::STORE_REF || op == Op::TARGET_REF) &&
         v.byte(pc + 1) >= 20) ||
        (op == Op::FUNCTION && v.byte(pc + 1) > (uint8_t)Function::GH) ||
        (op == Op::READ_KEY && (v.expression || v.language != Language::BASIC)) ||
        (op == Op::PRINT_SEPARATOR && v.byte(pc + 1) > 2) ||
        (op == Op::PRINT_END && v.byte(pc + 1) > 1) ||
        (op == Op::COMPARE_FALSE && v.byte(pc+1)>15) ||
        (op == Op::UPDATE_LOCAL && (v.byte(pc+1)>=26 ||
            ((v.byte(pc+2)&0x40) && (v.byte(pc+2)&0x3F)>=26))) ||
        (op == Op::FOR_FOCAL && v.byte(pc + 2 + v.address_bytes()) > 1))
      return Error::INVALID_IMAGE;
    if(op>=Op::GRAPHICS && v.expression &&
       !(op==Op::GRAPHICS && v.byte(pc+1)==(uint8_t)basic_graphics::Operation::POINT))
      return Error::INVALID_IMAGE;
    if(op==Op::GRAPHICS) {
      const auto operation=(basic_graphics::Operation)v.byte(pc+1);
      if((operation!=basic_graphics::Operation::PSET && operation!=basic_graphics::Operation::POINT &&
          operation!=basic_graphics::Operation::LINE && operation!=basic_graphics::Operation::BOX &&
          operation!=basic_graphics::Operation::CIRCLE && operation!=basic_graphics::Operation::SHOW) ||
         v.byte(pc+2)<basic_graphics::minimum(operation) || v.byte(pc+2)>basic_graphics::maximum(operation))
        return Error::INVALID_IMAGE;
    }
    if (op >= Op::DATA && op < Op::SOURCE_POS && v.language != Language::BASIC)
      return Error::INVALID_IMAGE;
    if((op==Op::GOTO_DIRECT || op==Op::GOSUB_DIRECT) && v.language!=Language::BASIC)
      return Error::INVALID_IMAGE;
    if (op == Op::PRINT_RESOURCE || op == Op::INPUT_RESOURCE) {
      const uint32_t at = (uint32_t)v.end + word(v.at(pc + 1));
      if (!(v.byte(7) & 4) || at >= length ||
          !resource_boundary((uint16_t)at) ||
          (op == Op::INPUT_RESOURCE && word(v.at(at)) > 95))
        return Error::INVALID_IMAGE;
    }
    if ((op == Op::ARRAY_CELL && v.byte(pc+1)>=26) ||
        (op == Op::CALL_PARAMS && (v.byte(pc+1+2*v.address_bytes())>4 || v.byte(pc+2+2*v.address_bytes())>1)) ||
        (op == Op::PRINT_PRECISION && (v.byte(pc+1)>64 || !v.byte(pc+2) || v.byte(pc+2)>15)) ||
        ((op == Op::ARRAY_CELL || op == Op::DROP) && v.language != Language::FOCAL))
      return Error::INVALID_IMAGE;
    if (op == Op::DATA) {
      const uint32_t end = following;
      for (uint32_t at = (pc + (v.wide_code()?5:3)); at < end;) {
        uint32_t following=0;
        Value value=0;
        if(!data_value(v,at,end,value,following)) return Error::INVALID_IMAGE;
        at = following;
      }
    }
    if (op == Op::SOURCE_POS && (!word(v.at(pc + 1)) || word(v.at(pc + 1)) > v.source_size))
      return Error::INVALID_IMAGE;
    if (op == Op::ON_GOTO || op == Op::ON_GOSUB)
      for (uint16_t i = 0; i < word(v.at(pc + 1)); ++i) {
        const uint16_t line = word(v.at(pc + 3 + i * 2));
        if (!line || line > 32767) return Error::INVALID_IMAGE;
      }
    pc = following;
  }
  if(!boundaries.flush())return Error::IO;
  auto target = [&](uint32_t pc) {
    return pc == v.missing() || (pc >= v.code && pc < v.end && boundaries.test(pc));
  };
  for (uint16_t i = 0; i < v.lines; ++i) {
    const uint32_t number = record_number(v, i);
    if (!number || number > (v.language == Language::BASIC ? 32767U : 999999U) ||
        (i && number <= record_number(v, (uint16_t)(i - 1))) ||
        !target(record_pc(v, i)) || record_pc(v, i) == v.missing() ||
        (!i && record_pc(v, i) != v.code) ||
        (i && record_pc(v, i) <= record_pc(v, (uint16_t)(i - 1))))
      return Error::INVALID_IMAGE;
  }
  for (uint32_t pc = v.code; pc < v.end; pc = next(v, pc)) {
    const Op op = (Op)v.byte(pc);
    if ((op == Op::JUMP || op == Op::JUMP_FALSE || op==Op::GOTO_DIRECT || op==Op::GOSUB_DIRECT ||
         op==Op::GRAPH_BEGIN || op==Op::GRAPH_NEXT) &&
        !target(v.address(v.at(pc + 1))))
      return Error::INVALID_IMAGE;
    if(op==Op::GRAPH_BEGIN) {
      const uint32_t finish=v.address(v.at(pc+1));
      if(finish<=pc+1+v.address_bytes() || (Op)v.byte(finish)!=Op::GRAPH_NEXT || v.address(v.at(finish+1))!=pc+1+v.address_bytes())
        return Error::INVALID_IMAGE;
      for(uint32_t at=(pc+1+v.address_bytes());at<finish;at=next(v,at)) {
        const auto inner=(Op)v.byte(at);
        const bool allowed=(inner>=Op::CONST_I8 && inner<=Op::LOAD_REF) ||
            inner==Op::LOAD_ARRAY || (inner>=Op::NEG && inner<=Op::FUNCTION) ||
            inner==Op::CONST_DEC8 || inner==Op::CONST_DEC16 || inner==Op::CONST_I32 ||
            inner==Op::FLOOR_DIV || inner==Op::LOAD_ARRAY_FIXED || inner==Op::SOURCE_POS ||
            inner==Op::LOAD_PARAMETER || inner==Op::BLOCK_INDEX || inner==Op::INTEGER_SPAN || inner==Op::INTEGER_SHORT ||
            (inner>=Op::CONST_0 && inner<=Op::CONST_15) ||
            (inner==Op::GRAPHICS && v.byte(at+1)==(uint8_t)basic_graphics::Operation::POINT);
        if(!allowed || inner==Op::STORE || (inner==Op::FUNCTION &&
            (v.byte(at+1)==(uint8_t)Function::RND || v.byte(at+1)==(uint8_t)Function::RND_LIMIT)))
          return Error::INVALID_IMAGE;
      }
    }
    if(op==Op::GRAPH_NEXT) {
      const auto body=v.address(v.at(pc+1));
      if(body<v.code+1+v.address_bytes() || (Op)v.byte(body-1-v.address_bytes())!=Op::GRAPH_BEGIN || v.address(v.at(body-v.address_bytes()))!=pc)
        return Error::INVALID_IMAGE;
    }
    if(op==Op::COMPARE_FALSE && !target(v.address(v.at(pc+2)))) return Error::INVALID_IMAGE;
    if(op==Op::DO_FOCAL || op==Op::CALL_PARAMS) {
      const uint32_t to=v.address(v.at(pc+1)), packed=v.address(v.at(pc+1+v.address_bytes()));
      const uint32_t end=packed==v.missing()?v.missing():packed&(v.group_bit()-1);
      if(!target(to) || (!(v.language==Language::BASIC && !packed) && !target(end)))return Error::INVALID_IMAGE;
      if(op==Op::CALL_PARAMS && !(v.language==Language::BASIC && !v.byte(pc+2+2*v.address_bytes()) && !packed) &&
         to!=v.missing() && (packed==v.missing() || end<=to))return Error::INVALID_IMAGE;
    }
    if(op==Op::FOR_FOCAL && !target(v.address(v.at(pc+2))))return Error::INVALID_IMAGE;
    if (op == Op::BRANCH)
      for (uint8_t i = 0; i < 3; ++i)
        if (!target(v.address(v.at(pc + 1 + i * v.address_bytes())))) return Error::INVALID_IMAGE;
  }
  return v.good() && boundaries.good()?Error::NONE:Error::IO;
}
} // namespace
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
      v.code != HEADER_SIZE + uint32_t(v.lines) * stride(v) || v.code >= v.end ||
      !v.source_size || v.source_size > source::MAX_SIZE ||
      checksum(bytes + HEADER_SIZE, length - HEADER_SIZE) != dword(bytes + 20))
    return Error::INVALID_IMAGE;
  Boundaries boundaries(false,{});
  const Error error=verify(v,boundaries);
  if(error==Error::NONE)out=v;
  return error;
}
Error inspect_flash(const flash::Reader& reader,flash::IO io,View& out) {
  out={};uint8_t h[HEADER_SIZE];
  if(!io.read || !io.write || !io.truncate)return Error::IO;
  if(reader.size()<HEADER_SIZE)return Error::INVALID_IMAGE;
  if(!reader.read(0,h,sizeof(h)))return Error::IO;
  if(memcmp(h,"LBV2",4) || h[4]!=14 || (h[5]!=1 && h[5]!=2) ||
     !h[6] || h[6]>MAX_STACK || (h[7]&~2) || dword(h+8)!=reader.size())return Error::INVALID_IMAGE;
  View v={nullptr,reader.size(),dword(h+12),word(h+18),word(h+16),h[6],Language(h[5]),false,(h[7]&2)!=0,dword(h+28),&reader,true};
  if(!v.lines || !v.source_size || v.source_size>source::MAX_SIZE ||
     v.code!=HEADER_SIZE+uint32_t(v.lines)*8 || v.code>=v.end || v.end!=v.size)return Error::INVALID_IMAGE;
  uint32_t crc=0xFFFFFFFF;
  uint8_t page[64];
  for(uint32_t at=HEADER_SIZE;at<v.size;) {
    const uint16_t n=uint16_t(v.size-at<sizeof(page)?v.size-at:sizeof(page));
    if(!reader.read(at,page,n) || !io.poll())return Error::IO;
    for(unsigned i=0;i<n;++i){crc^=page[i];for(unsigned j=0;j<8;++j)crc=(crc>>1)^(0xEDB88320U&uint32_t(-int32_t(crc&1)));}
    at+=n;
  }
  if(~crc!=dword(h+24))return Error::INVALID_IMAGE;
  Boundaries boundaries(true,io);
  const Error error=verify(v,boundaries);
  if(error==Error::NONE){out=v;out.lookup=io.lookup;out.lookup_context=io.context;}
  return reader.good()?error:Error::IO;
}
uint32_t line_pc(const View& v, uint32_t number) {
  if(v.lookup) {
    uint32_t result;
    if(v.lookup(v.lookup_context,number,true,&result))return result;
    if(v.reader)v.reader->fail();
    return v.missing();
  }
#if defined(MK61_BUILD_LANGUAGE_VM_MODULE)
  return v.missing();
#else
  uint16_t first=0,last=v.lines;
  while(first<last) {
    const uint16_t middle=(uint16_t)(first+(last-first)/2);
    const uint32_t found=record_number(v,middle);
    if(found==number) return record_pc(v,middle);
    if(found<number) first=(uint16_t)(middle+1); else last=middle;
  }
  return v.missing();
#endif
}
uint32_t source_line(const View& v, uint32_t pc) {
  if(v.lookup) {
    uint32_t result;
    if(v.lookup(v.lookup_context,pc,false,&result))return result;
    if(v.reader)v.reader->fail();
    return 0;
  }
#if defined(MK61_BUILD_LANGUAGE_VM_MODULE)
  return 0;
#else
  uint16_t first=0,last=v.lines;
  while(first<last) {
    const uint16_t middle=(uint16_t)(first+(last-first)/2);
    if(record_pc(v,middle)<=pc) first=(uint16_t)(middle+1); else last=middle;
  }
  return first ? record_number(v,(uint16_t)(first-1)) : 0;
#endif
}

uint16_t source_column(const View& v, uint32_t pc) {
  uint16_t column = 0;
  for (uint32_t at = v.code; at <= pc && at < v.end;) {
    const uint32_t following = next(v, at);
    if (!following) return 0;
    if ((Op)v.byte(at) == Op::SOURCE_POS) column = word(v.at(at + 1));
    if ((Op)v.byte(at) == Op::LINE) column = 0;
    at = following;
  }
  return column;
}

namespace {
__attribute__((noinline)) bool valid_resume(const View& v,const Continuation& s,const Bindings& data) {
    uint32_t cursor = v.code;
    while (cursor < s.data_pc) {
      const uint32_t following = next(v, cursor);
      if (!following) return false;
      cursor = following;
    }
    if (cursor != s.data_pc ||
        (s.data_index && (cursor >= v.end || (Op)v.byte(cursor) != Op::DATA ||
                          s.data_index > (v.wide_code()?dword(v.at(cursor+1)):word(v.at(cursor+1))))))
      return false;
    if (s.data_index) {
      uint32_t at = (s.data_pc + (v.wide_code()?5:3)), target = (at + s.data_index);
      while (at < target) {
        uint32_t following=0;
        Value value=0;
        const uint32_t end=(s.data_pc+(v.wide_code()?5:3)+(v.wide_code()?dword(v.at(s.data_pc+1)):word(v.at(s.data_pc+1))));
        if(!data_value(v,at,end,value,following)) return false;
        at=following;
      }
      if (at != target) return false;
    }
    for (uint8_t i = 0; i < s.call_count; ++i) {
      const auto& f = s.calls[i];
      if (f.resume < v.code || f.resume >= v.end || f.loops > MAX_LOOPS ||
          (f.mode & 8) || ((f.mode & 4) && (f.mode & 3)!=3) || (f.mode & 3) == 2 ||
          ((f.mode >> 4) && (f.mode & 3) != 3) || f.print_width > 64 ||
          (!(f.mode >> 4) && f.print_width) ||
          f.arguments>4 || unsigned(f.base)+f.arguments>data.stack_capacity ||
          (f.end && (f.end < v.code || f.end >= v.end)))
        return false;
    }
    for (uint8_t i = 0; i < s.loop_count; ++i) {
      const auto& f = s.loops[i];
      if (((f.variable & 0x8000U) ? (!data.array || (f.variable & 0x7FFFU) >= data.array_count)
                                  : f.variable >= 26) ||
          f.body < v.code || f.body >= v.end || (f.end && (f.end < v.code || f.end >= v.end)))
        return false;
    }
  return v.good();
}
}
namespace {
RunResult completed_run(const View& v,Error error,uint32_t pc,uint32_t steps) {
  const uint32_t line=source_line(v,pc);
  return {v.good()?error:Error::IO,pc,line,steps};
}
}
RunResult run(const View& v, State& s, const Services& host, uint32_t limit,
              bool resume) {
  return run(v, static_cast<Continuation&>(s), static_cast<const Bindings&>(s),
             host, limit, resume);
}
#if defined(__GNUC__) && !defined(__clang__) && !defined(MK61_CORE_STANDALONE)
__attribute__((optimize("no-inline-functions-called-once")))
#endif
#if defined(MK61_CORE_STANDALONE) && defined(PICO_ON_DEVICE) && PICO_ON_DEVICE
// Avoid XIP cache competition with the service loop. O2 saves 4 KiB of SRAM
// against O3 here, retaining heap space for APPs and prepared text fonts.
__attribute__((section(".time_critical.mk61_vm_run"),optimize("O2")))
#endif
RunResult run(const View& v, Continuation& s, const Bindings& data,
              const Services& host, uint32_t limit, bool resume) {
  if ((!v.bytes && !v.reader) || !data.variables || !data.stack || data.stack_capacity < v.stack ||
      data.stack_capacity > MAX_STACK)
    return {Error::INVALID_IMAGE, 0, 0, 0};
  if (!resume) {
    s.pc = v.code;
    s.sp = s.call_count = s.loop_count = 0;
    s.data_pc = v.code;
    s.data_index = 0;
    s.graph.active=false;
  } else if (s.graph.active || s.pc < v.code || s.pc >= v.end || s.sp > data.stack_capacity ||
             s.call_count > (v.language == Language::BASIC ? MAX_CALLS : 8) ||
             s.loop_count > MAX_LOOPS || s.data_pc < v.code || s.data_pc > v.end) {
    return {Error::INVALID_IMAGE, 0, 0, 0};
  }
  if(resume && !valid_resume(v,s,data))return {v.good()?Error::INVALID_IMAGE:Error::IO,0,0,0};
  Error error = Error::NONE;
  struct RestoreGraph {
    Continuation& state;const Bindings& data;
    ~RestoreGraph(){if(state.graph.active){data.variables['X'-'A']=state.graph.saved_x;state.graph.active=false;}}
  } restore_graph{s,data};
  uint32_t steps = 0;
  uint32_t instruction = s.pc;
  VM_OPCODE_PROFILE(v);
  // Compact decimal constants are exact wire recipes. Decode each hot recipe
  // once instead of repeating soft-double pow10/division in a loop. Eight
  // direct-mapped entries are bounded stack scratch, never part of an image
  // or a continuation; INPUT/resume simply starts a fresh cache.
  Value decimal_values[8];
  uint32_t decimal_pcs[8]={UINT32_MAX,UINT32_MAX,UINT32_MAX,UINT32_MAX,UINT32_MAX,UINT32_MAX,UINT32_MAX,UINT32_MAX};
  auto push = [&](Value value) {
    // The outlined push already receives both words in registers. Test the
    // tag/exponent here, avoiding a spill and another call to finite().
    // Shifting the high word discards the sign; NaNs and infinities are the
    // remaining values at or above 0xFFE00000, apart from our int32 tag.
    const uint32_t high=(uint32_t)(value.representation()>>32);
    if (high!=Value::INTEGER_TAG && (high<<1)>=UINT32_C(0xFFE00000))
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
  auto jump = [&](uint32_t to) {
    if (to < v.code || to >= v.end)
      error = Error::LINE;
    else
      s.pc = to;
  };
  auto call = [&](uint32_t to, uint32_t end) {
    if (v.language == Language::BASIC && to == v.missing()) { error=Error::MISSING_LINE; return; }
    const uint8_t maximum = v.language == Language::BASIC ? MAX_CALLS : 8;
    if (s.call_count >= maximum)
      error = v.language == Language::BASIC ? Error::CALL_STACK : Error::STACK;
    else {
      s.calls[s.call_count++] = {s.pc, (end & (v.group_bit()-1)), s.loop_count,
                                 (end & v.group_bit()) != 0, s.sp};
      jump(to);
    }
  };
  auto restore_print = [&](const CallFrame& frame) {
    if(frame.mode & 4) {Value unused=0;event(Event::PRINT_POP,nullptr,0,unused);}
    if(frame.mode >> 4) {
      Value width = frame.print_width;
      event(Event::PRECISION, nullptr, frame.mode >> 4, width);
    }
  };
  // Procedure groups propagate a source-level jump to their caller. A
  // single-line DO catches it and returns. Value calls keep their own frame
  // so internal branches can still compute an explicit function result.
  auto focal_jump = [&](uint32_t to) {
    if(to<v.code || to>=v.end){error=Error::LINE;return;}
    while(s.call_count) {
      const auto frame=s.calls[s.call_count-1];
      if(frame.mode&2)break;
      --s.call_count;s.loop_count=frame.loops;if(frame.mode)s.sp=frame.base;
      if(!frame.group){s.pc=frame.resume;return;}
    }
    while(s.loop_count && (to<s.loops[s.loop_count-1].body || to>=s.loops[s.loop_count-1].end))--s.loop_count;
    jump(to);
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
    Op op=Op::HALT;
    while(s.pc<v.end && (op=Op(v.reader?v.byte(s.pc):v.bytes[s.pc]))==Op::SOURCE_POS) {
      instruction=s.pc;
      if(v.end-s.pc<3) {error=Error::INVALID_IMAGE;break;}
      s.pc=(s.pc+3);
    }
    if(error!=Error::NONE) break;
    if (s.pc >= v.end) {
      error = Error::INVALID_IMAGE;
      break;
    }
    if(!v.good()){error=Error::IO;break;}
    instruction = s.pc;
    if (limit && steps == limit) {
      error = Error::LIMIT;
      break;
    }
    if ((steps++ & 31U) == 0 && host.service) {
      if(!host.service(host.context)) {
        error = Error::STOPPED;
        break;
      }
      // A service callback can modify a raw image through shared banks.
      // Otherwise the prefix scan has already fetched this opcode.
      op=Op(v.byte(s.pc));
    }
    VM_OPCODE_SAMPLE(scalar_op(op), s, data);
#if defined(LANGUAGE_VM_TRACE)
    trace_instruction(v, s.pc, steps);
#endif
#if defined(MK61_FOCAL_TRACE) && MK61_FOCAL_TRACE
    if(v.language==Language::FOCAL && host.event) {
      const uint8_t trace_opcode=uint8_t(op);
      double line=(double)source_line(v,s.pc);
      if(!host.event(host.context,Event::TRACE,(const char*)&trace_opcode,s.pc,line)) {error=Error::IO;break;}
    }
#endif
    // Metadata needs no operand decoder, constant decoder or value scratch.
    // Keep logical steps/service cadence and the original safety checks.
    if(op==Op::LINE) {
      ++s.pc;
      const uint8_t base=s.call_count
          ? (uint8_t)(s.calls[s.call_count-1].base+s.calls[s.call_count-1].arguments) : 0;
      if(s.sp!=base) error=Error::STACK;
      continue;
    }
#if MK61_VM_INTEGER_SPAN
    // The span validates every supported start itself, before the generic
    // operand decoder/snapshot. Keep disabled hints on their scalar fallback.
    if(op==Op::INTEGER_SPAN || op==Op::CONST_I8 || op==Op::CONST_I16 || op==Op::CONST_I32 ||
       (op>=Op::CONST_0 && op<=Op::CONST_15)
#if MK61_VM_INTEGER_BLOCK
       || op==Op::BLOCK_INDEX
#endif
#if MK61_VM_COMPARE_BLOCK
       || op==Op::BLOCK_COMPARE
#endif
       ) {
      const uint8_t count=integer_span(v,s,data,steps,instruction,limit);
      if(count) {VM_OPCODE_FUSED(count);continue;}
    }
#endif
    if(op>=Op::CONST_0 && op<=Op::CONST_15) {
      ++s.pc;push(Value((uint8_t)op-(uint8_t)Op::CONST_0));continue;
    }
    // Share width/bounds checks with the cold verifier, but reuse the opcode
    // already fetched by dispatch. Only variable records decode their count.
    const uint32_t after=instruction_after(v,s.pc,uint8_t(op));
    if (!after) {
      error = Error::INVALID_IMAGE;
      break;
    }
    // The opcode is already known. Read only the aligned operand payload;
    // variable records need just their two-byte count here.
    alignas(4) uint8_t operands[12];
    const uint8_t operand_bytes=uint8_t(after-instruction-1<=sizeof(operands)?after-instruction-1:2);
    if(operand_bytes) {
      // Copy a bounded raw snapshot with a compile-time size. Near the code
      // end and for paged images retain the original exact-sized I/O.
      if(!v.reader && v.end-instruction-1>=sizeof(operands))
        __builtin_memcpy(operands,v.bytes+instruction+1,sizeof(operands));
      else if(!v.read(instruction+1,operands,operand_bytes)){error=Error::IO;break;}
    }
    const uint8_t* p=operands;
    s.pc = after;
    Value a = 0, b = 0, value = 0;
    switch (op) {
#if MK61_VM_INTEGER_BLOCK && !MK61_VM_INTEGER_SPAN
      case Op::BLOCK_INDEX:
        {
          const uint8_t count=compiled_block(v,s,data,steps,instruction,limit,op,p);
          if(count) {
            VM_OPCODE_FUSED(count);
            break;
          }
        }
        [[fallthrough]];
#endif
      case Op::CONST_I8:case Op::CONST_I16:case Op::CONST_I32:
#if !MK61_VM_INTEGER_BLOCK || MK61_VM_INTEGER_SPAN
      case Op::BLOCK_INDEX:
#endif
      case Op::CONST_F64:
        (void)decode_constant(op,p,value);push(value);
        break;
      case Op::CONST_DEC8:
      case Op::CONST_DEC16: {
        const uint8_t slot=(instruction>>2)&7;
        if(decimal_pcs[slot]!=instruction) {
          (void)decode_constant(op,p,decimal_values[slot]);
          decimal_pcs[slot]=instruction;
        }
        push(decimal_values[slot]);
        break;
      }
      case Op::HALT: {
        const uint8_t expected=v.expression?1:s.call_count
            ? (uint8_t)(s.calls[s.call_count-1].base+s.calls[s.call_count-1].arguments):0;
        if(s.sp!=expected)error=Error::STACK;
        else if(v.language==Language::FOCAL && !v.expression)s.sp=s.call_count=s.loop_count=0;
        if(error==Error::NONE && !v.expression && host.event)
          event(Event::FINISH, nullptr, 0, value);
        return completed_run(v,error,instruction,steps);
      }
      case Op::DATA:
        break;
      case Op::READ_DATA: {
        while (s.data_pc < v.end) {
          const uint32_t following = next(v, s.data_pc);
          if (!following) {
            error = Error::INVALID_IMAGE;
            break;
          }
          if ((Op)v.byte(s.data_pc) == Op::DATA) {
            const uint32_t count = v.wide_code()?dword(v.at(s.data_pc+1)):word(v.at(s.data_pc+1));
            if (s.data_index < count) {
              const uint32_t literal = (s.data_pc + (v.wide_code()?5:3) + s.data_index);
              uint32_t following=0;
              if(!data_value(v,literal,(s.data_pc+(v.wide_code()?5:3)+count),value,following)) {
                error = Error::INVALID_IMAGE;
                break;
              }
              s.data_index = (s.data_index + following - literal);
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
        const uint32_t to = a == 0 ? v.code : line_pc(v, (uint32_t)b.number());
        if (to == v.missing()) {
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
        const uint32_t to = line_pc(v, image_word(v, instruction + 3 + ((uint16_t)a.number() - 1) * 2));
        if (to == v.missing())
          error = Error::MISSING_LINE;
        else if (op == Op::ON_GOSUB)
          call(to, 0);
        else
          jump(to);
        break;
      }
      case Op::INTEGER_SPAN:
        [[fallthrough]];
      case Op::INTEGER_SHORT:
#if MK61_VM_INTEGER_SPAN
        if(op==Op::INTEGER_SHORT) {
          const uint8_t count=compiled_block(v,s,data,steps,instruction,limit,op,p);
          if(count) {VM_OPCODE_FUSED_VALUE(count);break;}
        }
#endif
        [[fallthrough]];
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
        const uint8_t count=p[2*v.address_bytes()];
        if(s.sp<count || count>4 || p[2*v.address_bytes()+1]>1) {error=Error::STACK;break;}
        const uint8_t base=(uint8_t)(s.sp-count);
        call(v.address(p),v.address(p+v.address_bytes()));
        if(error==Error::NONE) {
          auto& f=s.calls[s.call_count-1];f.base=base;f.arguments=count;f.mode=(uint8_t)(1|(p[2*v.address_bytes()+1]?2:0));
          if(p[2*v.address_bytes()+1] && host.event) {
            if(host.isolate_print) {
              Value unused=0;event(Event::PRINT_PUSH,nullptr,0,unused);
              if(error==Error::NONE)f.mode|=4;
            }
            double format = 0;
            if(host.event(host.context,Event::PRINT_STATE,nullptr,0,format) &&
               format >= 1 && format <= 1039 && format == mk_math::trunc(format)) {
              const auto packed = (uint16_t)format;
              if(packed & 15) { f.mode |= (uint8_t)((packed & 15) << 4); f.print_width = (uint8_t)(packed >> 4); }
            }
          }
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
        if(error==Error::NONE)restore_print(frame);
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
      case Op::BLOCK_COMPARE:
#if MK61_VM_COMPARE_BLOCK && !MK61_VM_INTEGER_SPAN
        if(compiled_block(v,s,data,steps,instruction,limit,op,p)) {
          VM_OPCODE_FUSED(3);
          if(!v.read(instruction+1,operands,uint16_t(1+v.address_bytes()))){error=Error::IO;break;}
          p=operands;
        } else
#endif
        {
          if(*p>=26)error=Error::INVALID_IMAGE;else push(data.variables[*p]);
          break;
        }
        [[fallthrough]];
      case Op::COMPARE_FALSE:
        if(s.sp<2) error=Error::STACK;
        else {
          s.sp=(uint8_t)(s.sp-2);
          // The cold verifier rejects reserved mask bits. The hot operation
          // uses only four bounded order bits, never an unchecked table index.
          if(!comparison(data.stack[s.sp],data.stack[s.sp+1],*p)) jump(v.address(p+1));
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
          case Function::GW:
          case Function::GH:
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
        if(v.language==Language::FOCAL)focal_jump(v.address(p));else jump(v.address(p));break;
      case Op::JUMP_FALSE:
        a = pop();
        if (error == Error::NONE && a.zero()) jump(v.address(p));
        break;
      case Op::GOTO:
      case Op::GOSUB:
        a = pop();
        b = (a + Value(.5)).floor();
        if (!a.finite() || a < 1 || a > 32767 || mk_math::fabs((a - b).number()) > 1e-7)
          error = v.language == Language::BASIC ? Error::LINE_NUMBER : Error::LINE;
        else if (error == Error::NONE) {
          const uint32_t to = line_pc(v, (uint32_t)b.number());
          if (to == v.missing() && v.language == Language::BASIC)
            error = Error::MISSING_LINE;
          else if (op == Op::GOTO)
            jump(to);
          else
            call(to, 0);
        }
        break;
      case Op::GOTO_DIRECT:
      case Op::GOSUB_DIRECT:
        if(v.address(p)==v.missing()) error=Error::MISSING_LINE;
        else if(op==Op::GOSUB_DIRECT) call(v.address(p),0);
        else jump(v.address(p));
        break;
      case Op::RETURN:
        if (!s.call_count)
          error = Error::RETURN;
        else {
          const auto frame = s.calls[--s.call_count];
          s.pc = frame.resume;
          s.loop_count = frame.loops;
          s.sp=frame.base;
          if(frame.mode&2)error=Error::RETURN;
        }
        break;
      case Op::DO_FOCAL:
        call(v.address(p), v.address(p + v.address_bytes()));
        break;
      case Op::BRANCH:
        a=pop();if(error==Error::NONE){const uint32_t to=v.address(p+(a<0?0:a==0?1:2)*v.address_bytes());if(to!=v.missing())focal_jump(to);}break;
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
        if (op == Op::FOR_FOCAL && p[1+v.address_bytes()]) {
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
          jump(v.address(p + 1));
          break;
        }
        Value& counter = var & 0x8000U ? data.array[var & 0x7FFFU] : data.variables[var];
        counter = start;
        if (outside) {
          uint32_t scan = s.pc;
          uint8_t depth = 0;
          uint16_t vars[MAX_LOOPS] = {};
          bool found = false;
          while (scan < v.end && error == Error::NONE) {
            const Op candidate = (Op)v.byte(scan);
            const uint32_t following = next(v, scan);
            if (!following) {
              error = Error::INVALID_IMAGE;
              break;
            }
            if (candidate == Op::FOR_BASIC || candidate == Op::FOR_ARRAY) {
              if (depth == MAX_LOOPS) {
                error = Error::LOOP_STACK;
                break;
              }
              vars[depth++] = candidate == Op::FOR_ARRAY ? 0x8000U : v.byte(scan + 1);
            }
            if (candidate == Op::NEXT_BASIC || candidate == Op::NEXT_ARRAY) {
              const uint16_t variable = candidate == Op::NEXT_ARRAY ? 0x8000U : v.byte(scan + 1);
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
            end, step, start, s.pc, op == Op::FOR_FOCAL ? v.address(p + 1) : 0U, var};
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
      case Op::PRINT_AT: {
        basic_graphics::Request request={};request.operation=basic_graphics::Operation::TEXT;request.count=2;
        request.args[1]=pop().number();request.args[0]=pop().number();
        if(error==Error::NONE)event(Event::PRINT_AT,(const char*)&request,sizeof(request),value);
        break;
      }
      case Op::GRAPHICS: {
        basic_graphics::Request request={};request.operation=(basic_graphics::Operation)p[0];request.count=p[1];
        if(request.count>6){error=Error::INVALID_IMAGE;break;}
        for(unsigned i=request.count;i;--i)request.args[i-1]=pop().number();
        if(error==Error::NONE)event(Event::GRAPHICS,(const char*)&request,sizeof(request),value);
        if(error==Error::NONE && request.operation==basic_graphics::Operation::POINT)push(value);
        break;
      }
      case Op::GRAPH_BEGIN: {
        auto& graph=s.graph;
        if(graph.active || s.sp<4 || !host.value){error=Error::INVALID_IMAGE;break;}
        for(unsigned i=4;i;--i)graph.bounds[i-1]=pop().number();
        if(!(graph.bounds[0]<graph.bounds[1]) || !(graph.bounds[2]<graph.bounds[3]) ||
           !mk_math::is_finite(graph.bounds[1]-graph.bounds[0]) ||
           !mk_math::is_finite(graph.bounds[3]-graph.bounds[2])) {error=Error::GRAPHICS_ARGUMENT;break;}
        basic_graphics::Request request={};request.operation=basic_graphics::Operation::PSET;
        request.count=2;request.args[0]=request.args[1]=-1;
        event(Event::GRAPHICS,(const char*)&request,sizeof(request),value);
        if(error!=Error::NONE)break;
        const double width=host.value(host.context,Function::GW),height=host.value(host.context,Function::GH);
        if(width<1 || width>320 || height<1 || height>320){error=Error::GRAPHICS_UNAVAILABLE;break;}
        graph.width=(uint16_t)width;graph.height=(uint16_t)height;
        graph.next=v.address(p);graph.body=after;graph.column=0;graph.base=s.sp;
        graph.saved_x=data.variables['X'-'A'];graph.active=true;graph.skip=false;
        data.variables['X'-'A']=graph.bounds[0];
        break;
      }
      case Op::GRAPH_NEXT: {
        auto& graph=s.graph;
        if(!graph.active || v.address(p)!=graph.body || instruction!=graph.next){error=Error::INVALID_IMAGE;break;}
        if(!graph.skip) {
          value=pop();const double y=value.number();
          if(error==Error::NONE && y>=graph.bounds[2] && y<=graph.bounds[3]) {
            basic_graphics::Request request={};request.operation=basic_graphics::Operation::PSET;request.count=2;
            request.args[0]=graph.column;
            request.args[1]=(graph.bounds[3]-y)/(graph.bounds[3]-graph.bounds[2])*(graph.height-1);
            event(Event::GRAPHICS,(const char*)&request,sizeof(request),value);
          }
        }
        if(error!=Error::NONE)break;
        if(s.sp!=graph.base){error=Error::STACK;break;}
        graph.skip=false;
        if(++graph.column<graph.width) {
          data.variables['X'-'A']=graph.bounds[0]+(graph.bounds[1]-graph.bounds[0])*
              ((double)graph.column/(graph.width-1));
          s.pc=graph.body;
        } else {data.variables['X'-'A']=graph.saved_x;graph.active=false;}
        break;
      }
      case Op::PRINT_TEXT: {
        if(!v.reader)event(Event::TEXT,(const char*)v.bytes+instruction+3,word(p),value);
        else {
          const uint16_t length=word(p);char text[64];
          if(!length)event(Event::TEXT,text,0,value);
          for(uint32_t at=0;at<length && error==Error::NONE;) {
            const uint16_t n=uint16_t(length-at<sizeof(text)?length-at:sizeof(text));
            if(!v.read(instruction+3+at,text,n)){error=Error::IO;break;}
            event(at?Event::TEXT_CONTINUE:Event::TEXT,text,n,value);at+=n;
          }
        }
        break;
      }
      case Op::PRINT_RESOURCE: {
        const uint8_t* resource=v.bytes+v.end+word(p);
        event((v.byte(7)&OWNED_RESOURCE_FLAG)?Event::TEXT:Event::RESOURCE_TEXT,
            (const char*)resource+((v.byte(7)&OWNED_RESOURCE_FLAG)?2:0),word(resource),value);
        break;
      }
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
          return completed_run(v,Error::YIELDED,instruction,steps);
        const bool pooled=op==Op::INPUT_RESOURCE;
        const bool resource=pooled && !(v.byte(7)&OWNED_RESOURCE_FLAG);
        const uint8_t* prompt=pooled?v.bytes+v.end+word(p):v.bytes? v.bytes+instruction+1:nullptr;
        char text[96];
        const uint16_t length=word(p);
        if(v.reader) {
          if(length>95 || !v.read(instruction+3,text,length)){error=Error::IO;break;}
          event(Event::READ_INPUT,text,length,value);
        } else event(resource?Event::RESOURCE_INPUT:Event::READ_INPUT,
            (const char*)prompt+(resource?0:2),word(prompt),value);
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
    if(s.graph.active && (error==Error::MATH || error==Error::DIV_ZERO)) {
      error=Error::NONE;s.sp=s.graph.base;s.graph.skip=true;s.pc=s.graph.next;
    }
  }
  return completed_run(v,error,instruction,steps);
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
                                      "EXPECTED )", "NO GRAPHICS", "SCREEN CHANGED", "GRAPHICS ARGUMENT"};
  return (uint8_t)e < sizeof(names) / sizeof(names[0]) ? names[(uint8_t)e] : "UNKNOWN";
}
}  // namespace language_vm
