#ifndef MK61_COMPACT_FOCAL_COMPILER_HPP
#define MK61_COMPACT_FOCAL_COMPILER_HPP
#include "focal_syntax.hpp"
#include "basic_graphics_protocol.hpp"
#include "language_bytecode.hpp"
#include "language_source.hpp"
#include "language_flash_program.hpp"
namespace focal_next {
// Two sizing/emission passes, like the BASIC compiler. Only the sorted line
// map is retained. Emitted literals belong to the image, never to an APP.
template <bool Expression,bool Paged=false> class Compiler {
public:
  using Text = language_vm::source::Cursor;
  using Op = language_vm::Op;
  using E = language_vm::Error;
  struct Line {
    uint32_t number;
    uint16_t begin, end;
    uint32_t pc;
  };
  struct Target {
    uint8_t kind, index;
  };

private:
  Text source_, p_, end_;
  const language_vm::source::Reader* input_;
  const language_vm::ResourceSource *resources_;

public:
  struct Resource {
    uint16_t begin, length, offset;
    bool colon;
  };

private:
  Resource *resources_table_;
  uint16_t resource_count_ = 0, resource_bytes_ = 0;
  bool pool_ = false;
  bool owned() const {
    return !Paged && resources_ &&
           resources_->mode == language_vm::ResourceMode::EMBEDDED;
  }

  uint8_t *output_;
  uint16_t length_,offset_=0;
  uint32_t capacity_,pc_;
  Line *lines_;
  language_vm::flash::Program* flash_;
  Line line_at(uint16_t i) {
    if(!Paged)return lines_[i];
    const auto l=flash_->line(i);return {l.number,l.begin,l.end,l.pc};
  }
  void set_line_pc(uint16_t i,uint32_t pc) {if(Paged)flash_->pc(i,pc);else lines_[i].pc=pc;}
  void put_byte(uint32_t at,uint8_t b) {if(Paged)flash_->byte(at,b);else if(output_)output_[at]=b;}

  uint16_t count_=0;
  uint8_t pass_ = 0, depth_ = 0, sp_ = 0, maximum_ = 0;
  E error_ = E::NONE;
  Op before_op_=Op::HALT,previous_op_=Op::HALT;
  uint32_t before_pc_=0,previous_pc_=0;
  bool rf_, requires_rf_ = false, has_calls_ = false, graph_expression_ = false;
  void fail(E error) {
    if (error_ == E::NONE) {
      error_ = error;
      offset_ = uint16_t(p_ - source_);
    }
  }
  void skip_space() { p_ = skip(p_, end_); }
  bool take(char c) {
    skip_space();
    if (p_ < end_ && *p_ == c) {
      ++p_;
      return true;
    }
    return false;
  }
  void expect(char c) {
    if (!take(c))
      fail(E::SYNTAX);
  }
  void byte(uint8_t b) {
    if (pc_ >= capacity_ ||
        (!Paged && pc_ >= (pool_ && owned() ? language_vm::MAX_MODULE
                                 : language_vm::MAX_IMAGE))) {
      fail(E::FULL);
      return;
    }
    if((output_ || Paged) && pass_)put_byte(pc_,b);
    if(Paged && flash_->error()!=E::NONE)fail(flash_->error());
    ++pc_;
  }
  void emit_word(uint16_t w) {
    byte(uint8_t(w));
    byte(uint8_t(w >> 8));
  }
  void emit_address(uint32_t w) {emit_word(uint16_t(w));if(Paged)emit_word(uint16_t(w>>16));}
  void patch_address(uint32_t at,uint32_t value) {
    if(pass_ && (output_ || Paged)) {for(unsigned i=0;i<(Paged?4U:2U);++i)put_byte(at+i,uint8_t(value>>(i*8)));}
  }
  void dword(uint32_t w) {
    emit_word(uint16_t(w));
    emit_word(uint16_t(w >> 16));
  }
  void op(Op instruction, int change = 0) {
    if constexpr (!Expression) {
#if !defined(LANGUAGE_VM_TEST_NO_COMPILED_BLOCKS)
      if((output_ || Paged) && pass_ && language_vm::index_block_shape(instruction,pc_,
          before_op_,before_pc_,previous_op_,previous_pc_))
        put_byte(before_pc_,uint8_t(Op::BLOCK_INDEX));
#endif
      if(instruction!=Op::SOURCE_POS) {
        before_op_=previous_op_;before_pc_=previous_pc_;
        previous_op_=instruction;previous_pc_=pc_;
      }
    }
    byte(uint8_t(instruction));
    if (change < 0 && unsigned(-change) > sp_) {
      fail(E::INVALID_IMAGE);
      return;
    }
    int next = int(sp_) + change;
    if (next > language_vm::MAX_STACK) {
      fail(E::STACK);
      return;
    }
    sp_ = uint8_t(next);
    if (sp_ > maximum_)
      maximum_ = sp_;
  }
  void constant(double v) {
    if (v >= 0 && v <= 15 && mk_math::trunc(v) == v)
      op(Op(unsigned(Op::CONST_0) + unsigned(v)), 1);
    else if (v >= -128 && v <= 127 && mk_math::trunc(v) == v) {
      op(Op::CONST_I8, 1);
      byte(uint8_t(int8_t(v)));
    } else if (v >= -32768 && v <= 32767 && mk_math::trunc(v) == v) {
      op(Op::CONST_I16, 1);
      emit_word(uint16_t(int16_t(v)));
    } else if (v >= -2147483648.0 && v <= 2147483647.0 &&
               mk_math::trunc(v) == v) {
      op(Op::CONST_I32, 1);
      dword(uint32_t(int32_t(v)));
    } else {
      op(Op::CONST_F64, 1);
      uint64_t bits = mk_math::bit_copy<uint64_t>(v);
      for (unsigned i = 0; i < 8; ++i)
        byte(uint8_t(bits >> (i * 8)));
    }
  }
  int find(Address a) {
    if(Paged)return flash_->find(a.exact?key(a):a.major,!a.exact);
    for (unsigned n = 0; n < count_; ++n)
      if (a.exact ? line_at(n).number == key(a)
                  : line_at(n).number / 1000 == a.major)
        return int(n);
    return -1;
  }
  bool label(Address &a) {
    if (!address(p_, end_, a)) {
      fail(E::LINE);
      return false;
    }
    return true;
  }
  uint32_t label_pc(Address a) {
    int n = find(a);
    return n < 0 ? (Paged?UINT32_MAX:0xFFFF) : line_at(n).pc;
  }
  uint32_t label_end(Address a) {
    int n = find(a);
    if (n < 0)
      return Paged?UINT32_MAX:0xFFFF;
    if (a.exact)
      ++n;
    else
      while (n < count_ && line_at(n).number / 1000 == a.major)
        ++n;
    return n < count_ ? line_at(n).pc : image_halt_;
  }
  uint32_t image_halt_ = 0;
  void target(Target &t) {
    skip_space();
    t = {0, 0};
    if (take('.')) {
      Text b = p_;
      while (p_ < end_ && (alpha(*p_) || digit(*p_)))
        ++p_;
      t.kind = 1;
      if (p_ - b == 1) {
        const char *names = "XYZT";
        const char *c = strchr(names, upper(*b));
        if (c) {
          t.index = uint8_t(c - names);
          return;
        }
      }
      if (p_ - b == 2 && upper(*b) == 'R') {
        char c = upper(b[1]);
        int n = digit(c) ? c - '0' : c - 'A' + 10;
        if (n >= 0 && n <= 15) {
          if (n == 15) {
            requires_rf_ = true;
            if (!rf_)
              fail(E::REGISTER);
          }
          t.index = uint8_t(4 + n);
          return;
        }
      }
      fail(E::REGISTER);
      return;
    }
    if (p_ == end_ || !alpha(*p_)) {
      fail(E::VARIABLE);
      return;
    }
    t.index = uint8_t(upper(*p_++) - 'A');
    if (p_ < end_ && (alpha(*p_) || digit(*p_))) {
      fail(E::VARIABLE);
      return;
    }
    if (take('(')) {
      t.kind = 2;
      expression();
      if (take(','))
        expression();
      else
        constant(0);
      expect(')');
      op(Op::ARRAY_CELL, -1);
      byte(t.index);
    }
  }
  void store(Target t) {
    op(t.kind == 0   ? Op::STORE
       : t.kind == 1 ? Op::STORE_REF
                     : Op::STORE_ARRAY,
       t.kind == 2 ? -2 : -1);
    if (t.kind < 2)
      byte(t.index);
  }
  void load(Target t) {
    op(t.kind == 0   ? Op::LOAD
       : t.kind == 1 ? Op::LOAD_REF
                     : Op::LOAD_ARRAY,
       t.kind == 2 ? 0 : 1);
    if (t.kind < 2)
      byte(t.index);
  }
  void call(bool function) {
    Address a;
    if (!label(a))
      return;
    unsigned count = 0;
    while (take(',')) {
      if (count++ == 4) {
        fail(E::STACK);
        return;
      }
      expression();
    }
    has_calls_ = true;
    op(Op::CALL_PARAMS, int(function) - int(count));
    emit_address(label_pc(a));
    emit_address(label_end(a) | (a.exact?0:Paged?0x80000000U:0x8000U));
    byte(uint8_t(count));
    byte(uint8_t(function));
  }
  void primary() {
    skip_space();
    if (error_ != E::NONE)
      return;
    if (take('(')) {
      expression();
      expect(')');
      return;
    }
    if (p_ < end_ && *p_ == '.' && p_ + 1 < end_ && alpha(p_[1])) {
      Target t;
      target(t);
      load(t);
      return;
    }
    if (p_ < end_ && alpha(*p_)) {
      Text b = p_;
      while (p_ < end_ && alpha(*p_))
        ++p_;
      if (p_ - b == 1) {
        p_ = b;
        Target t;
        target(t);
        load(t);
        return;
      }
      unsigned id = 255;
      for (const auto &f : functions)
        if (equal(b, p_, f.name)) {
          id = f.id;
          break;
        }
      if (id == 255) {
        fail(E::FUNCTION);
        return;
      }
      Function fn = Function(id);
      if (fn == Function::GW || fn == Function::GH) {
        op(Op::FUNCTION, 1);
        byte(uint8_t(fn == Function::GW ? language_vm::Function::GW
                                       : language_vm::Function::GH));
        return;
      }
      if (graph_expression_ && (fn == Function::CALL || fn == Function::RND)) {
        fail(E::FUNCTION);
        return;
      }
      if (fn == Function::PI_VALUE) {
        op(Op::FUNCTION, 1);
        byte(uint8_t(language_vm::Function::PI_VALUE));
        return;
      }
      expect('(');
      if (fn == Function::CALL) {
        if (Expression) {
          fail(E::FUNCTION);
          return;
        }
        call(true);
        expect(')');
        return;
      }
      if (fn == Function::ARG) {
        if (Expression) {
          fail(E::FUNCTION);
          return;
        }
        expression();
        expect(')');
        op(Op::LOAD_PARAMETER);
        return;
      }
      if (fn == Function::RND) {
        expect(')');
        op(Op::FUNCTION, 1);
        byte(uint8_t(language_vm::Function::RND));
        return;
      }
      if (fn == Function::POINT) {
        expression();
        expect(',');
        expression();
        expect(')');
        op(Op::GRAPHICS, -1);
        byte(uint8_t(basic_graphics::Operation::POINT));
        byte(2);
        return;
      }
      expression();
      if (fn == Function::MIN)
        op(Op::NEG);
      bool binary =
          fn == Function::MAX || fn == Function::MIN || fn == Function::MOD;
      if (binary) {
        expect(',');
        expression();
        if (fn == Function::MIN)
          op(Op::NEG);
      }
      expect(')');
      if (fn == Function::MOD) {
        op(Op::MOD, -1);
        return;
      }
      if (fn == Function::MIN) {
        op(Op::FUNCTION, -1);
        byte(uint8_t(language_vm::Function::MAX));
        op(Op::NEG);
        return;
      }
      op(Op::FUNCTION, binary ? -1 : 0);
      byte(uint8_t(fn));
    } else {
      Text start = p_;
      while (p_ < end_ && digit(*p_))
        ++p_;
      if (p_ < end_ && *p_ == '.') {
        ++p_;
        while (p_ < end_ && digit(*p_))
          ++p_;
      }
      if (p_ == start || (p_ - start == 1 && *start == '.')) {
        fail(E::SYNTAX);
        return;
      }
      if (p_ < end_ && upper(*p_) == 'E') {
        ++p_;
        if (p_ < end_ && (*p_ == '+' || *p_ == '-'))
          ++p_;
        Text exponent = p_;
        while (p_ < end_ && digit(*p_))
          ++p_;
        if (p_ == exponent) {
          fail(E::SYNTAX);
          return;
        }
      }
      char number[64];
      unsigned n = unsigned(p_ - start);
      if (n >= sizeof(number)) {
        fail(E::FULL);
        return;
      }
      start.copy(number,n);
      number[n] = 0;
      const char *after = nullptr;
      double value = mk_math::strtod(number, &after);
      if (after != number + n) {
        fail(E::SYNTAX);
        return;
      }
      constant(value);
    }
  }
  void unary() {
    if (++depth_ > 32) {
      fail(E::STACK);
      --depth_;
      return;
    }
    if (take('-')) {
      unary();
      op(Op::NEG);
    } else if (take('+'))
      unary();
    else
      primary();
    --depth_;
  }
  void power() {
    unary();
    if (take('^')) {
      if (++depth_ > 32)
        fail(E::STACK);
      else {
        power();
        op(Op::POW, -1);
      }
      --depth_;
    }
  }
  void product() {
    power();
    while (error_ == E::NONE) {
      if (take('*')) {
        power();
        op(Op::MUL, -1);
      } else if (take('/')) {
        power();
        op(Op::DIV, -1);
      } else
        break;
    }
  }
  void expression() {
    if (++depth_ > 32) {
      fail(E::STACK);
      --depth_;
      return;
    }
    product();
    while (error_ == E::NONE) {
      if (take('+')) {
        product();
        op(Op::ADD, -1);
      } else if (take('-')) {
        product();
        op(Op::SUB, -1);
      } else
        break;
    }
    --depth_;
  }
  void literal(Text &b, unsigned &n) {
    char quote = *p_++;
    b = p_;
    while (p_ < end_ && *p_ != quote)
      ++p_;
    n = unsigned(p_ - b);
    if (p_ == end_)
      fail(E::UNTERMINATED_STRING);
    else
      ++p_;
  }
  uint8_t resource_byte(const Resource &r, unsigned i) const {
    return i < r.length ? uint8_t(source_[r.begin + i]) : uint8_t(':');
  }
  uint16_t intern(Text b, unsigned n, bool colon) {
    if(owned() && (n+colon>language_vm::MAX_MODULE-2U ||
        resource_bytes_>language_vm::MAX_MODULE-2U-n-colon)) {fail(E::FULL);return 0;}
    Resource r = {uint16_t(b - source_), uint16_t(n), resource_bytes_, colon};
    for (unsigned i = 0; i < resource_count_; ++i) {
      const auto &candidate = resources_table_[i];
      const unsigned length = candidate.length + candidate.colon;
      if (length != n + colon)
        continue;
      const unsigned common = candidate.length < n ? candidate.length : n;
      if (language_vm::source::equal(source_ + candidate.begin, b, common) &&
          (candidate.length == n || resource_byte(candidate, common) == resource_byte(r, common)))
        return candidate.offset;
    }
    if (pass_ || resource_count_ == 256) {
      fail(E::FULL);
      return 0;
    }
    resources_table_[resource_count_++] = r;
    const unsigned parts = (n + 254) / 255 + colon;
    resource_bytes_ =
        uint16_t(resource_bytes_ + (owned() ? 2 + n + colon : 3 + parts * 3));
    return r.offset;
  }
  void text(Op code, Text b, unsigned n, bool colon = false) {
    if (resources_) {
      do {
        const unsigned count=n>4096?4096:n;
        const auto resource = intern(b,count,colon && count==n);
        op(code == Op::READ_INPUT ? Op::INPUT_RESOURCE : Op::PRINT_RESOURCE);
        emit_word(resource);b+=count;n-=count;
      } while(n && error_==E::NONE);
      return;
    }
    op(code);
    emit_word(uint16_t(n + colon));
    for (unsigned i = 0; i < n; ++i)
      byte(uint8_t(b[i]));
    if (colon)
      byte(':');
  }
  void emit_resources() {
    if (!resources_)
      return;
    pool_ = true;
    for (unsigned i = 0; i < resource_count_; ++i) {
      const auto &r = resources_table_[i];
      emit_word(uint16_t(r.length + r.colon));
      if (owned()) {
        for (unsigned n = 0; n < unsigned(r.length + r.colon); ++n)
          byte(resource_byte(r, n));
      } else {
        byte(uint8_t((r.length + 254) / 255 + r.colon));
        unsigned left = r.length, at = r.begin;
        while (left) {
          unsigned n = left < 255 ? left : 255;
          emit_word(uint16_t(at));
          byte(uint8_t(n));
          at += n;
          left -= n;
        }
        if (r.colon) {
          emit_word(':');
          byte(0);
        }
      }
    }
    pool_ = false;
  }
  void output(bool input) {
    skip_space();
    if (p_ == end_) {
      op(input ? Op::WAIT : Op::PRINT_FLUSH);
      return;
    }
    if (!input) {
      op(Op::PRINT_BEGIN);
      Text after = p_;
      while (after < end_ && alpha(*after))
        ++after;
      if (equal(p_, after, "AT")) {
        p_ = after;
        expression();
        expect(',');
        expression();
        expect(',');
        op(Op::PRINT_AT, -2);
        skip_space();
        if (p_ == end_)
          fail(E::SYNTAX);
      }
    }
    Text prompt = nullptr;
    unsigned prompt_len = 0;
    bool target_seen = false;
    while (p_ < end_ && error_ == E::NONE) {
      if (*p_ == '"' || *p_ == '\'') {
        Text b;
        unsigned n;
        literal(b, n);
        if (input) {
          if (prompt) {
            fail(E::SYNTAX);
            return;
          }
          prompt = b;
          prompt_len = n;
          if (n > 95)
            fail(E::FULL);
        } else
          text(Op::PRINT_TEXT, b, n);
      } else if (!input && take('!'))
        op(Op::PRINT_FLUSH);
      else if (!input && take('%')) {
        unsigned width = 0, precision = 8;
        if (p_ < end_ && digit(*p_)) {
          do {
            width = width * 10 + unsigned(*p_++ - '0');
            if (width > 64)
              fail(E::FORMAT);
          } while (p_ < end_ && digit(*p_) && error_ == E::NONE);
          expect('.');
          precision = 0;
          if (p_ == end_ || !digit(*p_))
            fail(E::FORMAT);
          while (p_ < end_ && digit(*p_) && error_ == E::NONE) {
            precision = precision * 10 + unsigned(*p_++ - '0');
            if (precision > 15)
              fail(E::FORMAT);
          }
          if (!precision)
            fail(E::FORMAT);
        }
        op(Op::PRINT_PRECISION);
        byte(uint8_t(width));
        byte(uint8_t(precision));
        skip_space();
        if (p_ < end_ && *p_ != ',')
          continue;
      } else if (input) {
        Target t;
        Text b = p_;
        target(t);
        target_seen = true;
        if (t.kind == 1) {
          op(Op::TARGET_REF);
          byte(t.index);
        }
        if (t.kind == 2)
          op(Op::TARGET_ARRAY);
        if (prompt)
          text(Op::READ_INPUT, prompt, prompt_len);
        else {
          unsigned n = unsigned(p_ - b);
          if (n > 94)
            n = 0;
          text(Op::READ_INPUT, b, n, true);
        }
        // READ_INPUT pushes the value after its variable-length literal.
        ++sp_;
        if (sp_ > maximum_)
          maximum_ = sp_;
        store(t);
        prompt = nullptr;
        prompt_len = 0;
      } else {
        expression();
        op(Op::PRINT_NUMBER, -1);
      }
      skip_space();
      if (p_ == end_)
        break;
      expect(',');
      skip_space();
      if (p_ == end_)
        fail(E::SYNTAX);
    }
    if (input) {
      if (!target_seen || prompt)
        fail(E::VARIABLE);
    } else {
      op(Op::PRINT_END);
      byte(0);
    }
  }
  void graphics(basic_graphics::Operation operation) {
    uint8_t count = 0;
    skip_space();
    while (p_ < end_ && error_ == E::NONE) {
      if (count == basic_graphics::maximum(operation)) {
        fail(E::SYNTAX);
        return;
      }
      expression();
      ++count;
      skip_space();
      if (p_ == end_)
        break;
      expect(',');
      skip_space();
      if (p_ == end_)
        fail(E::SYNTAX);
    }
    if (count < basic_graphics::minimum(operation))
      fail(E::SYNTAX);
    op(Op::GRAPHICS, -count);
    byte(uint8_t(operation));
    byte(count);
  }
  void graph() {
    Text begin = p_, comma = delimiter(p_, end_, ',');
    if (comma == end_) {
      fail(E::SYNTAX);
      return;
    }
    Text end = end_;
    p_ = comma + 1;
    for (unsigned i = 0; i < 4; ++i) {
      expression();
      if (i < 3)
        expect(',');
    }
    skip_space();
    if (p_ != end_) {
      fail(E::SYNTAX);
      return;
    }
    op(Op::GRAPH_BEGIN, -4);
    const uint32_t patch = pc_;
    emit_address(0);
    const uint32_t body = pc_;
    p_ = begin;
    end_ = comma;
    graph_expression_ = true;
    expression();
    graph_expression_ = false;
    skip_space();
    if (p_ != end_)
      fail(E::SYNTAX);
    const uint32_t next = pc_;
    op(Op::GRAPH_NEXT, -1);
    emit_address(body);
    patch_address(patch,next);
    p_ = end_ = end;
  }
  void branch() {
    expect('(');
    expression();
    expect(')');
    const uint32_t missing=Paged?UINT32_MAX:0xFFFF;
    uint32_t targets[3] = {missing,missing,missing};
    for (unsigned i = 0; i < 3 && error_ == E::NONE; ++i) {
      skip_space();
      if (p_ < end_ && *p_ != ',') {
        Address a;
        if (!label(a))
          return;
        if (!a.exact) {
          fail(E::LINE);
          return;
        }
        targets[i] = label_pc(a);
      }
      skip_space();
      if (i < 2 && p_ < end_)
        expect(',');
    }
    op(Op::BRANCH, -1);
    for (auto t : targets)
      emit_address(t);
  }
  bool update_local(Target t) {
#if !defined(LANGUAGE_VM_TEST_NO_FUSION)
    if (t.kind)
      return false;
    Text saved = p_;
    skip_space();
    if (p_ == end_ || upper(*p_) != char('A' + t.index)) {
      p_ = saved;
      return false;
    }
    ++p_;
    skip_space();
    if (p_ == end_ || (*p_ != '+' && *p_ != '-')) {
      p_ = saved;
      return false;
    }
    bool subtract = *p_++ == '-';
    skip_space();
    uint8_t rhs = 0;
    if (p_ < end_ && alpha(*p_)) {
      rhs = uint8_t(0x40 | uint8_t(upper(*p_++) - 'A'));
    } else {
      unsigned n = 0;
      bool any = false;
      while (p_ < end_ && digit(*p_)) {
        any = true;
        n = n * 10 + unsigned(*p_++ - '0');
        if (n > 63) {
          p_ = saved;
          return false;
        }
      }
      if (!any) {
        p_ = saved;
        return false;
      }
      rhs = uint8_t(n);
    }
    skip_space();
    if (p_ != end_) {
      p_ = saved;
      return false;
    }
    op(Op::UPDATE_LOCAL);
    byte(t.index);
    byte(uint8_t(rhs | (subtract ? 0x80 : 0)));
    return true;
#else
    (void)t;
    return false;
#endif
  }
  void statement(Command c) {
    switch (c) {
    case Command::COMMENT:
      p_ = end_;
      break;
    case Command::SET: {
      Target t;
      target(t);
      expect('=');
      if (!update_local(t)) {
        expression();
        store(t);
      }
      break;
    }
    case Command::ASK:
      output(true);
      break;
    case Command::PRINT:
      output(false);
      break;
    case Command::IF:
      branch();
      break;
    case Command::GOTO: {
      Address a;
      if (!label(a))
        return;
      if (!a.exact) {
        fail(E::LINE);
        return;
      }
      op(Op::JUMP);
      emit_address(label_pc(a));
      break;
    }
    case Command::DO:
      call(false);
      break;
    case Command::RETURN:
      skip_space();
      if (p_ < end_) {
        expression();
        op(Op::RETURN_VALUE, -1);
      } else
        op(Op::RETURN);
      break;
    case Command::EXIT:
      op(Op::HALT);
      break;
    case Command::CLS:
      op(Op::CLEAR);
      break;
    case Command::PSET: graphics(basic_graphics::Operation::PSET); break;
    case Command::LINE: graphics(basic_graphics::Operation::LINE); break;
    case Command::BOX: graphics(basic_graphics::Operation::BOX); break;
    case Command::CIRCLE: graphics(basic_graphics::Operation::CIRCLE); break;
    case Command::SHOW: graphics(basic_graphics::Operation::SHOW); break;
    case Command::GRAPH: graph(); break;
    case Command::EXEC:
      expression();
      op(Op::DROP, -1);
      break;
    default:
      fail(E::UNKNOWN_COMMAND);
      break;
    }
  }
  void commands_list(unsigned depth) {
    if (depth >= 16) {
      fail(E::STACK);
      return;
    }
    while (error_ == E::NONE && p_ < end_) {
      skip_space();
      if (p_ == end_)
        break;
      Text at = p_;
      Command c = command(p_, end_);
      skip_space();
      if (c == Command::NONE) {
        fail(E::UNKNOWN_COMMAND);
        return;
      }
      Text line = at;
      while (line > source_ && line[-1] != '\r' && line[-1] != '\n')
        --line;
      op(Op::SOURCE_POS);
      emit_word(uint16_t(at - line + 1));
      if (c == Command::FOR) {
        Target t;
        target(t);
        if (t.kind) {
          fail(E::FOR);
          return;
        }
        expect('=');
        expression();
        expect(',');
        expression();
        bool three = take(',');
        if (three)
          expression();
        else
          constant(1);
        expect(';');
        skip_space();
        if (p_ == end_) {
          fail(E::FOR);
          return;
        }
        op(Op::FOR_FOCAL, -3);
        byte(t.index);
        uint32_t patch = pc_;
        emit_address(0);
        byte(three ? 1 : 0);
        commands_list(depth + 1);
        op(Op::NEXT_FOCAL);
        patch_address(patch,pc_);
        return;
      }
      Text saved = end_;
      end_ = c == Command::COMMENT ? saved : delimiter(p_, saved, ';');
      statement(c);
      skip_space();
      if (p_ != end_)
        fail(E::SYNTAX);
      p_ = end_;
      end_ = saved;
      if (p_ < end_) {
        ++p_;
        skip_space();
      }
    }
  }
  bool index_lines() {
    if(Paged) {count_=flash_->count();return true;}
    Text e = source_ + length_;
    p_ = source_;
    while (p_ < e && error_ == E::NONE) {
      Text line_end = p_ + p_.line_end(e);
      end_ = line_end;
      skip_space();
      if (p_ < end_) {
        Address a;
        if (!label(a))
          return false;
        if (!a.exact || p_ == end_ || !space(*p_)) {
          fail(E::LINE);
          return false;
        }
        skip_space();
        if (count_ == 80) {
          fail(E::FULL);
          return false;
        }
        unsigned pos = count_;
        while (pos && line_at(pos - 1).number > key(a))
          --pos;
        if ((pos < count_ && line_at(pos).number == key(a)) ||
            (pos && line_at(pos - 1).number == key(a))) {
          fail(E::LINE);
          return false;
        }
        for (unsigned i = count_; i > pos; --i)
          lines_[i] = lines_[i - 1];
        lines_[pos] = {key(a), uint16_t(p_ - source_),
                       uint16_t(line_end - source_), 0};
        ++count_;
      }
      p_ = line_end + (line_end < e);
    }
    if (!count_)
      fail(E::LINE);
    return error_ == E::NONE;
  }
  static void put16(uint8_t *p, uint16_t v) {
    p[0] = uint8_t(v);
    p[1] = uint8_t(v >> 8);
  }
  static void put32(uint8_t *p, uint32_t v) {
    put16(p, uint16_t(v));
    put16(p + 2, uint16_t(v >> 16));
  }

public:
  Compiler(const language_vm::source::Reader& input, uint16_t n, uint8_t *out, uint32_t cap, bool rf,
           const language_vm::ResourceSource *resources, Line *lines,
           Resource *table, language_vm::flash::Program* flash=nullptr)
      : source_(input), p_(input), end_(input), input_(&input), resources_(resources), output_(out),
        length_(n), capacity_(cap), pc_(0), lines_(lines), flash_(flash), rf_(rf) {
    resources_table_ = table;
  }
  bool valid_fragment() {
    if (!source_ || !length_ || length_ > 111)
      return false;
    p_ = source_;
    end_ = source_ + length_;
    pc_ = language_vm::HEADER_SIZE;
    expression();
    skip_space();
    return error_ == E::NONE && p_ == end_ && sp_ == 1;
  }
  language_vm::CompileResult compile() {
    if (!source_ || !length_ || length_ > (Expression ? 64 : language_vm::source::MAX_SIZE) ||
        (!Paged && input_->contains_nul()))
      return {length_>language_vm::source::MAX_SIZE?E::FULL:!input_->good()?E::IO:E::SYNTAX, 0, 0, 0, 0};
    if (!Expression)
      index_lines();
    const uint32_t code = language_vm::HEADER_SIZE + uint32_t(count_) * (Paged?8U:6U);
    for (pass_ = 0; pass_ < 2 && error_ == E::NONE; ++pass_) {
      if(pass_ && Paged && !flash_->begin_image()) {fail(E::IO);break;}
      pc_ = code;
      sp_ = maximum_ = depth_ = 0;
      if (Expression) {
        p_ = source_;
        end_ = source_ + length_;
        expression();
        skip_space();
        if (p_ != end_)
          fail(E::SYNTAX);
      } else
        for (unsigned i = 0; i < count_ && error_ == E::NONE; ++i) {
          if (!pass_)set_line_pc(uint16_t(i),pc_);
          p_ = source_ + line_at(i).begin;
          end_ = source_ + line_at(i).end;
          commands_list(0);
          if (sp_)
            fail(E::STACK);
          op(Op::LINE);
        }
      if (!pass_)
        image_halt_ = pc_;
      op(Op::HALT);
    }
    const uint32_t code_end = pc_;
    if (error_ == E::NONE)
      emit_resources();
    if(Paged) {
      if(error_==E::NONE && !flash_->finish(language_vm::Language::FOCAL,pc_,has_calls_?language_vm::MAX_STACK:maximum_,requires_rf_))error_=E::IO;
      if(flash_->error()!=E::NONE)error_=flash_->error();
    }
    if (error_ == E::NONE && output_) {
      memset(output_, 0, language_vm::HEADER_SIZE);
      memcpy(output_, "LBV1", 4);
      output_[4] = uint8_t(language_vm::VERSION);
      output_[5] = uint8_t(language_vm::Language::FOCAL);
      output_[6] = has_calls_ ? language_vm::MAX_STACK
                   : maximum_ ? maximum_
                              : 1;
      output_[7] = uint8_t(Expression) | (requires_rf_ ? 2 : 0) |
                   (resource_count_
                        ? language_vm::RESOURCE_FLAG |
                              (owned() ? language_vm::OWNED_RESOURCE_FLAG : 0)
                        : 0);
      if (resource_count_) {
        put16(output_ + 30, code_end);
        if (!owned()) {
          put16(output_ + 24, resources_->id);
          put32(output_ + 26, resources_->revision);
        }
      }
      put16(output_ + 8, pc_);
      put16(output_ + 10, code);
      put16(output_ + 12, count_);
      put16(output_ + 14, length_);
      put32(output_ + 16,
            input_->checksum());
      for (unsigned i = 0; i < count_; ++i) {
        auto *r = output_ + language_vm::HEADER_SIZE + i * 6;
        put32(r, line_at(i).number);
        put16(r + 4, line_at(i).pc);
      }
      if constexpr (!Expression)language_vm::mark_integer_spans(output_,code,code_end);
      put32(output_ + 20,
            language_vm::checksum(output_ + language_vm::HEADER_SIZE,
                                  pc_ - language_vm::HEADER_SIZE));
    }
    if(!input_->good()) error_=E::IO;
    return {error_, error_ == E::NONE ? pc_ : uint16_t(0), 0, offset_,
            uint8_t(has_calls_ ? language_vm::MAX_STACK
                    : maximum_ ? maximum_
                               : 1)};
  }
};
inline language_vm::CompileResult compile_flash_program(const language_vm::source::Reader& source,
    language_vm::flash::Program& program,bool rf) {
  language_vm::source::CursorScope scope(source);
  Compiler<false,true> compiler(source,source.size(),nullptr,UINT32_MAX,rf,nullptr,nullptr,nullptr,&program);
  return compiler.compile();
}
inline language_vm::CompileResult
compile_program(const language_vm::source::Reader& source, uint16_t length, uint8_t *output,
                uint16_t capacity, bool rf,
                const language_vm::ResourceSource *resources = nullptr) {
  language_vm::source::CursorScope cursor_scope(source);
  Compiler<false>::Line lines[80];
  Compiler<false>::Resource table[256];
  Compiler<false> compiler(source, length, output, capacity, rf, resources,
                           lines, table);
  return compiler.compile();
}
inline language_vm::CompileResult compile_expression(const char *source,
                                                     uint16_t length,
                                                     uint8_t *output,
                                                     uint16_t capacity) {
  language_vm::source::Reader input(source,length);
  language_vm::source::CursorScope cursor_scope(input);
  Compiler<true> compiler(input, length, output, capacity, true, nullptr,
                          nullptr, nullptr);
  return compiler.compile();
}
inline bool valid_fragment(const char *source, uint16_t length, bool rf) {
  language_vm::source::Reader input(source,length);
  language_vm::source::CursorScope cursor_scope(input);
  Compiler<false> compiler(input, length, nullptr, language_vm::MAX_IMAGE, rf,
                           nullptr, nullptr, nullptr);
  return compiler.valid_fragment();
}
} // namespace focal_next
#endif
