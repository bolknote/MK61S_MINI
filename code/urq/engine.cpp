#if defined(__GNUC__) && !defined(__clang__)
#pragma GCC optimize("Oz")
#endif
#include "engine.hpp"
#include "../mk8_codec.hpp"
#include <string.h>

namespace urq {
namespace {
bool space(char c) { return c == ' ' || c == '\t' || c == '\r' || c == '\n'; }
const char* skip(const char* p) { while(space(*p)) ++p; return p; }
uint16_t trimmed(const char* p, uint16_t n) { while(n && space(p[n - 1])) --n; return n; }
[[gnu::noinline]] bool prefix(const char* a, const char* b) {
  while(*b) if(lower(uint8_t(*a++)) != uint8_t(*b++)) return false;
  return true;
}
const char* word(const char* p, const char* target) {
  const uint16_t n = uint16_t(strlen(target));
  char quote = 0;
  for(const char* at = p; *at; ++at) {
    if(quote) { if(*at == quote) quote = 0; continue; }
    if(*at == '\'' || *at == '"') { quote = *at; continue; }
    if((at == p || space(at[-1])) && prefix(at, target) &&
       (!at[n] || space(at[n]))) return at;
  }
  return nullptr;
}
const char* compound(const char* source) {
  unsigned links = 0;
  for(const char* p = source; *p; ++p) {
    if(p[0] == '[' && p[1] == '[') { ++links; ++p; }
    else if(p[0] == ']' && p[1] == ']' && links) { --links; ++p; }
    else if(*p == '&' && !links) return p;
  }
  return nullptr;
}
bool glob(const char* text, const char* pattern) {
  const char* star = nullptr; const char* retry = nullptr;
  while(*text) {
    if(*pattern == '?' || lower(uint8_t(*pattern)) == lower(uint8_t(*text))) { ++text; ++pattern; }
    else if(*pattern == '*') { star = pattern++; retry = text; }
    else if(star) { pattern = star + 1; text = ++retry; }
    else return false;
  }
  while(*pattern == '*') ++pattern;
  return !*pattern;
}
[[gnu::noinline]] uint16_t character_order(uint8_t byte) {
  if(byte>=0xC0) return uint16_t(byte+0x350);
  if(byte>=0x80) return mk8::CP1251_80_BF[byte-0x80];
  return byte>=0x20 || byte<0x0E ? byte : mk8::PRIVATE_CODEPOINTS[byte-0x0E];
}
int compare_unicode(const char* a,const char* b) {
  while(*a && *a==*b) { ++a;++b; }
  const uint8_t x=uint8_t(*a),y=uint8_t(*b);
  return !x || !y ? int(x)-int(y) : int(character_order(x))-int(character_order(y));
}
enum Command : uint8_t {
  UNKNOWN, IF, BTN, GOTO, PROC, END, FORGET, CLS, CLST, CLSB, CLSL,
  PRINT, PRINTLN, INPUT, ANYKEY, PAUSE, QUIT, SAVE, INVKILL, VARKILL,
  PERKILL, INVADD, INVSUB, INSTR, TOKENS, MEDIA
};
Command command_at(const char* source, const char*& argument) {
  const char* end = source;
  while(*end && !space(*end)) ++end;
  argument = *end ? end + 1 : end;
  // Compact table rather than a separate string comparison at each opcode.
  static const char commands[] =
      "\001if\0\002btn\0\003goto\0\004proc\0\005end\0\006forget_procs\0"
      "\007cls\0\010clst\0\011clsb\0\012clsl\0\013p\0\013print\0"
      "\014pln\0\014println\0\015input\0\016anykey\0\017pause\0"
      "\020quit\0\021save\0\022invkill\0\023varkill\0\024perkill\0"
      "\025inv+\0\026inv-\0\027instr\0\030tokens\0"
      "\031image\0\031music\0\031play\0";
  for(const char* at = commands; *at;) {
    const Command code = Command(*at++);
    const char* p = source;
    while(*at && p < end && lower(uint8_t(*p)) == uint8_t(*at)) { ++p; ++at; }
    if(!*at && p == end) return code;
    while(*at++) {}
  }
  return UNKNOWN;
}
}
void Engine::attach(Pack& pack, State& state, Host host) {
  pack_ = &pack; state_ = &state; host_ = host; temporary_ = 0;
  yielded_ = false;
  temp_ = reinterpret_cast<char*>(state.transient);
  pack.cache(state.transient + 1536);
}
void Engine::fail(Error error) { state_->error = error; state_->status = Status::ERROR; }
bool Engine::decimal(const char* source, double& value) {
  char normalized[128]; unsigned n = 0;
  for(; *source; ++source) if(!space(*source)) {
    if(n + 1 == sizeof(normalized)) { fail(Error::LIMIT); return false; }
    normalized[n++] = *source == ',' ? '.' : *source;
  }
  normalized[n] = 0;
  if(!n || !host_.parse || !host_.parse(host_.context, normalized, value)) return false;
  // UrqW first checks Number(), then uses parseFloat() for a numeric literal.
  if(n > 2 && normalized[0] == '0' && strchr("xXoObB", normalized[1])) value = 0;
  return true;
}
[[gnu::noinline]] const char* Engine::text(uint16_t at) const {
  return at < state_->used ? state_->pool + at : "";
}
char* Engine::temporary(uint16_t size) {
  if(!size || size > 1536U - temporary_) { fail(Error::MEMORY); return nullptr; }
  char* out = temp_ + temporary_; temporary_ += size; return out;
}
const char* Engine::copy(const char* p, uint16_t size) {
  char* out = temporary(uint16_t(size + 1));
  if(!out) return "";
  memcpy(out, p, size); out[size] = 0; return out;
}
uint16_t Engine::store(const char* p) {
  if(!*p) return 0;
  const size_t size = strlen(p) + 1;
  if(size > unsigned(POOL_BYTES - state_->used)) { fail(Error::MEMORY); return 0; }
  const uint16_t at = state_->used;
  memcpy(state_->pool + at, p, size); state_->used += uint16_t(size); return at;
}
int Engine::find(const char* name) const {
  for(unsigned i = 0; i < state_->variables; ++i)
    if(state_->names[i] && equal_name(text(state_->names[i]), name)) return int(i);
  return -1;
}
void Engine::erase(int i) {
  if(i < 0) return;
  state_->names[i] = state_->strings[i] = 0;
  state_->types[i] = 0; state_->numbers[i] = 0;
}
double Engine::item_quantity(const char* name) const {
  for(unsigned i = 0; i < ITEMS; ++i)
    if(state_->items[i] && !strcmp(text(state_->items[i]), name)) return state_->quantities[i];
  return 0;
}
bool Engine::set_item(const char* name, const Value& value) {
  const double count = numeric(value);
  int slot = -1;
  for(unsigned i = 0; i < ITEMS; ++i) {
    if(state_->items[i] && !strcmp(text(state_->items[i]), name)) { slot = int(i); break; }
    if(!state_->items[i] && slot < 0) slot = int(i);
  }
  if(count > 0) {
    if(slot < 0) { fail(Error::MEMORY); return false; }
    state_->items[slot] = store(name); state_->quantities[slot] = count;
  } else if(slot >= 0) { state_->items[slot] = 0; state_->quantities[slot] = 0; }
  return set(name, {count > 0 ? count : 0, nullptr, 0});
}
bool Engine::set(const char* raw, const Value& value, bool item) {
  raw = skip(raw);
  if(item || prefix(raw, "inv_")) return set_item(item ? raw : raw + 4, value);
  char name[128];
  const uint16_t n = trimmed(raw, uint16_t(strlen(raw)));
  if(!n || n >= sizeof(name)) { fail(Error::LIMIT); return false; }
  memcpy(name, raw, n); name[n] = 0;
  for(unsigned i = 0; i < n; ++i) name[i] = char(lower(uint8_t(name[i])));
  const char* key = name;
  if(equal_name(key, "urq_mode")) {
    const char* mode = value.type == 1 ? value.text : "";
    state_->mode = !strcmp(mode, "dosurq") ? Mode::DOS : !strcmp(mode, "ripurq") ? Mode::RIP :
                   !strcmp(mode, "akurq") ? Mode::AK : Mode::URQW;
    return state_->mode != Mode::DOS || (set("style_backcolor", {0, "#000", 1}) && set("style_textcolor", {0, "#FFF", 1}));
  }
  if(equal_name(key, "style_dos_textcolor")) {
    double number = numeric(value);
    const unsigned color = number >= 0 && number < 4294967295.0 && number == double(uint32_t(number)) &&
        (value.type == 0 || number > 15) ? unsigned(uint32_t(number) & 15U) : 0;
    char rgb[8] = "#000000";
    for(unsigned channel = 0; channel < 3; ++channel) {
      unsigned component = ((color & (4U >> channel)) ? 170 : 0) + ((color & 8U) ? 85 : 0);
      if(color == 6 && channel == 1) component = 85;
      rgb[1 + channel * 2] = "0123456789ABCDEF"[component >> 4];
      rgb[2 + channel * 2] = "0123456789ABCDEF"[component & 15];
    }
    if(!set("style_textcolor", {0, rgb, 1})) return false;
  }
  if(equal_name(key, "javascript")) {
    fail(Error::UNSUPPORTED); return false;
  }
  if(host_.resource) {
    const bool url=equal_name(key,"file_url");
    if(url || equal_name(key,"file_content")) {
      auto callback=host_.resource;host_.resource=nullptr;
      const bool ok=callback(host_.context,url,stringify(value));host_.resource=callback;
      if(!ok) { fail(Error::IO);return false; }
      if(host_.deferred_save) state_->status=Status::SAVE;
      return true;
    }
  }
  int index = find(key);
  if(index < 0) {
    for(unsigned i = 0; i < state_->variables; ++i)
      if(!state_->names[i]) { index = int(i); break; }
    if(index < 0) {
      if(state_->variables == VARIABLES) { fail(Error::MEMORY); return false; }
      index = state_->variables++;
    }
    state_->names[index] = store(key);
  }
  state_->types[index] = value.type;
  state_->numbers[index] = value.type==1?0:value.number;
  state_->strings[index] = value.type == 1 ? store(value.text ? value.text : "") : 0;
  return state_->status != Status::ERROR;
}
Value Engine::get(const char* name) {
  if(prefix(name, "inv_")) name += 4;
  if(equal_name(name, "urq_mode"))
    return {0, state_->mode == Mode::DOS ? "dosurq" : state_->mode == Mode::RIP ? "ripurq" :
               state_->mode == Mode::AK ? "akurq" : "urqw", 1};
  if(prefix(name, "rnd")) {
    uint32_t x = state_->rng; x ^= x << 13; x ^= x >> 17; x ^= x << 5; state_->rng = x;
    const double random = double(x) / 4294967296.0;
    if(!name[3]) return {random, nullptr, 0};
    double limit = 0; decimal(name + 3, limit);
    const double product = random * limit;
    if(!(product > -9.0e18 && product < 9.0e18)) return {product, nullptr, 0};
    int64_t whole = int64_t(product);
    if(product < whole) --whole;
    return {double(whole + 1), nullptr, 0};
  }
  if(equal_name(name, "time") || (state_->mode == Mode::URQW && equal_name(name, "date")))
    return {host_.clock ? double(host_.clock(host_.context, equal_name(name, "date"))) : 0, nullptr, 0};
  if(equal_name(name, "urq_type") && state_->mode == Mode::AK) return {1, nullptr, 0};
  if(equal_name(name, "quest_path") && state_->mode == Mode::AK) return {0, "", 1};
  if(equal_name(name, "urqw_version")) return {0, "1.1", 1};
  if(equal_name(name, "urqw_game_ifid")) {
    char* value = temporary(256);
    if(!value || !pack_->info(3, value, 256)) { fail(pack_->error()); return {}; }
    return {0, value, 1};
  }
  if(equal_name(name, "urq_inv")) {
    unsigned n = 0;
    for(unsigned i = 0; i < ITEMS; ++i) if(state_->items[i]) ++n;
    return {double(n), nullptr, 0};
  }
  const int index = find(name);
  if(index >= 0) return {state_->numbers[index], text(state_->strings[index]), state_->types[index]};
  if(equal_name(name, "urqw_title")) return {0, "", 1};
  const char* delimiter = strchr(name, ' ');
  if(delimiter) {
    double count = 0;
    const char* quantity = copy(name, uint16_t(delimiter - name));
    if(decimal(quantity, count)) return {numeric(get(skip(delimiter))) >= count ? 1.0 : 0.0, nullptr, 2};
  }
  return {};
}
[[gnu::noinline]] bool Engine::truth(const Value& v) const {
  if(v.type == 1) return v.text && *v.text;
  return v.number != 0;
}
double Engine::numeric(const Value& v) const {
  if(v.type != 1) return v.number;
  if(!v.text || !*skip(v.text)) return 0;
  double number = 0;
  if(host_.parse && host_.parse(host_.context, v.text, number)) return number;
  return __builtin_nan("");
}
const char* Engine::stringify(const Value& v, bool fixed) {
  if(v.type == 1) return v.text ? v.text : "";
  if(v.type == 2) return v.number ? "true" : "false";
  char* out = temporary(48);
  if(!out) return "";
  if(host_.number) host_.number(host_.context, v.number, fixed, out, 48);
  else { fail(Error::UNSUPPORTED); out[0] = 0; }
  return out;
}
#if defined(__GNUC__)
__attribute__((noinline))
#endif
Value Engine::add(const Value& a, const Value& b) {
  if(a.type != 1 && b.type != 1) return {numeric(a) + numeric(b), nullptr, 0};
  const char* x = stringify(a); const char* y = stringify(b);
  const size_t nx = strlen(x), ny = strlen(y);
  if(nx + ny >= LINE_BYTES) { fail(Error::LIMIT); return {}; }
  char* out = temporary(uint16_t(nx + ny + 1));
  if(!out) return {};
  memcpy(out, x, nx); memcpy(out + nx, y, ny + 1); return {0, out, 1};
}
class Engine::Expression {
 public:
  Expression(Engine& engine, const char* input) : e(engine), p(input) {}
  bool parse(Value& out) {
    expression(1, 0, out);
    if(*skip(p)) e.fail(Error::SYNTAX);
    return e.state_->status != Status::ERROR;
  }
 private:
  struct Operator { uint8_t priority, length, kind; };
  Operator op() {
    p = skip(p);
    static const char symbols[] = "or\0and\0||\0&&\0==\0!=\0<>\0<=\0>=\0=\0<\0>\0+\0-\0*\0/\0^\0";
    static const uint8_t priorities[] = {1,2,1,2,3,3,3,4,4,3,4,4,5,5,6,6,8};
    static const uint8_t kinds[] = {1,2,1,2,3,4,4,6,8,5,7,9,10,11,12,13,14};
    const char* symbol = symbols;
    for(unsigned i = 0; i < sizeof(kinds); ++i) {
      const unsigned n = strlen(symbol);
      if(prefix(p, symbol) && (i > 1 || !p[n] || space(p[n])))
        return {priorities[i], uint8_t(n), kinds[i]};
      symbol += n + 1;
    }
    return {};
  }
  Value atom(uint8_t depth) {
    p = skip(p);
    if(depth > 24) { e.fail(Error::STACK); return {}; }
    if(prefix(p, "not") && (!p[3] || space(p[3]) || p[3] == '(')) {
      p += 3; Value v; expression(9, uint8_t(depth + 1), v);
      return {e.truth(v) ? 0.0 : 1.0, nullptr, 2};
    }
    if(*p == '-' || *p == '+') {
      const bool minus = *p++ == '-'; Value v; expression(7, uint8_t(depth + 1), v);
      if(minus) { if(v.type == 2) v.number = !v.number; else { v.number = -e.numeric(v); v.type = 0; } }
      return v;
    }
    if(*p == '(') {
      ++p; Value v; expression(1, uint8_t(depth + 1), v); p = skip(p);
      if(*p != ')') e.fail(Error::SYNTAX); else ++p;
      return v;
    }
    if(*p == '\'' || *p == '"') {
      const char quote = *p++; const char* start = p;
      while(*p && *p != quote) ++p;
      if(!*p) { e.fail(Error::SYNTAX); return {}; }
      const char* value = e.copy(start, uint16_t(p - start)); ++p; return {0, value, 1};
    }
    const char* start = p;
    while(*p && !strchr("()+-*/^=<>!&|", *p)) {
      if(space(*p) && (word(p, "and") == skip(p) || word(p, "or") == skip(p))) break;
      ++p;
    }
    const uint16_t length = trimmed(start, uint16_t(p - start));
    if(!length) { e.fail(Error::SYNTAX); return {}; }
    const char* token = e.copy(start, length); double number = 0;
    if(e.decimal(token, number)) return {number, nullptr, 0};
    return e.get(token);
  }
  void expression(uint8_t minimum, uint8_t depth, Value& left) {
    left = atom(depth);
    for(;;) {
      const Operator operation = op();
      if(!operation.priority || operation.priority < minimum || e.state_->status == Status::ERROR) return;
      p += operation.length;
      Value right;
      expression(uint8_t(operation.priority + (operation.kind == 14 ? 0 : 1)), uint8_t(depth + 1), right);
      const double a = e.numeric(left), b = e.numeric(right);
      const bool strings=left.type==1 && right.type==1;
      const int order=strings?compare_unicode(left.text,right.text):0;
      bool boolean = true, result = false;
      switch(operation.kind) {
        case 1: result = e.truth(left) || e.truth(right); break;
        case 2: result = e.truth(left) && e.truth(right); break;
        case 3: result = strings ? glob(left.text, right.text) : a == b; break;
        case 4: result = strings ? !equal_name(left.text, right.text) : a != b; break;
        case 5: result = strings ? equal_name(left.text, right.text) : a == b; break;
        case 6: result = strings ? order <= 0 : a <= b; break;
        case 7: result = strings ? order < 0 : a < b; break;
        case 8: result = strings ? order >= 0 : a >= b; break;
        case 9: result = strings ? order > 0 : a > b; break;
        case 10:
          boolean = false; left = e.add(left, right);
          break;
        case 11: boolean = false; left = {a - b, nullptr, 0}; break;
        case 12: boolean = false; left = {a * b, nullptr, 0}; break;
        case 13: boolean = false; left = {a / b, nullptr, 0}; break;
        case 14:
          boolean = false;
          if(!e.host_.power) { e.fail(Error::UNSUPPORTED); return; }
          left = {e.host_.power(e.host_.context, a, b), nullptr, 0}; break;
      }
      if(boolean) left = {result ? 1.0 : 0.0, nullptr, 2};
    }
  }
  Engine& e;
  const char* p;
};
bool Engine::evaluate(const char* expression, Value& result) {
  return Expression(*this, expression).parse(result);
}
bool Engine::tags(const char* source, const char*& result) {
  if(!strchr(source, '#')) { result = source; return true; }
  char output[LINE_BYTES];
  if(strlen(source) >= sizeof(output)) { fail(Error::LIMIT); return false; }
  copy_string(output, source);
  const uint16_t checkpoint = temporary_;
  for(unsigned expansion = 0; expansion < 64; ++expansion) {
    char* p = nullptr; char* end = output;
    for(; *end; ++end) {
      if(*end == '#') {
        p = end;
        if(end[1] == '#') ++end;
      } else if(*end == '$' && p) break;
    }
    if(!*end || !p) { result = copy(output, uint16_t(strlen(output))); return state_->status != Status::ERROR; }
    const char* content = p + 1; if(*content == '%') ++content;
    const uint16_t count = uint16_t(end - content);
    const char* replacement;
    if(!count) replacement = " ";
    else if(count == 1 && *content == '/') replacement = "\n";
    else if(*content == '#') {
      char* entity = temporary(uint16_t(count+3));if(!entity) return false;
      entity[0]='&';memcpy(entity+1,content,count);entity[count+1]=';';entity[count+2]=0;replacement=entity;
    } else {
      Value value;
      if(!evaluate(copy(content, count), value)) return false;
      replacement = stringify(value, true);
    }
    const size_t n = strlen(replacement), tail = strlen(end + 1);
    if(size_t(p - output) + n + tail >= sizeof(output)) { fail(Error::LIMIT); return false; }
    memmove(p + n, end + 1, tail + 1); memcpy(p, replacement, n);
    temporary_ = checkpoint;
  }
  fail(Error::LIMIT); return false;
}
void Engine::collect() {
  // Compact in place. Every persistent string is rooted through one of these offsets.
  auto roots = [&](uint16_t old, uint16_t next, bool move) {
    bool found = false;
    auto root = [&](uint16_t& value) {
      if(value == old) { found = true; if(move) value = next; }
    };
    for(unsigned i = 0; i < state_->variables; ++i) if(state_->names[i]) {
      root(state_->names[i]); if(state_->types[i] == 1) root(state_->strings[i]);
    }
    for(unsigned i = 0; i < ITEMS; ++i) root(state_->items[i]);
    for(unsigned i = 0; i < state_->action_count; ++i) if(state_->actions[i].live) {
      root(state_->actions[i].command); root(state_->actions[i].caption);
    }
    for(unsigned i = 0; i < state_->pending_count; ++i) root(state_->pending[i].text);
    root(state_->wait_name); root(state_->selection); root(state_->last_input); return found;
  };
  uint16_t out = 1, at = 1;
  while(at < state_->used) {
    const uint16_t size = uint16_t(strlen(state_->pool + at) + 1);
    if(roots(at, out, false)) {
      memmove(state_->pool + out, state_->pool + at, size);
      roots(at, out, true); out += size;
    }
    at += size;
  }
  state_->used = out;
  unsigned actions = 0;
  for(unsigned i = 0; i < state_->action_count; ++i) if(state_->actions[i].live) state_->actions[actions++] = state_->actions[i];
  state_->action_count = uint16_t(actions);
  for(unsigned i = actions; i < ACTIONS; ++i) state_->actions[i] = {};
  for(unsigned i = state_->pending_count; i < PENDING; ++i) state_->pending[i] = {};
}
bool Engine::push(const char* command) {
  if(!*skip(command)) return true;
  if(state_->pending_count == PENDING) { fail(Error::STACK); return false; }
  const uint16_t offset = store(command);
  state_->pending[state_->pending_count++] = {offset, state_->depth};
  return state_->status != Status::ERROR;
}
void Engine::discard(uint16_t depth) {
  unsigned out = 0;
  for(unsigned i = 0; i < state_->pending_count; ++i)
    if(state_->pending[i].depth < depth) state_->pending[out++] = state_->pending[i];
  state_->pending_count = uint16_t(out);
}
void Engine::clear(bool output, bool actions) {
  if(output) { state_->context_size = 0; state_->context[0] = 0; }
  if(actions) state_->action_count = state_->next_action = state_->next_link = 0;
  if(host_.clear) host_.clear(host_.context, output, actions);
}
bool Engine::jump(const char* name, uint8_t kind) {
  uint32_t line = 0;
  if(!pack_->label(name, line)) {
    if(pack_->error() != Error::NONE) fail(pack_->error());
    return false;
  }
  char canonical[128];copy_string(canonical,name);
  for(char* p=canonical;*p;++p) *p=char(lower(uint8_t(*p)));
  if(kind==1) name=canonical;
  if(kind == 1 || (kind == 0 && state_->mode != Mode::DOS && state_->mode != Mode::AK)) {
    const Value current = get("current_loc");
    if(!set("previous_loc", current) || !set("current_loc", {0, name, 1})) return false;
  }
  char counter[136];
  name=canonical;
  if(state_->mode == Mode::RIP) {
    if(strlen(name) >= sizeof(counter)) { fail(Error::LIMIT); return false; }
    copy_string(counter, name);
  } else {
    if(strlen(name) + 6 >= sizeof(counter)) { fail(Error::LIMIT); return false; }
    copy_string(counter, "count_"); join_string(counter, name);
  }
  const double count = numeric(get(counter));
  if(!set(counter, {count + 1, nullptr, 0})) return false;
  if(state_->mode == Mode::AK && !set("location", {0, name, 1})) return false;
  state_->pc = line; discard(state_->depth); return true;
}
bool Engine::procedure(const char* name) {
  if(state_->depth == FRAMES) { fail(Error::STACK); return false; }
  state_->frames[state_->depth] = {state_->pc, state_->depth, 0};
  ++state_->depth;
  if(jump(name, 2)) return true;
  --state_->depth; return false;
}
void Engine::end() {
  discard(state_->depth);
  if(state_->depth) state_->pc = state_->frames[--state_->depth].pc;
  else if(state_->selection_stage) selected();
  else state_->status = Status::CHOICE;
}
bool Engine::add_action(const char* command, const char* caption, bool link) {
  if(state_->action_count == ACTIONS) collect();
  if(state_->action_count == ACTIONS) { fail(Error::MEMORY); return false; }
  uint16_t& next = link ? state_->next_link : state_->next_action;
  if(next >= 0x8000) { fail(Error::LIMIT); return false; }
  state_->actions[state_->action_count++] = {store(command), store(caption), uint16_t(next++ | (link?0x8000:0)), uint8_t(link), 1};
  return state_->status != Status::ERROR;
}
bool Engine::output(const char* raw, bool newline) {
  char clean[LINE_BYTES]; uint16_t used = 0;
  for(const char* p = raw; *p;) {
    if(p[0] == '[' && p[1] == '[') {
      const char* close = find_string(p + 2, "]]");
      if(close) {
        const char* bar = strchr(p + 2, '|');
        if(!bar || bar > close) bar = close;
        const char* caption = copy(p + 2, trimmed(p + 2, uint16_t(bar - p - 2)));
        if(pack_->html()) {
          if(bar == close) {
            if(!add_action(caption, caption, true)) return false;
          } else {
          const char* second = strchr(bar + 1, '|');
          if(second && second < close) {
            const char* base = copy(bar + 1, uint16_t(second - bar - 1));
            const char* start = second + 1;
            while(start < close) {
              const char* comma = start;
              while(comma < close && *comma != ',') ++comma;
              const char* suffix = copy(skip(start), trimmed(skip(start), uint16_t(comma - skip(start))));
              char target[128], key[144];
              if(strlen(base) + strlen(suffix) >= sizeof(target)) { fail(Error::LIMIT); return false; }
              copy_string(target, base); join_string(target, suffix);
              copy_string(key, "hide_"); join_string(key, target);
              if(!truth(get(key))) {
                copy_string(key, "display_"); join_string(key, target);
                const Value display = get(key);
                if(!add_action(target, truth(display) ? stringify(display) : suffix, true)) return false;
              }
              start = comma + (comma != close);
            }
          } else if(!add_action(copy(skip(bar + 1), trimmed(skip(bar + 1), uint16_t(close - skip(bar + 1)))), caption, true)) return false;
          }
        }
        const size_t n = strlen(caption);
        if(n >= sizeof(clean) - used) { fail(Error::LIMIT); return false; }
        memcpy(clean + used, caption, n); used += uint16_t(n); p = close + 2; continue;
      }
    }
    if(*p == '<' && (pack_->html() || prefix(p,"<br>"))) {
      const char* close = strchr(p, '>');
      if(close) {
        if(prefix(p, "<br") || prefix(p, "</p") || prefix(p, "</div")) {
          if(used + 1 == sizeof(clean)) { fail(Error::LIMIT); return false; }
          clean[used++] = '\n';
        }
        p = close + 1; continue;
      }
    }
    if(used + 1 == sizeof(clean)) { fail(Error::LIMIT); return false; }
    if(p[0]=='&' && p[1]=='#') {
      uint32_t code=0;const char* at=p+2;
      while(*at>='0' && *at<='9' && code<0x110000) code=code*10+unsigned(*at++-'0');
      uint8_t byte=0;
      if(*at==';' && at!=p+2) {
        if(!mk8::from_codepoint(code,byte)) { fail(Error::UNSUPPORTED);return false; }
        clean[used++]=char(byte);p=at+1;continue;
      }
    }
    if(prefix(p, "&nbsp;")) { clean[used++] = ' '; p += 6; }
    else if(prefix(p, "&amp;")) { clean[used++] = '&'; p += 5; }
    else if(prefix(p, "&lt;")) { clean[used++] = '<'; p += 4; }
    else if(prefix(p, "&gt;")) { clean[used++] = '>'; p += 4; }
    else if(prefix(p, "&quot;")) { clean[used++] = '"'; p += 6; }
    else clean[used++] = *p++;
  }
  clean[used] = 0;
  if(host_.print) host_.print(host_.context, clean, newline);
  auto append = [&](char ch) {
    if(state_->context_size + 1 == sizeof(state_->context)) {
      memmove(state_->context, state_->context + 1, --state_->context_size);
    }
    state_->context[state_->context_size++] = ch;
    state_->context[state_->context_size] = 0;
  };
  for(unsigned i = 0; i < used; ++i) append(clean[i]);
  if(newline) append('\n');
  return state_->status != Status::ERROR;
}
bool Engine::execute(const char* source, uint8_t recursion) {
  if(recursion > 24) { fail(Error::STACK); return false; }
  source = skip(source);
  if(!*source || *source == ':') return true;
  const char* command;
  Command operation = command_at(source, command);
  if(operation == IF) {
    const char* then = word(command, "then");
    if(!then) { fail(Error::SYNTAX); return false; }
    Value condition;
    const char* expression = copy(command, trimmed(command, uint16_t(then - command)));
    const char* expanded;
    if(!tags(expression, expanded) || !evaluate(expanded, condition)) return false;
    const char* yes = skip(then + 4);
    const char* otherwise = word(yes, "else");
    // In nested IF, an ELSE following the nested IF belongs to that IF.
    const char* nested = word(yes, "if");
    if(nested && otherwise && nested < otherwise) otherwise = nullptr;
    if(truth(condition)) {
      const char* branch = otherwise ? copy(yes, trimmed(yes, uint16_t(otherwise - yes))) : yes;
      return execute(branch, uint8_t(recursion + 1));
    }
    return !otherwise || execute(skip(otherwise + 4), uint8_t(recursion + 1));
  }
  if(operation == BTN) {
    const char* comma = strchr(command, ',');
    if(!comma) { fail(Error::SYNTAX); return false; }
    const char* target = copy(command, trimmed(command, uint16_t(comma - command)));
    const char* caption = skip(comma + 1);
    if(const char* tail = compound(caption)) {
      if(!push(skip(tail + 1))) return false;
      caption = copy(caption, uint16_t(tail - caption));
    }
    if(!tags(caption, caption)) return false;
    if(!strchr(target, '&') && !tags(target, target)) return false;
    return add_action(target, caption);
  }
  const char* ampersand = compound(source);
  if(ampersand) {
    if(!push(skip(ampersand + 1))) return false;
    source = copy(source, uint16_t(ampersand - source));
  }
  const char* expanded;
  if(!tags(source, expanded)) return false;
  source = skip(expanded);
  operation = command_at(source, command);
  if(!*source) return true;
  if(operation == GOTO || operation == PROC) {
    command = skip(command); command = copy(command, trimmed(command, uint16_t(strlen(command))));
    return (operation == GOTO ? jump(command, 0) : procedure(command)) || state_->status != Status::ERROR;
  }
  if(operation == END) { end(); return true; }
  if(operation == FORGET) {
    const uint16_t old_depth = state_->depth; unsigned out = 0;
    for(unsigned i = 0; i < state_->pending_count; ++i) if(state_->pending[i].depth == old_depth) {
      state_->pending[out] = state_->pending[i]; state_->pending[out++].depth = 0;
    }
    state_->pending_count = uint16_t(out); state_->depth = 0; return true;
  }
  if(operation == CLS) { clear(true, true); return true; }
  if(operation == CLST) {
    clear(true, false);
    for(unsigned i = 0; i < state_->action_count; ++i)
      if(state_->actions[i].link) state_->actions[i].live = 0;
    state_->next_link = 0; return true;
  }
  if(operation == CLSB || operation == CLSL) {
    for(unsigned i = 0; i < state_->action_count; ++i)
      if(bool(state_->actions[i].link) == (operation == CLSL)) state_->actions[i].live = 0;
    (operation == CLSL ? state_->next_link : state_->next_action) = 0;
    if(host_.clear) host_.clear(host_.context, false, true);
    return true;
  }
  if(operation == PRINT || operation == PRINTLN) return output(command, operation == PRINTLN);
  if(operation == INPUT || operation == ANYKEY) {
    command = skip(command);command = copy(command,trimmed(command,uint16_t(strlen(command))));
    state_->wait_name = store(command);
    state_->status = operation == INPUT ? Status::INPUT : Status::ANYKEY;
    return state_->error == Error::NONE;
  }
  if(operation == PAUSE) {
    double value = 0;
    if(!decimal(command, value) || value < 0 || value > 2147483647.0) { fail(Error::LIMIT); return false; }
    state_->pause_ms = uint32_t(value); state_->status = Status::PAUSE; return true;
  }
  if(operation == QUIT) { state_->status = Status::QUIT; return true; }
  if(operation == SAVE) {
    if(!host_.save || !host_.save(host_.context)) { fail(Error::IO); return false; }
    if(host_.deferred_save) state_->status = Status::SAVE;
    yielded_ = true; return true;
  }
  if(operation == INVKILL || operation == VARKILL || operation == PERKILL) {
    command = skip(command); command = copy(command, trimmed(command, uint16_t(strlen(command))));
    const bool inventory = operation == INVKILL;
    if(operation == PERKILL) command = "";
    if(inventory) {
      if(*command) return set_item(command, {});
      for(unsigned i = 0; i < ITEMS; ++i) if(state_->items[i] && !set_item(text(state_->items[i]), {})) return false;
      return true;
    }
    if(*command && !equal_name(command, "urqw_title") && !equal_name(command, "urqw_game_lang") && !equal_name(command, "urq_mode")) {
      const int index = find(command);
      erase(index);
    } else {
      for(unsigned i = 0; i < state_->variables; ++i) {
        const char* name = text(state_->names[i]);
        if(!equal_name(name, "urqw_title") && !equal_name(name, "urqw_game_lang")) erase(int(i));
      }
      for(unsigned i = 0; i < ITEMS; ++i) if(state_->items[i] &&
          !set(text(state_->items[i]), {state_->quantities[i], nullptr, 0})) return false;
      if(!set("urq_mode", get("urq_mode"))) return false;
    }
    return true;
  }
  if(operation == INVADD || operation == INVSUB) {
    command = skip(command);command = copy(command,trimmed(command,uint16_t(strlen(command))));
    const char* comma = strchr(command, ','); double quantity = 1;
    if(comma) {
      Value count;
      if(!evaluate(copy(command, uint16_t(comma - command)), count)) return false;
      quantity = numeric(count); command = skip(comma + 1);
    }
    if(!(quantity > -9.0e18 && quantity < 9.0e18)) { fail(Error::LIMIT); return false; }
    quantity = double(int64_t(quantity));
    const double old = item_quantity(command);
    return set(command, {old + (operation == INVADD ? quantity : -quantity), nullptr, 0}, true);
  }
  if(operation == INSTR) {
    const char* equals = strchr(command, '=');
    const char* name = equals ? copy(command, trimmed(command, uint16_t(equals - command))) : command;
    const char* value = equals ? equals + 1 : "";
    if(!truth(get("instr_leave_spc"))) value = copy(skip(value), trimmed(skip(value), uint16_t(strlen(skip(value)))));
    return set(name, {0, value, 1});
  }
  if(operation == TOKENS) {
    Value source_value;
    if(!evaluate(command, source_value)) return false;
    const char* input = stringify(source_value);
    Value delimiters = get("tokens_delim");
    const char* separator = delimiters.type == 1 ? delimiters.text : " ,\"?!";
    const bool characters = equal_name(separator, "char"); unsigned count = 0;
    if(characters && !*input) return set("tokens_num", {});
    const char* start = input;
    do {
      const char* end_token = start;
      if(characters) { if(*end_token) ++end_token; }
      else while(*end_token && !strchr(separator, *end_token)) ++end_token;
      if(++count > VARIABLES) { fail(Error::MEMORY); return false; }
      char key[16] = "token"; unsigned number = count, digits = 0; char reverse[5];
      do { reverse[digits++] = char('0' + number % 10); number /= 10; } while(number);
      unsigned at = 5; while(digits) key[at++] = reverse[--digits]; key[at] = 0;
      if(!set(key, {0, copy(start, uint16_t(end_token - start)), 1})) return false;
      if(!*end_token) break;
      start = end_token + (characters ? 0 : 1);
    } while(true);
    return set("tokens_num", {double(count), nullptr, 0});
  }
  const char* equals = strchr(source, '=');
  if(equals && equals != source) {
    uint16_t n = trimmed(source, uint16_t(equals - source));
    char operation = 0;
    if(n && strchr("+-*/", source[n - 1])) { operation = source[--n]; n = trimmed(source, n); }
    const char* name = copy(source, n); Value value;
    if(!evaluate(skip(equals + 1), value)) return false;
    if(operation) {
      const Value old = get(name);
      if(operation == '+') value = add(old, value);
      else {
        const double a = numeric(old), b = numeric(value);
        value = {operation == '+' ? a + b : operation == '-' ? a - b :
                 operation == '*' ? a * b : a / b, nullptr, 0};
      }
    }
    return set(name, value);
  }
  if(operation == MEDIA) return true;
  return true; // UrqW ignores unknown non-assignment operands.
}
bool Engine::start(uint32_t seed) {
  memset(state_, 0, sizeof(*state_));
  pack_->invalidate();
  state_->used = 1; state_->rng = seed ? seed : 1; state_->mode = pack_->mode();
  state_->status = Status::RUNNING; temporary_ = 0;
  if(!set("urq_mode", get("urq_mode"))) return false;
  set("tokens_delim", {0, " ,\"?!", 1});
  char metadata[256];
  for(uint8_t field = 0; field < 3; ++field) {
    if(!pack_->info(field, metadata, sizeof(metadata))) { fail(pack_->error()); return false; }
    if(!*metadata) continue;
    if(!field) {
      set("current_loc", {0, metadata, 1}); set("previous_loc", {0, metadata, 1});
    } else set(field == 1 ? "urqw_title" : "urqw_game_lang", {0, metadata, 1});
  }
  collect(); return state_->status != Status::ERROR;
}
Status Engine::run(uint32_t budget) {
  char line[LINE_BYTES];
  while(budget-- && state_->status == Status::RUNNING) {
    temporary_ = 0; collect();
    if(state_->pending_count && state_->pending[state_->pending_count - 1].depth == state_->depth) {
      const char* next = text(state_->pending[--state_->pending_count].text);
      const size_t n = strlen(next);
      if(n >= sizeof(line)) { fail(Error::LIMIT); break; }
      memcpy(line, next, n + 1);
    } else {
      if(state_->pc >= pack_->lines()) { end(); continue; }
      if(!pack_->line(state_->pc++, line, sizeof(line))) { fail(pack_->error()); break; }
    }
    if(!execute(line)) break;
    if(state_->selection_stage && (state_->status == Status::INPUT || state_->status == Status::PAUSE || state_->status == Status::ANYKEY)) {
      if(!selected()) break;
    }
    if(yielded_) { yielded_ = false; break; }
    if(host_.service && (budget & 31U) == 0) host_.service(host_.context);
  }
  if(state_->status != Status::ERROR) collect();
  return state_->status;
}
bool Engine::common() {
  char name[128] = "common";
  temporary_ = 0; const Value value = get("common");
  if(state_->mode != Mode::RIP && (value.type == 1 || value.number != 0)) {
    const char* suffix = stringify(value);
    if(strlen(suffix) + 8 >= sizeof(name)) { fail(Error::LIMIT); return false; }
    join_string(name, "_"); join_string(name, suffix);
  }
  if(procedure(name)) {
    state_->pending_count = 0; state_->depth = 0;
    state_->status = Status::RUNNING;
    return true;
  }
  return false;
}
bool Engine::choose(uint16_t id) {
  if(state_->status != Status::CHOICE && state_->status != Status::PAUSE) return false;
  unsigned index = 0;
  while(index < state_->action_count && (!state_->actions[index].live || state_->actions[index].id != id)) ++index;
  if(index == state_->action_count) return false;
  const Action action = state_->actions[index];
  state_->selection = action.command; temporary_ = 0;
  if(!action.link && !set("last_btn_caption", {0, text(action.caption), 1})) return false;
  state_->actions[index].live = 0;
  uint32_t target = 0; const bool label = pack_->label(text(state_->selection), target);
  if(label) clear(true, true);
  collect();state_->selection_stage = label ? 1 : 2;
  if(common()) return true;
  if(state_->status == Status::ERROR) return false;
  return selected();
}
bool Engine::selected() {
  const bool label = state_->selection_stage == 1;state_->selection_stage = 0;
  state_->status = Status::RUNNING;
  const char* command = text(state_->selection);
  bool ok;
  if(label) ok = jump(command, 1);
  else {
    ok = push("end");
    if(ok) {
      char line[LINE_BYTES];
      if(strlen(command) >= sizeof(line)) { fail(Error::LIMIT); ok = false; }
      else { copy_string(line, command); temporary_ = 0; ok = execute(line); }
    }
  }
  state_->selection = 0; return ok && state_->status != Status::ERROR;
}
void Engine::finish_save(bool success) {
  if(state_->status != Status::SAVE) return;
  if(success) state_->status = Status::RUNNING;else fail(Error::IO);
}
bool Engine::submit(const char* value) {
  if(state_->status != Status::INPUT) return false;
  temporary_ = 0;
  if(strlen(value) >= 256) { fail(Error::LIMIT); return false; }
  if(!set(text(state_->wait_name), {0, value, 1})) return false;
  state_->last_input = store(value);
  if(state_->status == Status::ERROR) return false;
  state_->wait_name = 0; state_->status = Status::RUNNING; return true;
}
bool Engine::resume(uint32_t key) {
  if(state_->status != Status::ANYKEY) return false;
  if(state_->wait_name && !set(text(state_->wait_name), {double(key), nullptr, 0})) return false;
  state_->wait_name = 0; state_->status = Status::RUNNING; return true;
}
bool Engine::use(const char* label) {
  if(state_->status != Status::CHOICE && state_->status != Status::PAUSE) return false;
  temporary_ = 0; state_->status = Status::RUNNING;
  return push("end") && procedure(label);
}
void Engine::tick(uint32_t elapsed) {
  if(state_->status != Status::PAUSE) return;
  if(elapsed >= state_->pause_ms) { state_->pause_ms = 0; state_->status = Status::RUNNING; }
  else state_->pause_ms -= elapsed;
}
namespace {
enum Rule : uint8_t { ANY, WORDS, SIZES, REF, TYPE, BIT, PC, DEPTH, ZERO };
struct Field { uint16_t offset, count; uint8_t width, stride, rule; };
// Explicit wire columns. Native padding, pointers and scratch are never copied.
constexpr Field fields[] = {
  {offsetof(State, pc), 3, 4, 4, WORDS},
  {offsetof(State, used), 11, 2, 2, SIZES},
  {offsetof(State, selection_stage), 1, 1, 1, TYPE},
  {offsetof(State, numbers), VARIABLES, 8, 8, ANY},
  {offsetof(State, names), VARIABLES, 2, 2, REF},
  {offsetof(State, strings), VARIABLES, 2, 2, REF},
  {offsetof(State, types), VARIABLES, 1, 1, TYPE},
  {offsetof(State, quantities), ITEMS, 8, 8, ANY},
  {offsetof(State, items), ITEMS, 2, 2, REF},
  {offsetof(State, actions) + offsetof(Action, command), ACTIONS, 2, sizeof(Action), REF},
  {offsetof(State, actions) + offsetof(Action, caption), ACTIONS, 2, sizeof(Action), REF},
  {offsetof(State, actions) + offsetof(Action, id), ACTIONS, 2, sizeof(Action), ANY},
  {offsetof(State, actions) + offsetof(Action, link), ACTIONS, 1, sizeof(Action), BIT},
  {offsetof(State, actions) + offsetof(Action, live), ACTIONS, 1, sizeof(Action), BIT},
  {offsetof(State, frames) + offsetof(Frame, pc), FRAMES, 4, sizeof(Frame), PC},
  {offsetof(State, frames) + offsetof(Frame, depth), FRAMES, 2, sizeof(Frame), DEPTH},
  {offsetof(State, frames) + offsetof(Frame, reserved), FRAMES, 2, sizeof(Frame), ZERO},
  {offsetof(State, pending) + offsetof(Pending, text), PENDING, 2, sizeof(Pending), REF},
  {offsetof(State, pending) + offsetof(Pending, depth), PENDING, 2, sizeof(Pending), DEPTH}
};
constexpr uint32_t FIXED_WIRE_BYTES = 35 + VARIABLES * 13 + ITEMS * 10 + ACTIONS * 8 + FRAMES * 8 + PENDING * 4;
#if __BYTE_ORDER__ != __ORDER_LITTLE_ENDIAN__
#error "URQ wire cells require the supported little-endian M4/M0+/host targets"
#endif
struct Emitter {
  Sink sink;
  uint32_t count = 0, crc = 0;
  bool ok = true;
  void bytes(const void* p, uint32_t n) {
    crc = crc32(static_cast<const uint8_t*>(p), n, crc); count += n;
    if(ok && sink.write) ok = sink.write(sink.context, static_cast<const uint8_t*>(p), n);
  }
  void byte(uint8_t v) { bytes(&v, 1); }
  void half(uint16_t v) { uint8_t p[2]; put16(p, v); bytes(p, 2); }
  void word(uint32_t v) { uint8_t p[4]; put32(p, v); bytes(p, 4); }
};
void encode(const State& s, Emitter& out) {
  const auto* native = reinterpret_cast<const uint8_t*>(&s);
  for(const auto& field : fields)
    for(unsigned i = 0; i < field.count; ++i) {
      const auto* value=native+field.offset+i*field.stride;
      uint64_t bits=0;
      if(field.width==8) memcpy(&bits,value,8);
      else if(field.width==4) { uint32_t v;memcpy(&v,value,4);bits=v; }
      else if(field.width==2) { uint16_t v;memcpy(&v,value,2);bits=v; }
      else bits=*value;
      for(unsigned byte=0;byte<field.width;++byte) { out.byte(uint8_t(bits));bits>>=8; }
    }
  out.bytes(s.pool, s.used); out.bytes(s.context, s.context_size);
}
}
bool Engine::snapshot(Sink sink) const {
  if(state_->status == Status::ERROR || state_->used > POOL_BYTES) return false;
  Emitter measure{{nullptr, nullptr}}; encode(*state_, measure);
  uint8_t header[32]{};
  memcpy(header, "URQS", 4); put16(header + 4, 3);
  header[6] = uint8_t(state_->mode); header[7] = uint8_t(state_->status == Status::SAVE ? Status::RUNNING : state_->status);
  memcpy(header + 8, pack_->id(), 16); put32(header + 24, measure.count); put32(header + 28, measure.crc);
  if(!sink.write || !sink.write(sink.context, header, sizeof(header))) return false;
  Emitter writer{sink}; encode(*state_, writer); return writer.ok;
}
bool Engine::restore(Source source) {
  uint8_t header[32], prefix_bytes[32];
  if(!source.read || source.size < 32 + FIXED_WIRE_BYTES + 1 ||
     !source.read(source.context, 0, header, 32) ||
     memcmp(header, "URQS", 4) || le16(header + 4) != 3 || header[6] > 3 ||
     header[7] > uint8_t(Status::QUIT) || memcmp(header + 8, pack_->id(), 16) ||
     le32(header + 24) != source.size - 32 ||
     !source.read(source.context, 32, prefix_bytes, 32)) return false;
  const uint16_t used = le16(prefix_bytes + 12), context_size = le16(prefix_bytes + 26);
  if(!used || used > POOL_BYTES || context_size >= sizeof(state_->context) ||
     source.size != 32 + FIXED_WIRE_BYTES + used + context_size) return false;
  uint32_t crc = 0;
  uint8_t block[128];
  for(uint32_t at = 32; at < source.size;) {
    const uint32_t n = source.size - at < sizeof(block) ? source.size - at : sizeof(block);
    if(!source.read(source.context, at, block, n)) return false;
    crc = crc32(block, n, crc); at += n;
  }
  if(crc != le32(header + 28)) return false;
  uint8_t references[(POOL_BYTES+7)/8]{};
  // Validate every typed wire cell before applying any field to the live state.
  for(unsigned pass = 0; pass < 2; ++pass) {
    if(pass) {
      memset(state_, 0, sizeof(*state_));
      state_->mode = Mode(header[6]); state_->status = Status(header[7]);
      pack_->invalidate();
    }
    uint32_t offset = 32, cached = UINT32_MAX, valid = 0;
    auto pull = [&](uint8_t* out, unsigned n) {
      while(n--) {
        if(cached == UINT32_MAX || offset - cached >= valid) {
          cached = offset; valid = source.size - offset < sizeof(block) ? source.size - offset : sizeof(block);
          if(!valid || !source.read(source.context, cached, block, valid)) return false;
        }
        *out++ = block[offset++ - cached];
      }
      return true;
    };
    auto* native = reinterpret_cast<uint8_t*>(state_);
    for(const auto& field : fields) for(unsigned i = 0; i < field.count; ++i) {
      uint8_t cell[8]{};
      if(!pull(cell, field.width)) { if(pass) fail(Error::IO); return false; }
      const uint32_t value = le32(cell);
      uint32_t limit = UINT32_MAX;
      switch(field.rule) {
        case WORDS: if(!i) limit = pack_->lines(); break;
        case SIZES:
          if(i == 0) limit = POOL_BYTES;
          else if(i == 1) limit = VARIABLES;
          else if(i == 2) limit = ACTIONS;
          else if(i == 3 || i == 10) limit = 0x8000;
          else if(i == 4) limit = FRAMES;
          else if(i == 5) limit = PENDING;
          else if(i == 6 || i == 8 || i == 9) limit = used - 1;
          else if(i == 7) limit = sizeof(state_->context) - 1;
          break;
        case REF: limit = used - 1; break;
        case TYPE: limit = 2; break;
        case BIT: limit = 1; break;
        case PC: limit = pack_->lines(); break;
        case DEPTH: limit = FRAMES; break;
        case ZERO: limit = 0; break;
        default: break;
      }
      if(value > limit) return false;
      if(field.rule==REF || (field.rule==SIZES && (i==6 || i==8 || i==9)))
        references[value/8]|=uint8_t(1U<<(value%8));
      if(pass) {
        auto* target=native+field.offset+i*field.stride;
        if(field.width==8) {
          const uint64_t bits=uint64_t(le32(cell))|(uint64_t(le32(cell+4))<<32);memcpy(target,&bits,8);
        } else if(field.width==4) { const uint32_t v=le32(cell);memcpy(target,&v,4); }
        else if(field.width==2) { const uint16_t v=le16(cell);memcpy(target,&v,2); }
        else *target=*cell;
      }
    }
    uint8_t previous=0;
    for(unsigned i = 0; i < used; ++i) {
      uint8_t value = 0; if(!pull(&value, 1)) return false;
      if((!i || i + 1 == used) && value) return false;
      if((value && !mk8::valid_byte(value)) || ((references[i/8]&(1U<<(i%8))) && previous)) return false;
      previous=value;
      if(pass) state_->pool[i] = char(value);
    }
    for(unsigned i = 0; i < context_size; ++i) {
      uint8_t value = 0; if(!pull(&value, 1) || !mk8::valid_byte(value)) return false;
      if(pass) state_->context[i] = char(value);
    }
    if(offset != source.size) return false;
  }
  temporary_ = 0; collect(); return true;
}
}
