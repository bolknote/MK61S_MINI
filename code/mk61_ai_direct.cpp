#include "mk61_ai_direct.hpp"
#include "mk61_ai_spec.hpp"
#include "mk_math.hpp"
#if defined(PICO_ON_DEVICE)
#include "compact_math.hpp"
#endif
#include <algorithm>
#include <cmath>
#include <cstring>
#include <string_view>

namespace mk61ai {
namespace {
using Text = std::string_view;
constexpr unsigned bad = 0xff, constant = 0x10, pi = 0x11;
constexpr unsigned neg = 0x20, pow10 = 0x21, power = 0x44;
constexpr unsigned max_depth = 12;
constexpr Text step_markers[] = {" затем ", " потом ", " после этого ", " после чего ", " далее "};
#if defined(PICO_ON_DEVICE)
namespace numeric = compact_math;
#else
namespace numeric {
using std::acos, std::asin, std::atan, std::cos, std::exp, std::log10;
using std::pow, std::sin, std::sqrt, std::tan;
double ln(double x) { return std::log(x); }
}
#endif

// string_view::substr would link the exception and formatting runtime into
// the bounded firmware even with exceptions disabled at the call site.
Text slice(Text text, std::size_t at, std::size_t count = Text::npos) {
  return at < text.size() ? Text{text.data() + at, std::min(count, text.size() - at)} : Text{};
}
Text trim(Text text) {
  const auto first = text.find_first_not_of(' ');
  return first == Text::npos ? Text{} : slice(text, first, text.find_last_not_of(' ') - first + 1);
}
Text sentence(Text text) {
  text = trim(text);
  while (!text.empty() && Text(".!?;").find(text.back()) != Text::npos) {
    text.remove_suffix(1);
    text = trim(text);
  }
  return text;
}
bool prefix(Text &text, Text value) {
  if (slice(text, 0, value.size()) != value)
    return false;
  text.remove_prefix(value.size());
  text = trim(text);
  return true;
}
bool suffix(Text &text, Text value) {
  if (text.size() < value.size() || slice(text, text.size() - value.size()) != value)
    return false;
  text.remove_suffix(value.size());
  text = trim(text);
  return true;
}
bool clause(Text &text, Text value, bool allow_step = false) {
  auto rest = text;
  if (!suffix(rest, value) || rest.empty())
    return false;
  bool step = false;
  if (allow_step) {
    for (auto marker : step_markers) {
      marker.remove_suffix(1);
      if (suffix(rest, marker)) { step = true; break; }
    }
  }
  const bool joined = suffix(rest, " и") || suffix(rest, " а");
  if (rest.empty()) return false;
  if (Text(".!?;,").find(rest.back()) != Text::npos)
    rest.remove_suffix(1);
  else if (!joined && !step)
    return false;
  text = trim(rest);
  return !text.empty();
}
bool normalize(const char *source, char (&out)[1025]) {
  unsigned n = 0, depth = 0;
  for (const auto *p = reinterpret_cast<const unsigned char *>(source); *p;) {
    if (n + 3 >= sizeof(out))
      return false;
    unsigned a = *p++;
    if (a == ' ' || a == '\r' || a == '\n' || a == '\t' || (a == 0xc2 && *p == 0xa0)) {
      if (a == 0xc2) ++p;
      if (n && out[n - 1] != ' ') out[n++] = ' ';
    } else if (a == 0xe2 && ((!std::strncmp(reinterpret_cast<const char *>(p), "\x88\x92", 2)) ||
                            (!std::strncmp(reinterpret_cast<const char *>(p), "\x80\x93", 2)) ||
                            (!std::strncmp(reinterpret_cast<const char *>(p), "\x80\x94", 2)))) {
      p += 2;
      out[n++] = '-';
    } else if (a == 0xd0 || a == 0xd1 || a == 0xcf) {
      unsigned b = *p++;
      if (b < 0x80 || b > 0xbf || (a == 0xcf && b != 0x80)) return false;
      if ((a == 0xd0 && b == 0x81) || (a == 0xd1 && b == 0x91)) {
        a = 0xd0;
        b = 0xb5;
      } else if (a == 0xd0 && b >= 0x90 && b <= 0xaf) {
        b += 32;
        if (b >= 0xc0) { a = 0xd1; b -= 64; }
      }
      out[n++] = char(a);
      out[n++] = char(b);
    } else if (a >= 0x20 && a < 0x7f) {
      if (a == '(' && ++depth > max_depth) return false;
      if (a == ')') {
        if (!depth) return false;
        --depth;
      }
      out[n++] = char(a >= 'A' && a <= 'Z' ? a + ('a' - 'A') : a);
    } else return false;
  }
  out[n] = 0;
  return !depth && n;
}

// Delimiters in an operand's parentheses belong to that operand.
std::size_t at_top(Text text, Text token, std::size_t begin = 0) {
  unsigned depth = 0;
  for (std::size_t at = 0; at < text.size(); ++at) {
    if (!depth && at >= begin && slice(text, at, token.size()) == token)
      return at;
    if (text[at] == '(') ++depth;
    if (text[at] == ')') --depth;
  }
  return Text::npos;
}
bool split(Text text, Text token, Text &left, Text &right) {
  const auto at = at_top(text, token);
  if (at == Text::npos || at_top(text, token, at + token.size()) != Text::npos)
    return false;
  left = trim(slice(text, 0, at));
  right = trim(slice(text, at + token.size()));
  return !left.empty() && !right.empty();
}
bool group(Text &text) {
  if (text.size() < 3 || text.front() != '(')
    return false;
  unsigned depth = 0;
  for (std::size_t at = 0; at < text.size(); ++at) {
    if (text[at] == '(') ++depth;
    if (text[at] == ')' && !--depth) {
      if (at + 1 != text.size()) return false;
      text = trim(slice(text, 1, at - 1));
      return true;
    }
  }
  return false;
}

// Split only on an explicit sequencing phrase outside parentheses. Punctuation
// alone also appears in conditions such as the named roles of an exponent.
bool split_step(Text text, Text &head, Text &tail) {
  std::size_t at = Text::npos, after = 0;
  for (auto marker : step_markers) {
    const auto found = at_top(text, marker);
    if (found < at) {
      at = found;
      after = at + marker.size();
    }
  }
  if (at == Text::npos) return false;
  head = trim(slice(text, 0, at));
  suffix(head, " а") || suffix(head, " и");
  if (!head.empty() && head.back() == ',') head.remove_suffix(1);
  head = sentence(head);
  tail = trim(slice(text, after));
  prefix(tail, ":");
  return true;
}

bool value_word(Text &text) {
  return prefix(text, "значение ") || prefix(text, "значения ") || prefix(text, "значению ") ||
         prefix(text, "число ") || prefix(text, "числа ");
}
unsigned reg(Text text) {
  if (!(prefix(text, "r") || prefix(text, "р"))) return bad;
  if (text.size() == 1) {
    const char c = text.front();
    if (c >= '0' && c <= '9') return unsigned(c - '0');
    if (c >= 'a' && c <= 'e') return unsigned(c - 'a') + 10;
  }
  if (text == "а") return 10;
  if (text == "в") return 11;
  if (text == "с") return 12;
  if (text == "е") return 14;
  return bad;
}
bool number(Text text, char (&value)[24]) {
  const bool negative = prefix(text, "минус ") || prefix(text, "-");
  if (!negative) prefix(text, "+");
  if (text == "ноль") text = "0";
  if (text == "единица" || text == "единицу" || text == "один") text = "1";
  if (text == "два") text = "2";
  if (text == "десять") text = "10";
  if (text.empty() || text.size() > 19) return false;
  auto point = text.size();
  unsigned digits = 0;
  for (std::size_t i = 0; i < text.size(); ++i) {
    const char c = text[i];
    if (c >= '0' && c <= '9') ++digits;
    else if ((c == '.' || c == ',') && point == text.size()) point = i;
    else return false;
  }
  if (!digits) return false;
  std::size_t begin = 0, end = text.size();
  while (begin < point && text[begin] == '0') ++begin;
  if (point < end) {
    while (end > point + 1 && text[end - 1] == '0') --end;
    if (end == point + 1) end = point;
  }
  unsigned n = 0;
  if (negative && (begin < point || end > point)) value[n++] = '-';
  if (begin == point) value[n++] = '0';
  for (; begin < end; ++begin) value[n++] = text[begin] == ',' ? '.' : text[begin];
  value[n] = 0;
  return n - unsigned(value[0] == '-') <= 18;
}

struct Node { std::uint8_t op, left, right; };
struct Binary {
  Text start, delimiter;
  std::uint8_t op;
  bool reverse = false;
};
constexpr Binary binary[] = {
    {"степень с основанием ", " и показателем ", power},
    {"степень с показателем ", " и основанием ", power, true},
    {"возведи ", " в степень ", power}, {"возвести ", " в степень ", power},
    {"возведите ", " в степень ", power},
    {"сумма значений ", " и ", 0x40}, {"разность значений ", " и ", 0x41},
    {"произведение значений ", " и ", 0x42}, {"частное значений ", " и ", 0x43},
    {"сумма ", " и ", 0x40}, {"разность ", " и ", 0x41},
    {"произведение ", " и ", 0x42}, {"частное ", " и ", 0x43},
    {"к ", " добавь ", 0x40}, {"к ", " прибавь ", 0x40},
    {"прибавь ", " к ", 0x40, true}, {"добавь ", " к ", 0x40, true},
    {"сложи ", " с ", 0x40},
    {"вычти ", " из ", 0x41, true}, {"из ", " вычти ", 0x41},
    {"умножь ", " на ", 0x42}, {"раздели ", " на ", 0x43},
    {"значение ", " надо умножить на ", 0x42}, {"значение ", " нужно умножить на ", 0x42},
    {"числитель дроби равен ", ", знаменатель равен ", 0x43},
    {"", " плюс ", 0x40}, {"", " минус ", 0x41},
    {"", " умножить на ", 0x42}, {"", " разделить на ", 0x43},
    {"", " + ", 0x40}, {"", " - ", 0x41}, {"", " * ", 0x42}, {"", " / ", 0x43},
    {"", " в степени ", power},
};
struct Word { Text spelling; std::uint8_t op; };
constexpr Word unary[] = {
    {"противоположное число ", 0x20}, {"число с обратным знаком ", 0x20},
    {"десять в степени ", pow10}, {"10 в степени ", pow10},
    {"десятичный логарифм ", 0x23}, {"десятичного логарифма ", 0x23},
    {"натуральный логарифм ", 0x24}, {"натурального логарифма ", 0x24},
    {"экспонента ", 0x22}, {"экспоненту ", 0x22}, {"экспоненты ", 0x22},
    {"арксинус ", 0x25}, {"арксинуса ", 0x25}, {"арккосинус ", 0x26}, {"арккосинуса ", 0x26},
    {"арктангенс ", 0x27}, {"арктангенса ", 0x27}, {"синус ", 0x28}, {"синуса ", 0x28},
    {"косинус ", 0x29}, {"косинуса ", 0x29}, {"тангенс ", 0x2a}, {"тангенса ", 0x2a},
    {"квадратный корень ", 0x2b}, {"квадратного корня ", 0x2b},
    {"корень ", 0x2b}, {"корня ", 0x2b}, {"квадрат ", 0x2c}, {"квадрата ", 0x2c},
    {"обратная величина ", 0x2d}, {"обратной величины ", 0x2d},
    {"обратную величину ", 0x2d}, {"обратное число ", 0x2d}, {"обратного числа ", 0x2d},
    {"абсолютная величина ", 0x2e}, {"абсолютную величину ", 0x2e}, {"абсолютной величины ", 0x2e},
    {"модуль ", 0x2e}, {"модуля ", 0x2e}, {"знак ", 0x2f}, {"знака ", 0x2f},
    {"целая часть с отсечением к нулю ", 0x30}, {"целой части с отсечением к нулю ", 0x30},
    {"целую часть с отсечением к нулю ", 0x30}, {"целая часть ", 0x30},
    {"целой части ", 0x30}, {"целую часть ", 0x30},
    {"дробная часть с сохранением знака ", 0x31}, {"дробная часть с исходным знаком ", 0x31},
    {"дробная часть ", 0x31}, {"дробной части ", 0x31}, {"дробную часть ", 0x31},
};

constexpr Text prior_values[] = {
    "результат", "результата", "результату", "предыдущий результат", "предыдущего результата",
    "полученный результат", "полученного результата", "полученному результату", "этот результат",
    "этого результата", "это число", "это значение", "полученное", "полученного", "полученное число",
    "полученное значение", "полученного значения", "полученному значению", "найденного значения",
    "найденной величины", "его", "ее", "него", "нее", "нему",
};

struct Parser {
  DirectTask result;
  Node nodes[31]{};
  unsigned count = 0, previous = bad, references = 0;

