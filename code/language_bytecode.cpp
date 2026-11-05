#if defined(ARDUINO_ARCH_STM32)
#include "config.h"
#endif

// The compiler is experimental and not part of an ordinary resident image.
// Keep it available to host tools and portable APPs, and to opted-in VM builds.
#if !defined(ARDUINO_ARCH_STM32) || MK61_RESIDENT_LANGUAGE_VM || \
    MK61_OVERLAY_LANGUAGE_VM || defined(MK61_LANGUAGE_VM_COMPILER) || \
    defined(MK61_BUILD_LANGUAGE_VM_MODULE) || defined(MK61_BUILD_LANGUAGE_INPUT_MODULE) || \
    defined(MK61_BUILD_SOURCE_EDITOR_MODULE) || \
    defined(MK61_BUILD_FOCAL_MODULE) || (MK61_ENABLE_FOCAL && !MK61_FOCAL_IS_LOADABLE)
#include "language_bytecode.hpp"
#include "language_vm_abi.hpp"
#include "language_source_scan.hpp"
#include "tinybasic_syntax.hpp"
#include "basic_graphics_protocol.hpp"
#include "focal_compiler.hpp"
#include "language_flash_program.hpp"
#include "language_integer_spans.hpp"
#include "language_compact.hpp"
#include "language_source_map.hpp"

#include <string.h>
#include <new>

#include "mk_math.hpp"

namespace language_vm {
void mark_integer_spans(uint8_t* bytes,uint16_t code,uint16_t end) {
  detail::integer_spans(code,end,[&](uint32_t pc){return bytes[pc];},
      [&](uint32_t pc,Op){return instruction_end(bytes,end,uint16_t(pc));},
      [&](uint32_t pc,Op op){bytes[pc]=uint8_t(op);});
}

namespace {
void put_word(uint8_t* p, uint16_t v) {
  p[0] = (uint8_t)v;
  p[1] = (uint8_t)(v >> 8);
}
void put_dword(uint8_t* p, uint32_t v) {
  put_word(p, (uint16_t)v);
  put_word(p + 2, (uint16_t)(v >> 16));
}
char upper(char c) { return c >= 'a' && c <= 'z' ? (char)(c - 32) : c; }
bool alpha(char c) {
  c = upper(c);
  return c >= 'A' && c <= 'Z';
}
bool digit(char c) { return c >= '0' && c <= '9'; }
bool space(char c) { return c == ' ' || c == '\t'; }
struct Line {
  uint32_t number;
  uint16_t begin, end;
  uint32_t pc;
};
struct Keyword {
  const char* text;
  uint8_t minimum, id;
};
// INPUT() is I/O, lowered to a dedicated opcode rather than a math callback.
static constexpr uint8_t KEY_INPUT_FUNCTION = 254;
static constexpr uint8_t CALL_FUNCTION = 253, ARG_FUNCTION = 252;
static constexpr uint8_t POINT_FUNCTION = 251;
enum Command : uint8_t {
  ASSIGN,
  REM,
  PRINT,
  READ_INPUT,
  IF,
  GOTO_CMD,
  GOSUB_CMD,
  RETURN_CMD,
  FOR_CMD,
  NEXT_CMD,
  CLS,
  PAUSE,
  END,
  BRANCH_CMD,
  DO_CMD,
  DATA_CMD,
  READ_DATA_CMD,
  RESTORE_CMD,
  ON_CMD, PSET_CMD, LINE_CMD, BOX_CMD, CIRCLE_CMD, SHOW_CMD, GRAPH_CMD
};
// Expression-only INPUT/VM placements do not emit the BASIC statement lexer.
[[maybe_unused]] const Keyword basic_commands[] = {{"REM", 3, REM},
                                  {"REMARK", 3, REM},
                                  {"LET", 1, ASSIGN},
                                  {"PRINT", 1, PRINT},
                                  {"INPUT", 2, READ_INPUT},
                                  {"IF", 1, IF},
                                  {"GOTO", 1, GOTO_CMD},
                                  {"GOSUB", 3, GOSUB_CMD},
                                  {"RETURN", 1, RETURN_CMD},
                                  {"FOR", 1, FOR_CMD},
                                  {"NEXT", 1, NEXT_CMD},
                                  {"CLS", 1, CLS},
                                  {"PAUSE", 3, PAUSE},
                                  {"END", 1, END},
                                  {"STOP", 1, END},
                                  {"DATA", 2, DATA_CMD},
                                  {"READ", 3, READ_DATA_CMD},
                                  {"RESTORE", 4, RESTORE_CMD},
                                  {"ON", 15, ON_CMD},
                                  {"PSET", 2, PSET_CMD},
                                  {"LINE", 2, LINE_CMD},
                                  {"BOX", 1, BOX_CMD},
                                  {"CIRCLE", 2, CIRCLE_CMD},
                                  {"SHOW", 2, SHOW_CMD},
                                  {"GRAPH", 2, GRAPH_CMD},
                                  {nullptr, 0, 0}};
const Keyword functions[] = {
    {"SIZE", 1, (uint8_t)Function::SIZE},   {"COLS", 15, (uint8_t)Function::COLS},
    {"ROWS", 15, (uint8_t)Function::ROWS},  {"PI", 15, (uint8_t)Function::PI_VALUE},
    {"RND", 1, (uint8_t)Function::RND},     {"SIN", 2, (uint8_t)Function::SIN},
    {"COS", 1, (uint8_t)Function::COS},     {"TG", 1, (uint8_t)Function::TAN},
    {"ASIN", 2, (uint8_t)Function::ASIN},   {"ACOS", 2, (uint8_t)Function::ACOS},
    {"ATG", 2, (uint8_t)Function::ATAN},    {"LN", 2, (uint8_t)Function::LN},
    {"LG", 2, (uint8_t)Function::LOG10},    {"EXP", 1, (uint8_t)Function::EXP},
    {"SQRT", 2, (uint8_t)Function::SQRT},   {"ABS", 1, (uint8_t)Function::ABS},
    {"INT", 1, (uint8_t)Function::INT},     {"FRAC", 1, (uint8_t)Function::FRAC},
    {"ROUND", 2, (uint8_t)Function::ROUND}, {"SGN", 2, (uint8_t)Function::SGN},
    {"MAX", 1, (uint8_t)Function::MAX},
    {"INPUT", 3, KEY_INPUT_FUNCTION}, {"CALL", 3, CALL_FUNCTION},
    {"ARG", 2, ARG_FUNCTION}, {"GW",15,(uint8_t)Function::GW},
    {"GH",15,(uint8_t)Function::GH}, {"POINT",3,POINT_FUNCTION}, {nullptr, 0, 0}};
struct ResourceWorkspace {
  uint8_t* first;
  uint8_t* second;
  uint16_t half;
  uint8_t* at(uint16_t offset) {
    return offset < half ? first + offset : second + offset - half;
  }
  uint16_t word(uint16_t offset) {
    return (uint16_t)(*at(offset) | ((uint16_t)*at((uint16_t)(offset+1))<<8));
  }
  void word(uint16_t offset, uint16_t value) {
    *at(offset)=(uint8_t)value; *at((uint16_t)(offset+1))=(uint8_t)(value>>8);
  }
};
struct Target {
  uint8_t kind, index;
};  // 0 variable, 1 reference, 2 array

template <Language Lang,bool Paged=false,bool Expression=false>
class Compiler {
  using Text = source::Cursor;
  const source::Reader* input_;
 public:
  __attribute__((noinline)) Compiler(const source::Reader& input, uint16_t length, uint8_t* out, uint32_t capacity,
           Line* lines, bool rf_available = true, const ResourceSource* resources = nullptr, ResourceWorkspace workspace = {}, flash::Program* flash = nullptr) {
    // All fields are scalar pointers, integers or POD workspace descriptors.
    // A shared cold initializer avoids duplicating dozens of zero stores for
    // every bounded resource-workspace specialization in the compiler APP.
    static_assert((unsigned)Error::NONE==0 && (unsigned)Op::HALT==0,"zero compiler state changed");
    __builtin_memset(static_cast<void*>(this),0,sizeof(*this));
    input_=&input;source_=p_=end_=Text(input);length_=length;out_=out;capacity_=capacity;
    flash_=flash;lines_=lines;rf_available_=rf_available;resources_=resources;resource_data_=workspace;
  }

