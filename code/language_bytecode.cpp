#include "language_bytecode.hpp"
#include "tinybasic_syntax.hpp"

#include <string.h>

#include "mk_math.hpp"

namespace language_vm {
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
  uint16_t begin, end, pc;
};
struct Keyword {
  const char* text;
  uint8_t minimum, id;
};
// INPUT() is I/O, lowered to a dedicated opcode rather than a math callback.
static constexpr uint8_t KEY_INPUT_FUNCTION = 254;
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
  ON_CMD
};
const Keyword basic_commands[] = {{"REM", 3, REM},
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
    {"INPUT", 3, KEY_INPUT_FUNCTION},       {nullptr, 0, 0}};
struct ResourceWorkspace {
  uint8_t* first;
  uint8_t* second;
  uint16_t half;
  uint8_t* at(uint16_t offset) {
    return offset < half ? first + offset : second + offset - half;
  }
};
struct Target {
  uint8_t kind, index;
};  // 0 variable, 1 reference, 2 array

template <Language Lang>
class Compiler {
 public:
  Compiler(const char* source, uint16_t length, uint8_t* out, uint16_t capacity,
           Line* lines, bool rf_available = true, const ResourceSource* resources = nullptr, ResourceWorkspace workspace = {})
      : source_(source),
        length_(length),
        out_(out),
        capacity_(capacity),
        p_(source),
        end_(source),
        error_(Error::NONE),
        lines_(lines),
        count_(0),
        pc_(0),
        sp_(0),
        maximum_(0),
        depth_(0),
        line_(0),
        pass_(0),
        image_end_(0),
        rf_available_(rf_available),
        rf_required_(false),
        expression_only_(false), resources_(resources), resource_size_(0), resource_data_(workspace) {}

