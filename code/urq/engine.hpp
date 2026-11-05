#ifndef MK61_URQ_ENGINE_HPP
#define MK61_URQ_ENGINE_HPP
#include "pack.hpp"

namespace urq {
constexpr uint16_t VARIABLES = 128, ACTIONS = 48, FRAMES = 24,
                   PENDING = 32, ITEMS = 64, POOL_BYTES = 2560, LINE_BYTES = 1024;
enum class Status : uint8_t { RUNNING, CHOICE, ANYKEY, PAUSE, INPUT, QUIT, ERROR, SAVE };
struct Action { uint16_t command, caption, id; uint8_t link, live; };
struct Frame { uint32_t pc; uint16_t depth, reserved; };
struct Pending { uint16_t text, depth; };
// All durable references are offsets. No native address belongs in a save.
struct State {
  uint32_t pc, rng, pause_ms;
  uint16_t used, variables, action_count, next_action, depth, pending_count,
           wait_name, context_size, selection, last_input, next_link;
  Mode mode;
  Status status;
  Error error;
  uint8_t selection_stage;
  double numbers[VARIABLES];
  uint16_t names[VARIABLES], strings[VARIABLES];
  uint8_t types[VARIABLES];
  double quantities[ITEMS];
  uint16_t items[ITEMS];
  Action actions[ACTIONS];
  Frame frames[FRAMES];
  Pending pending[PENDING];
  char pool[POOL_BYTES];
  char context[512];
  uint8_t transient[2048]; // 1536 expression bytes + 512-byte immutable page window
};
static_assert(sizeof(State) <= 8192, "URQ common state must fit WORKSPACE");
struct Host {
  void* context = nullptr;
  void (*print)(void*, const char*, bool newline) = nullptr;
  void (*clear)(void*, bool text, bool actions) = nullptr;
  bool (*save)(void*) = nullptr;
  bool (*resource)(void*,bool url,const char* path) = nullptr;
  uint32_t (*clock)(void*, bool days) = nullptr;
  double (*power)(void*, double, double) = nullptr;
  void (*number)(void*, double, bool fixed, char*, uint16_t) = nullptr;
  bool (*parse)(void*, const char*, double&) = nullptr;
  void (*service)(void*) = nullptr;
  bool deferred_save = false;
};
struct Value {
  union { double number; const char* text; };
  uint8_t type; // 0 number, 1 string, 2 boolean
  Value(double n=0,const char* p=nullptr,uint8_t t=0):number(n),type(t) {
    if(t==1) text=p;
  }
};
struct Sink {
  void* context;
  bool (*write)(void*, const uint8_t*, uint32_t);
};
struct Source {
  void* context;
  bool (*read)(void*, uint32_t, uint8_t*, uint32_t);
  uint32_t size;
};
class Engine {
 public:
  void attach(Pack& pack, State& state, Host host);
  bool start(uint32_t seed = 0x61F17A35U);
  Status run(uint32_t budget = 4096);
  bool choose(uint16_t id);
  bool submit(const char* line);
  bool resume(uint32_t key = 13);
  bool use(const char* label);
  void finish_save(bool success);
  void tick(uint32_t elapsed_ms);
  Value get(const char* name);
  bool set(const char* name, const Value& value, bool item = false);
  bool evaluate(const char* text, Value& result);
  const char* text(uint16_t offset) const;
  bool snapshot(Sink sink) const;
  bool restore(Source source);
  State& state() { return *state_; }
  const State& state() const { return *state_; }
  Error error() const { return state_->error; }
  void fail(Error error);
 private:
  class Expression;
  friend class Expression;
  bool execute(const char*, uint8_t recursion = 0);
  bool jump(const char*, uint8_t kind);
  bool procedure(const char*);
  void end();
  bool common();
  bool selected();
  bool add_action(const char*, const char*, bool link = false);
  bool output(const char*, bool);
  bool tags(const char*, const char*&);
  char* temporary(uint16_t size);
  const char* copy(const char*, uint16_t size);
  const char* stringify(const Value& value, bool fixed = false);
  Value add(const Value&, const Value&);
  uint16_t store(const char*);
  void collect();
  bool push(const char*);
  void discard(uint16_t depth);
  bool truth(const Value&) const;
  double numeric(const Value&) const;
  bool decimal(const char*, double&);
  int find(const char*) const;
  void erase(int index);
  bool set_item(const char*, const Value&);
  double item_quantity(const char*) const;
  void clear(bool text, bool actions);
  Pack* pack_ = nullptr;
  State* state_ = nullptr;
  Host host_{};
  char* temp_ = nullptr;
  uint16_t temporary_ = 0;
  bool yielded_ = false;
};
}
#endif