  CompileResult compile() {
    if (!source_) return {Error::SYNTAX, 0, 0, 0, 0};
    const uint16_t quota = source::MAX_SIZE;
    if (length_ == 0 || length_ > quota || (!Paged && input_->contains_nul()))
      return {length_ > quota ? Error::FULL : !input_->good() ? Error::IO : Error::SYNTAX, 0, 0, 0, 0};
    index_lines();
    if (!count_ && error_ == Error::NONE) fail(Error::LINE);
    const uint32_t code = HEADER_SIZE + uint32_t(count_) * stride();
    // Labels and instruction lengths are determined before emission; source
    // may be unordered and every forward reference gets its final offset.
    for (pass_ = 0; pass_ < (Paged?3:2) && error_ == Error::NONE; ++pass_) {
      emitting_=pass_==1;
      if constexpr(Paged) {
        emitting_=pass_==2 || (pass_==1 && flash_->reserve_positions(positions_.bytes));
        if(pass_ && !(emitting_?flash_->begin_image():flash_->begin_positions())) {fail(Error::IO);break;}
      }
      pc_ = code;
      positions_.reset(code);
      resource_size_ = 0;
      sp_ = maximum_ = depth_ = 0;compact_.barrier();
      for (line_ = 0; line_ < count_ && error_ == Error::NONE; ++line_) {
        if (!pass_) set_line_pc(line_,pc_);
        const auto current=line_at(line_);
        p_ = source_ + current.begin;
        end_ = source_ + current.end;
        Text physical=p_;
        while(physical>source_ && physical[-1]!='\n' && physical[-1]!='\r')--physical;
        line_start_=uint16_t(physical-source_);
        if (basic())
          commands(0);
        else
          focal_statement(0);
        if (sp_ != 0 && error_ == Error::NONE) fail(Error::INVALID_IMAGE);
        emit(Op::LINE);
      }
      emit(Op::HALT);
      if(!positions_.flush(SourceOutput{this}))fail(Error::FULL);
      if (!pass_) {
        image_end_ = pc_ - 1;
        source_map_at_=pc_+(resource_data_.first?resource_size_:0);
      }
      if(Paged && pass_==1 && emitting_)break;
    }
    const uint32_t code_end = pc_;
    if (error_ == Error::NONE && resource_size_ && resource_data_.first) {
      if (pc_ > capacity_ || resource_size_ > capacity_ - pc_ ||
          resource_size_ > (owned_resources() ? MAX_MODULE : MAX_IMAGE) - pc_) fail(Error::FULL);
      else {
        if (out_) {
          const uint16_t first = resource_size_ < resource_data_.half ? resource_size_ : resource_data_.half;
          memcpy(out_ + pc_, resource_data_.first, first);
          if (resource_size_ > first) memcpy(out_ + pc_ + first, resource_data_.second, resource_size_ - first);
        }
        pc_ += resource_size_;
      }
    }
    if(Paged) {
      if(error_==Error::NONE && !flash_->finish(Lang,pc_,parameter_calls_?MAX_STACK:maximum_,rf_required_,positions_.count,positions_.bytes))error_=Error::IO;
      if(flash_->error()!=Error::NONE)error_=flash_->error();
      if(error_==Error::NONE)pc_=flash_->size();
    } else if(error_==Error::NONE && positions_.count) {
      const uint32_t limit=owned_resources()?MAX_MODULE:MAX_IMAGE;
      if(pc_>capacity_ || positions_.bytes+4U>capacity_-pc_ || pc_>limit || positions_.bytes+4U>limit-pc_)fail(Error::FULL);
      else {
        if(out_)put_dword(out_+pc_+positions_.bytes,positions_.bytes);
        pc_+=positions_.bytes+4U;
      }
    }
    if (error_ == Error::NONE && out_) {
      memset(out_, 0, HEADER_SIZE);
      memcpy(out_, "LBV2", 4);
      out_[4] = (uint8_t)VERSION;
      out_[5] = (uint8_t)Lang;
      out_[6] = parameter_calls_ ? MAX_STACK : maximum_ ? maximum_ : 1;
      out_[7] = (rf_required_ ? 2 : 0) | (resource_size_ && resource_data_.first ?
                  RESOURCE_FLAG | (owned_resources() ? OWNED_RESOURCE_FLAG : 0) : 0);
      if (resource_size_ && resource_data_.first) {
        if(!owned_resources()) {
          put_word(out_ + 32, resources_->id);
          put_dword(out_ + 34, resources_->revision);
        }
        put_dword(out_ + 28, code_end);
      }
      put_dword(out_ + 28, code_end);
      put_dword(out_ + 8, pc_);
      put_dword(out_ + 12, code);
      put_word(out_ + 18, count_);
      put_word(out_ + 16, length_);
      put_word(out_ + 38, positions_.count);
      put_dword(out_ + 20, input_->checksum());
      for (uint16_t i = 0; i < count_; ++i) {
        uint8_t* record = out_ + HEADER_SIZE + i * stride();
        put_dword(record, line_at(i).number);
        put_dword(record + 4, line_at(i).pc);
      }
      mark_integer_spans(out_,code,code_end);
      put_dword(out_ + 24, checksum(out_ + HEADER_SIZE, pc_ - HEADER_SIZE));
    }
    if(!input_->good()) error_=Error::IO;
    uint16_t offset =
        p_ >= source_ && p_ <= source_ + length_ ? (uint16_t)(p_ - source_) : 0;
    return {error_, error_ == Error::NONE ? pc_ : (uint16_t)0, line_, offset,
            parameter_calls_ ? MAX_STACK : maximum_};
  }
  uint16_t resource_reservation() const { return resource_size_; }
  CompileResult expression_only() {
    if (!source_ || !length_ || length_ > (basic() ? 64 : 111) ||
        input_->template contains_nul<true>())
      return {Error::SYNTAX, 0, 0, 0, 0};
    for (pass_ = 0; pass_ < 2 && error_ == Error::NONE; ++pass_) {
      p_ = source_;
      end_ = source_ + length_;
      pc_ = HEADER_SIZE;
      emitting_=pass_==1;
      sp_ = maximum_ = depth_ = 0;compact_.barrier();
      expression();
      skip();
      if (p_ != end_) fail(Error::SYNTAX);
      emit(Op::HALT);
    }
    if (error_ == Error::NONE && out_) {
      memset(out_, 0, HEADER_SIZE);
      memcpy(out_, "LBV2", 4);
      out_[4] = VERSION;
      out_[5] = (uint8_t)Lang;
      out_[6] = maximum_;
      out_[7] = rf_required_ ? 3 : 1;
      put_dword(out_ + 28, pc_);
      put_dword(out_ + 8, pc_);
      put_dword(out_ + 12, HEADER_SIZE);
      put_word(out_ + 16, length_);
      put_dword(out_ + 20, input_->checksum());
      put_dword(out_ + 24, checksum(out_ + HEADER_SIZE, pc_ - HEADER_SIZE));
    }
    return {error_, error_ == Error::NONE ? pc_ : (uint16_t)0, 0,
            (uint16_t)(p_ - source_), maximum_};
  }