  CompileResult compile() {
    if (!source_) return {Error::SYNTAX, 0, 0, 0, 0};
    const uint16_t quota = basic() ? 3584 : 1536;
    if (length_ == 0 || length_ > quota || memchr(source_, 0, length_))
      return {length_ > quota ? Error::FULL : Error::SYNTAX, 0, 0, 0, 0};
    index_lines();
    if (!count_ && error_ == Error::NONE) fail(Error::LINE);
    const uint16_t code = (uint16_t)(HEADER_SIZE + count_ * stride());
    // Labels and instruction lengths are determined before emission; source
    // may be unordered and every forward reference gets its final offset.
    for (pass_ = 0; pass_ < 2 && error_ == Error::NONE; ++pass_) {
      pc_ = code;
      resource_size_ = 0;
      sp_ = maximum_ = depth_ = 0;
      for (line_ = 0; line_ < count_ && error_ == Error::NONE; ++line_) {
        if (!pass_) lines_[line_].pc = pc_;
        p_ = source_ + lines_[line_].begin;
        end_ = source_ + lines_[line_].end;
        if (basic())
          commands(0);
        else
          focal_statement(0);
        if (sp_ != 0 && error_ == Error::NONE) fail(Error::INVALID_IMAGE);
        emit(Op::LINE);
      }
      emit(Op::HALT);
      if (!pass_) image_end_ = (uint16_t)(pc_ - 1);
    }
    const uint16_t code_end = pc_;
    if (error_ == Error::NONE && resource_size_ && resource_data_.first) {
      if (pc_ > capacity_ || resource_size_ > capacity_ - pc_ ||
          resource_size_ > MAX_IMAGE - pc_) fail(Error::FULL);
      else {
        if (out_) {
          const uint16_t first = resource_size_ < resource_data_.half ? resource_size_ : resource_data_.half;
          memcpy(out_ + pc_, resource_data_.first, first);
          if (resource_size_ > first) memcpy(out_ + pc_ + first, resource_data_.second, resource_size_ - first);
        }
        pc_ += resource_size_;
      }
    }
    if (error_ == Error::NONE && out_) {
      memset(out_, 0, HEADER_SIZE);
      memcpy(out_, "LBV1", 4);
      out_[4] = (uint8_t)VERSION;
      out_[5] = (uint8_t)Lang;
      out_[6] = maximum_ ? maximum_ : 1;
      out_[7] = (rf_required_ ? 2 : 0) | (resource_size_ && resource_data_.first ? 4 : 0);
      if (resource_size_ && resource_data_.first) {
        put_word(out_ + 24, resources_->id);
        put_dword(out_ + 26, resources_->revision);
        put_word(out_ + 30, code_end);
      }
      put_word(out_ + 8, pc_);
      put_word(out_ + 10, code);
      put_word(out_ + 12, count_);
      put_word(out_ + 14, length_);
      put_dword(out_ + 16, checksum((const uint8_t*)source_, length_));
      for (uint16_t i = 0; i < count_; ++i) {
        uint8_t* record = out_ + HEADER_SIZE + i * stride();
        if (basic())
          put_word(record, (uint16_t)lines_[i].number);
        else
          put_dword(record, lines_[i].number);
        put_word(record + stride() - 2, lines_[i].pc);
      }
      put_dword(out_ + 20, checksum(out_ + HEADER_SIZE, pc_ - HEADER_SIZE));
    }
    uint16_t offset =
        p_ >= source_ && p_ <= source_ + length_ ? (uint16_t)(p_ - source_) : 0;
    return {error_, error_ == Error::NONE ? pc_ : (uint16_t)0, line_, offset, maximum_};
  }
  uint16_t resource_reservation() const { return resource_size_; }
  CompileResult expression_only() {
    expression_only_ = true;
    if (!source_ || !length_ || length_ > (basic() ? 64 : 111) ||
        memchr(source_, 0, length_))
      return {Error::SYNTAX, 0, 0, 0, 0};
    for (pass_ = 0; pass_ < 2 && error_ == Error::NONE; ++pass_) {
      p_ = source_;
      end_ = source_ + length_;
      pc_ = HEADER_SIZE;
      sp_ = maximum_ = depth_ = 0;
      expression();
      skip();
      if (p_ != end_) fail(Error::SYNTAX);
      emit(Op::HALT);
    }
    if (error_ == Error::NONE && out_) {
      memset(out_, 0, HEADER_SIZE);
      memcpy(out_, "LBV1", 4);
      out_[4] = VERSION;
      out_[5] = (uint8_t)Lang;
      out_[6] = maximum_;
      out_[7] = rf_required_ ? 3 : 1;
      put_word(out_ + 8, pc_);
      put_word(out_ + 10, HEADER_SIZE);
      put_word(out_ + 14, length_);
      put_dword(out_ + 16, checksum((const uint8_t*)source_, length_));
      put_dword(out_ + 20, checksum(out_ + HEADER_SIZE, pc_ - HEADER_SIZE));
    }
    return {error_, error_ == Error::NONE ? pc_ : (uint16_t)0, 0,
            (uint16_t)(p_ - source_), maximum_};
  }