  struct Position { unsigned count, references; std::uint8_t literals; };
  Position position() const { return {count, references, result.literal_count}; }
  void restore(Position pos) {
    count = pos.count;
    references = pos.references;
    result.literal_count = pos.literals;
  }
  unsigned prior() {
    ++references;
    return previous;
  }

  unsigned node(unsigned op, unsigned a = bad, unsigned b = bad) {
    if (count == sizeof(nodes) / sizeof(*nodes)) return bad;
    nodes[count] = {std::uint8_t(op), std::uint8_t(a), std::uint8_t(b)};
    return count++;
  }
  unsigned leaf(Text text) {
    for (auto name : prior_values)
      if (text == name) return prior();
    if (text == "пи" || text == "число пи" || text == "π") return node(pi);
    value_word(text);
    prefix(text, "из ");
    prefix(text, "регистра ") || prefix(text, "регистре ") || prefix(text, "регистр ");
    if (const auto r = reg(text); r != bad) return node(r);
    char value[24]{};
    if (!number(text, value)) return bad;
    unsigned index = 0;
    while (index < result.literal_count && std::strcmp(value, result.literals[index])) ++index;
    if (index == result.literal_count) {
      if (index == 16) return bad;
      std::strcpy(result.literals[index], value);
      ++result.literal_count;
    }
    return node(constant, index);
  }
  unsigned operand(Text text, unsigned depth, bool bare_unary = true) {
    if (depth > max_depth || text.empty()) return bad;
    auto inner = text;
    if (group(inner) || (value_word(inner) && group(inner)))
      return expression(inner, depth + 1);
    for (const auto &name : unary) {
      inner = text;
      if (!prefix(inner, name.spelling)) continue;
      prefix(inner, "от ") || prefix(inner, "из ") || prefix(inner, "у ") || prefix(inner, "к ");
      const bool grouped = group(inner);
      if (!grouped && !bare_unary) continue;
      const auto child = grouped ? expression(inner, depth + 1) : operand(inner, depth + 1);
      return child == bad ? bad : node(name.op, child);
    }
    const auto atom = leaf(text);
    if (atom != bad || !bare_unary || !prefix(text, "минус ")) return atom;
    const auto child = operand(text, depth + 1);
    return child == bad ? bad : node(neg, child);
  }
  unsigned join(unsigned op, unsigned a, unsigned b) {
    if (a == bad || b == bad) return bad;
    if (op == power && nodes[a].op == constant && !std::strcmp(result.literals[nodes[a].left], "10"))
      return node(pow10, b);
    return node(op, a, b);
  }
  unsigned labels(Text t, unsigned depth);
  unsigned expression(Text t, unsigned depth);
  unsigned arithmetic(Text &text, unsigned precedence, unsigned depth);
  unsigned arithmetic_operand(Text &text, unsigned depth);
  unsigned step(Text t);
  bool serialize(unsigned index, unsigned depth = 0) {
    if (index >= count || depth > max_depth || result.size >= sizeof(result.body)) return false;
    const auto n = nodes[index];
    result.body[result.size++] = n.op;
    if (n.op < 15) result.registers |= 1U << n.op;
    if (n.op == constant) {
      if (result.size >= sizeof(result.body)) return false;
      result.body[result.size++] = n.left;
    }
    return (n.op < neg || serialize(n.left, depth + 1)) &&
           (n.op < 0x40 || serialize(n.right, depth + 1));
  }
};

unsigned Parser::arithmetic_operand(Text &text, unsigned depth) {
  if (prefix(text, "+"))
    return arithmetic(text, 3, depth + 1);
  if (prefix(text, "-")) {
    const auto child = arithmetic(text, 3, depth + 1);
    return child == bad ? bad : node(neg, child);
  }
  static constexpr Word functions[] = {
      {"abs(", 0x2e}, {"acos(", 0x26}, {"asin(", 0x25}, {"atan(", 0x27},
      {"cos(", 0x29}, {"exp(", 0x22}, {"ln(", 0x24}, {"log10(", 0x23},
      {"sin(", 0x28}, {"sqrt(", 0x2b}, {"tan(", 0x2a},
  };
  unsigned op = bad;
  bool group = prefix(text, "(");
  for (const auto &function : functions) {
    if (!group && prefix(text, function.spelling)) {
      op = function.op;
      group = true;
      break;
    }
  }
  if (group) {
    const auto inner = arithmetic(text, 1, depth + 1);
    if (inner == bad || !prefix(text, ")")) return bad;
    return op == bad ? inner : node(op, inner);
  }
  const auto end = text.find_first_of(" +-*/^()");
  const auto atom = slice(text, 0, end);
  if (atom.empty()) return bad;
  text = trim(slice(text, atom.size()));
  return atom == "pi" ? node(pi) : leaf(atom);
}

unsigned Parser::arithmetic(Text &text, unsigned precedence, unsigned depth) {
  if (text.empty() || depth > max_depth) return bad;
  auto left = arithmetic_operand(text, depth);
  constexpr Text operators = "+-*/^";
  while (left != bad && !text.empty()) {
    const auto operation = operators.find(text.front());
    if (operation == Text::npos) break;
    const unsigned level = 1 + unsigned(operation) / 2;
    if (level < precedence) break;
    text = trim(slice(text, 1));
    // A power binds from the right. The other binary operators bind left.
    const auto right = arithmetic(text, level + unsigned(level != 3), depth + 1);
    left = join(0x40 + unsigned(operation), left, right);
  }
  return left;
}

unsigned Parser::labels(Text text, unsigned depth) {
  prefix(text, "найди степень. ");
  clause(text, "вычисли степень") || clause(text, "какой получится результат") ||
      clause(text, "что получится");
  Text a, b;
  if (!split(text, ", ", a, b) && !split(text, " и ", a, b)) return bad;
  auto role = [](Text &value, Text name) {
    if (!prefix(value, name)) return false;
    prefix(value, "степени ");
    prefix(value, "равно ") || prefix(value, "равен ") || prefix(value, "равняется ") ||
        prefix(value, "- ") || prefix(value, ":") || prefix(value, "=");
    return true;
  };
  auto base = a, exponent = b;
  if (!(role(base, "основание ") && role(exponent, "показатель "))) {
    base = b;
    exponent = a;
    if (!(role(base, "основание ") && role(exponent, "показатель "))) return bad;
  }
  const auto left = operand(base, depth);
  return left == bad ? bad : join(power, left, operand(exponent, depth));
}

unsigned Parser::expression(Text text, unsigned depth) {
  if (text.empty() || depth > max_depth) return bad;
  auto part = text;
  if (group(part)) return expression(part, depth + 1);
  if (slice(text, 0, Text("основание ").size()) == "основание " ||
      slice(text, 0, Text("показатель ").size()) == "показатель " ||
      slice(text, 0, Text("найди степень. ").size()) == "найди степень. ")
    return labels(text, depth);
  const bool absolute = suffix(part, " по модулю");
  if (absolute || suffix(part, " с противоположным знаком")) {
    const unsigned op = absolute ? 0x2e : neg;
    const auto inner = operand(part, depth, false);
    return inner == bad ? bad : node(op, inner);
  }
  if ((prefix(part, "возведи ") || prefix(part, "возведите ")) && suffix(part, " в квадрат")) {
    const auto inner = operand(part, depth);
    return inner == bad ? bad : node(0x2c, inner);
  }
  const auto start = position();
  const auto single = operand(text, depth);
  if (single != bad) return single;
  restore(start);

  for (const auto &rule : binary) {
    part = text;
    if (!prefix(part, rule.start)) continue;
    if (rule.start == "числитель дроби равен " && !clause(part, "вычисли дробь")) continue;
    Text first, second;
    if (!split(part, rule.delimiter, first, second)) continue;
    if (rule.op == power) prefix(second, "равную ");
    // Named/imperative operators delimit their operands. Bare infix phrases
    // leave scope unclear when an operand is an unparenthesized unary term.
    const bool delimited = !rule.start.empty();
    const unsigned left = operand(rule.reverse ? second : first, depth, delimited);
    if (left != bad) {
      const auto right = operand(rule.reverse ? first : second, depth, delimited);
      if (right != bad) return join(rule.op, left, right);
    }
    restore(start);
  }
  const auto symbolic = arithmetic(text, 1, depth);
  if (symbolic != bad && text.empty()) return symbolic;
  restore(start);
  return bad;
}

Text evaluation(Text text) {
  prefix(text, "еще раз ");
  if (slice(text, 0, Text("найди степень. ").size()) == "найди степень. ") return text;
  constexpr Text verbs[] = {"вычисли", "вычислите", "посчитай", "посчитайте", "найди", "найдите",
                            "определи", "возьми", "возьмите", "извлеки"};
  for (auto verb : verbs) {
    if (slice(text, 0, verb.size()) == verb && text.size() > verb.size() &&
        (text[verb.size()] == ' ' || text[verb.size()] == ':')) {
      text = trim(slice(text, verb.size()));
      prefix(text, ":");
      prefix(text, "еще раз ");
      break;
    }
  }
  return text;
}

unsigned Parser::step(Text text) {
  text = evaluation(sentence(text));
  prefix(text, "x=") || prefix(text, "x =") || prefix(text, "х=") || prefix(text, "х =");
  const auto start = position();
  const auto root = expression(text, 0);
  if (root != bad || previous == bad) return root;
  restore(start);

  auto action = text;
  prefix(action, "его ") || prefix(action, "ее ");
  for (const auto &name : unary) {
    if (action == slice(name.spelling, 0, name.spelling.size() - 1))
      return node(name.op, prior());
  }
  if (action == "возведи в квадрат" || action == "возведите в квадрат")
    return node(0x2c, prior());
  if (action == "смени знак" || action == "смените знак" || action == "поменяй знак")
    return node(neg, prior());

  constexpr Word updates[] = {
      {"прибавь к результату ", 0x40}, {"прибавь к нему ", 0x40},
      {"прибавь ", 0x40}, {"добавь ", 0x40}, {"вычти ", 0x41},
      {"умножь на ", 0x42}, {"раздели на ", 0x43}, {"возведи в степень ", power},
  };
  for (const auto &update : updates) {
    auto arg = text;
    if (!prefix(arg, update.spelling)) continue;
    const auto right = operand(arg, 0);
    if (right != bad) return join(update.op, prior(), right);
    restore(start);
  }
  return bad;
}

constexpr Text stores[] = {"тот же результат запиши", "запиши ответ", "запиши результат",
                           "итог сохрани", "итог запиши", "сохрани результат", "оставь результат",
                           "полученный результат сохрани", "полученный результат запиши",
                           "результат запиши", "результат сохрани", "ответ сохрани", "ответ запиши",
                           "результат положи", "запиши", "сохрани", "ответ нужен в x и"};
unsigned destination(Text &text) {
  constexpr Text into = " в ";
  const auto at = text.rfind(into);
  if (at == Text::npos) return bad;
  auto value = trim(slice(text, at + into.size()));
  prefix(value, "регистре ") || prefix(value, "регистр ");
  const auto place = reg(value);
  if (place == bad) return bad;
  auto front = trim(slice(text, 0, at));
  for (auto store : stores) {
    auto expr = front;
    if (clause(expr, store, true)) {
      text = expr;
      return place;
    }
  }
  return bad;
}

// Calculate the independent reference in ordinary arithmetic. MK-61 output is
// still obtained from the isolated core and checked within its precision.
double decimal(const char *text) {
  const bool negative = *text == '-';
  if (negative) ++text;
  double result = 0, scale = 1;
  bool fractional = false;
  for (; *text; ++text) {
    if (*text == '.') fractional = true;
    else {
      if (*text < '0' || *text > '9') return NAN;
      result = result * 10 + (*text - '0');
      if (fractional) scale *= 10;
    }
  }
  return (negative ? -result : result) / scale;
}
double value(const DirectTask &spec, const Example &input, unsigned &at, double scale, unsigned depth = 0) {
  if (at >= spec.size || depth > max_depth) return NAN;
  const unsigned op = spec.body[at++];
  if (op < 15) return input.inputs & (1U << op) ? input.values[op] : 0;
  if (op == constant) {
    if (at >= spec.size || spec.body[at] >= spec.literal_count) return NAN;
    return decimal(spec.literals[spec.body[at++]]);
  }
  if (op == pi) return 3.14159265358979323846;
  const double a = value(spec, input, at, scale, depth + 1);
  if (!std::isfinite(a)) return NAN;
  switch (op) {
  case 0x20: return -a;
  case 0x21: return numeric::pow(10, a);
  case 0x22: return numeric::exp(a);
  case 0x23: return a > 0 ? numeric::log10(a) : NAN;
  case 0x24: return a > 0 ? numeric::ln(a) : NAN;
  case 0x25: return std::fabs(a) <= 1 ? numeric::asin(a) / scale : NAN;
  case 0x26: return std::fabs(a) <= 1 ? numeric::acos(a) / scale : NAN;
  case 0x27: return numeric::atan(a) / scale;
  case 0x28: return numeric::sin(a * scale);
  case 0x29: return numeric::cos(a * scale);
  case 0x2a: return numeric::tan(a * scale);
  case 0x2b: return a >= 0 ? numeric::sqrt(a) : NAN;
  case 0x2c: return a * a;
  case 0x2d: return a != 0 ? 1 / a : NAN;
  case 0x2e: return std::fabs(a);
  case 0x2f: return (a > 0) - (a < 0);
  case 0x30:
  case 0x31: {
    // The calculator helper canonicalizes a truncated zero.
    const double integral = std::copysign(mk_math::trunc(a), a);
    return op == 0x30 ? integral : a - integral;
  }
  default: break;
  }
  const double b = value(spec, input, at, scale, depth + 1);
  if (!std::isfinite(b)) return NAN;
  switch (op) {
  case 0x40: return a + b;
  case 0x41: return a - b;
  case 0x42: return a * b;
  case 0x43: return b != 0 ? a / b : NAN;
  case 0x44: return a > 0 ? numeric::pow(a, b) : NAN;
  default: return NAN;
  }
}
} // namespace

bool parse_direct_task(const char *source, unsigned angle, DirectTask &out) {
  char text[1025];
  if (!source || angle > 2 || !normalize(source, text)) return false;
  auto task = sentence(text);
  Parser parser{};
  parser.result.angle = std::uint8_t(angle);
  constexpr Text angles[] = {"в градусах", "в радианах", "в градах"};
  for (unsigned i = 0; i < 3; ++i) {
    auto head = task;
    if (clause(head, angles[i]) || suffix(head, i == 0 ? " в градусах" : i == 1 ? " в радианах" : " в градах") ||
        (i == 0 && (suffix(head, " градусов") || suffix(head, " градуса") || suffix(head, " градус")))) {
      task = sentence(head);
      parser.result.angle = std::uint8_t(i);
      parser.result.explicit_angle = true;
      break;
    }
  }
  clause(task, "что получится") || clause(task, "сколько выйдет");
  clause(task, "после вычисления остановись", true) || clause(task, "остановись", true);
  clause(task, "остальные регистры памяти сохрани") || clause(task, "остальные регистры сохрани");
  const bool preserve_all = clause(task, "память сохрани");
  const auto store = destination(task);
  if (preserve_all && store != bad) return false;
  parser.result.body[parser.result.size++] = std::uint8_t(store);
  clause(task, "результат оставь в x") || clause(task, "результат оставь в х") ||
      clause(task, "результат должен остаться в x") || clause(task, "ответ нужен в x");
  task = sentence(task);
  constexpr Text introductions[] = {
      "нужна программа мк-61 для следующего вычисления: ", "мне нужно вычислить это выражение: ",
      "составь программу мк-61: ", "составь программу для мк-61: ", "составьте программу для мк-61: ",
      "напиши программу для мк-61: ", "какое значение даст ", "посчитай, пожалуйста: ",
      "найди, чему равна ", "чему равно ", "чему равен ", "сколько будет ", "что получится, если ",
  };
  for (auto intro : introductions)
    if (prefix(task, intro)) break;
  prefix(task, "сначала ") || prefix(task, "сперва ");
  for (unsigned step = 0; step < 12; ++step) {
    Text section, next;
    const bool more = split_step(task, section, next);
    parser.references = 0;
    const auto root = parser.step(more ? section : task);
    if (root == bad || parser.references != unsigned(step != 0)) return false;
    if (!more) {
      if (!parser.serialize(root)) return false;
      out = parser.result;
      return true;
    }
    parser.previous = root;
    task = next;
  }
  return false;
}

bool DirectTask::compile(Program &code) const {
  return size <= sizeof(body) && literal_count <= 16 &&
         compile_spec_tree(body, size, literals, literal_count, code);
}
bool DirectTask::expectation(const Example &input, Example &checked) const {
  if (size < 2 || size > sizeof(body) || literal_count > 16 || input.angle > 2 ||
      input.scenario_count || (explicit_angle && input.angle != angle)) return false;
  constexpr double scales[] = {3.14159265358979323846 / 180, 1, 3.14159265358979323846 / 200};
  unsigned at = 1;
  const double answer = value(*this, input, at, scales[input.angle]);
  if (at != size || !std::isfinite(answer) || std::fabs(answer) >= 1e90) return false;
  const unsigned store = body[0];
  if (store != bad && store >= 15) return false;
  const std::uint32_t stored = store == bad ? 0 : 1U << store;
  checked = input;
  checked.has_expected = false;
  checked.expected_mask = X_MASK | stored;
  checked.expected_values[15] = answer;
  if (stored) checked.expected_values[store] = answer;
  checked.preserve |= 0x7fffU & ~stored;
  checked.absolute = checked.relative = 0.000002;
  return true;
}
} // namespace mk61ai