 private:
  Text source_;
  uint16_t length_;
  uint8_t* out_;
  uint32_t capacity_;
  Text p_;
  Text end_;
  Error error_;
  Line* lines_;
  flash::Program* flash_;
  Line line_at(uint16_t i) {
    if(!Paged)return lines_[i];
    const auto l=flash_->line(i);return {l.number,l.begin,l.end,l.pc};
  }
  void set_line_pc(uint16_t i,uint32_t pc) {if(Paged)flash_->pc(i,pc);else lines_[i].pc=pc;}
  void put_byte(uint32_t at,uint8_t b) {if(Paged)flash_->byte(at,b);else if(out_)out_[at]=b;}
  uint16_t count_;
  uint32_t pc_;
  uint8_t sp_, maximum_, depth_;
  uint16_t line_,line_start_;
  uint8_t pass_;
  bool emitting_=false;
  bool emitting() const {return emitting_;}
  uint32_t image_end_;
  bool rf_available_, rf_required_, parameter_calls_, graph_expression_;
  const ResourceSource* resources_;
  uint16_t resource_size_;
  ResourceWorkspace resource_data_;
#if !MK61_VM_COMPACT_OPERANDS || defined(LANGUAGE_VM_TEST_NO_FUSION)
  compact::History<!Expression> compact_;
#else
  compact::Tail compact_;
#endif
  uint32_t comparison_block_;
  source_map::Positions positions_;
  uint32_t source_map_at_;
  bool source_bytes(uint32_t at,const uint8_t* data,uint16_t n) {
    if(Paged)return pass_!=1 || flash_->source_bytes(at,data,n);
    if(!pass_)return true;
    const uint32_t limit=owned_resources()?MAX_MODULE:MAX_IMAGE;
    if(source_map_at_>capacity_ || at>capacity_-source_map_at_ || n>capacity_-source_map_at_-at ||
       source_map_at_>limit || at>limit-source_map_at_ || n>limit-source_map_at_-at)return false;
    if(out_)memcpy(out_+source_map_at_+at,data,n);
    return true;
  }
  struct SourceOutput {
    Compiler* compiler;
    bool operator()(uint32_t at,const uint8_t* data,uint16_t n) const {return compiler->source_bytes(at,data,n);}
  };
  bool owned_resources() const { return !Paged && resources_ && resources_->mode == ResourceMode::EMBEDDED; }
  bool resource_literals() const { return !Paged && resources_ && (owned_resources() || resources_->id != 0xFFFF); }
  uint16_t intern_resource(Text text, uint16_t length) {
    if(owned_resources()) {
      if(length > MAX_MODULE-2U || resource_size_ > MAX_MODULE-2U-length) {fail(Error::FULL);return 0;}
      if(!resource_data_.first) {
        resource_size_ += (uint16_t)(2 + length); return 0;
      }
      for(uint16_t at=0; at<resource_size_;) {
        const uint16_t n=resource_data_.word(at);
        bool same=n==length;
        for(uint16_t i=0; same && i<n; ++i)
          same=*resource_data_.at((uint16_t)(at+2+i))==(uint8_t)text[i];
        if(same) return at;
        at += (uint16_t)(2+n);
      }
      if(2U+length > (unsigned)resource_data_.half*2-resource_size_) {fail(Error::FULL);return 0;}
      const uint16_t at=resource_size_;
      resource_data_.word(at,length);
      for(uint16_t i=0;i<length;++i) *resource_data_.at((uint16_t)(at+2+i))=(uint8_t)text[i];
      resource_size_ += (uint16_t)(2+length); return at;
    }
    if(!resource_data_.first) {
      // Sizing mode needs only an upper bound. Raw literal bytes are already
      // contiguous; synthesized prompts can need at most one span per byte.
      const bool raw = text.from(*input_);
      const uint16_t parts = raw ? (uint16_t)((length + 254) / 255) : length;
      resource_size_ += (uint16_t)(3 + parts * 3);
      return 0;
    }
    // Compare actual M8 bytes, including normalized INPUT prompts. PRINT and
    // INPUT share handles even if they spelled the same text differently.
    for (uint16_t at = 0; at < resource_size_;) {
      const uint8_t* r = resource_data_.at(at);
      unsigned decoded = 0;
      bool same = (uint16_t)(r[0] | ((uint16_t)r[1] << 8)) == length;
      for (unsigned i = 0; same && i < r[2]; ++i) {
        const uint8_t* part = resource_data_.at((uint16_t)(at + 3 + i * 3));
        const uint16_t offset = (uint16_t)(part[0] | ((uint16_t)part[1] << 8));
        const uint8_t n = part[2];
        if (!n) same = (uint8_t)text[decoded] == (uint8_t)offset;
        else same = source::equal(text + decoded, source_ + offset, n);
        decoded += n ? n : 1;
      }
      if (same) return at;
      at += (uint16_t)(3 + r[2] * 3);
    }
    const uint16_t at = resource_size_;
    if (resource_size_ > resource_data_.half * 2 - 3) { fail(Error::FULL); return 0; }
    put_word(resource_data_.at(resource_size_), length);
    *resource_data_.at((uint16_t)(resource_size_ + 2)) = 0;
    resource_size_ += 3;
    while (length && error_ == Error::NONE) {
      uint16_t best = 0;
      uint8_t n = 0;
      const uint16_t wanted = length < 255 ? length : 255;
      if(text.from(*input_)) {best=(uint16_t)(text-source_);n=(uint8_t)wanted;}
      else for (uint16_t pos = 0; pos < length_; ++pos) {
        uint16_t match = 0;
        while (match < wanted && pos + match < length_ &&
               source_[pos + match] == text[match]) ++match;
        if (match > n) { best = pos; n = (uint8_t)match; }
        if (match == wanted) break;
      }
      const bool literal = !n;
      if (literal) { best = (uint8_t)*text; n = 1; }
      if (resource_size_ > resource_data_.half * 2 - 3 || *resource_data_.at((uint16_t)(at + 2)) == 255) {
        fail(Error::FULL); break;
      }
      put_word(resource_data_.at(resource_size_), best);
      *resource_data_.at((uint16_t)(resource_size_ + 2)) = literal ? 0 : n;
      resource_size_ += 3; ++*resource_data_.at((uint16_t)(at + 2));
      text += n; length -= n;
    }
    return at;
  }
  static constexpr bool basic() { return Lang == Language::BASIC; }
  uint8_t stride() const { return 8; }
  void fail(Error e) {
    if (error_ == Error::NONE) error_ = e;
  }
  void skip() {
    while (p_ < end_ && space(*p_)) ++p_;
  }
  bool match(char c) {
    skip();
    if (p_ < end_ && *p_ == c) {
      ++p_;
      return true;
    }
    return false;
  }
  void byte(uint8_t v) {
    if (pc_ >= capacity_ || (!Paged && pc_ >= MAX_IMAGE)) {
      fail(Error::FULL);
      return;
    }
    if(emitting() && (out_ || Paged))put_byte(pc_,v);
    if(Paged && flash_->error()!=Error::NONE)fail(flash_->error());
    ++pc_;
  }
  void emit(Op op) {
#if !defined(LANGUAGE_VM_TEST_NO_COMPILED_BLOCKS)
    if constexpr(!Expression) {
      const auto& last=compact_.last;const auto& before=compact_.before;
      uint32_t block_at=0;Op block=Op::HALT;
      if(index_block_shape(op,pc_,before.op,before.pc,last.op,last.pc)) {
        block_at=before.pc;block=Op::BLOCK_INDEX;
      }
      if(op==Op::COMPARE_FALSE && pc_==last.pc && comparison_block_) {
        block_at=comparison_block_;block=Op::BLOCK_COMPARE;
      }
      comparison_block_=(op>=Op::EQ && op<=Op::GE && before.op==Op::LOAD &&
          last.pc==before.pc+2U && last.op>=Op::CONST_0 && last.op<=Op::CONST_15 &&
          pc_==last.pc+1U)?before.pc:0;
      if(block!=Op::HALT && emitting() && (out_ || Paged))put_byte(block_at,uint8_t(block));
    }
#endif
    compact_.begin(op,pc_);byte(uint8_t(op));
  }
  void u16(uint16_t v) {
    byte((uint8_t)v);
    byte((uint8_t)(v >> 8));
  }
  void patch(uint32_t at, uint16_t v) {
    if(emitting() && (out_ || Paged) && at<=capacity_ && capacity_-at>=2) {put_byte(at,uint8_t(v));put_byte(at+1,uint8_t(v>>8));}
  }
  void emit_address(uint32_t value) {u16(uint16_t(value));u16(uint16_t(value>>16));}
  void patch_address(uint32_t at,uint32_t value) {patch(at,uint16_t(value));patch(at+2,uint16_t(value>>16));}
  void stack(int effect) {
    const int n = sp_ + effect;
    if (n < 0 || n > MAX_STACK) {
      fail(Error::STACK);
      return;
    }
    sp_ = (uint8_t)n;
    if (sp_ > maximum_) maximum_ = sp_;
  }
  void operation(Op op, int effect) {
#if MK61_VM_COMPACT_OPERANDS && !defined(LANGUAGE_VM_TEST_NO_FUSION)
    // The existing CONST_I16/local index block is already smaller than a
    // stack operand followed by BINARY_PAIR, and has a guarded integer path.
    if(!Expression && index_block_shape(op,pc_,compact_.before.op,compact_.before.pc,
        compact_.last.op,compact_.last.pc)) {emit(op);stack(effect);return;}
    compact::Rewrite r;
    if(effect==-1 && sp_>=2 && compact_.rewrite(op,pc_,r)) {
      pc_=r.begin;compact_.barrier();
      if(r.folded) {sp_-=2;constant(r.value);return;}
      emit(Op::BINARY_PAIR);byte(uint8_t(op));byte(r.left);byte(r.right);
      compact_.last.arguments=uint32_t(op)|(uint32_t(r.left)<<8)|(uint32_t(r.right)<<16);
      stack(-1);return;
    }
#endif
    emit(op);stack(effect);
  }
  void constant(double value, Text literal = nullptr,
                Text finish = nullptr) {
    const Value number(value);
    if(number.integer()) {
      const int32_t n=number.integer_value();
      if(n>=0 && n<=15)emit(Op(unsigned(Op::CONST_0)+unsigned(n)));
      else if(n>=-128 && n<=127) {emit(Op::CONST_I8);byte(uint8_t(n));}
      else if(n>=-32768 && n<=32767) {emit(Op::CONST_I16);u16(uint16_t(n));}
      else {emit(Op::CONST_I32);for(uint8_t i=0;i<4;++i)byte(uint8_t(uint32_t(n)>>(i*8)));}
      compact_.last.arguments=uint32_t(n);
    } else if(literal && decimal(value,literal,finish)) {
      // Exact decimal recipe avoids turning a three-byte .1 into F64+opcode.
    } else {
      emit(Op::CONST_F64);
      const uint64_t bits=mk_math::bit_copy<uint64_t>(value);
      for(uint8_t i=0;i<8;++i)byte(uint8_t(bits>>(i*8)));
    }
    stack(1);
  }
  __attribute__((noinline)) bool decimal(double value, Text begin, Text end) {
#if defined(LANGUAGE_VM_TEST_NO_DECIMAL_RECIPE)
    (void)value; (void)begin; (void)end;
    return false;
#else
    uint32_t mantissa = 0;
    int exponent = 0;
    bool fraction = false;
    Text q = begin;
    while (q < end && (digit(*q) || *q == '.')) {
      if (*q == '.')
        fraction = true;
      else {
        mantissa = mantissa * 10 + (unsigned)(*q - '0');
        if (mantissa > 65535) return false;
        if (fraction) --exponent;
      }
      ++q;
    }
    if (q < end && (*q == 'e' || *q == 'E')) {
      ++q;
      bool negative = false;
      if (q < end && (*q == '+' || *q == '-')) negative = *q++ == '-';
      int scale = 0;
      while (q < end && digit(*q)) {
        scale = scale * 10 + (*q++ - '0');
        if (scale > 127) return false;
      }
      exponent += negative ? -scale : scale;
    }
    if (q != end || exponent < -127 || exponent > 127) return false;
    double reconstructed = (double)mantissa;
    if (exponent < 0)
      reconstructed /= mk_math::pow10_int(-exponent);
    else
      reconstructed *= mk_math::pow10_int(exponent);
    if (memcmp(&reconstructed, &value, sizeof(value))) return false;
    emit(mantissa < 256 ? Op::CONST_DEC8 : Op::CONST_DEC16);
    byte((uint8_t)mantissa);
    if (mantissa >= 256) byte((uint8_t)(mantissa >> 8));
    byte((uint8_t)(int8_t)exponent);
    return true;
#endif
  }
  bool keyword(const char* word, uint8_t minimum) {
    skip();
    Text saved = p_;
    unsigned n = 0;
    while (p_ < end_ && alpha(*p_)) {
      ++p_;
      ++n;
    }
    const bool dotted = p_ < end_ && *p_ == '.';
    if (dotted) ++p_;
    const size_t length = strlen(word);
    bool ok = n != 0 && (dotted ? n >= minimum && n <= length : n == length);
    for (unsigned i = 0; ok && i < n; ++i) ok = upper(saved[i]) == word[i];
    if (!ok) p_ = saved;
    return ok;
  }
  uint8_t lookup(const Keyword* words, uint8_t missing) {
    for (; words->text; ++words)
      if (keyword(words->text, words->minimum)) return words->id;
    return missing;
  }
  uint32_t address(bool group) {
    skip();
    uint32_t major = 0, minor = 0;
    if (p_ == end_ || !digit(*p_)) {
      fail(Error::LINE);
      return 0;
    }
    while (p_ < end_ && digit(*p_)) {
      major = major * 10 + (*p_++ - '0');
      if (major > 999) fail(Error::LINE);
    }
    if (match('.')) {
      if (p_ == end_ || !digit(*p_)) fail(Error::LINE);
      while (p_ < end_ && digit(*p_)) {
        minor = minor * 10 + (*p_++ - '0');
        if (minor > 999) fail(Error::LINE);
      }
    } else if (!group)
      fail(Error::LINE);
    return major * 1000 + minor;
  }
  void index_lines() {
    if(Paged) {count_=flash_->count();return;}
    Text cursor = source_;
    while (cursor < source_ + length_ && error_ == Error::NONE) {
      while (cursor < source_ + length_ && (*cursor == '\r' || *cursor == '\n'))
        ++cursor;
      Text begin = cursor;
      cursor += cursor.line_end(source_ + length_);
      p_ = begin;
      end_ = cursor;
      skip();
      while (end_ > p_ && space(end_[-1])) --end_;
      if (!basic() && end_ - p_ >= 128) {
        fail(Error::FULL);
        break;
      }
      if (p_ == end_) continue;
      const uint16_t maximum_lines = basic() ? 192 : 80;
      if (count_ == maximum_lines) {
        fail(Error::FULL);
        break;
      }
      uint32_t number = 0;
      if (basic()) {
        if (!digit(*p_)) {
          fail(Error::LINE);
          break;
        }
        while (p_ < end_ && digit(*p_)) {
          number = number * 10 + (*p_++ - '0');
          if (number > 32767) fail(Error::LINE);
        }
        if (number == 0 || p_ == end_ || !space(*p_)) fail(Error::LINE);
      } else
        number = address(false);
      skip();
      if (p_ == end_) {
        fail(Error::SYNTAX);
        break;
      }
      if (!basic() && end_ - p_ >= 128) {
        fail(Error::FULL);
        break;
      }
      uint16_t at = count_;
      while (at && line_at(at - 1).number > number) {
        lines_[at] = lines_[at - 1];
        --at;
      }
      if (at && line_at(at - 1).number == number) {
        fail(Error::LINE);
        break;
      }
      lines_[at] = {number, (uint16_t)(p_ - source_), (uint16_t)(end_ - source_), 0};
      ++count_;
    }
  }
  uint32_t target_pc(uint32_t number, bool group = false) {
    if (!pass_) return 0;
    if(Paged) {
      const int i=flash_->find(group?number/1000:number,group);
      return i<0?UINT32_MAX:line_at(uint16_t(i)).pc;
    }
    for (uint16_t i = 0; i < count_; ++i)
      if (group ? line_at(i).number / 1000 == number / 1000 : line_at(i).number == number)
        return line_at(i).pc;
    return UINT32_MAX;
  }
  bool direct_basic_branch(bool sub) {
    skip();
    Text q=p_;
    uint32_t number=0;
    if(q==end_ || !digit(*q)) return false;
    while(q<end_ && digit(*q)) {
      number=number*10+(unsigned)(*q++-'0');
      if(number>32767) return false;
    }
    while(q<end_ && space(*q)) ++q;
    if(q!=end_ || !number) return false;
    // Resolve only a bare, valid line literal. Dynamic/invalid numeric
    // expressions retain their original evaluation and error semantics.
    emit(sub ? Op::GOSUB_DIRECT : Op::GOTO_DIRECT);
    emit_address(target_pc(number));p_=q;return true;
  }
  void basic_call(bool result) {
    unsigned number = 0;
    Text after = tinybasic_syntax::integer(p_, end_, number);
    if (!after || !number || number > 32767) { fail(Error::LINE_NUMBER); return; }
    p_ = after;
    unsigned arguments = 0;
    while (match(',')) {
      if (++arguments > 4) { fail(Error::STACK); return; }
      expression();
    }
    parameter_calls_ = true;
    operation(Op::CALL_PARAMS, int(result) - int(arguments));
    emit_address(target_pc(number)); emit_address(result ? image_end_ : 0);
    byte((uint8_t)arguments); byte(result);
  }
  bool fixed_array_index(uint16_t& index) {
#if defined(LANGUAGE_VM_TEST_NO_FUSION)
    (void)index;return false;
#else
    // A bare unsigned integer has no numeric/I/O side effects. Out-of-range
    // indices still compile and fail at the original array access at runtime.
    Text q=p_;
    while(q<end_ && space(*q)) ++q;
    if(q==end_ || !digit(*q)) return false;
    uint32_t number=0;
    do {
      number=number*10+(unsigned)(*q++-'0');
      if(number>65535) return false;
    } while(q<end_ && digit(*q));
    while(q<end_ && space(*q)) ++q;
    // CONST_0..15 + LOAD_ARRAY is already two bytes; do not grow it to three.
    if(q==end_ || *q!=')' || number<16) return false;
    index=(uint16_t)number;p_=q+1;return true;
#endif
  }
  bool reference(uint8_t& id) {
    if (!match('.')) return false;
    if (p_ == end_) {
      fail(Error::REGISTER);
      return false;
    }
    const char c = upper(*p_++);
    if (c == 'R') {
      if (p_ == end_) {
        fail(Error::REGISTER);
        return false;
      }
      const char r = upper(*p_++);
      const int v = digit(r) ? r - '0' : r - 'A' + 10;
      if (v < 0 || v > 15) {
        fail(Error::REGISTER);
        return false;
      }
      id = (uint8_t)(4 + v);
      if (!basic() && v == 15) {
        rf_required_ = true;
        if (!rf_available_) fail(Error::REGISTER);
      }
    } else if (c >= 'X' && c <= 'Z')
      id = (uint8_t)(c - 'X');
    else if (c == 'T')
      id = 3;
    else {
      fail(Error::REGISTER);
      return false;
    }
    if (p_ < end_ && (alpha(*p_) || digit(*p_))) fail(Error::REGISTER);
    return error_ == Error::NONE;
  }
  Target target() {
    skip();
    Target t = {0, 0};
    Text target_start = p_;
    if (p_ == end_) {
      fail(Error::VARIABLE);
      return t;
    }
    if (*p_ == '.' && p_ + 1 < end_ && alpha(p_[1])) {
      t.kind = 1;
      (void)reference(t.index);
      if (basic()) {
        emit(Op::TARGET_REF);
        byte(t.index);
      }
    } else if (basic() && match('@')) {
      t.kind = 2;
      if (!match('(')) fail(Error::SYNTAX);
      expression();
      if (!match(')')) fail(Error::EXPECTED_PAREN);
      source_position(target_start);
      emit(Op::TARGET_ARRAY);
    } else if (alpha(*p_))
      t.index = (uint8_t)(upper(*p_++) - 'A');
    else
      fail(Error::VARIABLE);
    return t;
  }
  void store(Target t) {
    operation(t.kind == 0   ? Op::STORE
              : t.kind == 1 ? Op::STORE_REF
                            : Op::STORE_ARRAY,
              t.kind == 2 ? -2 : -1);
    if (t.kind != 2) byte(t.index);
  }
  void expression() {
    // Every producing VM operation checks finiteness in both languages.
    // Separate CHECK instructions would repeat the same test and dispatch.
    binary(0);
  }
  void binary(uint8_t level) {
    if (level == 3) {
      prefix(false);
      return;
    }
    binary((uint8_t)(level + 1));
    while (error_ == Error::NONE) {
      skip();
      Op op = Op::HALT;
      Text saved = p_;
      if (level == 0 && basic()) {
        if (match('<'))
          op = match('=') ? Op::LE : match('>') ? Op::NE : Op::LT;
        else if (match('>'))
          op = match('=') ? Op::GE : Op::GT;
        else if (match('='))
          op = Op::EQ;
        else if (match('#'))
          op = Op::NE;
      } else if (level == 1) {
        if (match('+'))
          op = Op::ADD;
        else if (match('-'))
          op = Op::SUB;
        else if (basic() && keyword("OR", 2))
          op = Op::OR;
        else if (basic() && keyword("XOR", 3))
          op = Op::XOR;
      } else if (level == 2) {
        if (match('*'))
          op = Op::MUL;
        else if (match('/'))
          op = Op::DIV;
        else if (basic() && keyword("MOD", 3))
          op = Op::MOD;
        else if (basic() && keyword("AND", 3))
          op = Op::AND;
      }
      if (op == Op::HALT) {
        p_ = saved;
        break;
      }
      binary((uint8_t)(level + 1));
      if (basic() && (op == Op::DIV || op == Op::MOD)) source_position(saved);
      operation(op, -1);
    }
  }
  void prefix(bool power_operand) {
    if (depth_ >= 96) {
      fail(Error::STACK);
      return;
    }
    ++depth_;
    if (!basic() && !power_operand) {
      prefix(true);
      if (match('^')) {
        prefix(false);
        operation(Op::POW, -1);
      }
      --depth_;
      return;
    }
    if (match('+'))
      prefix(power_operand);
    else if (match('-')) {
      prefix(power_operand);
      emit(Op::NEG);
    } else if (basic() && keyword("NOT", 3)) {
      prefix(power_operand);
      emit(Op::NOT);
    } else if (!basic()) {
      primary();
    } else {
      primary();
      if (!power_operand)
        while (error_ == Error::NONE && match('^')) {
          prefix(true);
          operation(Op::POW, -1);
        }
    }
    --depth_;
  }
  void primary() {
    skip();
    Text primary_start = p_;
    if (p_ == end_) {
      fail(Error::SYNTAX);
      return;
    }
    if (match('(')) {
      binary(0);
      if (!match(')')) fail(Error::EXPECTED_PAREN);
      return;
    }
    if (*p_ == '.' && p_ + 1 < end_ && alpha(p_[1])) {
      uint8_t ref = 0;
      (void)reference(ref);
      emit(Op::LOAD_REF);
      byte(ref);
      stack(1);
      return;
    }
    if (basic() && match('@')) {
      if (!match('(')) fail(Error::SYNTAX);
      uint16_t index=0;
      if(fixed_array_index(index)) {
        source_position(primary_start);
        operation(Op::LOAD_ARRAY_FIXED,1);u16(index);return;
      }
      binary(0);
      if (!match(')')) fail(Error::EXPECTED_PAREN);
      source_position(primary_start);
      emit(Op::LOAD_ARRAY);
      return;
    }
    if (digit(*p_) || *p_ == '.') {
      Text after = nullptr;
      double value = 0;
if (!number(value, after)) { fail(Error::SYNTAX); return; }
      if (after == p_ || after > end_) {
        fail(Error::SYNTAX);
        return;
      }
      Text literal = p_;
      p_ = after;
      constant(value, literal, after);
      return;
    }
    if (alpha(*p_)) {
      Text start = p_;
      const uint8_t fn = lookup(functions, 255);
      if (fn == 255) {
        p_ = start;
        const uint8_t var = (uint8_t)(upper(*p_++) - 'A');
        if (p_ < end_ && (alpha(*p_) || *p_ == '.')) {
          fail(Error::FUNCTION);
          return;
        }
        emit(Op::LOAD);compact_.last.arguments=var;
        byte(var);
        stack(1);
        return;
      }
      const Function f = (Function)fn;
      if(graph_expression_ && (fn==CALL_FUNCTION || fn==KEY_INPUT_FUNCTION || f==Function::RND)) {
        fail(Error::FUNCTION);return;
      }
      if(fn==POINT_FUNCTION) {
        if(!basic() || !match('(')){fail(Error::FUNCTION);return;}
        expression();if(!match(','))fail(Error::FUNCTION);expression();
        if(!match(')'))fail(Error::EXPECTED_PAREN);
        operation(Op::GRAPHICS,-1);byte((uint8_t)basic_graphics::Operation::POINT);byte(2);return;
      }
      if (fn == CALL_FUNCTION || fn == ARG_FUNCTION) {
        if (!basic() || Expression || !match('(')) { fail(Error::FUNCTION); return; }
        if (fn == CALL_FUNCTION) basic_call(true);
        else { expression(); source_position(primary_start); emit(Op::LOAD_PARAMETER); }
        if (!match(')')) fail(Error::EXPECTED_PAREN);
        return;
      }
      if (!basic() && f >= Function::SIZE) {
        fail(Error::FUNCTION);
        return;
      }
      if (fn == KEY_INPUT_FUNCTION) {
        if (!match('(') || !match(')') || Expression) {
          fail(Error::FUNCTION);
          return;
        }
        emit(Op::READ_KEY);
        stack(1);
        return;
      }
      if (f == Function::PI_VALUE || f >= Function::SIZE) {
        emit(Op::FUNCTION);
        byte(fn);
        stack(1);
        return;
      }
      if (!match('(')) {
        fail(Error::FUNCTION);
        return;
      }
      if (f == Function::RND && match(')')) {
        emit(Op::FUNCTION);
        byte(fn);
        stack(1);
        return;
      }
      binary(0);
      if (f == Function::MAX) {
        if (!match(',')) fail(Error::FUNCTION);
        binary(0);
      }
      if (!match(')')) fail(Error::EXPECTED_PAREN);
      if (f == Function::RND && !basic()) fail(Error::FUNCTION);
      const bool floor_div = f == Function::INT && compact_.last.op == Op::DIV;
      const uint32_t division = compact_.last.pc;
      if (basic()) source_position(primary_start);
      if(floor_div) {
        if(emitting() && (out_ || Paged))put_byte(division,(uint8_t)Op::FLOOR_DIV);
        compact_.last={division,0,Op::FLOOR_DIV};
      } else {
        emit(Op::FUNCTION);
        byte(f == Function::RND ? (uint8_t)Function::RND_LIMIT : fn);
      }
      if (f == Function::MAX) stack(-1);
      return;
    }
    fail(Error::SYNTAX);
  }
  Text command_end(Text begin, bool print) {
    char quote = 0;
    int nesting = 0;
    Text alternate = tinybasic_syntax::else_at(begin, end_);
    for (Text q = begin; q < end_; ++q) {
      if (quote) {
        if (*q == quote) quote = 0;
        continue;
      }
      if (*q == '\'' || *q == '"') {
        quote = *q;
        continue;
      }
      if (*q == '(')
        ++nesting;
      else if (*q == ')' && nesting)
        --nesting;
      if (nesting) continue;
      if (q == alternate) return q;
      if (print && *q == '#') {
        unsigned width, digits;
        Text format = tinybasic_syntax::print_precision(q, end_, width, digits);
        if (format) { q = format - 1; continue; }
      }
      if (*q == ':') return q;
      if (*q == ';') {
        if (!print) return q;
        Text saved = p_;
        p_ = q + 1;
        const uint8_t cmd = lookup(basic_commands, 255);
        skip();
        bool looks = cmd != 255;
        if (cmd == READ_INPUT && p_ < end_ && *p_ == '(') looks = false;
        if (!looks) {
          p_ = q + 1;
          skip();
          if (p_ < end_ && alpha(*p_)) {
            ++p_;
            skip();
            looks = p_ < end_ && *p_ == '=';
          } else if (p_ < end_ && *p_ == '@') {
            // A PRINT item may itself be an array expression. Only an '='
            // after the complete target starts the next assignment.
            ++p_;
            skip();
            if (p_ < end_ && *p_ == '(') {
              int brackets = 0;
              do {
                if (*p_ == '(') ++brackets;
                if (*p_ == ')') --brackets;
                ++p_;
              } while (p_ < end_ && brackets);
              skip();
              looks = p_ < end_ && *p_ == '=';
            }
          } else if (p_ < end_ && *p_ == '.') {
            ++p_;
            while (p_ < end_ && (alpha(*p_) || digit(*p_))) ++p_;
            skip();
            looks = p_ < end_ && *p_ == '=';
          }
        }
        p_ = saved;
        if (looks) return q;
      }
    }
    return end_;
  }
  bool text(uint8_t opcode) {
    skip();
    if (p_ == end_) return false;
    if (*p_ == '"' || (basic() && *p_ == '\'')) {
      const char quote = *p_++;
      Text start = p_;
      while (p_ < end_ && *p_ != quote) ++p_;
      if (p_ == end_) {
        fail(Error::UNTERMINATED_STRING);
        return true;
      }
      if (resource_literals()) {
        do {
          const uint16_t n=(uint16_t)(p_-start>4096?4096:p_-start);
          emit(Op::PRINT_RESOURCE);u16(intern_resource(start,n));start+=n;
        } while(start<p_ && error_==Error::NONE);
      } else {
        byte(opcode);
        u16((uint16_t)(p_ - start));
        while (start < p_) byte((uint8_t)*start++);
      }
      ++p_;
      return true;
    }
    if (basic() && match('_')) {
      byte(opcode);
      u16(1);
      byte('\r');
      return true;
    }
    if (basic() && match('^')) {
      if (p_ == end_ || !alpha(*p_))
        fail(Error::SYNTAX);
      else {
        byte(opcode);
        u16(1);
        byte((uint8_t)(upper(*p_++) ^ 0x40));
      }
      return true;
    }
    return false;
  }
  void assignment() {
    Target t = target();
    if (!match('=')) fail(Error::SYNTAX);
    do {
#if !defined(LANGUAGE_VM_TEST_NO_FUSION)
      const uint32_t begin=pc_;
#endif
      expression();
#if !defined(LANGUAGE_VM_TEST_NO_FUSION)
      if(t.kind || !fuse_assignment(t.index,begin))
#endif
        store(t);
      skip();
      if (!basic() || !match(',')) break;
      Text saved = p_;
      const uint32_t save_pc = pc_;
      const uint8_t save_sp = sp_;
      const Error save_error = error_;
      const auto save_positions=positions_;
      Target next = target();
      if(error_==Error::NONE && match('='))t=next;
      else {
        p_=saved;pc_=save_pc;sp_=save_sp;error_=save_error;
        positions_=save_positions;compact_.barrier();
        if(t.kind!=0 || t.index==25)fail(Error::VARIABLE);
        else ++t.index;
      }
    } while (error_ == Error::NONE);
  }
  __attribute__((noinline)) bool fuse_assignment(uint8_t index,uint32_t begin) {
#if MK61_VM_COMPACT_OPERANDS && !defined(LANGUAGE_VM_TEST_NO_FUSION)
    const auto tail=compact_.last;
    uint8_t source=0;
    if(tail.pc+tail.width()==pc_ && (tail.op==Op::BINARY_PAIR ||
        (tail.pc==begin && tail.operand(source)))) {
      const auto operation=Op(uint8_t(tail.arguments));
      const uint8_t left=uint8_t(tail.arguments>>8),right=uint8_t(tail.arguments>>16);
      pc_=tail.pc;compact_.barrier();
      if(tail.op!=Op::BINARY_PAIR) {emit(Op::MOVE_LOCAL);byte(source);byte(index);}
      else if(left==index && (operation==Op::ADD || operation==Op::SUB) &&
              (right<26 || (right>=128 && compact::literal(right)>=0))) {
        emit(Op::UPDATE_LOCAL);byte(index);
        byte(uint8_t((right<26?right|64:compact::literal(right)) | (operation==Op::SUB?128:0)));
      } else {emit(Op::BINARY_STORE);byte(uint8_t(operation));byte(left);byte(right);byte(index);}
      stack(-1);return true;
    }
    return false;
#else
    const auto& lhs=compact_.earlier;const auto& rhs=compact_.before;const auto& last=compact_.last;
    if((last.op!=Op::ADD && last.op!=Op::SUB) || pc_!=last.pc+1 ||
       lhs.pc!=begin || lhs.op!=Op::LOAD || lhs.arguments!=index || rhs.pc!=begin+2U)return false;
    uint8_t source=0;
    if(rhs.op>=Op::CONST_0 && rhs.op<=Op::CONST_15 && last.pc==begin+3U)
      source=uint8_t(rhs.op)-uint8_t(Op::CONST_0);
    else if(rhs.op==Op::LOAD && last.pc==begin+4U)source=uint8_t(rhs.arguments)|64;
    else return false;
    source|=uint8_t((unsigned(last.op)-unsigned(Op::ADD))<<7);
    pc_=begin;compact_.barrier();operation(Op::UPDATE_LOCAL,-1);byte(index);byte(source);return true;
#endif
  }