 private:
  const char* source_;
  uint16_t length_;
  uint8_t* out_;
  uint16_t capacity_;
  const char* p_;
  const char* end_;
  Error error_;
  Line* lines_;
  uint16_t count_, pc_;
  uint8_t sp_, maximum_, depth_;
  uint16_t line_;
  uint8_t pass_;
  uint16_t image_end_;
  bool rf_available_, rf_required_, expression_only_;
  const ResourceSource* resources_;
  uint16_t resource_size_;
  ResourceWorkspace resource_data_;
  bool resource_literals() const { return resources_ && resources_->id != 0xFFFF; }
  uint16_t intern_resource(const char* text, uint16_t length) {
    if(!resource_data_.first) {
      // Sizing mode needs only an upper bound. Raw literal bytes are already
      // contiguous; synthesized prompts can need at most one span per byte.
      const uintptr_t begin = (uintptr_t)source_, at = (uintptr_t)text;
      const bool raw = at >= begin && at - begin <= length_;
      const uint16_t parts = raw ? (uint16_t)((length + 254) / 255) : length;
      resource_size_ += (uint16_t)(3 + parts * 3);
      return 0;
    }
    // Compare actual M8 bytes, including normalized INPUT prompts. PRINT and
    // INPUT share handles even if they spelled the same text differently.
    for (uint16_t at = 0; at < resource_size_;) {
      const uint8_t* r = resource_data_.at(at);
      uint16_t decoded = 0;
      bool same = (uint16_t)(r[0] | ((uint16_t)r[1] << 8)) == length;
      for (uint8_t i = 0; i < r[2]; ++i) {
        const uint8_t* part = resource_data_.at((uint16_t)(at + 3 + i * 3));
        const uint16_t offset = (uint16_t)(part[0] | ((uint16_t)part[1] << 8));
        const uint8_t n = part[2];
        if (same) {
          if (offset & 0x8000) same = (uint8_t)text[decoded] == (uint8_t)offset;
          else same = !memcmp(text + decoded, source_ + offset, n);
        }
        decoded += n;
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
      for (uint16_t pos = 0; pos < length_; ++pos) {
        uint16_t match = 0;
        while (match < wanted && pos + match < length_ &&
               source_[pos + match] == text[match]) ++match;
        if (match > n) { best = pos; n = (uint8_t)match; }
        if (match == wanted) break;
      }
      if (!n) { best = (uint16_t)(0x8000 | (uint8_t)*text); n = 1; }
      if (resource_size_ > resource_data_.half * 2 - 3 || *resource_data_.at((uint16_t)(at + 2)) == 255) {
        fail(Error::FULL); break;
      }
      put_word(resource_data_.at(resource_size_), best);
      *resource_data_.at((uint16_t)(resource_size_ + 2)) = n;
      resource_size_ += 3; ++*resource_data_.at((uint16_t)(at + 2));
      text += n; length -= n;
    }
    return at;
  }
  static constexpr bool basic() { return Lang == Language::BASIC; }
  uint8_t stride() const { return basic() ? 4 : 6; }
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
    if (pc_ >= capacity_ || pc_ >= MAX_IMAGE) {
      fail(Error::FULL);
      return;
    }
    if (pass_ && out_) out_[pc_] = v;
    ++pc_;
  }
  void emit(Op op) { byte((uint8_t)op); }
  void u16(uint16_t v) {
    byte((uint8_t)v);
    byte((uint8_t)(v >> 8));
  }
  void patch(uint16_t at, uint16_t v) {
    if (pass_ && out_ && at <= capacity_ && capacity_ - at >= 2) put_word(out_ + at, v);
  }
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
    emit(op);
    stack(effect);
  }
  void check() {
    if (!basic()) emit(Op::CHECK);
  }
  void constant(double value, const char* literal = nullptr,
                const char* finish = nullptr) {
    if (value >= 0 && value <= 15 && value == (int)value) {
      emit((Op)((uint8_t)Op::CONST_0 + (uint8_t)value));
    } else if (value >= -128 && value <= 127 && value == (int)value) {
      emit(Op::CONST_I8);
      byte((uint8_t)(int8_t)value);
    } else if (value >= -32768 && value <= 32767 && value == (int)value) {
      emit(Op::CONST_I16);
      u16((uint16_t)(int16_t)value);
    } else if (literal && decimal(value, literal, finish)) {
      // Exact decimal recipe avoids turning a three-byte .1 into F64+opcode.
    } else {
      emit(Op::CONST_F64);
      uint64_t bits = 0;
      memcpy(&bits, &value, sizeof(bits));
      for (uint8_t i = 0; i < 8; ++i) byte((uint8_t)(bits >> (i * 8)));
    }
    stack(1);
  }
  bool decimal(double value, const char* begin, const char* end) {
#if defined(LANGUAGE_VM_TEST_NO_DECIMAL_RECIPE)
    (void)value; (void)begin; (void)end;
    return false;
#else
    uint32_t mantissa = 0;
    int exponent = 0;
    bool fraction = false;
    const char* q = begin;
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
    const char* saved = p_;
    uint8_t n = 0;
    while (p_ < end_ && alpha(*p_)) {
      ++p_;
      ++n;
    }
    const bool dotted = p_ < end_ && *p_ == '.';
    if (dotted) ++p_;
    const size_t length = strlen(word);
    bool ok = n != 0 && (dotted ? n >= minimum && n <= length : n == length);
    for (uint8_t i = 0; ok && i < n; ++i) ok = upper(saved[i]) == word[i];
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
    const char* cursor = source_;
    while (cursor < source_ + length_ && error_ == Error::NONE) {
      while (cursor < source_ + length_ && (*cursor == '\r' || *cursor == '\n'))
        ++cursor;
      const char* begin = cursor;
      while (cursor < source_ + length_ && *cursor != '\r' && *cursor != '\n') ++cursor;
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
      while (at && lines_[at - 1].number > number) {
        lines_[at] = lines_[at - 1];
        --at;
      }
      if (at && lines_[at - 1].number == number) {
        fail(Error::LINE);
        break;
      }
      lines_[at] = {number, (uint16_t)(p_ - source_), (uint16_t)(end_ - source_), 0};
      ++count_;
    }
  }
  uint16_t target_pc(uint32_t number, bool group = false) {
    if (!pass_) return 0;
    for (uint16_t i = 0; i < count_; ++i)
      if (group ? lines_[i].number / 1000 == number / 1000 : lines_[i].number == number)
        return lines_[i].pc;
    return 0xFFFF;
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
    const char* target_start = p_;
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
    binary(0);
    emit(Op::CHECK);
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
      const char* saved = p_;
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
      check();
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
        check();
      }
      --depth_;
      return;
    }
    if (match('+'))
      prefix(power_operand);
    else if (match('-')) {
      prefix(power_operand);
      emit(Op::NEG);
      check();
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
    const char* primary_start = p_;
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
      check();
      return;
    }
    if (basic() && match('@')) {
      if (!match('(')) fail(Error::SYNTAX);
      binary(0);
      if (!match(')')) fail(Error::EXPECTED_PAREN);
      source_position(primary_start);
      emit(Op::LOAD_ARRAY);
      return;
    }
    if (digit(*p_) || *p_ == '.') {
      const char* after = nullptr;
      double value = 0;
#if defined(MK61_BUILD_PORTABLE_SYSTEM)
      if (!portable_system::parse_number(p_, value, after)) {
        fail(Error::SYNTAX);
        return;
      }
#else
      value = mk_math::strtod(p_, &after);
#endif
      if (after == p_ || after > end_) {
        fail(Error::SYNTAX);
        return;
      }
      const char* literal = p_;
      p_ = after;
      constant(value, literal, after);
      // Reject a non-finite BASIC numeric token before a comparison can turn
      // it into a finite boolean; intermediate arithmetic retains its checks.
      if(basic() && !mk_math::is_finite(value))emit(Op::CHECK);
      check();
      return;
    }
    if (alpha(*p_)) {
      const char* start = p_;
      const uint8_t fn = lookup(functions, 255);
      if (fn == 255) {
        p_ = start;
        const uint8_t var = (uint8_t)(upper(*p_++) - 'A');
        if (p_ < end_ && (alpha(*p_) || *p_ == '.')) {
          fail(Error::FUNCTION);
          return;
        }
        emit(Op::LOAD);
        byte(var);
        stack(1);
        check();
        return;
      }
      const Function f = (Function)fn;
      if (!basic() && f >= Function::SIZE) {
        fail(Error::FUNCTION);
        return;
      }
      if (fn == KEY_INPUT_FUNCTION) {
        if (!match('(') || !match(')') || expression_only_) {
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
      if (basic()) source_position(primary_start);
      emit(Op::FUNCTION);
      byte(f == Function::RND ? (uint8_t)Function::RND_LIMIT : fn);
      if (f == Function::MAX) stack(-1);
      check();
      return;
    }
    fail(Error::SYNTAX);
  }
  const char* command_end(const char* begin, bool print) {
    char quote = 0;
    int nesting = 0;
    const char* alternate = tinybasic_syntax::else_at(begin, end_);
    for (const char* q = begin; q < end_; ++q) {
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
      if (*q == ':') return q;
      if (*q == ';') {
        if (!print) return q;
        const char* saved = p_;
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
      const char* start = p_;
      while (p_ < end_ && *p_ != quote) ++p_;
      if (p_ == end_) {
        fail(Error::UNTERMINATED_STRING);
        return true;
      }
      if (resource_literals()) {
        emit(Op::PRINT_RESOURCE);
        u16(intern_resource(start, (uint16_t)(p_ - start)));
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
      expression();
      store(t);
      skip();
      if (!basic() || !match(',')) break;
      const char* saved = p_;
      const uint16_t save_pc = pc_;
      const uint8_t save_sp = sp_;
      const Error save_error = error_;
      Target next = target();
      if (error_ == Error::NONE && match('='))
        t = next;
      else {
        p_ = saved;
        pc_ = save_pc;
        sp_ = save_sp;
        error_ = save_error;
        if (t.kind != 0 || t.index == 25)
          fail(Error::VARIABLE);
        else
          ++t.index;
      }
    } while (error_ == Error::NONE);
  }
  void print() {
    emit(Op::PRINT_BEGIN);
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
      const bool carriage =
          basic() && (*p_ == '_' || (p_ + 1 < end_ && *p_ == '^' && upper(p_[1]) == 'M'));
      if (!basic() && match('!'))
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
    byte(separator ? 1 : 0);
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
      const char* name = p_;
      Target t = target();
      if (!custom) {
        while (name < p_ && space(*name)) ++name;
        const char* finish = p_;
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
  void source_position(const char* at) {
    if (!count_) return;  // INPUT expressions have no statement/source map.
    const char* line = at;
    while (line > source_ && line[-1] != '\n' && line[-1] != '\r') --line;
    emit(Op::SOURCE_POS);
    u16((uint16_t)(at - line + 1));
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
    const char* after = nullptr;
#if defined(MK61_BUILD_PORTABLE_SYSTEM)
    if (!portable_system::parse_number(p_, value, after)) {
      fail(Error::SYNTAX);
      return false;
    }
#else
    value = mk_math::strtod(p_, &after);
#endif
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
    const uint16_t count_at = pc_;
    u16(0);
    uint16_t count = 0;
    do {
      const char* literal=p_;
      while(literal<end_ && space(*literal)) ++literal;
      const bool negative=literal<end_ && *literal=='-';
      if(literal<end_ && (*literal=='+' || *literal=='-')) ++literal;
      while(literal<end_ && space(*literal)) ++literal;
      double value = 0;
      if (!data_literal(value)) break;
      const uint16_t before = pc_;
      constant(negative ? -value : value,literal,p_);
      if(negative) emit(Op::NEG);
      stack(-1);  // DATA literals occupy the image, never the execution stack.
      count = (uint16_t)(count + pc_ - before);
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
    const uint16_t count_at = pc_;
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
      const char* const command_start = p_;
      const uint8_t cmd = lookup(basic_commands, ASSIGN);
      if (cmd == REM) {
        p_ = end_;
        break;
      }
      if (cmd == ASSIGN && !tinybasic_syntax::word(command_start, end_, "LET", 1)) {
        const char* word = command_start;
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
        operation(Op::JUMP_FALSE, -1);
        const uint16_t patch_at = pc_;
        u16(0);
        skip();
        if (p_ == end_) fail(Error::SYNTAX);
        const char* full_end = end_;
        const char* after_else = nullptr;
        const char* alternate = tinybasic_syntax::else_at(p_, end_, &after_else);
        end_ = alternate;
        skip();
        if (p_ == end_) fail(Error::SYNTAX);
        commands((uint8_t)(nesting + 1));
        if (alternate < full_end) {
          emit(Op::JUMP);
          const uint16_t skip_else = pc_;
          u16(0);
          patch(patch_at, pc_);
          end_ = full_end;
          p_ = after_else;
          skip();
          if (p_ == end_) fail(Error::SYNTAX);
          commands((uint8_t)(nesting + 1));
          patch(skip_else, pc_);
        } else
          patch(patch_at, pc_);
        end_ = full_end;
        p_ = full_end;
        break;
      }
      const char* const full_end = end_;
      const char* const segment = command_end(p_, cmd == PRINT || cmd == READ_INPUT);
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
          expression();
          operation(cmd == GOTO_CMD ? Op::GOTO : Op::GOSUB, -1);
          if (cmd == GOTO_CMD && segment < full_end &&
              !tinybasic_syntax::word(segment, full_end, "ELSE", 2))
            fail(Error::SYNTAX);
          break;
        case RETURN_CMD:
          if (segment < full_end && !tinybasic_syntax::word(segment, full_end, "ELSE", 2))
            fail(Error::SYNTAX);
          emit(Op::RETURN);
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
    const char* begin = p_;
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
          u16(target_pc(number));
          if (i < 2 && !match(',')) fail(Error::LINE);
        }
        break;
      }
      case 5: {
        const char* start = p_;
        const uint32_t number = address(true);
        bool group = true;
        for (const char* q = start; q < p_; ++q)
          if (*q == '.') group = false;
        emit(Op::DO_FOCAL);
        u16(target_pc(number, group));
        uint16_t finish = 0xFFFF;
        if (pass_)
          for (uint16_t i = 0; i < count_; ++i)
            if (lines_[i].pc == target_pc(number, group)) {
              uint16_t j = (uint16_t)(i + 1);
              if (group)
                while (j < count_ && lines_[j].number / 1000 == number / 1000) ++j;
              finish = j < count_ ? lines_[j].pc : image_end_;
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
        const uint16_t after = pc_;
        u16(0);
        const uint16_t body = pc_;
        byte(0);  // patched below: operand order
        // Distinguish two/three expressions without reparsing literals.
        bool three = false;
        int nesting_count = 0;
        uint8_t commas = 0;
        for (const char* q = begin; q < p_; ++q) {
          if (*q == '(')
            ++nesting_count;
          else if (*q == ')')
            --nesting_count;
          else if (*q == ',' && !nesting_count)
            ++commas;
        }
        three = commas == 2;
        if (pass_ && out_ && body < capacity_) out_[body] = three ? 1 : 0;
        if (!match(';')) fail(Error::FOR);
        focal_statement((uint8_t)(nesting + 1));
        emit(Op::NEXT_FOCAL);
        patch(after, pc_);
        break;
      }
      case 8: {
        const uint32_t number = address(false);
        emit(Op::JUMP);
        u16(target_pc(number));
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
    const char* source, uint16_t length, uint8_t* output, uint16_t capacity,
    Line* lines, bool rf, const ResourceSource* resources, uint8_t* first) {
  uint8_t second[Half];
  Compiler<Lang> compiler(source, length, output, capacity, lines, rf, resources, {first, second, Half});
  return compiler.compile();
}
template<Language Lang, uint16_t Half>
__attribute__((noinline)) CompileResult compile_resource_first(
    const char* source, uint16_t length, uint8_t* output, uint16_t capacity,
    Line* lines, bool rf, const ResourceSource* resources) {
  uint8_t first[Half];
  return compile_resource_second<Lang, Half>(source, length, output, capacity, lines, rf, resources, first);
}
template<Language Lang>
CompileResult compile_resources(const char* source, uint16_t length, uint8_t* output,
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
CompileResult compile_basic(const char* source, uint16_t length, uint8_t* output,
                            uint16_t capacity, bool rf_available, const ResourceSource* resources) {
  if (capacity < HEADER_SIZE) return {Error::FULL, 0, 0, 0, 0};
  Line lines[192];
  Compiler<Language::BASIC> compiler(source, length, output, capacity, lines,
                                     rf_available, resources);
  const auto sized = compiler.compile();
  if(sized.error != Error::NONE || !compiler.resource_reservation()) return sized;
  return compile_resources<Language::BASIC>(source,length,output,capacity,lines,rf_available,
                                             resources,compiler.resource_reservation());
}
CompileResult compile_focal(const char* source, uint16_t length, uint8_t* output,
                            uint16_t capacity, bool rf_available, const ResourceSource* resources) {
  if (capacity < HEADER_SIZE) return {Error::FULL, 0, 0, 0, 0};
  Line lines[80];
  Compiler<Language::FOCAL> compiler(source, length, output, capacity, lines,
                                     rf_available, resources);
  const auto sized = compiler.compile();
  if(sized.error != Error::NONE || !compiler.resource_reservation()) return sized;
  return compile_resources<Language::FOCAL>(source,length,output,capacity,lines,rf_available,
                                             resources,compiler.resource_reservation());
}
CompileResult compile_expression(Language language, const char* source, uint16_t length,
                                 uint8_t* output, uint16_t capacity) {
  if (capacity < HEADER_SIZE) return {Error::FULL, 0, 0, 0, 0};
  if (language == Language::BASIC) {
    Compiler<Language::BASIC> compiler(source, length, output, capacity, nullptr);
    return compiler.expression_only();
  }
  if (language == Language::FOCAL) {
    Compiler<Language::FOCAL> compiler(source, length, output, capacity, nullptr);
    return compiler.expression_only();
  }
  return {Error::SYNTAX, 0, 0, 0, 0};
}

}  // namespace language_vm
