#include "mk61_ai_spec.hpp"
#include <cstdarg>
#include <cstdio>
#include <cstring>

namespace mk61ai {
namespace {
bool word(unsigned char c) {
  return c >= 128 || (c >= 'A' && c <= 'Z') || (c >= 'a' && c <= 'z') ||
         (c >= '0' && c <= '9') || c == '_';
}
bool digit(char c) { return c >= '0' && c <= '9'; }
bool canonical(const char *s, unsigned n, char *out) {
  if (!n || n >= 24)
    return false;
  bool negative = *s == '-';
  if (*s == '+' || *s == '-') {
    ++s;
    --n;
  }
  unsigned dot = 0;
  while (dot < n && s[dot] != '.')
    ++dot;
  unsigned begin = 0, end = n;
  while (begin < dot && s[begin] == '0')
    ++begin;
  if (dot < n) {
    while (end > dot + 1 && s[end - 1] == '0')
      --end;
    if (end == dot + 1)
      end = dot;
  }
  if (begin == dot && end == dot) {
    std::strcpy(out, "0");
    return true;
  }
  unsigned at = 0;
  auto put = [&](char c) { if (at+1>=24) return false; out[at++]=c; return true; };
  if (negative && !put('-')) return false;
  if (begin == dot && !put('0')) return false;
  for (unsigned i = begin; i < end; ++i)
    if(!put(s[i])) return false;
  out[at] = 0;
  return true;
}
bool emit(Program &p, unsigned byte) {
  if (p.size == PROGRAM_SIZE)
    return false;
  p.bytes[p.size++] = std::uint8_t(byte);
  return true;
}
bool literal(Program &p, const char *s) {
  const bool negative = *s == '-';
  if (negative)
    ++s;
  if (std::strlen(s) > 18 || !emit(p, 0x0e) || !emit(p, 0x0d))
    return false;
  for (; *s; ++s)
    if (!emit(p, *s == '.' ? 0x0a : unsigned(*s - '0')))
      return false;
  return !negative || emit(p, 0x0b);
}
} // namespace
bool SpecProtocol::add(const char *s) {
  for (unsigned i = 0; i < count_; ++i)
    if (!std::strcmp(pool_[i], s))
      return true;
  if (count_ == 64 || std::strlen(s) >= sizeof(pool_[0]))
    return false;
  std::strcpy(pool_[count_++], s);
  return true;
}
bool SpecProtocol::collect(const char *task) {
  char normal[1025];
  unsigned length = 0;
  for (const char *p = task; *p;) {
    if (length + 1 >= sizeof(normal))
      return false;
    if (!std::strncmp(p, "−", 3)) {
      normal[length++] = '-';
      p += 3;
    } else
      normal[length++] = *p++;
  }
  normal[length] = 0;
  task = normal;
  static const char *const base[] = {"0",   "1", "-1",  "-2", "0.25", "0.5",
                                     "1.5", "2", "2.5", "3",  "4",    "10"};
  count_ = 0;
  for (const auto s : base)
    if (!add(s))
      return false;
  // This is literal extraction, not interpretation of an expression. Match
  // the training pool's ordering, decimal normalization and sign counterparts.
  const char *p = task;
  while (*p) {
    if ((!std::strncmp(p, "МК", 4) || !std::strncmp(p, "мк", 4)) &&
        (!std::strncmp(p + 4, "-61", 3) || !std::strncmp(p + 4, "61", 2))) {
      p += p[4] == '-' ? 7 : 6;
      continue;
    }
    const char *start = p;
    if ((p == task || !word(static_cast<unsigned char>(p[-1]))) &&
        (digit(*p) || *p == '.' || *p == '+' || *p == '-')) {
      if (*p == '+' || *p == '-')
        ++p;
      unsigned digits = 0;
      while (digit(*p)) {
        ++p;
        ++digits;
      }
      if (*p == '.') {
        ++p;
        while (digit(*p)) {
          ++p;
          ++digits;
        }
      }
      if (digits && !word(static_cast<unsigned char>(*p))) {
        char value[24];
        if (!canonical(start, unsigned(p - start), value) || !add(value))
          return false;
        continue;
      }
    }
    p = start + 1;
  }
  // Explicit literals that are already in base also receive their counterpart.
  // Re-scan source order rather than appending unused opposites of every base
  // item.
  p = task;
  while (*p) {
    if ((!std::strncmp(p, "МК", 4) || !std::strncmp(p, "мк", 4)) &&
        (!std::strncmp(p + 4, "-61", 3) || !std::strncmp(p + 4, "61", 2))) {
      p += p[4] == '-' ? 7 : 6;
      continue;
    }
    const char *start = p;
    if ((p == task || !word(static_cast<unsigned char>(p[-1]))) &&
        (digit(*p) || *p == '.' || *p == '+' || *p == '-')) {
      if (*p == '+' || *p == '-')
        ++p;
      unsigned digits = 0;
      while (digit(*p)) {
        ++p;
        ++digits;
      }
      if (*p == '.') {
        ++p;
        while (digit(*p)) {
          ++p;
          ++digits;
        }
      }
      if (digits && !word(static_cast<unsigned char>(*p))) {
        char value[24], opposite[24];
        if (!canonical(start, unsigned(p - start), value))
          return false;
        if (!std::strcmp(value, "0"))
          std::strcpy(opposite, "0");
        else if (*value == '-')
          std::strcpy(opposite, value + 1);
        else {
          if (std::strlen(value) + 1 >= sizeof(opposite))
            return false;
          opposite[0] = '-';
          std::strcpy(opposite + 1, value);
        }
        if (!add(opposite))
          return false;
        continue;
      }
    }
    p = start + 1;
  }
  return true;
}
bool SpecProtocol::prompt(const char *task, unsigned angle, char *out,
                          unsigned cap) {
  reset();
  if (angle > 2 || !collect(task))
    return false;
  unsigned used = 0;
  auto append = [&](const char *format, ...) {
    if (used >= cap)
      return false;
    va_list args;
    va_start(args, format);
    const int n = std::vsnprintf(out + used, cap - used, format, args);
    va_end(args);
    if (n < 0 || unsigned(n) >= cap - used) {
      used = cap;
      return false;
    }
    used += unsigned(n);
    return true;
  };
  append(
      "МК-61: %s; 105 ячеек; R0–RE, стек X/Y/Z/T/X1. HEX+макросы FF00=байт FF, "
      "FF01kk=константа kk, FF02ll=метка ll, FF03ll=адрес метки ll.\n"
      "Вызовы: <write>SPEC</write><run/>, <run>номер теста HEX</run>, "
      "<trace/>, <done/>. Эмулятор сообщает фактическое состояние.\n"
      "DIAG: <diag>TT HH LL AA BB</diag>. TT: 00=верно, 01=операция, "
      "02=аргумент, 03=порядок. HH LL — первый индекс различия в текущем HEX; "
      "AA — текущий байт; BB — нужный байт. Для верного кода: 00 FF FF 00 00. "
      "Диагноз — гипотеза; исправляй WRITE и проверяй RUN.\nКонстанты: ",
      angle == 0   ? "DEG"
      : angle == 2 ? "GRAD"
                   : "RAD");
  for (unsigned i = 0; i < count_; ++i)
    append("%s%02X=%s", i ? ";" : "", i, pool_[i]);
  append("\nЗадача: %s\nЗаметки: Осталось действий: 12. Исправление: WRITE с "
         "компактной спецификацией SPEC. Проверяй результат по условию; "
         "stopped означает только останов. DONE заявляет решение. Если условие "
         "неполно или решение не найдено, UNSURE. \nАссистент: ",
         task);
  return used < cap;
}
bool SpecProtocol::allows(std::uint16_t token, const char *piece) const {
  // This grammar constrains wire syntax only, exactly as the research decoder.
  // It does not constrain the generated tree to a known answer.
  if (!action_)
    return token == WRITE;
  if (ended_)
    return false;
  if (token == END)
    return digits_ == 2 && size_ >= 2;
  if (!((token >= 18 && token <= 27) || (token >= 35 && token <= 40) ||
        token == 223 || token == 973 || token == 1007 || token == 1218 ||
        token == 1277 || token == 1503 || token == 1568))
    return false;
  if (!piece || !*piece)
    return false;
  unsigned digits = digits_, size = size_;
  for (const char *p = piece; *p; ++p) {
    if (*p == ' ') {
      if (digits != 2 || size >= sizeof(body_))
        return false;
      digits = 0;
      continue;
    }
    if (!((*p >= '0' && *p <= '9') || (*p >= 'A' && *p <= 'F')) ||
        digits >= 2 || size >= sizeof(body_))
      return false;
    if (++digits == 2)
      ++size;
  }
  return true;
}
bool SpecProtocol::accept(std::uint16_t token, const char *piece) {
  if (!allows(token, piece))
    return false;
  if (!action_) {
    action_ = true;
    return true;
  }
  if (token == END) {
    ended_ = true;
    return true;
  }
  for (const char *p = piece; *p; ++p) {
    if (*p == ' ') {
      digits_ = half_ = 0;
      continue;
    }
    half_ = half_ * 16 + unsigned(*p <= '9' ? *p - '0' : *p - 'A' + 10);
    if (++digits_ == 2)
      body_[size_++] = std::uint8_t(half_);
  }
  return true;
}
bool SpecProtocol::expression(unsigned &at, unsigned depth, unsigned &nodes,
                              Program &p) const {
  if (depth > 12 || nodes++ >= 31 || at >= size_)
    return false;
  const unsigned op = body_[at++];
  if (op <= 14)
    return emit(p, 0x60 + op);
  if (op == 0x10) {
    if (at >= size_ || body_[at] >= count_)
      return false;
    return literal(p, pool_[body_[at++]]);
  }
  if (op == 0x11)
    return emit(p, 0x20);
  static constexpr std::uint8_t unary[] = {0x0b, 0x15, 0x16, 0x17, 0x18, 0x19,
                                           0x1a, 0x1b, 0x1c, 0x1d, 0x1e, 0x21,
                                           0x22, 0x23, 0x31, 0x32, 0x34, 0x35};
  if (op >= 0x20 && op <= 0x31)
    return expression(at, depth + 1, nodes, p) && emit(p, unary[op - 0x20]);
  if (op < 0x40 || op > 0x44)
    return false;
  // Record the first subtree's emitted range; x^y needs exponent before base.
  const unsigned begin = p.size;
  if (!expression(at, depth + 1, nodes, p))
    return false;
  const unsigned middle = p.size;
  if (!expression(at, depth + 1, nodes, p))
    return false;
  if (op == 0x44) {
    std::uint8_t left[PROGRAM_SIZE];
    const unsigned n = middle - begin;
    std::memcpy(left, p.bytes + begin, n);
    std::memmove(p.bytes + begin, p.bytes + middle, p.size - middle);
    std::memcpy(p.bytes + p.size - n, left, n);
    return emit(p, 0x24) && emit(p, 0x14) && emit(p, 0x0d) && emit(p, 0x10);
  }
  return emit(p, 0x10 + op - 0x40);
}
bool SpecProtocol::compile(Program &p) const {
  p = {};
  if (!ended_ || size_ < 2 || (body_[0] != 0xff && body_[0] > 14))
    return false;
  unsigned at = 1, nodes = 0;
  if (!expression(at, 0, nodes, p) || at != size_)
    return false;
  if (body_[0] != 0xff && !emit(p, 0x40 + body_[0]))
    return false;
  return emit(p, 0x50);
}
} // namespace mk61ai