  void print() {
    emit(Op::PRINT_BEGIN);
    const bool positioned=basic() && keyword("AT",2);
    if(positioned) {
      expression();if(!match(','))fail(Error::SYNTAX);expression();
      if(!match(';'))fail(Error::SYNTAX);
      operation(Op::PRINT_AT,-2);
      skip();if(p_==end_)fail(Error::SYNTAX);
    }
    uint8_t separator = 0;
    skip();
    if (!basic() && p_ == end_) fail(Error::SYNTAX);
    while (p_ < end_ && error_ == Error::NONE) {
      skip();
      if (p_ == end_) break;
      if (basic() && (*p_ == ',' || *p_ == ';')) {
        separator = (uint8_t)*p_++;
        emit(Op::PRINT_SEPARATOR);
        byte(separator == ',' ? 1 : 0);
        continue;
      }
      bool format = false;
      unsigned width = 0, digits = 0;
      Text precision = basic() ? tinybasic_syntax::print_precision(p_, end_, width, digits) : nullptr;
      const bool carriage =
          basic() && (*p_ == '_' || (p_ + 1 < end_ && *p_ == '^' && upper(p_[1]) == 'M'));
      if (precision) {
        if (width > 63 || !digits || digits > 15) { fail(Error::FORMAT); return; }
        p_ = precision; format = true;
        emit(Op::PRINT_PRECISION); byte((uint8_t)width); byte((uint8_t)digits);
      } else if (!basic() && match('!'))
        emit(Op::PRINT_FLUSH);
      else if (!text((uint8_t)Op::PRINT_TEXT)) {
        format = basic() && match('#');
        expression();
        operation(format ? Op::PRINT_FORMAT : Op::PRINT_NUMBER, -1);
      }
      skip();
      if (p_ < end_ && (*p_ == ',' || (basic() && *p_ == ';'))) {
        separator = (uint8_t)*p_++;
        if (basic()) {
          emit(Op::PRINT_SEPARATOR);
          byte(separator == ',' && !format && !carriage ? 2 : 0);
        }
        continue;
      }
      separator = 0;
      break;
    }
    emit(Op::PRINT_END);
    byte(!positioned && separator ? 1 : 0);
  }
  void graphics(basic_graphics::Operation op) {
    uint8_t count = 0;
    skip();
    if (p_ < end_)
      do {
        if (count == basic_graphics::maximum(op)) {
          fail(Error::SYNTAX);
          break;
        }
        expression();
        ++count;
        skip();
        if (p_ == end_)
          break;
        if (!match(',')) {
          fail(Error::SYNTAX);
          break;
        }
      } while (error_ == Error::NONE);
    if (count < basic_graphics::minimum(op))
      fail(Error::SYNTAX);
    operation(Op::GRAPHICS, -count);
    byte((uint8_t)op);
    byte(count);
  }
  void graph() {
    Text expression_start = p_;
    Text comma = tinybasic_syntax::parameter_separator(p_, end_);
    if (comma == end_) {
      fail(Error::SYNTAX);
      return;
    }
    Text full_end = end_;
    p_ = comma + 1;
    for (unsigned i = 0; i < 4; ++i) {
      expression();
      if (i < 3 && !match(','))
        fail(Error::SYNTAX);
    }
    skip();
    if (p_ != full_end) {
      fail(Error::SYNTAX);
      return;
    }
    operation(Op::GRAPH_BEGIN, -4);
    const uint32_t next_at = pc_;
    emit_address(0);
    const uint32_t body = pc_;
    p_ = expression_start;
    end_ = comma;
    graph_expression_ = true;
    expression();
    graph_expression_ = false;
    skip();
    if (p_ != end_)
      fail(Error::SYNTAX);
    const uint32_t next = pc_;
    operation(Op::GRAPH_NEXT, -1);
    emit_address(body);
    patch_address(next_at, next);
    end_ = full_end;
    p_ = full_end;
  }
  void input() {
    skip();
    if (!basic() && p_ == end_) {
      emit(Op::WAIT);
      return;
    }
    bool any = false;
    while (p_ < end_ && error_ == Error::NONE) {
      char prompt[96];
      uint8_t used = 0;
      bool custom = false;
      while (p_ < end_) {
        skip();
        if (p_ == end_) break;
        if (*p_ != '"' && *p_ != '\'' && *p_ != '^' && *p_ != '_') break;
        if (!basic()) {
          fail(Error::VARIABLE);
          break;
        }
        char quote = *p_++;
        custom = true;
        if (quote == '_') {
          used = 0;
        } else if (quote == '^') {
          if (p_ == end_ || !alpha(*p_))
            fail(Error::SYNTAX);
          else {
            const char c = (char)(upper(*p_++) ^ 0x40);
            if (c == '\r')
              used = 0;
            else if (used < 95)
              prompt[used++] = c;
          }
        } else {
          while (p_ < end_ && *p_ != quote) {
            const char c = *p_++;
            if (used < 95) {
              prompt[used++] = c;
            }
          }
          if (p_ == end_)
            fail(Error::SYNTAX);
          else
            ++p_;
        }
        skip();
        if (p_ < end_ && (*p_ == ',' || *p_ == ';')) ++p_;
      }
      Text name = p_;
      Target t = target();
      if (!custom) {
        while (name < p_ && space(*name)) ++name;
        Text finish = p_;
        while (finish > name && space(finish[-1])) --finish;
        while (name < finish && used < 94) {
          prompt[used++] = *name++;
        }
        if (basic()) prompt[used++] = ':';
      }
      if (resource_literals()) {
        emit(Op::INPUT_RESOURCE); u16(intern_resource(prompt, used));
      } else {
        emit(Op::READ_INPUT); u16(used);
        for (uint8_t i = 0; i < used; ++i) byte((uint8_t)prompt[i]);
      }
      stack(1);
      store(t);
      any = true;
      skip();
      if (p_ == end_) break;
      if (!basic() || (*p_ != ',' && *p_ != ';')) {
        fail(Error::SYNTAX);
        break;
      }
      ++p_;
    }
    if (!any && basic()) fail(Error::VARIABLE);
  }
  __attribute__((noinline)) void source_position(Text at) {
    if constexpr(Expression)return;
    if (!count_) return;  // INPUT expressions have no statement/source map.
    compact_.barrier();
    if(!positions_.note(pc_,uint16_t(at-source_-line_start_+1),SourceOutput{this}))fail(Error::FULL);
  }
  bool number(double& value, Text& after) {
    char token[64]; unsigned n=0;
    Text q=p_;
    while(q<end_ && n+1<sizeof(token)) {
      const char c=*q;
      if(!digit(c) && c!='.' && c!='e' && c!='E' && c!='+' && c!='-')break;
      token[n++]=c;++q;
    }
    token[n]=0;
    const char* parsed=nullptr;
#if defined(MK61_BUILD_PORTABLE_SYSTEM)
    if(!portable_system::parse_number(token,value,parsed))return false;
#else
    value=mk_math::strtod(token,&parsed);
#endif
    after=p_+(parsed-token);
    // strtod may end before the speculative + / - suffix.
    return parsed!=token && (unsigned(parsed-token)<n || q==end_ ||
        (!digit(*q) && *q!='.' && *q!='e' && *q!='E'));
  }
  bool data_literal(double& value) {
    skip();
    const bool negative = match('-');
    if (!negative) (void)match('+');
    skip();
    if (p_ == end_ || (!digit(*p_) && *p_ != '.')) {
      fail(Error::SYNTAX);
      return false;
    }
    Text after = nullptr;
if (!number(value, after)) { fail(Error::SYNTAX); return false; }
    if (after == p_ || after > end_ || !mk_math::is_finite(value)) {
      fail(Error::SYNTAX);
      return false;
    }
    p_ = after;
    if (negative) value = -value;
    return true;
  }
  void data() {
    emit(Op::DATA);
    const uint32_t count_at = pc_;
    emit_address(0);
    uint32_t count = 0;
    do {
      Text literal=p_;
      while(literal<end_ && space(*literal)) ++literal;
      const bool negative=literal<end_ && *literal=='-';
      if(literal<end_ && (*literal=='+' || *literal=='-')) ++literal;
      while(literal<end_ && space(*literal)) ++literal;
      double value = 0;
      if (!data_literal(value)) break;
      const uint32_t before = pc_;
      constant(negative ? -value : value,literal,p_);
      if(negative) emit(Op::NEG);
      stack(-1);  // DATA literals occupy the image, never the execution stack.
      count += pc_ - before;
      skip();
      if (p_ == end_) break;
      if (!match(',')) {
        fail(Error::SYNTAX);
        break;
      }
      if (p_ == end_) fail(Error::SYNTAX);
    } while (error_ == Error::NONE);
    patch_address(count_at, count);
  }
  void read_data() {
    do {
      Target t = target();
      operation(Op::READ_DATA, 1);
      store(t);
      skip();
      if (p_ == end_) break;
      if (!match(',')) {
        fail(Error::SYNTAX);
        break;
      }
      if (p_ == end_) fail(Error::SYNTAX);
    } while (error_ == Error::NONE);
  }
  void on() {
    expression();
    const bool sub = keyword("GOSUB", 3);
    if (!sub && !keyword("GOTO", 1)) {
      fail(Error::SYNTAX);
      return;
    }
    operation(sub ? Op::ON_GOSUB : Op::ON_GOTO, -1);
    const uint32_t count_at = pc_;
    u16(0);
    uint16_t count = 0;
    do {
      double line = 0;
      if (!data_literal(line)) break;
      if (line < 1 || line > 32767 || line != mk_math::floor(line)) {
        fail(Error::LINE_NUMBER);
        break;
      }
      u16((uint16_t)line);
      ++count;
      skip();
      if (p_ == end_) break;
      if (!match(',')) {
        fail(Error::SYNTAX);
        break;
      }
      if (p_ == end_) fail(Error::SYNTAX);
    } while (error_ == Error::NONE);
    patch(count_at, count);
  }
  void commands(uint8_t nesting) {
    if (nesting >= 16) {
      fail(Error::STACK);
      return;
    }
    while (p_ < end_ && error_ == Error::NONE) {
      skip();
      if (p_ == end_) break;
      Text const command_start = p_;
      const uint8_t cmd = lookup(basic_commands, ASSIGN);
      if (cmd == REM) {
        p_ = end_;
        break;
      }
      if (cmd == ASSIGN && !tinybasic_syntax::word(command_start, end_, "LET", 1)) {
        Text word = command_start;
        while (word < end_ && alpha(*word)) ++word;
        if (word - command_start > 1) {
          fail(Error::UNKNOWN_COMMAND);
          break;
        }
      }
      source_position(command_start);
      if (cmd == IF) {
        expression();
        (void)keyword("THEN", 1);
#if !defined(LANGUAGE_VM_TEST_NO_FUSION)
        if(compact_.last.op>=Op::EQ && compact_.last.op<=Op::GE && pc_==compact_.last.pc+1) {
          // Fuse only the final comparison, never an earlier operand or an
          // operation across a source prefix. Sizing and EMIT take this path.
          const Op comparison=compact_.last.op;pc_=compact_.last.pc;
          operation(Op::COMPARE_FALSE,-1);byte(comparison_mask(comparison));
        } else
#endif
          operation(Op::JUMP_FALSE, -1);
        const uint32_t patch_at = pc_;
        emit_address(0);
        skip();
        if (p_ == end_) fail(Error::SYNTAX);
        Text full_end = end_;
        Text after_else = nullptr;
        Text alternate = tinybasic_syntax::else_at(p_, end_, &after_else);
        end_ = alternate;
        skip();
        if (p_ == end_) fail(Error::SYNTAX);
        commands((uint8_t)(nesting + 1));
        if (alternate < full_end) {
          emit(Op::JUMP);
          const uint32_t skip_else = pc_;
          emit_address(0);
          patch_address(patch_at, pc_);
          end_ = full_end;
          p_ = after_else;
          skip();
          if (p_ == end_) fail(Error::SYNTAX);
          commands((uint8_t)(nesting + 1));
          patch_address(skip_else, pc_);
        } else
          patch_address(patch_at, pc_);
        end_ = full_end;
        p_ = full_end;
        break;
      }
      Text const full_end = end_;
      Text const segment = command_end(p_, cmd == PRINT || cmd == READ_INPUT);
      end_ = segment;
      switch (cmd) {
        case ASSIGN:
          assignment();
          break;
        case PRINT:
          print();
          break;
        case READ_INPUT:
          input();
          break;
        case GOTO_CMD:
        case GOSUB_CMD:
          if (cmd == GOSUB_CMD && tinybasic_syntax::parameter_separator(p_, end_) < end_)
            basic_call(false);
          else if(!direct_basic_branch(cmd==GOSUB_CMD)) {
            expression();
            operation(cmd == GOTO_CMD ? Op::GOTO : Op::GOSUB, -1);
          }
          if (cmd == GOTO_CMD && segment < full_end &&
              !tinybasic_syntax::word(segment, full_end, "ELSE", 2))
            fail(Error::SYNTAX);
          break;
        case RETURN_CMD:
          if (segment < full_end && !tinybasic_syntax::word(segment, full_end, "ELSE", 2))
            fail(Error::SYNTAX);
          skip();
          if (p_ < end_) { expression(); operation(Op::RETURN_VALUE, -1); }
          else emit(Op::RETURN);
          break;
        case FOR_CMD: {
          Target t = target();
          if (t.kind == 1 || !match('=')) fail(Error::FOR);
          expression();
          if (!keyword("TO", 1)) fail(Error::FOR);
          expression();
          if (keyword("STEP", 1))
            expression();
          else
            constant(1);
          operation(t.kind == 2 ? Op::FOR_ARRAY : Op::FOR_BASIC, t.kind == 2 ? -4 : -3);
          if (t.kind != 2) byte(t.index);
          break;
        }
        case NEXT_CMD: {
          Target t = target();
          if (t.kind == 1) fail(Error::FOR);
          if (t.kind == 2)
            operation(Op::NEXT_ARRAY, -1);
          else {
            emit(Op::NEXT_BASIC);
            byte(t.index);
          }
          break;
        }
        case DATA_CMD:
          data();
          break;
        case READ_DATA_CMD:
          read_data();
          break;
        case RESTORE_CMD:
          skip();
          if (p_ == end_)
            constant(0);
          else
            expression();
          operation(Op::RESTORE_DATA, -1);
          break;
        case ON_CMD:
          on();
          break;
        case CLS:
          emit(Op::CLEAR);
          break;
        case PSET_CMD:graphics(basic_graphics::Operation::PSET);break;
        case LINE_CMD:graphics(basic_graphics::Operation::LINE);break;
        case BOX_CMD:graphics(basic_graphics::Operation::BOX);break;
        case CIRCLE_CMD:graphics(basic_graphics::Operation::CIRCLE);break;
        case SHOW_CMD:graphics(basic_graphics::Operation::SHOW);break;
        case GRAPH_CMD:graph();break;
        case PAUSE:
          emit(Op::WAIT);
          break;
        case END:
          if (segment < full_end && !tinybasic_syntax::word(segment, full_end, "ELSE", 2))
            fail(Error::SYNTAX);
          emit(Op::HALT);
          break;
        default:
          fail(Error::SYNTAX);
          break;
      }
      skip();
      if (p_ != end_) fail(Error::SYNTAX);
      end_ = full_end;
      p_ = tinybasic_syntax::word(segment, full_end, "ELSE", 2) ? full_end
           : segment < full_end                                 ? segment + 1
                                                                : segment;
    }
  }
  void focal_statement(uint8_t nesting) {
    if (nesting >= MAX_LOOPS) {
      fail(Error::STACK);
      return;
    }
    skip();
    Text begin = p_;
    while (p_ < end_ && alpha(*p_)) ++p_;
    const size_t n = (size_t)(p_ - begin);
    skip();
    if (end_ - p_ >= 80) {
      fail(Error::FULL);
      return;
    }
    static const char* const names[] = {"SET", "COMMENT", "PRINT", "ASK",  "BRANCH",
                                        "DO",  "EXIT",    "FOR",   "GOTO", "RETURN"};
    uint8_t cmd = 255;
    for (uint8_t i = 0; i < 10; ++i) {
      const size_t length = strlen(names[i]);
      bool match_word = n == 1 || n == length;
      for (size_t j = 0; match_word && j < n; ++j)
        match_word = upper(begin[j]) == names[i][j];
      if (match_word) {
        cmd = i;
        break;
      }
    }
    switch (cmd) {
      case 0:
        assignment();
        break;
      case 1:
        p_ = end_;
        return;
      case 2:
        print();
        break;
      case 3:
        input();
        break;
      case 4: {
        if (!match('(')) fail(Error::SYNTAX);
        expression();
        if (!match(')')) fail(Error::EXPECTED_PAREN);
        operation(Op::BRANCH, -1);
        for (uint8_t i = 0; i < 3; ++i) {
          const uint32_t number = address(false);
          emit_address(target_pc(number));
          if (i < 2 && !match(',')) fail(Error::LINE);
        }
        break;
      }
      case 5: {
        Text start = p_;
        const uint32_t number = address(true);
        bool group = true;
        for (Text q = start; q < p_; ++q)
          if (*q == '.') group = false;
        emit(Op::DO_FOCAL);
        u16(target_pc(number, group));
        uint16_t finish = 0xFFFF;
        if (emitting())
          for (uint16_t i = 0; i < count_; ++i)
            if (line_at(i).pc == target_pc(number, group)) {
              uint16_t j = (uint16_t)(i + 1);
              if (group)
                while (j < count_ && line_at(j).number / 1000 == number / 1000) ++j;
              finish = j < count_ ? line_at(j).pc : image_end_;
              break;
            }
        u16(finish == 0xFFFF ? finish : (uint16_t)(finish | (group ? 0x8000U : 0U)));
        break;
      }
      case 6:
        emit(Op::HALT);
        break;
      case 7: {
        Target t = target();
        if (t.kind || !match('=')) fail(Error::FOR);
        expression();
        if (!match(',')) fail(Error::FOR);
        expression();
        if (match(',')) {
          expression(); /* start, step, limit */
        } else {
          constant(1); /* start, limit, step; swap flag */
        }
        operation(Op::FOR_FOCAL, -3);
        byte(t.index);
        const uint32_t after = pc_;
        u16(0);
        const uint32_t body = pc_;
        byte(0);  // patched below: operand order
        // Distinguish two/three expressions without reparsing literals.
        bool three = false;
        int nesting_count = 0;
        uint8_t commas = 0;
        for (Text q = begin; q < p_; ++q) {
          if (*q == '(')
            ++nesting_count;
          else if (*q == ')')
            --nesting_count;
          else if (*q == ',' && !nesting_count)
            ++commas;
        }
        three = commas == 2;
        if(emitting() && (out_ || Paged) && body<capacity_)put_byte(body,three?1:0);
        if (!match(';')) fail(Error::FOR);
        focal_statement((uint8_t)(nesting + 1));
        emit(Op::NEXT_FOCAL);
        patch(after, pc_);
        break;
      }
      case 8: {
        const uint32_t number = address(false);
        emit(Op::JUMP);
        emit_address(target_pc(number));
        break;
      }
      case 9:
        emit(Op::RETURN);
        break;
      default:
        fail(Error::SYNTAX);
        break;
    }
    skip();
    if (p_ != end_) fail(Error::SYNTAX);
  }
};
template<Language Lang, uint16_t Half>
__attribute__((noinline)) CompileResult compile_resource_second(
    const source::Reader& source, uint16_t length, uint8_t* output, uint16_t capacity,
    Line* lines, bool rf, const ResourceSource* resources, uint8_t* first) {
  uint8_t second[Half];
  Compiler<Lang> compiler(source, length, output, capacity, lines, rf, resources, {first, second, Half});
  return compiler.compile();
}
template<Language Lang, uint16_t Half>
__attribute__((noinline)) CompileResult compile_resource_first(
    const source::Reader& source, uint16_t length, uint8_t* output, uint16_t capacity,
    Line* lines, bool rf, const ResourceSource* resources) {
  uint8_t first[Half];
  return compile_resource_second<Lang, Half>(source, length, output, capacity, lines, rf, resources, first);
}
template<Language Lang>
CompileResult compile_resources(const source::Reader& source, uint16_t length, uint8_t* output,
    uint16_t capacity, Line* lines, bool rf, const ResourceSource* resources, uint16_t needed) {
  if(needed <= 192) return compile_resource_first<Lang,96>(source,length,output,capacity,lines,rf,resources);
  if(needed <= 768) return compile_resource_first<Lang,384>(source,length,output,capacity,lines,rf,resources);
  if(needed <= 3072) return compile_resource_first<Lang,1536>(source,length,output,capacity,lines,rf,resources);
  return compile_resource_first<Lang,3072>(source,length,output,capacity,lines,rf,resources);
}
}  // namespace

uint32_t checksum(const uint8_t* p, size_t length) {
  uint32_t crc = 0xFFFFFFFFU;
  while (length--) {
    crc ^= *p++;
    for (uint8_t bit = 0; bit < 8; ++bit)
      crc = (crc >> 1) ^ (0xEDB88320U & (0U - (crc & 1U)));
  }
  return ~crc;
}
// Resident/split-VM images only compile INPUT expressions. Full programs are
// compiled by the language APP (or host tools), which owns the larger stack
// budget. Keep those entry points out of the resident translation unit rather
// than relying on LTO to discard their workspace frames.
#if !defined(ARDUINO_ARCH_STM32) || defined(MK61_LANGUAGE_VM_COMPILER) || \
    defined(MK61_LANGUAGE_VM_TEST) || (MK61_ENABLE_FOCAL && !MK61_FOCAL_IS_LOADABLE)
CompileResult compile_flash_source(Language language,const source::Reader& source,flash::IO io,bool rf_available,void* scratch) {
  if(language!=Language::BASIC && language!=Language::FOCAL)return {Error::SYNTAX,0,0,0,0};
  if(!io.read || !io.write || !io.truncate)return {Error::IO,0,0,0,0};
#if defined(MK61_BUILD_PORTABLE_SYSTEM) && defined(MK61_LANGUAGE_VM_COMPILER)
  if(!scratch)return {Error::IO,0,0,0,0};
  static_assert(sizeof(flash::Program)<=FLASH_COMPILER_WORKSPACE_SIZE-FLASH_FRONTEND_BYTES,"Flash compiler scratch prefix");
#else
  alignas(flash::Program) uint8_t local[sizeof(flash::Program)];
  if(!scratch)scratch=local;
#endif
  source::CursorScope scope(source);
  auto& program=*new(scratch) flash::Program(source,io);
  struct ProgramLifetime {
    flash::Program& value;
    __attribute__((noinline)) ~ProgramLifetime(){value.~Program();memset(static_cast<void*>(&value),0,sizeof(value));}
  } lifetime{program};
  if(!program.prepare(language))return {program.error(),0,0,0,0};
  if(language==Language::FOCAL)return focal_next::compile_flash_program(source,program,rf_available);
  Compiler<Language::BASIC,true> compiler(source,source.size(),nullptr,UINT32_MAX,nullptr,
                                    rf_available,nullptr,{},&program);
  return compiler.compile();
}
CompileResult compile_basic_source(const source::Reader& source, uint16_t length, uint8_t* output,
                            uint16_t capacity, bool rf_available, const ResourceSource* resources) {
  if (capacity < HEADER_SIZE) return {Error::FULL, 0, 0, 0, 0};
  source::CursorScope cursor_scope(source);
  Line lines[192];
  Compiler<Language::BASIC> compiler(source, length, output, capacity, lines,
                                     rf_available, resources);
  const auto sized = compiler.compile();
  if(sized.error != Error::NONE || !compiler.resource_reservation()) return sized;
  return compile_resources<Language::BASIC>(source,length,output,capacity,lines,rf_available,
                                             resources,compiler.resource_reservation());
}
CompileResult compile_focal_source(const source::Reader& source, uint16_t length, uint8_t* output,
                            uint16_t capacity, bool rf_available, const ResourceSource* resources) {
  return focal_next::compile_program(source,length,output,capacity,rf_available,resources);
}
CompileResult compile_source(Language language, const source::Reader& source,
                             uint8_t* output, uint16_t capacity, bool rf,
                             const ResourceSource* resources) {
  if(language==Language::BASIC) return compile_basic_source(source,source.size(),output,capacity,rf,resources);
  if(language==Language::FOCAL) return compile_focal_source(source,source.size(),output,capacity,rf,resources);
  return {Error::SYNTAX,0,0,0,0};
}
CompileResult compile_basic(const char* text,uint16_t n,uint8_t* out,uint16_t cap,bool rf,const ResourceSource* resources) {
  if(!text)return {Error::SYNTAX,0,0,0,0};
  source::Reader source(text,n);return compile_source(Language::BASIC,source,out,cap,rf,resources);
}
CompileResult compile_focal(const char* text,uint16_t n,uint8_t* out,uint16_t cap,bool rf,const ResourceSource* resources) {
  if(!text)return {Error::SYNTAX,0,0,0,0};
  source::Reader source(text,n);return compile_source(Language::FOCAL,source,out,cap,rf,resources);
}

#endif
bool validate_focal_expression(const char* source,uint16_t length,bool rf_available) {
  return source && focal_next::valid_fragment(source,length,rf_available);
}
CompileResult compile_expression(Language language, const char* source, uint16_t length,
                                 uint8_t* output, uint16_t capacity) {
  if(!source)return {Error::SYNTAX,0,0,0,0};
  if(language==Language::FOCAL)
    return focal_next::compile_expression(source,length,output,capacity);

  source::Reader input(source,length);
  source::CursorScope cursor_scope(input);
  if (capacity < HEADER_SIZE) return {Error::FULL, 0, 0, 0, 0};
  if (language == Language::BASIC) {
    Compiler<Language::BASIC,false,true> compiler(input, length, output, capacity, nullptr);
    return compiler.expression_only();
  }
  if (language == Language::FOCAL) {
    Compiler<Language::FOCAL,false,true> compiler(input, length, output, capacity, nullptr);
    return compiler.expression_only();
  }
  return {Error::SYNTAX, 0, 0, 0, 0};
}

}  // namespace language_vm
#endif
